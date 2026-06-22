"""Position management system with persistence and thread safety."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.bus import Bus
from src.core.clock import now
from src.core.config import load_instruments
from src.core.contracts import (
    BusChannel,
    ExecutionMode,
    Instrument,
    OrderSide,
    PortfolioState,
    PositionSummary,
)

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages open positions, tracks portfolio state, and enforces SL/TP rules."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        bus: Optional[Bus] = None,
        execution_mode: ExecutionMode = ExecutionMode.PAPER,
        state_file: str = "data/state/positions.json",
    ):
        """Initialize position manager."""
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.bus = bus
        self.execution_mode = execution_mode
        self.state_file = state_file

        self.positions: Dict[Instrument, PositionSummary] = {}
        self.sl_tp: Dict[Instrument, Tuple[Optional[float], Optional[float]]] = {}
        self.total_realized_pnl = 0.0
        self.realized_pnl_today = 0.0
        self.peak_equity = initial_capital
        self.last_pnl_reset_date = now().date()

        self.lock = asyncio.Lock()

        # Load instrument settings for lot size
        try:
            self.instruments_config = load_instruments()
        except Exception:
            self.instruments_config = {}

        # Restore state on startup
        self.load_positions()

        logger.info(
            f"PositionManager initialized: capital=${initial_capital:,.0f}, "
            f"mode={execution_mode.value}"
        )

    def _get_lot_size(self, instrument: Instrument) -> float:
        """Get lot size for instrument, default to 100,000."""
        if instrument in self.instruments_config:
            return self.instruments_config[instrument].lot_size
        return 100000.0

    def load_positions(self) -> None:
        """Restore position state from positions.json if it exists."""
        path = Path(self.state_file)
        if not path.exists():
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)

            self.cash = data.get("cash", self.initial_capital)
            self.initial_capital = data.get("initial_capital", self.initial_capital)
            self.total_realized_pnl = data.get("total_realized_pnl", 0.0)
            self.realized_pnl_today = data.get("realized_pnl_today", 0.0)
            self.peak_equity = data.get("peak_equity", self.initial_capital)

            positions_data = data.get("positions", {})
            for key, val in positions_data.items():
                try:
                    inst = Instrument(key)
                except ValueError:
                    continue

                self.positions[inst] = PositionSummary(
                    instrument=inst,
                    side=OrderSide(val["side"]),
                    size=val["size"],
                    entry_price=val["entry_price"],
                    current_price=val["current_price"],
                    unrealized_pnl=val["unrealized_pnl"],
                    open_since=datetime.fromisoformat(val["open_since"]),
                )
                self.sl_tp[inst] = (val.get("sl"), val.get("tp"))

            logger.info(f"Loaded {len(self.positions)} persisted positions from {self.state_file}")

        except Exception as e:
            logger.error(f"Failed to load persisted positions from {self.state_file}: {e}")

    def save_positions(self) -> None:
        """Save current position state to positions.json."""
        path = Path(self.state_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            positions_data = {}
            for inst, pos in self.positions.items():
                sl, tp = self.sl_tp.get(inst, (None, None))
                positions_data[inst.value] = {
                    "side": pos.side.value,
                    "size": pos.size,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "open_since": pos.open_since.isoformat(),
                    "sl": sl,
                    "tp": tp,
                }

            data = {
                "cash": self.cash,
                "initial_capital": self.initial_capital,
                "total_realized_pnl": self.total_realized_pnl,
                "realized_pnl_today": self.realized_pnl_today,
                "peak_equity": self.peak_equity,
                "positions": positions_data,
            }

            with open(path, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save positions to {self.state_file}: {e}")

    async def open_position(
        self,
        instrument: Instrument,
        side: OrderSide,
        entry_price: float,
        size: float,  # lots
        signal_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        entry_time: Optional[datetime] = None,
    ) -> PositionSummary:
        """Open a new position.

        Raises:
            ValueError: If position already exists or insufficient cash.
        """
        async with self.lock:
            if instrument in self.positions:
                raise ValueError(f"Position for {instrument.value} already exists")

            lot_size = self._get_lot_size(instrument)
            position_value = size * lot_size * entry_price

            # Check cash (simple validation)
            if position_value > self.cash:
                raise ValueError(
                    f"Insufficient cash: have ${self.cash:,.2f}, need ${position_value:,.2f}"
                )

            self.cash -= position_value

            position = PositionSummary(
                instrument=instrument,
                side=side,
                size=size,
                entry_price=entry_price,
                current_price=entry_price,
                unrealized_pnl=0.0,
                open_since=entry_time or now(),
            )

            self.positions[instrument] = position
            self.sl_tp[instrument] = (sl, tp)

            self.save_positions()

            logger.info(
                f"Opened {side.value} position: {instrument.value} @ ${entry_price:.4f}, "
                f"size={size:.2f} lots, sl={sl}, tp={tp}"
            )

            await self._publish_portfolio_state(signal_id)
            return position

    async def close_position(
        self,
        instrument: Instrument,
        exit_price: float,
        signal_id: str,
        exit_time: Optional[datetime] = None,
    ) -> float:
        """Close an open position.

        Returns:
            Realized PnL of the trade.
        """
        async with self.lock:
            if instrument not in self.positions:
                raise ValueError(f"No active position for {instrument.value}")

            position = self.positions[instrument]
            lot_size = self._get_lot_size(instrument)

            # Calculate PnL
            if position.side == OrderSide.BUY:
                pnl = position.size * lot_size * (exit_price - position.entry_price)
            else:  # OrderSide.SELL
                pnl = position.size * lot_size * (position.entry_price - exit_price)

            # Return cash
            position_value = position.size * lot_size * exit_price
            self.cash += position_value + pnl

            # Update totals
            self.total_realized_pnl += pnl
            self._check_daily_reset()
            self.realized_pnl_today += pnl

            # Remove position
            del self.positions[instrument]
            if instrument in self.sl_tp:
                del self.sl_tp[instrument]

            self.save_positions()

            logger.info(
                f"Closed {position.side.value} position: {instrument.value} @ ${exit_price:.4f}, "
                f"PnL=${pnl:,.2f}"
            )

            await self._publish_portfolio_state(signal_id)
            return pnl

    async def update_positions(self, prices: Dict[Instrument, float], signal_id: str) -> None:
        """Update mark-to-market prices for all open positions."""
        async with self.lock:
            updated = False
            for inst, pos in self.positions.items():
                if inst in prices:
                    price = prices[inst]
                    pos.current_price = price
                    lot_size = self._get_lot_size(inst)
                    if pos.side == OrderSide.BUY:
                        pos.unrealized_pnl = pos.size * lot_size * (price - pos.entry_price)
                    else:
                        pos.unrealized_pnl = pos.size * lot_size * (pos.entry_price - price)
                    updated = True

            if updated:
                self.save_positions()
                await self._publish_portfolio_state(signal_id)

    async def check_sl_tp(
        self, prices: Dict[Instrument, float], signal_id: str
    ) -> List[Tuple[Instrument, float, str]]:
        """Check if any active positions have hit their SL or TP levels.

        Returns:
            List of tuples of (instrument, exit_price, reason)
        """
        hits = []
        async with self.lock:
            for inst, pos in self.positions.items():
                if inst not in prices:
                    continue

                price = prices[inst]
                sl, tp = self.sl_tp.get(inst, (None, None))

                # LONG check
                if pos.side == OrderSide.BUY:
                    if sl is not None and price <= sl:
                        hits.append((inst, price, "sl"))
                    elif tp is not None and price >= tp:
                        hits.append((inst, price, "tp"))
                # SHORT check
                else:
                    if sl is not None and price >= sl:
                        hits.append((inst, price, "sl"))
                    elif tp is not None and price <= tp:
                        hits.append((inst, price, "tp"))

        return hits

    def _check_daily_reset(self) -> None:
        """Reset realized_pnl_today if a new UTC day has started."""
        current_date = now().date()
        if current_date > self.last_pnl_reset_date:
            self.last_pnl_reset_date = current_date
            self.realized_pnl_today = 0.0

    async def get_portfolio_state(self, signal_id: str) -> PortfolioState:
        """Construct the current PortfolioState model."""
        async with self.lock:
            total_unrealized = sum(pos.unrealized_pnl for pos in self.positions.values())
            total_exposure = sum(pos.size * self._get_lot_size(pos.instrument) * pos.current_price for pos in self.positions.values())
            equity = self.cash + total_exposure + total_unrealized

            # Update peak equity for drawdown tracking
            if equity > self.peak_equity:
                self.peak_equity = equity

            drawdown_pct = 0.0
            if self.peak_equity > 0:
                drawdown_pct = (self.peak_equity - equity) / self.peak_equity

            # Margin used: total open position value
            margin_used = total_exposure

            free_margin = equity - margin_used
            self._check_daily_reset()

            return PortfolioState(
                signal_id=signal_id,
                timestamp=now(),
                execution_mode=self.execution_mode,
                balance=self.cash,
                equity=equity,
                margin_used=margin_used,
                free_margin=free_margin,
                open_positions=list(self.positions.values()),
                realized_pnl_today=self.realized_pnl_today,
                drawdown_pct=drawdown_pct,
            )

    async def _publish_portfolio_state(self, signal_id: str) -> None:
        """Publish updated PortfolioState to the message bus."""
        if self.bus:
            # We can't acquire the lock again, so we call internal calculation
            total_unrealized = sum(pos.unrealized_pnl for pos in self.positions.values())
            total_exposure = sum(pos.size * self._get_lot_size(pos.instrument) * pos.current_price for pos in self.positions.values())
            equity = self.cash + total_exposure + total_unrealized

            if equity > self.peak_equity:
                self.peak_equity = equity

            drawdown_pct = 0.0
            if self.peak_equity > 0:
                drawdown_pct = (self.peak_equity - equity) / self.peak_equity

            margin_used = total_exposure
            free_margin = equity - margin_used
            self._check_daily_reset()

            state = PortfolioState(
                signal_id=signal_id,
                timestamp=now(),
                execution_mode=self.execution_mode,
                balance=self.cash,
                equity=equity,
                margin_used=margin_used,
                free_margin=free_margin,
                open_positions=list(self.positions.values()),
                realized_pnl_today=self.realized_pnl_today,
                drawdown_pct=drawdown_pct,
            )

            await self.bus.publish(BusChannel.PORTFOLIO_UPDATE, state)

    def get_num_positions(self) -> int:
        """Utility method to get count of active open positions."""
        return len(self.positions)

    def get_portfolio_value(self) -> float:
        """Utility method to get current portfolio value (equity)."""
        total_unrealized = sum(pos.unrealized_pnl for pos in self.positions.values())
        return self.cash + self.get_total_exposure() + total_unrealized

    def get_total_exposure(self) -> float:
        """Utility method to get total open position values."""
        exposure = 0.0
        for inst, pos in self.positions.items():
            lot_size = self._get_lot_size(inst)
            exposure += pos.size * lot_size * pos.current_price
        return exposure

    def get_stats(self) -> dict:
        """Utility method to get stats dict."""
        equity = self.get_portfolio_value()
        return {
            "cash": self.cash,
            "num_positions": len(self.positions),
            "total_exposure": self.get_total_exposure(),
            "total_unrealized_pnl": sum(pos.unrealized_pnl for pos in self.positions.values()),
            "total_realized_pnl": self.total_realized_pnl,
            "portfolio_value": equity,
        }

    def has_position(self, instrument: Instrument) -> bool:
        """Check if position exists for instrument."""
        if isinstance(instrument, str):
            instrument = Instrument(instrument.upper())
        return instrument in self.positions
