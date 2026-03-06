"""Integration tests for execution system."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from execution.engine import ExecutionEngine, ExecutionConfig
from execution.risk_manager import RiskViolation
from execution.circuit_breaker import HaltReason


def test_execution_engine_initialization():
    """Test execution engine initialization."""
    config = ExecutionConfig(initial_capital=100000, dry_run=True)
    engine = ExecutionEngine(config)

    assert engine.config.initial_capital == 100000
    assert engine.is_running == False
    assert engine.risk_manager is not None
    assert engine.circuit_breaker is not None
    assert engine.position_manager is not None


def test_execution_dry_run_mode():
    """Test execution in dry run mode."""
    config = ExecutionConfig(initial_capital=100000, dry_run=True)
    engine = ExecutionEngine(config)
    engine.start()

    # Execute signals
    result = engine.execute_signal("EURUSD", 1, 1.1000, 10000)
    assert result == "opened"

    result = engine.execute_signal("GBPUSD", -1, 1.2500, 5000)
    assert result == "opened"

    # In dry run, positions aren't actually opened
    assert engine.position_manager.get_num_positions() == 0

    engine.stop()


def test_execution_real_mode():
    """Test execution with real position management."""
    config = ExecutionConfig(initial_capital=100000, dry_run=False)
    engine = ExecutionEngine(config)
    engine.start()

    # Open position
    result = engine.execute_signal("EURUSD", 1, 1.1000, 10000)
    assert result == "opened"
    assert engine.position_manager.get_num_positions() == 1

    # Try to open same position again (should skip)
    result = engine.execute_signal("EURUSD", 1, 1.1050, 10000)
    assert result == "skipped"
    assert engine.position_manager.get_num_positions() == 1

    # Close position
    result = engine.execute_signal("EURUSD", 0, 1.1050, 0)
    assert result == "closed"
    assert engine.position_manager.get_num_positions() == 0

    # Check PnL
    status = engine.get_status()
    assert status["realized_pnl"] > 0  # Should have made profit

    engine.stop()


def test_execution_risk_limits():
    """Test risk limit enforcement."""
    config = ExecutionConfig(initial_capital=10000, dry_run=False)
    engine = ExecutionEngine(config)
    engine.start()

    # Try to open position larger than allowed
    result = engine.execute_signal("EURUSD", 1, 1.1000, 200000)
    assert result == "skipped"  # Should be rejected by risk check

    engine.stop()


def test_execution_circuit_breaker():
    """Test circuit breaker halt."""
    config = ExecutionConfig(initial_capital=100000, dry_run=False)
    engine = ExecutionEngine(config)
    engine.start()

    # Manual halt
    engine.manual_halt("Testing")
    assert engine.circuit_breaker.is_halted

    # Try to execute while halted
    result = engine.execute_signal("EURUSD", 1, 1.1000, 10000)
    assert result == "halted"

    # Resume
    engine.manual_resume("Test complete")
    assert not engine.circuit_breaker.is_halted

    # Should work now
    result = engine.execute_signal("EURUSD", 1, 1.1000, 10000)
    assert result == "opened"

    engine.stop()


def test_execution_status_reporting():
    """Test execution status reporting."""
    config = ExecutionConfig(initial_capital=100000, dry_run=False)
    engine = ExecutionEngine(config)
    engine.start()

    # Get initial status
    status = engine.get_status()
    assert status["is_running"] == True
    assert status["is_halted"] == False
    assert status["portfolio_value"] == 100000
    assert status["num_positions"] == 0

    # Open position
    engine.execute_signal("EURUSD", 1, 1.1000, 10000)

    # Get updated status
    status = engine.get_status()
    assert status["num_positions"] == 1
    assert status["cash"] < 100000  # Some cash used
    assert "risk_metrics" in status

    engine.stop()


def test_execution_multiple_positions():
    """Test managing multiple positions."""
    config = ExecutionConfig(initial_capital=100000, dry_run=False)
    engine = ExecutionEngine(config)
    engine.start()

    # Open multiple positions
    engine.execute_signal("EURUSD", 1, 1.1000, 5000)
    engine.execute_signal("GBPUSD", -1, 1.2500, 3000)
    engine.execute_signal("USDJPY", 1, 110.00, 100)

    assert engine.position_manager.get_num_positions() == 3

    # Close one
    engine.execute_signal("GBPUSD", 0, 1.2450, 0)
    assert engine.position_manager.get_num_positions() == 2

    # Check exposure
    status = engine.get_status()
    assert status["total_exposure"] > 0

    engine.stop()


def test_execution_pnl_tracking():
    """Test PnL tracking across trades."""
    config = ExecutionConfig(initial_capital=100000, dry_run=False)
    engine = ExecutionEngine(config)
    engine.start()

    initial_value = engine.position_manager.get_portfolio_value()

    # Profitable trade
    engine.execute_signal("EURUSD", 1, 1.1000, 10000)
    engine.execute_signal("EURUSD", 0, 1.1100, 0)  # 100 pips profit

    status = engine.get_status()
    assert status["realized_pnl"] > 0

    # Portfolio value should be higher
    final_value = engine.position_manager.get_portfolio_value()
    assert final_value > initial_value

    engine.stop()


def test_execution_consecutive_losses():
    """Test circuit breaker tracks consecutive losses."""
    config = ExecutionConfig(initial_capital=100000, dry_run=False)
    engine = ExecutionEngine(config)
    engine.start()

    # Simulate consecutive losses
    for i in range(3):
        symbol = f"PAIR{i}"
        engine.execute_signal(symbol, 1, 1.0, 1000)
        engine.execute_signal(symbol, 0, 0.95, 0)  # Loss

    # Should track losses (may or may not halt depending on timing)
    assert engine.circuit_breaker.consecutive_losses >= 3

    engine.stop()


def test_execution_audit_log():
    """Test audit log integration."""
    config = ExecutionConfig(initial_capital=100000, dry_run=False, enable_audit_log=True)
    engine = ExecutionEngine(config)

    assert engine.audit_log is not None

    engine.start()
    engine.execute_signal("EURUSD", 1, 1.1000, 10000)
    engine.execute_signal("EURUSD", 0, 1.1050, 0)
    engine.stop()

    # Check audit log has events
    stats = engine.audit_log.get_stats()
    assert stats["total_events"] >= 4  # start, signal, open, close, stop

    engine.stop()
