"""Dataclasses and configuration models for D08-BACKTEST engines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    initial_capital: float = 10000.0
    commission_pct: float = 0.001  # 0.1% per trade
    slippage_pct: float = 0.0005  # 0.05% slippage
    position_size_pct: float = 1.0  # 100% of capital per trade
    min_trade_interval: int = 1  # Minimum bars between trades
    max_positions: int = 1  # Only 1 position at a time for now


@dataclass
class Trade:
    """Record of a single trade (used in vectorized backtest)."""

    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    size: float
    side: str  # 'long' or 'short'
    pnl: float
    pnl_pct: float
    commission: float


@dataclass
class BacktestResult:
    """Results of a backtest."""

    trades: list[Trade]
    equity_curve: pd.Series
    positions: pd.Series
    returns: pd.Series
    config: BacktestConfig
    metadata: dict[str, Any]
