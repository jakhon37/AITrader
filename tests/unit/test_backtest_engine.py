"""Tests for backtesting engine."""

import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestConfig, BacktestEngine, Trade


@pytest.fixture
def sample_data():
    """Generate sample OHLCV data."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    np.random.seed(42)

    # Trending price data
    prices = 100 + np.cumsum(np.random.randn(100) * 0.5)

    data = pd.DataFrame(
        {
            "open": prices + np.random.randn(100) * 0.1,
            "high": prices + abs(np.random.randn(100) * 0.2),
            "low": prices - abs(np.random.randn(100) * 0.2),
            "close": prices,
            "volume": np.random.randint(1000, 10000, 100),
        },
        index=dates,
    )
    return data


@pytest.fixture
def simple_signals():
    """Generate simple buy-and-hold signal."""
    return pd.Series([1] * 100, index=pd.date_range("2024-01-01", periods=100, freq="D"))


@pytest.fixture
def alternating_signals():
    """Generate alternating long/short signals."""
    signals = []
    for i in range(100):
        if i < 20:
            signals.append(1)  # Long
        elif i < 40:
            signals.append(-1)  # Short
        elif i < 60:
            signals.append(1)  # Long
        else:
            signals.append(0)  # Flat
    return pd.Series(signals, index=pd.date_range("2024-01-01", periods=100, freq="D"))


def test_backtest_config_defaults():
    """Test default config values."""
    config = BacktestConfig()
    assert config.initial_capital == 10000.0
    assert config.commission_pct == 0.001
    assert config.slippage_pct == 0.0005
    assert config.position_size_pct == 1.0


def test_backtest_engine_init():
    """Test engine initialization."""
    engine = BacktestEngine()
    assert engine.config.initial_capital == 10000.0

    config = BacktestConfig(initial_capital=50000.0)
    engine = BacktestEngine(config)
    assert engine.config.initial_capital == 50000.0


def test_backtest_simple_long(sample_data, simple_signals):
    """Test simple buy-and-hold strategy."""
    config = BacktestConfig(
        initial_capital=10000.0,
        commission_pct=0.0,  # No commission for simplicity
        slippage_pct=0.0,  # No slippage
    )
    engine = BacktestEngine(config)

    result = engine.run(sample_data, simple_signals)

    assert len(result.trades) == 1  # One trade (buy and hold)
    assert result.trades[0].side == "long"
    assert len(result.equity_curve) == len(sample_data)
    assert result.metadata["total_trades"] == 1


def test_backtest_alternating_signals(sample_data, alternating_signals):
    """Test strategy with alternating signals."""
    config = BacktestConfig(
        initial_capital=10000.0,
        commission_pct=0.001,
        slippage_pct=0.0005,
    )
    engine = BacktestEngine(config)

    result = engine.run(sample_data, alternating_signals)

    # Should have 3 trades: long -> short -> long
    assert len(result.trades) == 3
    assert result.trades[0].side == "long"
    assert result.trades[1].side == "short"
    assert result.trades[2].side == "long"


def test_backtest_no_signals(sample_data):
    """Test with no signals (all zeros)."""
    signals = pd.Series(0, index=sample_data.index)
    engine = BacktestEngine()

    result = engine.run(sample_data, signals)

    assert len(result.trades) == 0
    assert (result.equity_curve == engine.config.initial_capital).all()


def test_backtest_commission_reduces_pnl(sample_data):
    """Test that commission reduces PnL."""
    signals = pd.Series([1] * 50 + [0] * 50, index=sample_data.index)

    # Run with no commission
    config_no_comm = BacktestConfig(commission_pct=0.0, slippage_pct=0.0)
    engine_no_comm = BacktestEngine(config_no_comm)
    result_no_comm = engine_no_comm.run(sample_data, signals)

    # Run with commission
    config_with_comm = BacktestConfig(commission_pct=0.01, slippage_pct=0.0)
    engine_with_comm = BacktestEngine(config_with_comm)
    result_with_comm = engine_with_comm.run(sample_data, signals)

    # PnL should be lower with commission
    pnl_no_comm = result_no_comm.trades[0].pnl
    pnl_with_comm = result_with_comm.trades[0].pnl

    assert pnl_with_comm < pnl_no_comm
    assert result_with_comm.trades[0].commission > 0


def test_backtest_slippage_affects_price(sample_data):
    """Test that slippage affects execution prices."""
    signals = pd.Series([1] * 50 + [0] * 50, index=sample_data.index)

    # Run with no slippage
    config_no_slip = BacktestConfig(commission_pct=0.0, slippage_pct=0.0)
    engine_no_slip = BacktestEngine(config_no_slip)
    result_no_slip = engine_no_slip.run(sample_data, signals)

    # Run with slippage
    config_with_slip = BacktestConfig(commission_pct=0.0, slippage_pct=0.01)
    engine_with_slip = BacktestEngine(config_with_slip)
    result_with_slip = engine_with_slip.run(sample_data, signals)

    # Entry price should be higher with slippage (worse for buyer)
    assert (
        result_with_slip.trades[0].entry_price
        > result_no_slip.trades[0].entry_price
    )


def test_backtest_position_sizing(sample_data, simple_signals):
    """Test position sizing."""
    # Test with 50% position size
    config = BacktestConfig(
        initial_capital=10000.0,
        position_size_pct=0.5,
        commission_pct=0.0,
        slippage_pct=0.0,
    )
    engine = BacktestEngine(config)
    result = engine.run(sample_data, simple_signals)

    # Position value should be ~5000 (50% of capital)
    trade = result.trades[0]
    position_value = trade.size * trade.entry_price
    assert abs(position_value - 5000.0) < 100  # Allow small tolerance


def test_backtest_equity_curve_shape(sample_data, alternating_signals):
    """Test equity curve has correct shape."""
    engine = BacktestEngine()
    result = engine.run(sample_data, alternating_signals)

    assert len(result.equity_curve) == len(sample_data)
    assert result.equity_curve.iloc[0] == engine.config.initial_capital


def test_backtest_returns_calculation(sample_data, alternating_signals):
    """Test returns are calculated correctly."""
    engine = BacktestEngine()
    result = engine.run(sample_data, alternating_signals)

    # Returns should be percentage changes in equity
    assert len(result.returns) == len(sample_data)
    assert result.returns.iloc[0] == 0.0  # First return is always 0


def test_backtest_positions_tracking(sample_data):
    """Test position tracking."""
    signals = pd.Series([1] * 30 + [0] * 30 + [-1] * 40, index=sample_data.index)
    engine = BacktestEngine()
    result = engine.run(sample_data, signals)

    # Check positions match trades
    assert (result.positions.iloc[:30] == 1).sum() > 0  # Long position
    assert (result.positions.iloc[60:] == -1).sum() > 0  # Short position


def test_backtest_min_trade_interval(sample_data):
    """Test minimum trade interval enforcement."""
    # Signals that change rapidly
    signals = pd.Series(
        [1 if i % 3 == 0 else -1 for i in range(100)],
        index=sample_data.index,
    )

    config = BacktestConfig(min_trade_interval=5)
    engine = BacktestEngine(config)
    result = engine.run(sample_data, signals)

    # Count trades - with min interval enforcement, should have fewer trades
    # Without enforcement, would switch every ~3 bars
    # With min_trade_interval=5, should have significantly fewer trades
    assert len(result.trades) < 20  # Much less than 33 (100/3)


def test_backtest_missing_close_column():
    """Test error when close column is missing."""
    data = pd.DataFrame(
        {"open": [100, 101, 102], "high": [101, 102, 103]},
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )
    signals = pd.Series([1, 1, 1], index=data.index)

    engine = BacktestEngine()
    with pytest.raises(ValueError, match="close"):
        engine.run(data, signals)


def test_backtest_signal_data_length_mismatch():
    """Test error when signal length doesn't match data."""
    data = pd.DataFrame(
        {"close": [100, 101, 102]},
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )
    signals = pd.Series([1, 1], index=pd.date_range("2024-01-01", periods=2, freq="D"))

    engine = BacktestEngine()
    with pytest.raises(ValueError, match="length"):
        engine.run(data, signals)


def test_backtest_long_position_pnl(sample_data):
    """Test PnL calculation for long position."""
    # Create upward trending data
    data = sample_data.copy()
    data["close"] = np.linspace(100, 120, len(data))

    signals = pd.Series([1] * 50 + [0] * 50, index=data.index)

    config = BacktestConfig(commission_pct=0.0, slippage_pct=0.0)
    engine = BacktestEngine(config)
    result = engine.run(data, signals)

    # Long position should profit in uptrend
    assert result.trades[0].pnl > 0
    assert result.trades[0].side == "long"


def test_backtest_short_position_pnl(sample_data):
    """Test PnL calculation for short position."""
    # Create downward trending data
    data = sample_data.copy()
    data["close"] = np.linspace(120, 100, len(data))

    signals = pd.Series([-1] * 50 + [0] * 50, index=data.index)

    config = BacktestConfig(commission_pct=0.0, slippage_pct=0.0)
    engine = BacktestEngine(config)
    result = engine.run(data, signals)

    # Short position should profit in downtrend
    assert result.trades[0].pnl > 0
    assert result.trades[0].side == "short"


def test_backtest_metadata(sample_data, simple_signals):
    """Test backtest metadata."""
    engine = BacktestEngine()
    result = engine.run(sample_data, simple_signals)

    assert result.metadata["total_bars"] == len(sample_data)
    assert result.metadata["total_trades"] == len(result.trades)
    assert result.metadata["start_date"] == sample_data.index[0]
    assert result.metadata["end_date"] == sample_data.index[-1]


def test_trade_dataclass():
    """Test Trade dataclass."""
    trade = Trade(
        entry_time=pd.Timestamp("2024-01-01"),
        exit_time=pd.Timestamp("2024-01-10"),
        entry_price=100.0,
        exit_price=105.0,
        size=10.0,
        side="long",
        pnl=50.0,
        pnl_pct=5.0,
        commission=2.0,
    )

    assert trade.entry_price == 100.0
    assert trade.exit_price == 105.0
    assert trade.pnl == 50.0
    assert trade.side == "long"
