"""Tests for backtest replay, session state, scorer, and reporter."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest
from pathlib import Path

from src.core.contracts import Instrument, Timeframe, Order, OrderSide, OrderStatus, ExecutionMode
from src.backtest.session_state import ReplaySessionState
from src.backtest.scorer import ReplayScorer
from src.backtest.reporter import ReplayReporter
from src.backtest.replay import ManualReplaySession
from src.data.store import DataStore


def test_session_state_init_and_update():
    """Test ReplaySessionState initialization and thread-safe updates."""
    state = ReplaySessionState(
        mode="watch",
        instrument=Instrument.EURUSD,
        total_bars=100,
        speed=5.0,
    )
    
    assert state.mode == "watch"
    assert state.instrument == Instrument.EURUSD
    assert state.total_bars == 100
    assert state.speed == 5.0
    assert state.status == "paused"
    
    # Update fields
    state.update(status="running", speed=10.0, current_bar_index=42)
    
    assert state.status == "running"
    assert state.speed == 10.0
    assert state.current_bar_index == 42
    
    # Convert to dict
    d = state.to_dict()
    assert d["mode"] == "watch"
    assert d["status"] == "running"
    assert d["speed"] == 10.0
    assert d["current_bar_index"] == 42


def test_replay_scorer_metrics():
    """Test ReplayScorer performance and discipline metrics."""
    # Create mock completed orders (acting like completed trades)
    trades = [
        # Win trade
        {
            "pnl": 150.0,
            "side": "long",
            "entry_price": 1.1000,
            "exit_price": 1.1015,
            "sl": 1.0950,
            "tp": 1.1100,
        },
        # Loss trade - respected stop loss
        {
            "pnl": -50.0,
            "side": "long",
            "entry_price": 1.1000,
            "exit_price": 1.0950,
            "sl": 1.0950,
            "tp": 1.1100,
        },
        # Loss trade - violated stop loss (held past SL)
        {
            "pnl": -80.0,
            "side": "long",
            "entry_price": 1.1000,
            "exit_price": 1.0920,
            "sl": 1.0950,
            "tp": 1.1100,
        }
    ]
    
    # Mock equity curve
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    equity_curve = pd.Series([10000.0, 10150.0, 10100.0, 10020.0], index=dates)
    
    metrics = ReplayScorer.calculate_metrics(
        trades=trades,  # type: ignore
        equity_curve=equity_curve,
        initial_capital=10000.0,
        buy_and_hold_return=0.005,
    )
    
    assert metrics["initial_capital"] == 10000.0
    assert metrics["final_equity"] == 10020.0
    assert metrics["net_profit"] == 20.0
    assert metrics["net_profit_pct"] == 0.2
    assert metrics["total_trades"] == 3
    assert metrics["win_rate"] == pytest.approx(100.0 / 3.0)
    assert metrics["profit_factor"] == 150.0 / 130.0
    
    # One violation out of three trades with SL -> 2/3 = 66.67% discipline score
    assert metrics["discipline_score"] == pytest.approx(200.0 / 3.0)
    assert metrics["buy_and_hold_return_pct"] == 0.5
    assert metrics["outperformed_benchmark"] is False


def test_reporter_generation(tmp_path):
    """Test ReplayReporter generates files and cleans up properly."""
    reporter = ReplayReporter(reports_dir=str(tmp_path), retention_count=2, retention_days=30)
    
    # Mock data
    metrics = {
        "final_equity": 10200.0,
        "net_profit": 200.0,
        "net_profit_pct": 2.0,
        "total_trades": 2,
        "win_rate": 50.0,
        "profit_factor": 1.5,
    }
    trades = [
        {"entry_time": datetime.now(), "exit_time": datetime.now(), "pnl": 300.0, "pnl_pct": 0.03, "size": 1.0, "side": "long", "entry_price": 1.10, "exit_price": 1.13},
        {"entry_time": datetime.now(), "exit_time": datetime.now(), "pnl": -100.0, "pnl_pct": -0.01, "size": 1.0, "side": "long", "entry_price": 1.10, "exit_price": 1.09},
    ]
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    equity_curve = pd.Series([10000.0, 10300.0, 10200.0], index=dates)
    
    # Generate report 1
    paths1 = reporter.generate(
        mode="manual",
        instrument=Instrument.EURUSD,
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 3, tzinfo=timezone.utc),
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
    )
    
    assert Path(paths1["json"]).exists()
    assert Path(paths1["html"]).exists()
    
    # Generate report 2
    paths2 = reporter.generate(
        mode="manual",
        instrument=Instrument.EURUSD,
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 3, tzinfo=timezone.utc),
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
    )
    
    # Manually adjust mtimes of generated files to ensure strictly chronological ordering
    import os
    import time
    now_t = time.time()
    os.utime(paths1["json"], (now_t - 10, now_t - 10))
    os.utime(paths1["html"], (now_t - 10, now_t - 10))
    os.utime(paths2["json"], (now_t - 5, now_t - 5))
    os.utime(paths2["html"], (now_t - 5, now_t - 5))
    
    # Generate report 3 (triggers retention cleanup of oldest report)
    paths3 = reporter.generate(
        mode="manual",
        instrument=Instrument.EURUSD,
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 3, tzinfo=timezone.utc),
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
    )
    
    # Verify retention count limit (retention_count=2)
    # The oldest report files (paths1) should have been cleaned up
    assert not Path(paths1["json"]).exists()
    assert not Path(paths1["html"]).exists()
    assert Path(paths2["json"]).exists()
    assert Path(paths3["json"]).exists()


@pytest.mark.asyncio
async def test_manual_replay_session_stepping(tmp_path):
    """Test ManualReplaySession starts and steps forward correctly."""
    store = DataStore(base_dir=tmp_path)
    
    # Store sufficient primary TF bars (H1) for technical engine indicators (e.g. 210 bars)
    periods = 210
    dates = pd.date_range("2024-01-01 00:00:00", periods=periods, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.1000 + i * 0.0001 for i in range(periods)],
            "high": [1.1005 + i * 0.0001 for i in range(periods)],
            "low": [1.0995 + i * 0.0001 for i in range(periods)],
            "close": [1.1002 + i * 0.0001 for i in range(periods)],
            "volume": [100.0] * periods,
        },
        index=dates,
    )
    store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df)
    
    session = ManualReplaySession(
        instrument=Instrument.EURUSD,
        start_date=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 5, 0, 0, tzinfo=timezone.utc),
        initial_capital=10000.0,
        store=store,
        reports_dir=str(tmp_path),
    )
    
    await session.start()
    
    assert session.state.status == "running"
    assert session.state.current_bar_index == 1
    
    await session.step()
    assert session.state.current_bar_index == 2
    
    # Test step_multiple
    await session.step_multiple(5)
    assert session.state.current_bar_index == 7
    
    # End session
    scorecard = await session.end_session()
    assert scorecard["initial_capital"] == 10000.0
    assert session.state.status == "ended"
