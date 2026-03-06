"""Simulated broker for paper trading."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(Enum):
    """Order status."""

    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class OrderSide(Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """Trading order."""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None  # For limit/stop orders
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_size: float = 0.0
    commission: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


@dataclass
class SimBrokerConfig:
    """Sim broker configuration."""

    # Slippage
    slippage_bps: float = 1.0  # 1 basis point = 0.01%
    slippage_std_bps: float = 0.5  # Randomness

    # Commissions
    commission_bps: float = 5.0  # 5 bps = 0.05%
    min_commission: float = 1.0  # $1 minimum

    # Limits
    max_order_size: float = 1_000_000  # $1M
    min_order_size: float = 100  # $100

    # Execution
    fill_rate: float = 0.99  # 99% orders fill
    execution_delay_ms: int = 100  # 100ms delay


class SimBroker:
    """Simulated broker for paper trading.

    Simulates:
    - Order execution with slippage
    - Commissions
    - Order rejection
    - Fill delays
    """

    def __init__(
        self, initial_cash: float = 100000, config: Optional[SimBrokerConfig] = None
    ):
        """Initialize sim broker."""
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.config = config or SimBrokerConfig()

        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, float] = {}  # symbol -> size (positive=long, negative=short)
        self.prices: Dict[str, float] = {}  # Latest prices

        self.total_commission = 0.0
        self.total_slippage = 0.0

        logger.info(f"SimBroker initialized: cash=${initial_cash:,.0f}")

    def update_price(self, symbol: str, price: float) -> None:
        """Update latest price for a symbol."""
        self.prices[symbol] = price

    def update_prices(self, prices: Dict[str, float]) -> None:
        """Update multiple prices."""
        self.prices.update(prices)

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
    ) -> Order:
        """Submit an order.

        Args:
            symbol: Trading symbol
            side: Buy or sell
            size: Order size in units
            order_type: Market, limit, or stop
            price: Limit/stop price (required for non-market orders)

        Returns:
            Order object
        """
        order = Order(
            order_id=str(uuid4()),
            symbol=symbol,
            side=side,
            order_type=order_type,
            size=size,
            price=price,
        )

        # Validate
        if symbol not in self.prices:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"No price data for {symbol}"
            logger.warning(f"Order rejected: {order.rejection_reason}")
            return order

        market_price = self.prices[symbol]
        order_value = size * market_price

        # Check size limits
        if order_value > self.config.max_order_size:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"Order too large: ${order_value:,.0f} > ${self.config.max_order_size:,.0f}"
            logger.warning(f"Order rejected: {order.rejection_reason}")
            return order

        if order_value < self.config.min_order_size:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"Order too small: ${order_value:,.0f} < ${self.config.min_order_size:,.0f}"
            logger.warning(f"Order rejected: {order.rejection_reason}")
            return order

        # Check cash (for buys)
        if side == OrderSide.BUY and order_value > self.cash:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"Insufficient cash: need ${order_value:,.0f}, have ${self.cash:,.0f}"
            logger.warning(f"Order rejected: {order.rejection_reason}")
            return order

        # Store order
        self.orders[order.order_id] = order

        # Execute immediately for market orders
        if order_type == OrderType.MARKET:
            self._execute_order(order)

        return order

    def _execute_order(self, order: Order) -> None:
        """Execute an order."""
        import random

        # Simulate fill rate
        if random.random() > self.config.fill_rate:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "Market conditions prevented fill"
            logger.warning(f"Order {order.order_id} not filled (random rejection)")
            return

        # Get market price
        market_price = self.prices[order.symbol]

        # Calculate slippage (in price units)
        slippage_pct = (
            self.config.slippage_bps
            + random.gauss(0, self.config.slippage_std_bps)
        ) / 10000

        # Apply slippage (worse for buyer, better for seller)
        if order.side == OrderSide.BUY:
            fill_price = market_price * (1 + abs(slippage_pct))
        else:
            fill_price = market_price * (1 - abs(slippage_pct))

        # Calculate commission
        order_value = order.size * fill_price
        commission = max(
            self.config.min_commission,
            order_value * self.config.commission_bps / 10000,
        )

        # Execute fill
        order.filled_price = fill_price
        order.filled_size = order.size
        order.commission = commission
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()

        # Update positions
        position_delta = order.size if order.side == OrderSide.BUY else -order.size
        self.positions[order.symbol] = self.positions.get(order.symbol, 0) + position_delta

        # Update cash
        if order.side == OrderSide.BUY:
            self.cash -= order_value + commission
        else:
            self.cash += order_value - commission

        # Track stats
        self.total_commission += commission
        slippage_cost = abs(fill_price - market_price) * order.size
        self.total_slippage += slippage_cost

        logger.info(
            f"Order filled: {order.side.value} {order.size} {order.symbol} "
            f"@ ${fill_price:.4f} (slippage=${slippage_cost:.2f}, commission=${commission:.2f})"
        )

    def get_position(self, symbol: str) -> float:
        """Get position size for a symbol."""
        return self.positions.get(symbol, 0.0)

    def get_all_positions(self) -> Dict[str, float]:
        """Get all positions."""
        return {k: v for k, v in self.positions.items() if v != 0}

    def get_portfolio_value(self) -> float:
        """Get total portfolio value (cash + positions)."""
        positions_value = 0.0
        for symbol, size in self.positions.items():
            if symbol in self.prices:
                positions_value += size * self.prices[symbol]

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
            "fill_rate": len(filled_orders) / num_orders if num_orders > 0 else 0,
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
        }

    def close_position(self, symbol: str) -> Optional[Order]:
        """Close a position."""
        position = self.get_position(symbol)
        if position == 0:
            logger.warning(f"No position to close for {symbol}")
            return None

        # Determine side (sell if long, buy if short)
        side = OrderSide.SELL if position > 0 else OrderSide.BUY
        size = abs(position)

        return self.submit_order(symbol, side, size, OrderType.MARKET)

    def close_all_positions(self) -> List[Order]:
        """Close all open positions."""
        orders = []
        for symbol in list(self.get_all_positions().keys()):
            order = self.close_position(symbol)
            if order:
                orders.append(order)
        return orders

    def reset(self) -> None:
        """Reset broker to initial state."""
        self.cash = self.initial_cash
        self.orders.clear()
        self.positions.clear()
        self.prices.clear()
        self.total_commission = 0.0
        self.total_slippage = 0.0
        logger.info("SimBroker reset")
