"""D08-BACKTEST — Backward-compatible wrapper for backtesting engines."""

from src.backtest.engine.__init__ import (
    BacktestConfig,
    Trade,
    BacktestResult,
    BacktestEngine,
    MockDecisionEngine,
    MockExecutionEngine,
    EventDrivenBacktestEngine,
)

__all__ = [
    "BacktestConfig",
    "Trade",
    "BacktestResult",
    "BacktestEngine",
    "MockDecisionEngine",
    "MockExecutionEngine",
    "EventDrivenBacktestEngine",
]
