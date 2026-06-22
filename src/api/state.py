"""Shared memory state cache for the API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from src.core.contracts import (
    FundamentalSignal,
    OrderEvent,
    PortfolioState,
    SystemHealthEvent,
    TechnicalSignal,
    TradeSignal,
)

# Max signal history to retain in memory
MAX_HISTORY_LIMIT = 200

latest_portfolio: Optional[PortfolioState] = None
latest_technical: Dict[str, TechnicalSignal] = {}  # instrument -> TechnicalSignal
latest_fundamental: Dict[str, FundamentalSignal] = {}  # instrument -> FundamentalSignal

technical_history: List[TechnicalSignal] = []
fundamental_history: List[FundamentalSignal] = []
trade_signal_history: List[TradeSignal] = []
order_event_history: List[OrderEvent] = []
health_history: List[SystemHealthEvent] = []


def add_to_history(lst: List[Any], item: Any) -> None:
    """Helper to append an item to a list and keep it capped at MAX_HISTORY_LIMIT."""
    lst.append(item)
    if len(lst) > MAX_HISTORY_LIMIT:
        lst.pop(0)
