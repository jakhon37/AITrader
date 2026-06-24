"""Event-driven backtesting engine and simulation components for D08-BACKTEST."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from src.core.bus import Bus
from src.core.contracts import (
    BusChannel,
    Instrument,
    OrderSide,
    OHLCVBar,
    TechnicalSignal,
    TradeSignal,
)
from src.technical.engine import TechnicalEngine
from src.backtest.engine.contracts import Trade

logger = logging.getLogger(__name__)


def _order_id_from_signal(signal_id: str) -> str:
    """Stable short id for pending-order UI; use 12 chars to avoid UUID prefix collisions."""
    return signal_id.replace("-", "")[:12]


def _price_decimals(instrument: Instrument) -> int:
    return 3 if "JPY" in instrument.value else 5


def _round_price(instrument: Instrument, price: Optional[float]) -> Optional[float]:
    if price is None:
        return None
    decimals = _price_decimals(instrument)
    return float(f"{float(price):.{decimals}f}")


class MockDecisionEngine:
    """Subscribes to TECHNICAL_SIGNAL and republishes as TRADE_SIGNAL for isolated event backtests."""

    def __init__(self, bus: Bus) -> None:
        self.bus = bus

    async def start(self) -> None:
        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, self.on_technical_signal)

    async def stop(self) -> None:
        await self.bus.unsubscribe(BusChannel.TECHNICAL_SIGNAL, self.on_technical_signal)

    async def on_technical_signal(self, payload: TechnicalSignal) -> None:
        """Convert TechnicalSignal to TradeSignal and publish to the bus."""
        side = None
        if payload.suggested_direction == 1:
            side = OrderSide.BUY
        elif payload.suggested_direction == -1:
            side = OrderSide.SELL

        trade_sig = TradeSignal(
            signal_id=payload.signal_id,
            instrument=payload.instrument,
            timeframe=payload.timeframe,
            suggested_side=side,
            suggested_entry=payload.price,
            suggested_sl=payload.stop_loss,
            suggested_tp=payload.take_profit,
            timestamp=payload.timestamp,
        )
        await self.bus.publish(BusChannel.TRADE_SIGNAL, trade_sig)


class MockExecutionEngine:
    """Processes TRADE_SIGNALs and updates account balance on an isolated bus.

    Each fill opens an independent position leg (keyed by signal_id). Same-direction
    orders are never merged — Replay Studio can track multiple preset limits separately.
    """

    def __init__(self, bus: Bus, initial_capital: float = 10000.0) -> None:
        self.bus = bus
        self.capital = initial_capital
        self.balance = initial_capital
        self.equity = initial_capital
        self.position_legs: dict[str, dict[str, Any]] = {}
        self.pending_orders: list[dict[str, Any]] = []
        self.trade_history: list[Trade] = []
        self.equity_history: list[tuple[datetime, float]] = []

    async def start(self) -> None:
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, self.on_trade_signal)
        await self.bus.subscribe(BusChannel.OHLCV_BAR, self.on_ohlcv_bar)

    async def stop(self) -> None:
        await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, self.on_trade_signal)
        await self.bus.unsubscribe(BusChannel.OHLCV_BAR, self.on_ohlcv_bar)

    def _legs_for_instrument(self, instrument: Instrument) -> list[tuple[str, dict[str, Any]]]:
        return [
            (leg_id, leg)
            for leg_id, leg in self.position_legs.items()
            if leg["instrument"] == instrument
        ]

    def _resolve_leg_id(self, leg_id: str) -> Optional[str]:
        """Match a leg id from the UI/API to position_legs keys.

        Accepts full signal UUID, short order_id prefix, or dashed UUID prefix.
        """
        if leg_id in self.position_legs:
            return leg_id

        normalized = leg_id.replace("-", "").lower()
        if not normalized:
            return None

        for key in self.position_legs:
            key_norm = key.replace("-", "").lower()
            if key_norm == normalized or key_norm.startswith(normalized) or normalized.startswith(key_norm):
                return key
            if _order_id_from_signal(key) == leg_id:
                return key

        return None

    async def on_ohlcv_bar(self, payload: OHLCVBar) -> None:
        instrument = payload.instrument
        close = payload.close
        high = payload.high
        low = payload.low
        timestamp = payload.timestamp

        if not hasattr(self, "latest_prices"):
            self.latest_prices = {}
        prev_close = self.latest_prices.get(instrument, close)
        self.latest_prices[instrument] = close

        # 1. Process pending limit orders
        triggered_indices: list[int] = []
        for i, order in enumerate(self.pending_orders):
            if order["instrument"] != instrument:
                continue

            entry_price = order["entry_price"]
            side = order["side"]

            triggered = False
            if low <= entry_price <= high:
                triggered = True
            elif (prev_close <= entry_price <= close) or (prev_close >= entry_price >= close):
                triggered = True

            if triggered:
                slippage_val = 0.00005
                fill_price = entry_price + (slippage_val if side == OrderSide.BUY else -slippage_val)

                leg_id = order["signal_id"]
                self._open_leg(
                    leg_id,
                    instrument,
                    side,
                    order["size"],
                    fill_price,
                    close,
                    order["sl"],
                    order["tp"],
                    timestamp,
                )
                logger.info(f"Pending limit order triggered for {instrument.value} at {fill_price}")
                triggered_indices.append(i)

        for idx in sorted(triggered_indices, reverse=True):
            self.pending_orders.pop(idx)

        # 2. Update mark-to-market and check SL/TP per leg
        for leg_id, pos in list(self.position_legs.items()):
            if pos["instrument"] != instrument:
                continue

            pos["current_price"] = close
            side = pos["side"]
            sl = pos["sl"]
            tp = pos["tp"]
            should_close = False
            exit_price = close

            if side == OrderSide.BUY:
                if sl is not None and low <= sl:
                    should_close = True
                    exit_price = sl
                elif tp is not None and high >= tp:
                    should_close = True
                    exit_price = tp
            elif side == OrderSide.SELL:
                if sl is not None and high >= sl:
                    should_close = True
                    exit_price = sl
                elif tp is not None and low <= tp:
                    should_close = True
                    exit_price = tp

            if should_close:
                await self._close_leg(leg_id, exit_price, timestamp)

        # 3. Record equity curve value
        unrealized_pnl = sum(self._calculate_pnl(leg) for leg in self.position_legs.values())
        self.equity = self.balance + unrealized_pnl
        self.equity_history.append((timestamp, self.equity))

    async def on_trade_signal(self, payload: TradeSignal) -> None:
        instrument = payload.instrument
        side = payload.suggested_side
        timestamp = payload.timestamp

        if side is None:
            if self._legs_for_instrument(instrument):
                await self._close_all_legs(instrument, payload.suggested_entry or 0.0, timestamp)
            self.pending_orders = [o for o in self.pending_orders if o["instrument"] != instrument]
            return

        is_lim = getattr(payload, "is_limit", False)
        entry_price = payload.suggested_entry or 0.0
        if entry_price == 0.0:
            return

        size_lots = payload.suggested_size if payload.suggested_size is not None else 0.1
        unit_size = size_lots * 100000.0
        if is_lim:
            self.pending_orders.append({
                "order_id": _order_id_from_signal(payload.signal_id),
                "signal_id": payload.signal_id,
                "instrument": instrument,
                "side": side,
                "size": unit_size,
                "size_lots": size_lots,
                "entry_price": _round_price(instrument, entry_price) or entry_price,
                "sl": _round_price(instrument, payload.suggested_sl),
                "tp": _round_price(instrument, payload.suggested_tp),
                "timestamp": timestamp,
            })
            logger.info(f"Pending limit order queued for {instrument.value} at {entry_price}")
            return

        slippage_val = 0.00005
        fill_price = entry_price + (slippage_val if side == OrderSide.BUY else -slippage_val)

        self._open_leg(
            payload.signal_id,
            instrument,
            side,
            unit_size,
            fill_price,
            fill_price,
            payload.suggested_sl,
            payload.suggested_tp,
            timestamp,
        )

    def modify_position_leg(
        self,
        leg_id: str,
        *,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        clear_sl: bool = False,
        clear_tp: bool = False,
    ) -> bool:
        """Update SL/TP on an open position leg."""
        resolved_id = self._resolve_leg_id(leg_id)
        if not resolved_id:
            return False
        leg = self.position_legs[resolved_id]
        instrument = leg["instrument"]
        if clear_sl:
            leg["sl"] = None
        elif stop_loss is not None:
            leg["sl"] = _round_price(instrument, stop_loss)
        if clear_tp:
            leg["tp"] = None
        elif take_profit is not None:
            leg["tp"] = _round_price(instrument, take_profit)
        return True

    async def close_position_leg(
        self,
        leg_id: str,
        exit_price: float,
        timestamp: datetime,
    ) -> bool:
        """Close a single open leg by id."""
        resolved_id = self._resolve_leg_id(leg_id)
        if not resolved_id:
            return False
        await self._close_leg(resolved_id, exit_price, timestamp)
        return True

    def get_pending_orders_serializable(self) -> list[dict[str, Any]]:
        """Return pending limit orders for API / WebSocket session state."""
        return [
            {
                "order_id": o["order_id"],
                "signal_id": o["signal_id"],
                "instrument": o["instrument"].value,
                "side": o["side"].value.lower(),
                "size_lots": o.get("size_lots", o["size"] / 100_000.0),
                "entry_price": o["entry_price"],
                "sl": o.get("sl"),
                "tp": o.get("tp"),
                "created_at": o["timestamp"].isoformat()
                if hasattr(o["timestamp"], "isoformat")
                else str(o["timestamp"]),
            }
            for o in self.pending_orders
        ]

    def cancel_pending_order(self, order_id: str) -> bool:
        """Remove a queued limit order by order_id. Returns True if found."""
        before = len(self.pending_orders)
        self.pending_orders = [o for o in self.pending_orders if o.get("order_id") != order_id]
        return len(self.pending_orders) < before

    def modify_pending_order(
        self,
        order_id: str,
        *,
        side: OrderSide,
        size_lots: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Update an existing pending limit order in place."""
        for order in self.pending_orders:
            if order.get("order_id") != order_id:
                continue
            order["side"] = side
            order["size"] = size_lots * 100_000.0
            order["size_lots"] = size_lots
            inst = order["instrument"]
            order["entry_price"] = _round_price(inst, entry_price) or entry_price
            order["sl"] = _round_price(inst, stop_loss)
            order["tp"] = _round_price(inst, take_profit)
            return True
        return False

    def _open_leg(
        self,
        leg_id: str,
        instrument: Instrument,
        side: OrderSide,
        size: float,
        entry_price: float,
        current_price: float,
        sl: Optional[float],
        tp: Optional[float],
        timestamp: datetime,
    ) -> None:
        if leg_id in self.position_legs:
            logger.warning(
                "Refusing to overwrite open leg %s for %s — each fill must use a unique signal_id",
                leg_id[:8],
                instrument.value,
            )
            return
        self.position_legs[leg_id] = {
            "instrument": instrument,
            "side": side,
            "size": size,
            "entry_price": _round_price(instrument, entry_price) or entry_price,
            "current_price": _round_price(instrument, current_price) or current_price,
            "sl": _round_price(instrument, sl),
            "tp": _round_price(instrument, tp),
            "entry_time": timestamp,
        }

    async def _close_all_legs(
        self,
        instrument: Instrument,
        exit_price: float,
        timestamp: datetime,
    ) -> None:
        for leg_id, _ in list(self._legs_for_instrument(instrument)):
            await self._close_leg(leg_id, exit_price, timestamp)

    async def _close_leg(self, leg_id: str, exit_price: float, timestamp: datetime) -> None:
        pos = self.position_legs.pop(leg_id, None)
        if not pos:
            return

        pnl = self._calculate_pnl(pos, exit_price)
        commission = pos["size"] * exit_price * 0.0001
        pnl -= commission
        self.balance += pnl

        trade = Trade(
            entry_time=pd.Timestamp(pos["entry_time"]),
            exit_time=pd.Timestamp(timestamp),
            entry_price=pos["entry_price"],
            exit_price=exit_price,
            size=pos["size"],
            side="long" if pos["side"] == OrderSide.BUY else "short",
            pnl=pnl,
            pnl_pct=pnl / self.capital,
            commission=commission,
        )
        self.trade_history.append(trade)

    def _calculate_pnl(self, pos: dict[str, Any], exit_price: Optional[float] = None) -> float:
        side = pos["side"]
        size = pos["size"]
        entry = pos["entry_price"]
        current = exit_price if exit_price is not None else pos["current_price"]

        if side == OrderSide.BUY:
            return size * (current - entry)
        return size * (entry - current)


class EventDrivenBacktestEngine:
    """Event-driven backtest engine running on the isolated bus."""

    def __init__(self, initial_capital: float = 10000.0) -> None:
        self.initial_capital = initial_capital

    async def run(
        self,
        feed: Any,  # DataFeed
        bus: Bus,
        tech_engine: TechnicalEngine,
    ) -> tuple[list[Trade], pd.Series]:
        """Run the simulation through the historical feed."""
        decision_engine = MockDecisionEngine(bus)
        exec_engine = MockExecutionEngine(bus, initial_capital=self.initial_capital)

        await tech_engine.start()
        await decision_engine.start()
        await exec_engine.start()

        async for bar in feed.run(speed=0.0):
            await bus.publish(BusChannel.OHLCV_BAR, bar)

        await tech_engine.stop()
        await decision_engine.stop()
        await exec_engine.stop()

        if exec_engine.equity_history:
            times, values = zip(*exec_engine.equity_history)
            equity_curve = pd.Series(values, index=pd.to_datetime(times))
        else:
            equity_curve = pd.Series([self.initial_capital], index=[feed.start])

        return exec_engine.trade_history, equity_curve