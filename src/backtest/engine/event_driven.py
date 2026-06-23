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
    """Processes TRADE_SIGNALs and updates account balance on an isolated bus."""

    def __init__(self, bus: Bus, initial_capital: float = 10000.0) -> None:
        self.bus = bus
        self.capital = initial_capital
        self.balance = initial_capital
        self.equity = initial_capital
        self.positions: dict[Instrument, dict[str, Any]] = {}
        self.trade_history: list[Trade] = []
        self.equity_history: list[tuple[datetime, float]] = []

    async def start(self) -> None:
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, self.on_trade_signal)
        await self.bus.subscribe(BusChannel.OHLCV_BAR, self.on_ohlcv_bar)

    async def stop(self) -> None:
        await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, self.on_trade_signal)
        await self.bus.unsubscribe(BusChannel.OHLCV_BAR, self.on_ohlcv_bar)

    async def on_ohlcv_bar(self, payload: OHLCVBar) -> None:
        instrument = payload.instrument
        close = payload.close
        timestamp = payload.timestamp

        # 1. Update current price and check SL/TP for open position
        if instrument in self.positions:
            pos = self.positions[instrument]
            pos["current_price"] = close

            side = pos["side"]
            sl = pos["sl"]
            tp = pos["tp"]
            should_close = False
            exit_price = close

            if side == OrderSide.BUY:
                if sl is not None and close <= sl:
                    should_close = True
                    exit_price = sl
                elif tp is not None and close >= tp:
                    should_close = True
                    exit_price = tp
            elif side == OrderSide.SELL:
                if sl is not None and close >= sl:
                    should_close = True
                    exit_price = sl
                elif tp is not None and close <= tp:
                    should_close = True
                    exit_price = tp

            if should_close:
                await self._close_position(instrument, exit_price, timestamp)

        # 2. Record daily/hourly equity curve value
        unrealized_pnl = 0.0
        for pos in self.positions.values():
            unrealized_pnl += self._calculate_pnl(pos)

        self.equity = self.balance + unrealized_pnl
        self.equity_history.append((timestamp, self.equity))

    async def on_trade_signal(self, payload: TradeSignal) -> None:
        instrument = payload.instrument
        side = payload.suggested_side
        timestamp = payload.timestamp

        # Close existing position if signal is Neutral
        if side is None:
            if instrument in self.positions:
                await self._close_position(instrument, payload.suggested_entry or 0.0, timestamp)
            return

        # Close opposite position if exists
        if instrument in self.positions:
            existing = self.positions[instrument]
            if existing["side"] != side:
                await self._close_position(instrument, payload.suggested_entry or 0.0, timestamp)
            else:
                # Already holding this direction
                return

        # Open new position (default: 0.1 lots = 10,000 units for Forex)
        entry_price = payload.suggested_entry or 0.0
        if entry_price == 0.0:
            return

        # Apply slippage (0.5 pip = 0.00005)
        slippage_val = 0.00005
        fill_price = entry_price + (slippage_val if side == OrderSide.BUY else -slippage_val)

        # Standard Forex lot sizes
        unit_size = 10000.0  # 0.1 lot

        self.positions[instrument] = {
            "side": side,
            "size": unit_size,
            "entry_price": fill_price,
            "current_price": fill_price,
            "sl": payload.suggested_sl,
            "tp": payload.suggested_tp,
            "entry_time": timestamp,
        }

    async def _close_position(self, instrument: Instrument, exit_price: float, timestamp: datetime) -> None:
        pos = self.positions.pop(instrument, None)
        if not pos:
            return

        pnl = self._calculate_pnl(pos, exit_price)

        # Subtract commission (0.01% of notional)
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
        else:
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

        # Start components
        await tech_engine.start()
        await decision_engine.start()
        await exec_engine.start()

        # Iterate over bars
        async for bar in feed.run(speed=0.0):
            await bus.publish(BusChannel.OHLCV_BAR, bar)

        # Stop components
        await tech_engine.stop()
        await decision_engine.stop()
        await exec_engine.stop()

        # Convert equity history to Series
        if exec_engine.equity_history:
            times, values = zip(*exec_engine.equity_history)
            equity_curve = pd.Series(values, index=pd.to_datetime(times))
        else:
            equity_curve = pd.Series([self.initial_capital], index=[feed.start])

        return exec_engine.trade_history, equity_curve
