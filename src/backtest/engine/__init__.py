"""D08-BACKTEST — Vectorized and Event-Driven Backtesting Engines."""

from src.backtest.engine.contracts import BacktestConfig, BacktestResult, Trade
from src.backtest.engine.vectorized import BacktestEngine
from src.backtest.engine.event_driven import (
    EventDrivenBacktestEngine,
    MockDecisionEngine,
    MockExecutionEngine,
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
