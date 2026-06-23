"""Backtesting engine with vectorized calculations and event-driven simulation.

Simulates trading strategies on historical data with realistic
transaction costs and slippage modeling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel

from src.core.bus import Bus
from src.core.contracts import (
    BusChannel,
    Direction,
    Instrument,
    Timeframe,
    OHLCVBar,
    TechnicalSignal,
    TradeSignal,
    SignalSource,
    SignalStrength,
    OrderSide,
    OrderStatus,
    ExecutionMode,
    Order,
)
from src.core.clock import ReplayClock
from src.core.config import InstrumentConfig
from src.technical.engine import TechnicalEngine
from src.technical.loader import timeframe_to_timedelta

logger = logging.getLogger(__name__)


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


class BacktestEngine:
    """Vectorized backtesting engine.

    Supports:
    - Long and short positions
    - Transaction costs and slippage
    - Position sizing
    - Realistic trade execution
    """

    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        """Initialize backtesting engine.

        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()
        logger.info(f"Initialized backtest engine with config: {self.config}")

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.Series,
        position_sizes: Optional[pd.Series] = None,
    ) -> BacktestResult:
        """Run backtest on historical data.

        Args:
            data: DataFrame with OHLCV data (must have 'close' column)
            signals: Series with trading signals (1=long, -1=short, 0=neutral)
            position_sizes: Optional position sizes (default: config.position_size_pct)

        Returns:
            BacktestResult with trades, equity curve, and performance metrics
        """
        logger.info(f"Starting backtest on {len(data)} bars")

        # Validate inputs
        if "close" not in data.columns:
            raise ValueError("Data must contain 'close' column")

        if len(signals) != len(data):
            raise ValueError("Signals must match data length")

        # Align signals with data
        signals = signals.reindex(data.index, fill_value=0)

        # Use default position sizes if not provided
        if position_sizes is None:
            position_sizes = pd.Series(
                self.config.position_size_pct, index=data.index
            )
        else:
            position_sizes = position_sizes.reindex(
                data.index, fill_value=self.config.position_size_pct
            )

        # Generate trades
        trades = self._generate_trades(data, signals, position_sizes)

        # Calculate equity curve
        equity_curve, positions, returns = self._calculate_equity_curve(
            data, trades
        )

        # Create result
        result = BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            positions=positions,
            returns=returns,
            config=self.config,
            metadata={
                "total_bars": len(data),
                "total_trades": len(trades),
                "start_date": data.index[0],
                "end_date": data.index[-1],
            },
        )

        logger.info(f"Backtest complete: {len(trades)} trades executed")
        return result

    def _generate_trades(
        self,
        data: pd.DataFrame,
        signals: pd.Series,
        position_sizes: pd.Series,
    ) -> list[Trade]:
        """Generate trades from signals."""
        trades = []
        current_position = None
        last_trade_idx = -np.inf

        prices = data["close"].values
        times = data.index

        for i, (time, signal) in enumerate(zip(times, signals)):
            # Check if we should enforce min trade interval
            if i - last_trade_idx < self.config.min_trade_interval:
                continue

            # Exit current position if signal changed or goes to neutral
            if current_position is not None:
                should_exit = (
                    signal == 0  # Signal goes neutral
                    or signal != current_position["side"]  # Signal reverses
                )

                if should_exit:
                    # Exit at current price with slippage
                    exit_price = self._apply_slippage(
                        prices[i], current_position["side"], is_entry=False
                    )

                    # Calculate PnL
                    if current_position["side"] == 1:  # Long
                        pnl = current_position["size"] * (
                            exit_price - current_position["entry_price"]
                        )
                    else:  # Short
                        pnl = current_position["size"] * (
                            current_position["entry_price"] - exit_price
                        )

                    # Subtract exit commission
                    commission = (
                        abs(current_position["size"] * exit_price)
                        * self.config.commission_pct
                    )
                    pnl -= commission

                    # Create trade record
                    trade = Trade(
                        entry_time=current_position["entry_time"],
                        exit_time=time,
                        entry_price=current_position["entry_price"],
                        exit_price=exit_price,
                        size=current_position["size"],
                        side="long" if current_position["side"] == 1 else "short",
                        pnl=pnl,
                        pnl_pct=pnl / self.config.initial_capital,
                        commission=commission,
                    )
                    trades.append(trade)
                    current_position = None
                    last_trade_idx = i

            # Enter new position if signal is non-zero and we have no position
            if current_position is None and signal in [1, -1]:
                # Calculate trade size based on capital
                capital = self.config.initial_capital
                if len(trades) > 0:
                    capital += sum(t.pnl for t in trades)

                # Limit position size
                trade_size_pct = position_sizes.iloc[i]
                position_value = capital * trade_size_pct
                entry_price = self._apply_slippage(prices[i], signal, is_entry=True)
                size = position_value / entry_price

                # Apply entry commission
                commission = position_value * self.config.commission_pct

                current_position = {
                    "entry_time": time,
                    "entry_price": entry_price,
                    "size": size,
                    "side": signal,
                    "commission": commission,
                }
                last_trade_idx = i

        # Force-close any open position on the last bar
        if current_position is not None:
            exit_price = self._apply_slippage(prices[-1], current_position["side"], is_entry=False)
            
            if current_position["side"] == 1:
                pnl = current_position["size"] * (exit_price - current_position["entry_price"])
            else:
                pnl = current_position["size"] * (current_position["entry_price"] - exit_price)

            commission = abs(current_position["size"] * exit_price) * self.config.commission_pct
            pnl -= commission

            trade = Trade(
                entry_time=current_position["entry_time"],
                exit_time=times[-1],
                entry_price=current_position["entry_price"],
                exit_price=exit_price,
                size=current_position["size"],
                side="long" if current_position["side"] == 1 else "short",
                pnl=pnl,
                pnl_pct=pnl / self.config.initial_capital,
                commission=commission,
            )
            trades.append(trade)

        return trades

    def _apply_slippage(
        self, price: float, side: int, is_entry: bool
    ) -> float:
        """Apply slippage to price."""
        # For entry: buy price goes up (+), sell price goes down (-)
        # For exit: buy close (sell order) goes down (-), sell close (buy order) goes up (+)
        multiplier = 1.0
        if is_entry:
            multiplier = 1.0 if side == 1 else -1.0
        else:
            multiplier = -1.0 if side == 1 else 1.0

        return price * (1.0 + multiplier * self.config.slippage_pct)

    def _calculate_equity_curve(
        self, data: pd.DataFrame, trades: list[Trade]
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate equity curve, position states, and returns."""
        capital = self.config.initial_capital
        equity = pd.Series(capital, index=data.index)
        positions = pd.Series(0, index=data.index)

        # Vectorized calculation of position weights
        for trade in trades:
            positions.loc[trade.entry_time : trade.exit_time] = (
                1 if trade.side == "long" else -1
            )

        # Step-by-step equity simulation
        for i in range(1, len(data)):
            current_time = data.index[i]
            prev_time = data.index[i - 1]

            # Calculate returns for active positions
            pos = positions.loc[prev_time]
            if pos != 0:
                ret = (data["close"].iloc[i] / data["close"].iloc[i - 1]) - 1.0
                capital_change = capital * pos * ret
                capital += capital_change

            # Update commissions and realized PnL at trade exit
            for trade in trades:
                if trade.exit_time == current_time:
                    # Commission was already subtracted in PnL, but we need to adjust
                    # the capital curve for any deviations from pure close returns
                    pass

            equity.iloc[i] = capital

        returns = equity.pct_change().fillna(0.0)
        return equity, positions, returns


# ── Event-Driven Simulation Components ────────────────────────────────────────

class MockDecisionEngine:
    """Listen to TECHNICAL_SIGNAL and fuse into TRADE_SIGNAL for isolated backtest."""

    def __init__(self, bus: Bus) -> None:
        self.bus = bus

    async def start(self) -> None:
        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, self.on_technical_signal)

    async def stop(self) -> None:
        await self.bus.unsubscribe(BusChannel.TECHNICAL_SIGNAL, self.on_technical_signal)

    async def on_technical_signal(self, payload: TechnicalSignal) -> None:
        if payload.direction == Direction.LONG:
            side = OrderSide.BUY
        elif payload.direction == Direction.SHORT:
            side = OrderSide.SELL
        else:
            side = None

        trade_sig = TradeSignal(
            signal_id=payload.signal_id,
            instrument=payload.instrument,
            timestamp=payload.timestamp,
            valid_until=payload.valid_until,
            direction=payload.direction,
            confidence=payload.confidence,
            strength=payload.strength,
            fundamental_weight=0.0,
            technical_weight=1.0,
            suggested_side=side,
            suggested_entry=payload.entry_price,
            suggested_sl=payload.stop_loss,
            suggested_tp=payload.take_profit,
            suggested_size=0.1,  # 0.1 lot default size
            narrative="Fused mock trade signal from technical analysis",
            sources=SignalSource(fundamental=None, technical=payload),
            model_version="mock_v1",
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
