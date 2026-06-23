"""D02-DATA — DataScheduler: candle-close timer and OHLCVBar bus publisher.

Responsibilities
----------------
- In **live mode**: sleep until each candle close (wall-clock), fetch the
  completed bar from yfinance, validate it, and publish an OHLCVBar onto
  BusChannel.OHLCV_BAR.
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
from typing import Any, Callable, Dict, Optional

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
from src.data.store import DataStore
from src.data.validation import validate_ohlcv, normalize_ohlcv_columns

_log = get_logger("D02-DATA")


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


# ── Fetcher protocol ──────────────────────────────────────────────────────────

class OHLCVFetcher:
    """Thin wrapper around LiveDataFetcher producing single OHLCVBar objects.

    In production this wraps LiveDataFetcher (yfinance).
    In tests it can be replaced with a stub.
    """

    # yfinance symbol mapping (matches LiveDataFetcher.SYMBOL_MAP)
    _SYMBOL_MAP: Dict[Instrument, str] = {
        Instrument.EURUSD: "EURUSD=X",
        Instrument.GBPUSD: "GBPUSD=X",
        Instrument.USDJPY: "USDJPY=X",
        Instrument.XAUUSD: "GC=F",
    }

    def __init__(self) -> None:
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError:
            raise DataError(
                "yfinance is not installed. "
                "Install with: pip install yfinance"
            )

    def fetch_latest_bar(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> OHLCVBar:
        """Fetch the most recently closed bar for instrument/timeframe.

        Returns an OHLCVBar with the bar's open time as timestamp.
        Raises DataError on any failure.
        """
        ticker_sym = self._SYMBOL_MAP.get(instrument)
        if ticker_sym is None:
            raise DataError(f"No yfinance symbol mapping for {instrument.value}")

        # Map Timeframe to yfinance interval
        _TF_TO_YF: Dict[Timeframe, str] = {
            Timeframe.M1:  "1m",
            Timeframe.M5:  "5m",
            Timeframe.M15: "15m",
            Timeframe.M30: "30m",
            Timeframe.H1:  "1h",
            Timeframe.H4:  "1h",   # resample from 1h
            Timeframe.D1:  "1d",
            Timeframe.W1:  "1wk",
        }
        yf_interval = _TF_TO_YF[timeframe]

        # Fetch the last 3 bars (enough to always have one complete closed bar)
        try:
            ticker = self._yf.Ticker(ticker_sym)
            df = ticker.history(period="1d", interval=yf_interval)
        except Exception as exc:
            raise DataError(
                f"yfinance fetch failed for {instrument.value} ({ticker_sym}): {exc}"
            ) from exc

        if df.empty:
            raise DataError(
                f"yfinance returned empty data for {instrument.value} at {timeframe.value}. "
                "Market may be closed or symbol unavailable."
            )

        # Lowercase columns
        df.columns = [c.lower() for c in df.columns]
        required = {"open", "high", "low", "close"}
        if not required.issubset(set(df.columns)):
            raise DataError(
                f"yfinance response missing OHLC columns for {instrument.value}. "
                f"Got: {list(df.columns)}"
            )

        # The LAST row is the most recently closed bar
        # (yfinance returns the current incomplete bar last; skip it by taking iloc[-2]
        #  when there are at least 2 rows; otherwise iloc[-1] is the only bar available)
        idx = -2 if len(df) >= 2 else -1
        row = df.iloc[idx]
        bar_ts = df.index[idx]

        # Ensure UTC-aware
        if hasattr(bar_ts, "tzinfo") and bar_ts.tzinfo is None:
            bar_ts = bar_ts.tz_localize("UTC")
        bar_ts_dt = pd.Timestamp(bar_ts).tz_convert("UTC").to_pydatetime()

        volume = float(row.get("volume", 0.0) or 0.0)

        return OHLCVBar(
            signal_id=new_signal_id(),
            instrument=instrument,
            timeframe=timeframe,
            timestamp=bar_ts_dt,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=volume,
            source="yfinance",
        )


# ── DataScheduler ─────────────────────────────────────────────────────────────

class DataScheduler:
    """Candle-close event scheduler for D02-DATA.

    Live mode
    ---------
    ``run()`` starts an asyncio loop that:
    1. Calculates the next candle-close time for each (instrument, timeframe).
    2. Sleeps until the earliest upcoming close.
    3. Fetches the completed bar and publishes OHLCVBar on the bus.
    4. Stores the bar in the DataStore.

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
        active_pairs: Optional[list[tuple[Instrument, Timeframe]]] = None,
    ) -> None:
        self._bus = bus
        self._store = store
        self._clock = clock
        self._fetcher = fetcher or OHLCVFetcher()
        self._active_pairs: list[tuple[Instrument, Timeframe]] = active_pairs or [
            (Instrument.EURUSD, Timeframe.H1),
            (Instrument.GBPUSD, Timeframe.H1),
            (Instrument.USDJPY, Timeframe.H1),
            (Instrument.XAUUSD, Timeframe.H1),
        ]
        self._running = False
        # Track the last emitted candle open time per (instrument, timeframe)
        self._last_emitted: dict[tuple[Instrument, Timeframe], datetime] = {}

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

    async def _live_loop(self) -> None:
        """Inner loop: sleep to the next close, emit, repeat."""
        while self._running:
            now = self._clock.now()

            # Find the next candle close across all active pairs
            next_closes = [
                _next_candle_close(now, tf)
                for _, tf in self._active_pairs
            ]
            earliest_close = min(next_closes)

            sleep_secs = (earliest_close - now).total_seconds()
            if sleep_secs > 0:
                _log.debug("scheduler_sleeping", seconds=round(sleep_secs, 1))
                await asyncio.sleep(sleep_secs)

            if not self._running:
                break

            # Emit bars for any pair whose close time has now passed
            now_after_sleep = self._clock.now()
            for instrument, timeframe in self._active_pairs:
                close_time = _next_candle_close(
                    now, timeframe  # use `now` before sleep so we target the same candle
                )
                if now_after_sleep >= close_time:
                    await self._fetch_and_publish(instrument, timeframe)

    async def _fetch_and_publish(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> None:
        """Fetch latest bar, validate, store, and publish to bus."""
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

        # Avoid publishing the same bar twice (e.g. if sleep drifted)
        last = self._last_emitted.get((instrument, timeframe))
        if last is not None and bar.timestamp <= last:
            _log.debug(
                "scheduler_duplicate_skipped",
                instrument=instrument.value,
                timeframe=timeframe.value,
                bar_ts=str(bar.timestamp),
            )
            return

        # Store bar in DataStore (best-effort — publish even if store fails)
        try:
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

        # Publish to bus
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

    @property
    def active_pairs(self) -> list[tuple[Instrument, Timeframe]]:
        return list(self._active_pairs)
