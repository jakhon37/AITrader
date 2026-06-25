"""Unit tests for D02-DATA: DataScheduler.

Tests cover:
  - candle open time and next-close calculation helpers
  - tick() in replay mode: emits bars for crossed boundaries
  - tick() does NOT re-emit the same bar twice
  - tick() skips missing bars gracefully (no DataError propagation)
  - stop() sets _running to False
  - reset_last_emitted() clears tracking
  - _fetch_and_publish stores bar in DataStore and publishes to bus
  - Live mode: _live_loop exits cleanly when stop() is called

All external I/O is stubbed — no real yfinance or filesystem calls.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from src.core.clock import ReplayClock, LiveClock
from src.core.contracts import BusChannel, Instrument, OHLCVBar, Timeframe
from src.core.exceptions import DataError
from src.data.scheduler import (
    DataScheduler,
    OHLCVFetcher,
    _candle_open_time,
    _next_candle_close,
)
from src.data.store import DataStore


# ── helpers ───────────────────────────────────────────────────────────────────

def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _make_bar(instrument: Instrument, timeframe: Timeframe, ts: datetime) -> OHLCVBar:
    return OHLCVBar(
        signal_id="test-id",
        instrument=instrument,
        timeframe=timeframe,
        timestamp=ts,
        open=1.10,
        high=1.11,
        low=1.09,
        close=1.105,
        volume=1000.0,
        source="test",
    )


@pytest.fixture()
def mock_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture()
def mock_store() -> MagicMock:
    store = MagicMock(spec=DataStore)
    store.write_ohlcv = MagicMock()
    return store


@pytest.fixture()
def mock_fetcher() -> MagicMock:
    return MagicMock(spec=OHLCVFetcher)


EURUSD = Instrument.EURUSD
H1 = Timeframe.H1


# ── candle time helpers ───────────────────────────────────────────────────────

class TestCandleHelpers:
    def test_candle_open_time_h1(self) -> None:
        dt = datetime(2024, 3, 15, 9, 43, 12, tzinfo=timezone.utc)
        open_t = _candle_open_time(dt, H1)
        assert open_t == _utc(2024, 3, 15, 9)

    def test_candle_open_time_m15(self) -> None:
        dt = datetime(2024, 3, 15, 9, 43, tzinfo=timezone.utc)
        open_t = _candle_open_time(dt, Timeframe.M15)
        assert open_t == datetime(2024, 3, 15, 9, 30, tzinfo=timezone.utc)

    def test_next_candle_close_h1(self) -> None:
        dt = datetime(2024, 3, 15, 9, 30, tzinfo=timezone.utc)
        close = _next_candle_close(dt, H1)
        assert close == _utc(2024, 3, 15, 10)

    def test_next_candle_close_exactly_on_boundary(self) -> None:
        # Exactly at candle open — next close is 1 hour away
        dt = _utc(2024, 3, 15, 9)
        close = _next_candle_close(dt, H1)
        assert close == _utc(2024, 3, 15, 10)


# ── replay tick() ─────────────────────────────────────────────────────────────

class TestReplayTick:
    async def test_tick_emits_bar_when_boundary_crossed(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        clock = ReplayClock(start=_utc(2024, 3, 15, 10))
        ts = _utc(2024, 3, 15, 10)
        bar = _make_bar(EURUSD, H1, ts)

        # DataStore returns the bar
        df = pd.DataFrame(
            {"open": [bar.open], "high": [bar.high], "low": [bar.low],
             "close": [bar.close], "volume": [bar.volume]},
            index=pd.DatetimeIndex([ts], tz="UTC"),
        )
        mock_store.get_ohlcv.return_value = df

        scheduler = DataScheduler(
            bus=mock_bus,
            store=mock_store,
            clock=clock,
            fetcher=mock_fetcher,
            active_pairs=[(EURUSD, H1)],
        )

        await scheduler.tick()

        mock_bus.publish.assert_called_once()
        channel, payload = mock_bus.publish.call_args[0]
        assert channel == BusChannel.OHLCV_BAR
        assert isinstance(payload, OHLCVBar)
        assert payload.instrument == EURUSD

    async def test_tick_does_not_emit_same_bar_twice(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        clock = ReplayClock(start=_utc(2024, 3, 15, 10))
        ts = _utc(2024, 3, 15, 10)
        bar = _make_bar(EURUSD, H1, ts)

        df = pd.DataFrame(
            {"open": [bar.open], "high": [bar.high], "low": [bar.low],
             "close": [bar.close], "volume": [bar.volume]},
            index=pd.DatetimeIndex([ts], tz="UTC"),
        )
        mock_store.get_ohlcv.return_value = df

        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=clock,
            fetcher=mock_fetcher, active_pairs=[(EURUSD, H1)],
        )

        await scheduler.tick()
        await scheduler.tick()  # same virtual time — should NOT re-emit

        assert mock_bus.publish.call_count == 1

    async def test_tick_skips_missing_bar_gracefully(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        clock = ReplayClock(start=_utc(2024, 3, 15, 10))
        mock_store.get_ohlcv.side_effect = DataError("no data")

        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=clock,
            fetcher=mock_fetcher, active_pairs=[(EURUSD, H1)],
        )

        # Should NOT raise, just skip
        await scheduler.tick()
        mock_bus.publish.assert_not_called()


# ── live mode helpers ─────────────────────────────────────────────────────────

class TestFetchAndPublish:
    async def test_fetch_and_publish_stores_and_publishes(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        clock = LiveClock()
        ts = _utc(2024, 3, 15, 9)
        bar = _make_bar(EURUSD, H1, ts)
        mock_fetcher.fetch_latest_bar.return_value = bar

        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=clock,
            fetcher=mock_fetcher, active_pairs=[(EURUSD, H1)],
        )

        await scheduler._fetch_and_publish(EURUSD, H1)

        mock_store.write_ohlcv.assert_called_once()
        mock_bus.publish.assert_called_once()
        channel, payload = mock_bus.publish.call_args[0]
        assert channel == BusChannel.OHLCV_BAR
        assert payload.close == bar.close

    async def test_fetch_and_publish_skips_duplicate(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        clock = LiveClock()
        ts = _utc(2024, 3, 15, 9)
        bar = _make_bar(EURUSD, H1, ts)
        mock_fetcher.fetch_latest_bar.return_value = bar

        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=clock,
            fetcher=mock_fetcher, active_pairs=[(EURUSD, H1)],
        )
        # Pre-seed last_emitted with the same timestamp
        scheduler._last_emitted[(EURUSD, H1)] = ts

        await scheduler._fetch_and_publish(EURUSD, H1)
        mock_bus.publish.assert_not_called()

    async def test_fetch_error_raises_data_error(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        clock = LiveClock()
        mock_fetcher.fetch_latest_bar.side_effect = DataError("yfinance down")

        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=clock,
            fetcher=mock_fetcher, active_pairs=[(EURUSD, H1)],
        )

        with pytest.raises(DataError, match="yfinance down"):
            await scheduler._fetch_and_publish(EURUSD, H1)


# ── control methods ───────────────────────────────────────────────────────────

class TestControl:
    def test_stop_sets_running_false(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher,
        )
        scheduler._running = True
        scheduler.stop()
        assert scheduler._running is False

    def test_reset_last_emitted_clears_tracking(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher,
        )
        scheduler._last_emitted[(EURUSD, H1)] = _utc(2024, 1, 1)
        scheduler.reset_last_emitted()
        assert len(scheduler._last_emitted) == 0

    def test_active_pairs_property(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        pairs = [(EURUSD, H1), (Instrument.GBPUSD, Timeframe.M15)]
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher, active_pairs=pairs,
        )
        assert scheduler.active_pairs == pairs

    def test_add_active_pair(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher, active_pairs=[],
        )
        assert len(scheduler.active_pairs) == 0
        scheduler.add_active_pair(EURUSD, H1)
        assert scheduler.active_pairs == [(EURUSD, H1)]
        # Duplicate check
        scheduler.add_active_pair(EURUSD, H1)
        assert scheduler.active_pairs == [(EURUSD, H1)]

    def test_set_focused_pair_registers_and_tracks(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher, active_pairs=[],
        )
        scheduler.set_focused_pair(EURUSD, H1)
        assert scheduler.focused_pair == (EURUSD, H1)
        assert scheduler.active_pairs == [(EURUSD, H1)]

    def test_set_focused_pair_prunes_stale_chart_pairs(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        bootstrap = [(EURUSD, H1), (Instrument.GBPUSD, H1)]
        scheduler = DataScheduler(
            bus=mock_bus,
            store=mock_store,
            clock=LiveClock(),
            fetcher=mock_fetcher,
            active_pairs=list(bootstrap),
        )
        scheduler.add_active_pair(EURUSD, Timeframe.M5)
        scheduler.add_active_pair(EURUSD, Timeframe.M30)
        scheduler.set_focused_pair(EURUSD, Timeframe.M1)
        assert scheduler.focused_pair == (EURUSD, Timeframe.M1)
        assert (EURUSD, Timeframe.M5) not in scheduler.active_pairs
        assert (EURUSD, Timeframe.M30) not in scheduler.active_pairs
        assert (EURUSD, Timeframe.M1) in scheduler.active_pairs
        assert (Instrument.GBPUSD, H1) in scheduler.active_pairs

    def test_is_intraday_focused(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher, active_pairs=[(EURUSD, H1)],
        )
        assert scheduler.is_intraday_focused() is False
        scheduler.set_focused_pair(EURUSD, Timeframe.M1)
        assert scheduler.is_intraday_focused() is True
        scheduler.set_focused_pair(EURUSD, H1)
        assert scheduler.is_intraday_focused() is False

    def test_get_live_status_shape(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher, active_pairs=[(EURUSD, H1)],
        )
        status = scheduler.get_live_status()
        assert status["running"] is False
        assert status["active_pairs"] == [{"instrument": "EURUSD", "timeframe": "1h"}]
        assert status["poll_interval_focused_sec"] == 2.0

    async def test_empty_loop_safety(
        self, mock_bus: AsyncMock, mock_store: MagicMock, mock_fetcher: MagicMock
    ) -> None:
        scheduler = DataScheduler(
            bus=mock_bus, store=mock_store, clock=LiveClock(),
            fetcher=mock_fetcher, active_pairs=[],
        )
        import asyncio
        task = asyncio.create_task(scheduler.run())
        await asyncio.sleep(0.1)
        scheduler.stop()
        await task
        assert scheduler._running is False


def test_sync_m1_window_fills_gap_after_last_stored() -> None:
    from src.data.scheduler.store_ops import sync_m1_window_to_store

    store = MagicMock()
    last = datetime(2024, 6, 10, 14, 59, tzinfo=timezone.utc)
    store.list_ohlcv_range.return_value = (last, last)

    idx = pd.date_range(
        datetime(2024, 6, 10, 15, 0, tzinfo=timezone.utc),
        datetime(2024, 6, 10, 15, 5, tzinfo=timezone.utc),
        freq="1min",
        tz="UTC",
    )
    m1_df = pd.DataFrame(
        {
            "open": [1.1] * len(idx),
            "high": [1.1001] * len(idx),
            "low": [1.0999] * len(idx),
            "close": [1.1] * len(idx),
            "volume": [0.0] * len(idx),
        },
        index=idx,
    )
    now = datetime(2024, 6, 10, 15, 6, tzinfo=timezone.utc)

    rows = sync_m1_window_to_store(store, EURUSD, m1_df, now)
    assert rows == 6
    store.write_ohlcv.assert_called_once()
    written = store.write_ohlcv.call_args[0][2]
    assert len(written) == 6
    assert written.index[0].to_pydatetime() == datetime(
        2024, 6, 10, 15, 0, tzinfo=timezone.utc
    )
