"""Unit tests for non-blocking Dukascopy access."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pandas as pd
import pytest

from unittest.mock import AsyncMock

from src.core.contracts import Instrument, Timeframe
from src.data.feeds.dukascopy import DukascopyFeed, _M1CacheEntry
from src.data.feeds.lock import DUKASCOPY_LOCK, dukascopy_lock_held


def test_dukascopy_lock_held_detects_active_fetch() -> None:
    DUKASCOPY_LOCK.acquire()
    try:
        assert dukascopy_lock_held() is True
    finally:
        DUKASCOPY_LOCK.release()
    assert dukascopy_lock_held() is False


def test_fetch_m1_recent_returns_stale_cache_when_lock_busy() -> None:
    feed = DukascopyFeed(live_m1_cache_ttl_sec=300.0)
    stale = pd.DataFrame(
        {"open": [1.1], "high": [1.2], "low": [1.0], "close": [1.15], "volume": [1.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-06-25 10:00", tz="UTC")]),
    )
    feed._m1_cache[Instrument.EURUSD] = _M1CacheEntry(
        df=stale,
        fetched_at=time.monotonic() - 120.0,
    )

    DUKASCOPY_LOCK.acquire()
    try:
        result = feed.fetch_m1_recent(Instrument.EURUSD, wait_for_lock=False)
    finally:
        DUKASCOPY_LOCK.release()

    assert not result.empty
    assert result.iloc[-1]["close"] == pytest.approx(1.15)


def test_scheduler_poll_does_not_block_live_loop() -> None:
    from src.core.clock import LiveClock
    from src.data.scheduler import DataScheduler

    async def _run() -> None:
        bus = MagicMock()
        bus.publish = AsyncMock()
        store = MagicMock()

        scheduler = DataScheduler(
            bus=bus,
            store=store,
            clock=LiveClock(),
            active_pairs=[(Instrument.EURUSD, Timeframe.H1)],
        )
        scheduler._running = True

        async def slow_poll(*_args: object, **_kwargs: object) -> None:
            await asyncio.sleep(2)

        scheduler._poll_instrument = slow_poll  # type: ignore[method-assign]
        scheduler._schedule_poll(Instrument.EURUSD, [Timeframe.H1])

        await asyncio.sleep(0.05)
        task = scheduler._poll_tasks[Instrument.EURUSD]
        assert task is not None
        assert not task.done()

        scheduler.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run())