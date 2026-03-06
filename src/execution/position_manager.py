"""Position management system."""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class PositionSide(Enum):
    """Position side."""

    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """Trading position."""

    symbol: str
    side: PositionSide
    entry_price: float
    size: float  # Number of units
    entry_time: datetime
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    def get_value(self) -> float:
        """Get position value."""
        return abs(self.size * self.entry_price)

    def update_unrealized_pnl(self, current_price: float) -> float:
        """Update and return unrealized PnL."""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = self.size * (current_price - self.entry_price)
        else:  # SHORT
            self.unrealized_pnl = self.size * (self.entry_price - current_price)
        return self.unrealized_pnl


class PositionManager:
    """Manage open positions and track PnL."""

    def __init__(self, initial_capital: float = 100000.0):
        """Initialize position manager."""
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}
        self.closed_positions: list[Position] = []
        self.total_realized_pnl = 0.0

        logger.info(f"Position manager initialized: ${initial_capital:,.0f}")

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        size: float,
        entry_time: Optional[datetime] = None,
    ) -> Position:
        """Open a new position.

        Args:
            symbol: Trading symbol
            side: Long or short
            entry_price: Entry price
            size: Position size (number of units)
            entry_time: Entry timestamp

        Returns:
            Position object

        Raises:
            ValueError: If position already exists or insufficient cash
        """
        if symbol in self.positions:
            raise ValueError(f"Position for {symbol} already exists")

        position_value = abs(size * entry_price)
        if position_value > self.cash:
            raise ValueError(
                f"Insufficient cash: ${self.cash:,.0f} for ${position_value:,.0f} position"
            )

        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=size,
            entry_time=entry_time or datetime.now(),
        )

        self.positions[symbol] = position
        self.cash -= position_value

        logger.info(
            f"Opened {side.value} position: {symbol} @ ${entry_price:.4f}, "
            f"size={size:.2f}, value=${position_value:,.0f}"
        )

        return position

    def close_position(
        self, symbol: str, exit_price: float, exit_time: Optional[datetime] = None
    ) -> float:
        """Close a position.

        Args:
            symbol: Trading symbol
            exit_price: Exit price
            exit_time: Exit timestamp

        Returns:
            Realized PnL

        Raises:
            ValueError: If position doesn't exist
        """
        if symbol not in self.positions:
            raise ValueError(f"No open position for {symbol}")

        position = self.positions[symbol]
        position.update_unrealized_pnl(exit_price)

        # Realize PnL
        realized_pnl = position.unrealized_pnl
        position.realized_pnl = realized_pnl
        position.unrealized_pnl = 0.0

        # Return cash
        exit_value = abs(position.size * exit_price)
        self.cash += exit_value

        # Update totals
        self.total_realized_pnl += realized_pnl
        self.cash += realized_pnl  # Add/subtract profit/loss

        # Move to closed positions
        self.closed_positions.append(position)
        del self.positions[symbol]

        logger.info(
            f"Closed {position.side.value} position: {symbol} @ ${exit_price:.4f}, "
            f"PnL=${realized_pnl:,.2f}"
        )

        return realized_pnl

    def update_positions(self, prices: dict[str, float]) -> None:
        """Update all positions with current prices.

        Args:
            prices: Dictionary of symbol -> current price
        """
        for symbol, position in self.positions.items():
            if symbol in prices:
                position.update_unrealized_pnl(prices[symbol])

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol."""
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if position exists."""
        return symbol in self.positions

    def get_total_exposure(self) -> float:
        """Get total portfolio exposure."""
        return sum(pos.get_value() for pos in self.positions.values())

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized PnL."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_portfolio_value(self) -> float:
        """Get total portfolio value (cash + positions + unrealized PnL)."""
        return self.cash + self.get_total_exposure() + self.get_total_unrealized_pnl()

    def get_num_positions(self) -> int:
        """Get number of open positions."""
        return len(self.positions)

    def get_position_summary(self) -> pd.DataFrame:
        """Get summary of all open positions."""
        if not self.positions:
            return pd.DataFrame()

        data = []
        for symbol, pos in self.positions.items():
            data.append(
                {
                    "symbol": symbol,
                    "side": pos.side.value,
                    "entry_price": pos.entry_price,
                    "size": pos.size,
                    "value": pos.get_value(),
                    "unrealized_pnl": pos.unrealized_pnl,
                    "entry_time": pos.entry_time,
                }
            )

        return pd.DataFrame(data)

    def get_stats(self) -> dict:
        """Get portfolio statistics."""
        return {
            "cash": self.cash,
            "num_positions": len(self.positions),
            "total_exposure": self.get_total_exposure(),
            "total_unrealized_pnl": self.get_total_unrealized_pnl(),
            "total_realized_pnl": self.total_realized_pnl,
            "portfolio_value": self.get_portfolio_value(),
            "num_closed_positions": len(self.closed_positions),
        }
