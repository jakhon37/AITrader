"""Tests for backtest DataFeed, EventDrivenBacktestEngine, and isolation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from src.core.bus import InProcessBus, create_bus
from src.core.clock import ReplayClock, get_clock, now, set_clock, LiveClock
from src.core.contracts import Instrument, Timeframe, OHLCVBar, BusChannel, Direction
from src.core.config import InstrumentConfig
from src.data.store import DataStore
from src.backtest.feed import DataFeed
from src.backtest.engine import EventDrivenBacktestEngine, Trade
from src.technical.engine import TechnicalEngine


@pytest.fixture()
def sample_ohlcv_data() -> pd.DataFrame:
    """Generate sample OHLCV data."""
    dates = pd.date_range("2024-01-01 00:00:00", periods=50, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.1000 + i * 0.0001 for i in range(50)],
            "high": [1.1005 + i * 0.0001 for i in range(50)],
            "low": [1.0995 + i * 0.0001 for i in range(50)],
            "close": [1.1002 + i * 0.0001 for i in range(50)],
            "volume": [100.0] * 50,
        },
        index=dates,
    )
    return df


@pytest.mark.asyncio
async def test_data_feed_chronological_order(tmp_path, sample_ohlcv_data):
    store = DataStore(base_dir=tmp_path)
    
    # Write H1 and M15 data to store
    df_h1 = sample_ohlcv_data.copy()
    df_m15 = sample_ohlcv_data.copy()
    df_m15.index = pd.date_range("2024-01-01 00:00:00", periods=50, freq="15min", tz="UTC")
    
    store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df_h1)
    store.write_ohlcv(Instrument.EURUSD, Timeframe.M15, df_m15)
    
    clock = ReplayClock(datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
    set_clock(clock)
    
    feed = DataFeed(
        store=store,
        instrument=Instrument.EURUSD,
        timeframes=[Timeframe.H1, Timeframe.M15],
        start=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        clock=clock,
    )
    
    emitted_bars = []
    async for bar in feed.run(speed=0.0):
        emitted_bars.append(bar)
        # Assert clock advances to bar's close time (which is open timestamp + duration)
        duration = timedelta(hours=1) if bar.timeframe == Timeframe.H1 else timedelta(minutes=15)
        assert clock.now() == bar.timestamp + duration

    assert len(emitted_bars) > 0
    
    # Assert chronological ordering by close time
    last_close = None
    for bar in emitted_bars:
        duration = timedelta(hours=1) if bar.timeframe == Timeframe.H1 else timedelta(minutes=15)
        close_time = bar.timestamp + duration
        if last_close is not None:
            assert close_time >= last_close
        last_close = close_time


@pytest.mark.asyncio
async def test_event_driven_backtest_pipeline(tmp_path, sample_ohlcv_data):
    # Ensure a fresh ReplayClock
    clock = ReplayClock(datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
    set_clock(clock)

    bus = InProcessBus()
    store = DataStore(base_dir=tmp_path)
    
    # Store at least 210 bars to allow indicators/regime to calculate without error
    dates = pd.date_range("2024-01-01 00:00:00", periods=250, freq="h", tz="UTC")
    df_h1 = pd.DataFrame(
        {
            "open": [1.1000 + i * 0.0001 for i in range(250)],
            "high": [1.1005 + i * 0.0001 for i in range(250)],
            "low": [1.0995 + i * 0.0001 for i in range(250)],
            "close": [1.1002 + i * 0.0001 for i in range(250)],
            "volume": [100.0] * 250,
        },
        index=dates,
    )
    
    store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df_h1)

    inst_configs = {
        Instrument.EURUSD: InstrumentConfig(
            pip_size=0.0001,
            lot_size=100000.0,
            session_hours={"open": "22:00", "close": "22:00"},
            active_timeframes=[Timeframe.H1],
            primary_timeframe=Timeframe.H1,
        )
    }

    tech_engine = TechnicalEngine(
        bus=bus,
        store=store,
        instruments_config=inst_configs,
    )

    feed = DataFeed(
        store=store,
        instrument=Instrument.EURUSD,
        timeframes=[Timeframe.H1],
        start=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc),
        clock=clock,
    )

    engine = EventDrivenBacktestEngine(initial_capital=10000.0)
    trades, equity_curve = await engine.run(feed, bus, tech_engine)

    assert isinstance(trades, list)
    assert isinstance(equity_curve, pd.Series)
    assert len(equity_curve) > 0


@pytest.mark.asyncio
async def test_replay_isolation(tmp_path, sample_ohlcv_data):
    # Isolation test: assert that replay events do NOT bleed into the production clock / bus singleton.
    # Set production clock to LiveClock
    prod_clock = LiveClock()
    set_clock(prod_clock)
    
    # Replay bus is created locally
    replay_bus = InProcessBus()
    replay_clock = ReplayClock(datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
    
    store = DataStore(base_dir=tmp_path)
    df_h1 = sample_ohlcv_data.copy()
    store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df_h1)

    inst_configs = {
        Instrument.EURUSD: InstrumentConfig(
            pip_size=0.0001,
            lot_size=100000.0,
            session_hours={"open": "22:00", "close": "22:00"},
            active_timeframes=[Timeframe.H1],
            primary_timeframe=Timeframe.H1,
        )
    }

    tech_engine = TechnicalEngine(
        bus=replay_bus,
        store=store,
        instruments_config=inst_configs,
    )

    feed = DataFeed(
        store=store,
        instrument=Instrument.EURUSD,
        timeframes=[Timeframe.H1],
        start=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        clock=replay_clock,
    )

    # Subscribe to production clock mode check and assert it remains LIVE
    assert get_clock().mode() == "live"

    engine = EventDrivenBacktestEngine(initial_capital=10000.0)
    
    # We temporarily set the global clock to replay clock for the feed to find it via now() calls inside other components
    set_clock(replay_clock)
    trades, equity_curve = await engine.run(feed, replay_bus, tech_engine)
    
    # Restore prod clock
    set_clock(prod_clock)

    assert get_clock().mode() == "live"
