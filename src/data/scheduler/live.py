"""Live-mode poll loop — Dukascopy fetch, emit, persist."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import pandas as pd

from src.core.contracts import BusChannel, Instrument, OHLCVBar, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.core.poll_schedule import compute_live_poll_interval, m1_cache_ttl_sec
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.scheduler.bars import normalize_wick
from src.data.scheduler.store_ops import (
    bars_from_store,
    save_bar_to_store,
    sync_m1_window_to_store,
)
from src.data.scheduler.types import (
    LIGHT_M1_LOOKBACK_HOURS,
    M1_LIVE_DERIVED_TFS,
    STORE_ONLY_LIGHT_TFS,
)

if TYPE_CHECKING:
    from src.data.scheduler.core import DataScheduler

_log = get_logger("D02-DATA")

_FOCUS_POLL_COOLDOWN_SEC = 20.0


class LiveSchedulerMixin:
    """Async live polling loop mixed into DataScheduler."""

    async def poll_pair_now(
        self: DataScheduler,
        instrument: Instrument,
        timeframe: Timeframe,
        *,
        light: bool = True,
    ) -> None:
        """Immediately poll one pair after a chart focus change (throttled)."""
        if not self._running:
            return
        pair = (instrument, timeframe)
        now_mono = time.monotonic()
        last = self._last_immediate_poll_mono.get(pair, 0.0)
        if now_mono - last < _FOCUS_POLL_COOLDOWN_SEC:
            return
        self._last_immediate_poll_mono[pair] = now_mono
        poll_at = datetime.now(timezone.utc)
        self._last_global_poll_at = poll_at
        await self._poll_instrument(instrument, [timeframe], light=light)

    async def run(self: DataScheduler) -> None:
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
        self: DataScheduler,
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
                    self._background_poll_interval_sec
                    / max(self._focused_poll_interval_sec, 1.0),
                ),
            )
        if focused:
            if timeframe == Timeframe.M1:
                return self._m1_poll_interval_sec
            return self._focused_poll_interval_sec
        return self._background_poll_interval_sec

    async def _live_loop(self: DataScheduler) -> None:
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

            for instrument, timeframe in self.drain_focus_wake_pairs():
                due_by_instrument.setdefault(instrument, [])
                if timeframe not in due_by_instrument[instrument]:
                    due_by_instrument[instrument].append(timeframe)
                    last_poll[(instrument, timeframe)] = 0.0
                next_wake_sec = min(next_wake_sec, 0.5)

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

            max_sleep = 5.0 if self._focused_pair is not None else 30.0
            await asyncio.sleep(max(0.5, min(next_wake_sec, max_sleep)))

    async def _poll_instrument(
        self: DataScheduler,
        instrument: Instrument,
        timeframes: list[Timeframe],
        *,
        light: bool = False,
    ) -> None:
        """Fetch one M1 window and derive live bars for all due timeframes."""
        poll_at = datetime.now(timezone.utc)
        feed = getattr(self._fetcher, "_feed", None)
        m1_df: Optional[pd.DataFrame] = None

        needs_m1 = (
            not light
            or any(tf in M1_LIVE_DERIVED_TFS for tf in timeframes)
        )
        if isinstance(feed, DukascopyFeed) and needs_m1:
            try:
                min_interval = min(
                    self._poll_interval_for(instrument, tf, poll_at) for tf in timeframes
                )
                cache_ttl = m1_cache_ttl_sec(min_interval)
                lookback_hours = LIGHT_M1_LOOKBACK_HOURS if light else None
                executor = asyncio.get_running_loop()
                m1_df = await executor.run_in_executor(
                    None,
                    lambda: feed.fetch_m1_recent(
                        instrument,
                        max_cache_age_sec=cache_ttl,
                        lookback_hours=lookback_hours,
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
                light=light,
            )

    async def _poll_pair(
        self: DataScheduler,
        instrument: Instrument,
        timeframe: Timeframe,
        *,
        poll_at: Optional[datetime] = None,
        m1_df: Optional[pd.DataFrame] = None,
        light: bool = False,
    ) -> None:
        """Fetch and publish bars for a single instrument/timeframe pair."""
        pair_key = self._pair_key(instrument, timeframe)
        poll_at = poll_at or datetime.now(timezone.utc)

        if light and timeframe in STORE_ONLY_LIGHT_TFS:
            try:
                completed_bar, active_bar = bars_from_store(
                    self._store, instrument, timeframe
                )
                await self._emit_bars(
                    instrument,
                    timeframe,
                    completed_bar,
                    active_bar,
                    poll_at,
                    persist_completed=False,
                )
                return
            except DataError:
                pass

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
                completed_bar = normalize_wick(completed_bar)
                if active_bar is not None:
                    active_bar = normalize_wick(active_bar)
            elif hasattr(self._fetcher, "fetch_live_bars"):
                completed_bar, active_bar = self._fetcher.fetch_live_bars(
                    instrument, timeframe
                )
            else:
                completed_bar = self._fetcher.fetch_latest_bar(instrument, timeframe)
                active_bar = None

            synced_m1 = False
            if (
                not light
                and timeframe == Timeframe.M1
                and m1_df is not None
                and not m1_df.empty
            ):
                sync_m1_window_to_store(self._store, instrument, m1_df, poll_at)
                synced_m1 = True

            await self._emit_bars(
                instrument,
                timeframe,
                completed_bar,
                active_bar,
                poll_at,
                persist_completed=not synced_m1,
            )

        except Exception as exc:
            try:
                completed_bar, active_bar = bars_from_store(
                    self._store, instrument, timeframe
                )
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
        self: DataScheduler,
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
            if persist_completed and timeframe == Timeframe.M1:
                save_bar_to_store(self._store, instrument, timeframe, completed_bar)
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

    async def _fetch_and_publish(
        self: DataScheduler,
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
            raise

        last = self._last_emitted.get((instrument, timeframe))
        if last is not None and bar.timestamp <= last:
            return

        save_bar_to_store(self._store, instrument, timeframe, bar)
        await self._bus.publish(BusChannel.OHLCV_BAR, bar)
        self._last_emitted[(instrument, timeframe)] = bar.timestamp
        _log.info(
            "ohlcv_bar_published",
            instrument=instrument.value,
            timeframe=timeframe.value,
            bar_ts=str(bar.timestamp),
            close=bar.close,
        )