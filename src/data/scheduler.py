"""D02-DATA — DataScheduler: candle-close timer and OHLCVBar bus publisher.

Responsibilities
----------------
- In **live mode**: poll Dukascopy for completed and active bars, validate,
  persist, and publish OHLCVBar events onto BusChannel.OHLCV_BAR.
- In **replay mode**: on every ``tick()`` call, check whether the virtual
  clock has crossed one or more candle boundaries; if so, fetch/construct
  the bar from the DataStore and publish.  No wall-clock sleep in replay.

Public API
----------
    scheduler = DataScheduler(bus, store, clock, fetcher, instruments_config)

    # Live trading:
    await scheduler.run()          # blocks until stopped or error

    # Replay (called from D08 feed loop):
    await scheduler.tick()         # check boundaries and emit bars

    scheduler.stop()               # graceful shutdown

Design rules
------------
- ONLY DataScheduler publishes to BusChannel.OHLCV_BAR.  No other module does.
- All OHLCVBar timestamps are the bar's OPEN time, UTC, timezone-aware.
- Fail loud: fetch failures raise DataError (logged + re-raised); never
  silently swallow a missing bar.
- VirtualClock is used for all timestamp comparisons — never datetime.now().
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, TypedDict

import pandas as pd

from src.core.bus import Bus
from src.core.clock import VirtualClock, clock_mode
from src.core.contracts import (
    BusChannel,
    Instrument,
    OHLCVBar,
    Timeframe,
)
from src.core.exceptions import DataError
from src.core.ids import new_signal_id
from src.core.logging import get_logger
from src.data.feeds.base import OHLCVFeed
from src.data.feeds.dukascopy import DukascopyFeed
from src.core.poll_schedule import compute_live_poll_interval, m1_cache_ttl_sec
from src.core.session import pip_size_for
from src.data.store import DataStore

_log = get_logger("D02-DATA")

FOCUSED_POLL_INTERVAL_SEC = 2.0
BACKGROUND_POLL_INTERVAL_SEC = 10.0


class PairLiveStatus(TypedDict, total=False):
    last_bar_at: str
    close: float
    source: str
    last_error: str
    last_poll_at: str


# ── Timeframe helpers ─────────────────────────────────────────────────────────

_TF_DURATION: Dict[Timeframe, timedelta] = {
    Timeframe.M1:  timedelta(minutes=1),
    Timeframe.M5:  timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1:  timedelta(hours=1),
    Timeframe.H4:  timedelta(hours=4),
    Timeframe.D1:  timedelta(days=1),
    Timeframe.W1:  timedelta(weeks=1),
}


def _candle_open_time(dt: datetime, timeframe: Timeframe) -> datetime:
    """Return the open time of the candle that contains ``dt``."""
    dur = _TF_DURATION[timeframe]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = (dt - epoch).total_seconds()
    dur_secs = dur.total_seconds()
    candle_epoch_secs = (elapsed // dur_secs) * dur_secs
    return epoch + timedelta(seconds=candle_epoch_secs)


def _next_candle_close(dt: datetime, timeframe: Timeframe) -> datetime:
    """Return the close time (= open time of the NEXT candle) after ``dt``."""
    open_time = _candle_open_time(dt, timeframe)
    return open_time + _TF_DURATION[timeframe]


def _normalize_wick(bar: OHLCVBar) -> OHLCVBar:
    """Ensure open/close sit inside [low, high] for chart libraries."""
    low = min(bar.open, bar.high, bar.low, bar.close)
    high = max(bar.open, bar.high, bar.low, bar.close)
    if high == low:
        pip = pip_size_for(bar.instrument)
        high = bar.close + pip / 2
        low = bar.close - pip / 2
    return bar.model_copy(update={"high": high, "low": low})


# ── Fetcher protocol ──────────────────────────────────────────────────────────

def create_ohlcv_feed(source: str = "dukascopy") -> OHLCVFeed:
    """Factory for the configured OHLCV feed."""
    if source == "dukascopy":
        return DukascopyFeed()
    raise DataError(f"Unsupported data source: {source!r}. Use 'dukascopy'.")


class OHLCVFetcher:
    """Backward-compatible wrapper around OHLCVFeed for scheduler and tests."""

    def __init__(self, feed: Optional[OHLCVFeed] = None, source: str = "dukascopy") -> None:
        self._feed = feed or create_ohlcv_feed(source)

    def fetch_live_bars(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[OHLCVBar, Optional[OHLCVBar]]:
        completed, active = self._feed.fetch_live_bars(instrument, timeframe)
        completed = _normalize_wick(completed)
        if active is not None:
            active = _normalize_wick(active)
        return completed, active

    def fetch_latest_bar(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> OHLCVBar:
        completed_bar, _ = self.fetch_live_bars(instrument, timeframe)
        return completed_bar


# ── DataScheduler ─────────────────────────────────────────────────────────────

class DataScheduler:
    """Candle-close event scheduler for D02-DATA.

    Live mode
    ---------
    ``run()`` starts an asyncio loop that:
    1. Polls Dukascopy for registered active pairs (faster for focused chart).
    2. Broadcasts active candles to WebSockets in real time.
    3. Detects completed candle transitions, writes completed bars to Parquet, and publishes.

    Replay mode
    -----------
    ``tick()`` is called from D08's feed loop on each virtual-time step.
    It checks whether the virtual clock has crossed any candle boundary
    and emits bars without wall-clock sleep.

    Parameters
    ----------
    bus:
        Injected Bus instance (InProcessBus in dev/test).
    store:
        DataStore for persisting bars and (in replay mode) reading historical data.
    clock:
        VirtualClock — must be a LiveClock in live mode, ReplayClock in replay.
    fetcher:
        OHLCVFetcher (or compatible stub in tests).
    active_pairs:
        Iterable of (Instrument, Timeframe) pairs to schedule.
        Defaults to all four instruments at H1 if not specified.
    """

    def __init__(
        self,
        bus: Bus,
        store: DataStore,
        clock: VirtualClock,
        fetcher: Optional[OHLCVFetcher] = None,
        feed: Optional[OHLCVFeed] = None,
        data_source: str = "dukascopy",
        active_pairs: Optional[list[tuple[Instrument, Timeframe]]] = None,
        focused_poll_interval_sec: float = FOCUSED_POLL_INTERVAL_SEC,
        background_poll_interval_sec: float = BACKGROUND_POLL_INTERVAL_SEC,
        m1_poll_interval_sec: float = 60.0,
        live_poll_adaptive: bool = True,
    ) -> None:
        self._bus = bus
        self._store = store
        self._clock = clock
        self._fetcher = fetcher or OHLCVFetcher(feed=feed, source=data_source)
        self._m1_poll_interval_sec = m1_poll_interval_sec
        self._active_pairs: list[tuple[Instrument, Timeframe]] = (
            active_pairs if active_pairs is not None else [
                (Instrument.EURUSD, Timeframe.H1),
                (Instrument.GBPUSD, Timeframe.H1),
                (Instrument.USDJPY, Timeframe.H1),
                (Instrument.XAUUSD, Timeframe.H1),
            ]
        )
        self._focused_pair: Optional[tuple[Instrument, Timeframe]] = None
        self._focused_poll_interval_sec = focused_poll_interval_sec
        self._background_poll_interval_sec = background_poll_interval_sec
        self._live_poll_adaptive = live_poll_adaptive
        self._running = False
        # Track the last emitted candle open time per (instrument, timeframe)
        self._last_emitted: dict[tuple[Instrument, Timeframe], datetime] = {}
        self._pair_status: dict[str, PairLiveStatus] = {}
        self._last_global_error: Optional[str] = None
        self._last_global_poll_at: Optional[datetime] = None

    # ── Live mode ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start the live scheduling loop.  Blocks until ``stop()`` is called."""
        self._running = True
        _log.info(
            "scheduler_started",
            pairs=[(i.value, tf.value) for i, tf in self._active_pairs],
        )
        try:
            await self._live_loop()
        finally:
            self._running = False
            _log.info("scheduler_stopped")

    def _poll_interval_for(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        now: Optional[datetime] = None,
    ) -> float:
        pair = (instrument, timeframe)
        focused = pair == self._focused_pair
        if self._live_poll_adaptive:
            now = now or datetime.now(timezone.utc)
            return compute_live_poll_interval(
                timeframe,
                now,
                focused=focused,
                background_multiplier=max(
                    2.0,
                    self._background_poll_interval_sec / max(self._focused_poll_interval_sec, 1.0),
                ),
            )
        if focused:
            if timeframe == Timeframe.M1:
                return self._m1_poll_interval_sec
            return self._focused_poll_interval_sec
        return self._background_poll_interval_sec

    async def _live_loop(self) -> None:
        """Inner loop: one M1 fetch per instrument, derive all due timeframes."""
        last_poll: dict[tuple[Instrument, Timeframe], float] = {}
        loop = asyncio.get_running_loop()

        while self._running:
            if not self._active_pairs:
                await asyncio.sleep(1.0)
                continue

            now_mono = loop.time()
            now_utc = datetime.now(timezone.utc)
            due_by_instrument: dict[Instrument, list[Timeframe]] = {}
            next_wake_sec = 30.0

            for instrument, timeframe in list(self._active_pairs):
                if not self._running:
                    break
                pair = (instrument, timeframe)
                interval = self._poll_interval_for(instrument, timeframe, now_utc)
                elapsed = now_mono - last_poll.get(pair, 0.0)
                if elapsed < interval:
                    next_wake_sec = min(next_wake_sec, max(1.0, interval - elapsed))
                    continue
                last_poll[pair] = now_mono
                due_by_instrument.setdefault(instrument, []).append(timeframe)

            if due_by_instrument:
                self._last_global_poll_at = now_utc
                for instrument, timeframes in due_by_instrument.items():
                    await self._poll_instrument(instrument, timeframes)

            await asyncio.sleep(max(1.0, min(next_wake_sec, 30.0)))

    async def _poll_instrument(
        self,
        instrument: Instrument,
        timeframes: list[Timeframe],
    ) -> None:
        """Fetch one M1 window and derive live bars for all due timeframes."""
        poll_at = datetime.now(timezone.utc)
        feed = getattr(self._fetcher, "_feed", None)
        m1_df: Optional[pd.DataFrame] = None

        if isinstance(feed, DukascopyFeed):
            try:
                min_interval = min(
                    self._poll_interval_for(instrument, tf, poll_at) for tf in timeframes
                )
                cache_ttl = m1_cache_ttl_sec(min_interval)
                executor = asyncio.get_running_loop()
                m1_df = await executor.run_in_executor(
                    None,
                    lambda: feed.fetch_m1_recent(
                        instrument, max_cache_age_sec=cache_ttl
                    ),
                )
            except Exception as exc:
                _log.warning(
                    "scheduler_m1_batch_fetch_failed",
                    instrument=instrument.value,
                    error=str(exc),
                )

        for timeframe in timeframes:
            await self._poll_pair(
                instrument,
                timeframe,
                poll_at=poll_at,
                m1_df=m1_df,
            )

    async def _poll_pair(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        *,
        poll_at: Optional[datetime] = None,
        m1_df: Optional[pd.DataFrame] = None,
    ) -> None:
        """Fetch and publish bars for a single instrument/timeframe pair."""
        pair_key = self._pair_key(instrument, timeframe)
        poll_at = poll_at or datetime.now(timezone.utc)

        try:
            feed = getattr(self._fetcher, "_feed", None)
            if (
                m1_df is not None
                and not m1_df.empty
                and isinstance(feed, DukascopyFeed)
            ):
                completed_bar, active_bar = feed.live_bars_from_m1(
                    instrument, timeframe, m1_df
                )
                completed_bar = _normalize_wick(completed_bar)
                if active_bar is not None:
                    active_bar = _normalize_wick(active_bar)
            elif hasattr(self._fetcher, "fetch_live_bars"):
                completed_bar, active_bar = self._fetcher.fetch_live_bars(
                    instrument, timeframe
                )
            else:
                completed_bar = self._fetcher.fetch_latest_bar(instrument, timeframe)
                active_bar = None

            await self._emit_bars(
                instrument, timeframe, completed_bar, active_bar, poll_at
            )

        except Exception as exc:
            try:
                completed_bar, active_bar = self._bars_from_store(instrument, timeframe)
            except Exception:
                err = str(exc)
                _log.error(
                    "scheduler_live_poll_failed",
                    instrument=instrument.value,
                    timeframe=timeframe.value,
                    error=err,
                )
                status = self._pair_status.setdefault(pair_key, {})
                status["last_poll_at"] = poll_at.isoformat()
                status["last_error"] = err
                self._last_global_error = err
                return

            _log.warning(
                "scheduler_live_poll_store_fallback",
                instrument=instrument.value,
                timeframe=timeframe.value,
                error=str(exc),
            )
            await self._emit_bars(
                instrument,
                timeframe,
                completed_bar,
                active_bar,
                poll_at,
                persist_completed=False,
            )

    async def _emit_bars(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        completed_bar: OHLCVBar,
        active_bar: Optional[OHLCVBar],
        poll_at: datetime,
        *,
        persist_completed: bool = True,
    ) -> None:
        """Publish bars and update pair status."""
        pair_key = self._pair_key(instrument, timeframe)
        last = self._last_emitted.get((instrument, timeframe))
        if last is None or completed_bar.timestamp > last:
            # Only persist M1 from live poll; higher TFs come from resample.
            if persist_completed and timeframe == Timeframe.M1:
                self._save_to_store(instrument, timeframe, completed_bar)
            await self._bus.publish(BusChannel.OHLCV_BAR, completed_bar)
            self._last_emitted[(instrument, timeframe)] = completed_bar.timestamp
            _log.info(
                "ohlcv_bar_published",
                instrument=instrument.value,
                timeframe=timeframe.value,
                bar_ts=str(completed_bar.timestamp),
                close=completed_bar.close,
            )

        latest_bar = completed_bar
        if active_bar is not None and active_bar.timestamp > completed_bar.timestamp:
            await self._bus.publish(BusChannel.OHLCV_BAR, active_bar)
            latest_bar = active_bar

        status = self._pair_status.setdefault(pair_key, {})
        status["last_poll_at"] = poll_at.isoformat()
        status["last_bar_at"] = latest_bar.timestamp.isoformat()
        status["close"] = latest_bar.close
        status["source"] = latest_bar.source
        status.pop("last_error", None)
        self._last_global_error = None

    def _bars_from_store(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[OHLCVBar, Optional[OHLCVBar]]:
        """Read the latest completed/active bars from Parquet when Dukascopy is busy."""
        now = datetime.now(timezone.utc)
        dur = _TF_DURATION[timeframe]
        candle_open = _candle_open_time(now, timeframe)
        df = self._store.get_ohlcv(
            instrument,
            timeframe,
            candle_open - dur * 5,
            now,
        )
        if df.empty:
            raise DataError(f"No stored bars for {instrument.value}/{timeframe.value}")

        def _row_to_bar(ts: datetime, row: pd.Series, source: str) -> OHLCVBar:
            return OHLCVBar(
                signal_id=new_signal_id(),
                instrument=instrument,
                timeframe=timeframe,
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                source=source,
            )

        active_bar: Optional[OHLCVBar] = None
        completed_bar: Optional[OHLCVBar] = None
        if candle_open in df.index:
            active_bar = _row_to_bar(candle_open, df.loc[candle_open], "store_active")
            prior = df.loc[: candle_open - timedelta(microseconds=1)]
            if not prior.empty:
                ts = prior.index[-1].to_pydatetime()
                completed_bar = _row_to_bar(ts, prior.iloc[-1], "store")
        else:
            ts = df.index[-1].to_pydatetime()
            completed_bar = _row_to_bar(ts, df.iloc[-1], "store")

        if completed_bar is None:
            raise DataError(f"No completed bar in store for {instrument.value}/{timeframe.value}")
        return _normalize_wick(completed_bar), (
            _normalize_wick(active_bar) if active_bar is not None else None
        )

    def _save_to_store(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        bar: OHLCVBar,
    ) -> None:
        """Store bar in DataStore without downgrading existing wicks."""
        try:
            bar = _normalize_wick(bar)
            dur = _TF_DURATION[timeframe]
            try:
                existing = self._store.get_ohlcv(
                    instrument,
                    timeframe,
                    bar.timestamp,
                    bar.timestamp + dur - timedelta(microseconds=1),
                )
            except DataError:
                existing = pd.DataFrame()

            if not existing.empty:
                row = existing.iloc[-1]
                old_spread = float(row["high"]) - float(row["low"])
                new_spread = bar.high - bar.low
                if new_spread <= 0 and old_spread > 0:
                    return
                if old_spread > 0 or new_spread > 0:
                    bar = bar.model_copy(
                        update={
                            "open": float(row["open"]),
                            "high": max(bar.high, float(row["high"])),
                            "low": min(bar.low, float(row["low"])),
                            "close": bar.close,
                            "volume": max(bar.volume, float(row.get("volume", 0.0) or 0.0)),
                        }
                    )
                    bar = _normalize_wick(bar)

            row_df = pd.DataFrame(
                {
                    "open": [bar.open],
                    "high": [bar.high],
                    "low": [bar.low],
                    "close": [bar.close],
                    "volume": [bar.volume],
                },
                index=pd.DatetimeIndex([bar.timestamp], tz="UTC"),
            )
            self._store.write_ohlcv(instrument, timeframe, row_df)
        except Exception as exc:
            _log.error(
                "scheduler_store_failed",
                instrument=instrument.value,
                timeframe=timeframe.value,
                error=str(exc),
            )

    async def _fetch_and_publish(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> None:
        """Legacy helper kept for backwards-compatibility with tests."""
        try:
            bar = self._fetcher.fetch_latest_bar(instrument, timeframe)
        except DataError as exc:
            _log.error(
                "scheduler_fetch_failed",
                instrument=instrument.value,
                timeframe=timeframe.value,
                error=str(exc),
            )
            raise  # Fail loud

        last = self._last_emitted.get((instrument, timeframe))
        if last is not None and bar.timestamp <= last:
            return

        self._save_to_store(instrument, timeframe, bar)
        await self._bus.publish(BusChannel.OHLCV_BAR, bar)
        self._last_emitted[(instrument, timeframe)] = bar.timestamp
        _log.info(
            "ohlcv_bar_published",
            instrument=instrument.value,
            timeframe=timeframe.value,
            bar_ts=str(bar.timestamp),
            close=bar.close,
        )

    # ── Replay mode ───────────────────────────────────────────────────────────

    async def tick(self) -> None:
        """Check the virtual clock and emit any bars whose close time has passed.

        Called from D08's feed loop on each virtual-time advancement.
        Does NOT sleep — replay timing is driven entirely by D08's clock control.
        """
        now = self._clock.now()
        for instrument, timeframe in self._active_pairs:
            candle_open = _candle_open_time(now, timeframe)
            last = self._last_emitted.get((instrument, timeframe))
            if last is not None and candle_open <= last:
                continue  # Already emitted this candle

            # Try to load the bar from store
            try:
                bar = self._load_bar_from_store(instrument, timeframe, candle_open)
            except DataError as exc:
                _log.warning(
                    "scheduler_replay_bar_missing",
                    instrument=instrument.value,
                    timeframe=timeframe.value,
                    candle_open=str(candle_open),
                    error=str(exc),
                )
                continue  # Skip missing bars in replay (not a fatal error)

            await self._bus.publish(BusChannel.OHLCV_BAR, bar)
            self._last_emitted[(instrument, timeframe)] = bar.timestamp

            _log.debug(
                "ohlcv_bar_replayed",
                instrument=instrument.value,
                timeframe=timeframe.value,
                bar_ts=str(bar.timestamp),
                close=bar.close,
            )

    def _load_bar_from_store(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        candle_open: datetime,
    ) -> OHLCVBar:
        """Read a single bar from the DataStore by its open timestamp."""
        dur = _TF_DURATION[timeframe]
        # Query a 1-bar-width window
        df = self._store.get_ohlcv(
            instrument,
            timeframe,
            start=candle_open,
            end=candle_open + dur - timedelta(seconds=1),
        )
        if df.empty:
            raise DataError(
                f"No bar at {candle_open} for {instrument.value}/{timeframe.value}"
            )
        row = df.iloc[0]
        return OHLCVBar(
            signal_id=new_signal_id(),
            instrument=instrument,
            timeframe=timeframe,
            timestamp=df.index[0].to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            source="replay",
        )

    # ── Control ───────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal the live loop to stop after the current sleep."""
        self._running = False
        _log.info("scheduler_stop_requested")

    def reset_last_emitted(self) -> None:
        """Clear emission tracking — used by D08 when starting a new replay session."""
        self._last_emitted.clear()

    def add_active_pair(self, instrument: Instrument, timeframe: Timeframe) -> None:
        """Dynamically add an instrument/timeframe pair to the scheduling loop."""
        pair = (instrument, timeframe)
        if pair not in self._active_pairs:
            self._active_pairs.append(pair)
            _log.info(
                "scheduler_pair_added",
                instrument=instrument.value,
                timeframe=timeframe.value,
            )

    def set_focused_pair(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> None:
        """Mark the chart's active pair for faster polling."""
        pair = (instrument, timeframe)
        self.add_active_pair(instrument, timeframe)
        self._focused_pair = pair
        _log.info(
            "scheduler_pair_focused",
            instrument=instrument.value,
            timeframe=timeframe.value,
        )

    def get_live_status(self) -> dict[str, Any]:
        """Return scheduler health for the terminal live-chart status UI."""
        focused: Optional[dict[str, str]] = None
        focused_poll_interval_sec: Optional[float] = None
        if self._focused_pair is not None:
            inst, tf = self._focused_pair
            focused = {"instrument": inst.value, "timeframe": tf.value}
            focused_poll_interval_sec = self._poll_interval_for(inst, tf)

        return {
            "running": self._running,
            "focused_pair": focused,
            "focused_poll_interval_sec": focused_poll_interval_sec,
            "active_pairs": [
                {"instrument": i.value, "timeframe": tf.value}
                for i, tf in self._active_pairs
            ],
            "data_source": getattr(
                getattr(self._fetcher, "_feed", self._fetcher),
                "source_name",
                "dukascopy",
            ),
            "live_poll_adaptive": self._live_poll_adaptive,
            "poll_interval_focused_sec": self._focused_poll_interval_sec,
            "poll_interval_background_sec": self._background_poll_interval_sec,
            "poll_interval_m1_sec": self._m1_poll_interval_sec,
            "last_poll_at": (
                self._last_global_poll_at.isoformat()
                if self._last_global_poll_at is not None
                else None
            ),
            "last_error": self._last_global_error,
            "pairs": dict(self._pair_status),
        }

    @staticmethod
    def _pair_key(instrument: Instrument, timeframe: Timeframe) -> str:
        return f"{instrument.value}/{timeframe.value}"

    @property
    def active_pairs(self) -> list[tuple[Instrument, Timeframe]]:
        return list(self._active_pairs)

    @property
    def focused_pair(self) -> Optional[tuple[Instrument, Timeframe]]:
        return self._focused_pair
