"""Simulated broker for paper trading using typed contracts."""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Callable, Dict, List, Optional
from uuid import uuid4

from src.core.clock import now
from src.core.contracts import (
    ExecutionMode,
    Instrument,
    Order,
    OrderEvent,
    OrderSide,
    OrderStatus,
)

logger = logging.getLogger(__name__)


class SimBrokerConfig:
    """Sim broker configuration."""

    def __init__(
        self,
        slippage_bps: float = 1.0,  # 1 basis point = 0.01%
        slippage_std_bps: float = 0.5,
        commission_bps: float = 5.0,  # 5 bps = 0.05%
        min_commission: float = 1.0,
        max_order_size: float = 1_000_000,  # in USD/base currency
        min_order_size: float = 100,
        fill_rate: float = 0.99,
        execution_delay_ms: int = 100,
    ):
        self.slippage_bps = slippage_bps
        self.slippage_std_bps = slippage_std_bps
        self.commission_bps = commission_bps
        self.min_commission = min_commission
        self.max_order_size = max_order_size
        self.min_order_size = min_order_size
        self.fill_rate = fill_rate
        self.execution_delay_ms = execution_delay_ms


class SimBroker:
    """Simulated broker for paper trading.

    Implements:
    - Order execution with slippage
    - Commissions
    - Order rejection
    - Cash/position tracking
    """

    def __init__(
        self,
        initial_cash: float = 100000.0,
        config: Optional[SimBrokerConfig] = None,
        lot_size: float = 100000.0,
    ):
        """Initialize sim broker."""
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.config = config or SimBrokerConfig()
        self.lot_size = lot_size

        self.orders: Dict[str, Order] = {}
        self.positions: Dict[Instrument, float] = {}  # instrument -> size in lots (positive=long, negative=short)
        self.prices: Dict[Instrument, float] = {}  # Latest prices

        self.total_commission = 0.0
        self.total_slippage = 0.0

        logger.info(f"SimBroker initialized: cash=${initial_cash:,.0f}")

    def update_price(self, instrument: Instrument, price: float) -> None:
        """Update latest price for an instrument."""
        # Handle string or Instrument enum
        if isinstance(instrument, str):
            instrument = Instrument(instrument.upper())
        self.prices[instrument] = price

    def update_prices(self, prices: Dict[Instrument, float]) -> None:
        """Update multiple prices."""
        for inst, price in prices.items():
            self.update_price(inst, price)

    def submit_order(self, order: Order, on_event: Callable[[OrderEvent], None]) -> None:
        """Submit an order to the broker.

        Args:
            order: The Order to be executed.
            on_event: Callback function to receive OrderEvent updates.
        """
        self.orders[order.order_id] = order

        # Notify "created" event
        created_event = OrderEvent(
            signal_id=order.signal_id,
            event_type="created",
            order=order,
            timestamp=now(),
        )
        on_event(created_event)

        # Validate order parameters
        instrument = order.instrument
        if instrument not in self.prices:
            order.status = OrderStatus.REJECTED
            rejected_event = OrderEvent(
                signal_id=order.signal_id,
                event_type="rejected",
                order=order,
                timestamp=now(),
            )
            logger.warning(f"Order rejected: No price data for {instrument}")
            on_event(rejected_event)
            return

        market_price = self.prices[instrument]
        # order.size is in lots, convert to units for cash/exposure math
        order_units = order.size * self.lot_size
        order_value = order_units * market_price

        # Check size limits
        if order_value > self.config.max_order_size:
            order.status = OrderStatus.REJECTED
            rejected_event = OrderEvent(
                signal_id=order.signal_id,
                event_type="rejected",
                order=order,
                timestamp=now(),
            )
            logger.warning(f"Order rejected: Order too large (${order_value:,.0f})")
            on_event(rejected_event)
            return

        if order_value < self.config.min_order_size:
            order.status = OrderStatus.REJECTED
            rejected_event = OrderEvent(
                signal_id=order.signal_id,
                event_type="rejected",
                order=order,
                timestamp=now(),
            )
            logger.warning(f"Order rejected: Order too small (${order_value:,.0f})")
            on_event(rejected_event)
            return

        # Check cash (for buys)
        if order.side == OrderSide.BUY and order_value > self.cash:
            order.status = OrderStatus.REJECTED
            rejected_event = OrderEvent(
                signal_id=order.signal_id,
                event_type="rejected",
                order=order,
                timestamp=now(),
            )
            logger.warning(f"Order rejected: Insufficient cash (need ${order_value:,.0f}, have ${self.cash:,.0f})")
            on_event(rejected_event)
            return

        # Execute
        self._execute_order(order, on_event)

    def submit(self, order: Order, on_event: Callable[[OrderEvent], None]) -> None:
        """Alias for submit_order to satisfy different caller preferences."""
        self.submit_order(order, on_event)

    def _execute_order(self, order: Order, on_event: Callable[[OrderEvent], None]) -> None:
        """Execute an order with simulated slippage and commission."""
        # Simulate fill rate
        if random.random() > self.config.fill_rate:
            order.status = OrderStatus.REJECTED
            rejected_event = OrderEvent(
                signal_id=order.signal_id,
                event_type="rejected",
                order=order,
                timestamp=now(),
            )
            logger.warning(f"Order {order.order_id} rejected due to execution failure simulation")
            on_event(rejected_event)
            return

        market_price = self.prices[order.instrument]

        # Calculate slippage
        slippage_pct = (
            self.config.slippage_bps
            + random.gauss(0, self.config.slippage_std_bps)
        ) / 10000.0

        # Apply slippage (worse for buyer, better for seller)
        if order.side == OrderSide.BUY:
            fill_price = market_price * (1.0 + abs(slippage_pct))
        else:
            fill_price = market_price * (1.0 - abs(slippage_pct))

        # Calculate commission
        order_units = order.size * self.lot_size
        order_value = order_units * fill_price
        commission = max(
            self.config.min_commission,
            order_value * self.config.commission_bps / 10000.0,
        )

        # Update order properties
        order.filled_price = fill_price
        order.filled_at = now()
        order.commission = commission
        order.slippage = abs(fill_price - market_price) * order_units
        order.status = OrderStatus.FILLED

        # Update positions
        position_delta = order.size if order.side == OrderSide.BUY else -order.size
        self.positions[order.instrument] = self.positions.get(order.instrument, 0.0) + position_delta

        # Update cash
        if order.side == OrderSide.BUY:
            self.cash -= order_value + commission
        else:
            self.cash += order_value - commission

        # Track stats
        self.total_commission += commission
        self.total_slippage += order.slippage

        logger.info(
            f"Order filled: {order.side.value} {order.size} lots {order.instrument.value} "
            f"@ ${fill_price:.4f} (slippage=${order.slippage:.2f}, commission=${commission:.2f})"
        )

        filled_event = OrderEvent(
            signal_id=order.signal_id,
            event_type="filled",
            order=order,
            timestamp=now(),
        )
        on_event(filled_event)

    def get_position(self, instrument: Instrument) -> float:
        """Get current position size for an instrument (positive=long, negative=short)."""
        if isinstance(instrument, str):
            instrument = Instrument(instrument.upper())
        return self.positions.get(instrument, 0.0)

    def get_all_positions(self) -> Dict[Instrument, float]:
        """Get all open positions."""
        return {k: v for k, v in self.positions.items() if v != 0.0}

    def get_portfolio_value(self, prices: Optional[Dict[Instrument, float]] = None) -> float:
        """Get total portfolio value (cash + positions value)."""
        current_prices = prices or self.prices
        positions_value = 0.0
        for inst, size in self.positions.items():
            price = current_prices.get(inst) or self.prices.get(inst, 0.0)
            if price > 0.0:
                # Value of a position in base currency (approx)
                positions_value += size * self.lot_size * price
        return self.cash + positions_value

    def get_stats(self) -> dict:
        """Get broker statistics."""
        num_orders = len(self.orders)
        filled_orders = [o for o in self.orders.values() if o.status == OrderStatus.FILLED]
        rejected_orders = [o for o in self.orders.values() if o.status == OrderStatus.REJECTED]

        return {
            "cash": self.cash,
            "portfolio_value": self.get_portfolio_value(),
            "total_pnl": self.get_portfolio_value() - self.initial_cash,
            "num_positions": len(self.get_all_positions()),
            "num_orders": num_orders,
            "num_filled": len(filled_orders),
            "num_rejected": len(rejected_orders),
            "fill_rate": len(filled_orders) / num_orders if num_orders > 0 else 0.0,
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
        }

    def reset(self) -> None:
        """Reset broker to initial state."""
        self.cash = self.initial_cash
        self.orders.clear()
        self.positions.clear()
        self.prices.clear()
        self.total_commission = 0.0
        self.total_slippage = 0.0
        logger.info("SimBroker reset")
