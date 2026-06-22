"""D06-EXECUTION — Broker Interface Protocol.

All broker adapters (mock, OANDA, MT5, etc.) must implement this protocol.
"""

from __future__ import annotations

from typing import Callable, Dict, Protocol
from src.core.contracts import Instrument, Order, OrderEvent


class Broker(Protocol):
    """Protocol defining the interface for broker adapters."""

    def submit_order(self, order: Order, on_event: Callable[[OrderEvent], None]) -> None:
        """Submit an order to the broker.

        Args:
            order: The Order to be executed.
            on_event: Callback function to receive OrderEvent updates.
        """
        ...

    def get_position(self, instrument: Instrument) -> float:
        """Get current position size for an instrument (positive=long, negative=short)."""
        ...

    def get_all_positions(self) -> Dict[Instrument, float]:
        """Get all open positions."""
        ...

    def get_portfolio_value(self, prices: Dict[Instrument, float]) -> float:
        """Get total portfolio value (cash + position value) given the current prices."""
        ...

    def update_price(self, instrument: Instrument, price: float) -> None:
        """Update price feed for simulation/tracking."""
        ...
