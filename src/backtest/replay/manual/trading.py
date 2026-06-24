"""Trading operations mixin: manual order placement and position close.

Owns:
- place_order(side, size)     — build + publish TradeSignal, return filled Order
- close_position(instrument)  — publish neutral TradeSignal, return close Order

Future additions: partial_close(), modify_sl_tp(), bracket_order()
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from src.core.contracts import (
    BusChannel,
    Direction,
    Instrument,
    Order,
    OrderSide,
    OrderStatus,
    SignalSource,
    SignalStrength,
    TradeSignal,
)
from src.core.ids import new_signal_id
from src.backtest.engine.event_driven import _order_id_from_signal

logger = logging.getLogger(__name__)

# Default pip sizes for SL/TP calculation
_PIP_STANDARD = 0.0001
_PIP_JPY = 0.01
_DEFAULT_SL_PIPS = 50
_DEFAULT_TP_PIPS = 100


class TradingMixin:
    """Manual trade operations for ManualReplaySession.

    All attribute access (instrument, clock, bus, state, emitter, etc.)
    is satisfied by BaseReplaySession and ManualReplaySession at runtime.
    """

    async def place_order(
        self,
        side: OrderSide,
        size: float,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Order:
        """Build and publish a manual TradeSignal; return the simulated filled Order.

        SL/TP defaults to 50 / 100 pips if not provided. Custom values are used if specified.
        """
        if not self._current_bar:  # type: ignore[attr-defined]
            raise ValueError("No active bar — cannot determine entry price.")

        is_lim = entry_price is not None
        actual_entry: float = entry_price if entry_price is not None else self._current_bar.close
        sig_id = new_signal_id()

        pip = (
            _PIP_JPY
            if self.instrument == Instrument.USDJPY  # type: ignore[attr-defined]
            else _PIP_STANDARD
        )

        # If sl/tp are explicitly sent as optional values, use them. Otherwise compute defaults.
        sl = stop_loss
        tp = take_profit

        trade_sig = TradeSignal(
            signal_id=sig_id,
            instrument=self.instrument,  # type: ignore[attr-defined]
            timestamp=self.clock.now(),  # type: ignore[attr-defined]
            valid_until=self.clock.now() + timedelta(hours=1),  # type: ignore[attr-defined]
            direction=Direction.LONG if side == OrderSide.BUY else Direction.SHORT,
            confidence=1.0,
            strength=SignalStrength.STRONG,
            fundamental_weight=0.0,
            technical_weight=0.0,
            suggested_side=side,
            suggested_entry=actual_entry,
            suggested_sl=sl,
            suggested_tp=tp,
            suggested_size=size,
            narrative="Manual trader execution",
            sources=SignalSource(fundamental=None, technical=None),
            model_version="manual",
            is_limit=is_lim,
        )
        await self.bus.publish(BusChannel.TRADE_SIGNAL, trade_sig)  # type: ignore[attr-defined]
        await asyncio.sleep(0.02)  # let exec engine process

        if self._current_bar:  # type: ignore[attr-defined]
            self._update_session_state(self.clock.now())  # type: ignore[attr-defined]
            await self.emitter.emit_frame(  # type: ignore[attr-defined]
                bar=self._current_bar,  # type: ignore[attr-defined]
                technical_signal=self._last_tech_sig,  # type: ignore[attr-defined]
                trade_signal=trade_sig,
                portfolio_state=self.state.current_portfolio,  # type: ignore[attr-defined]
                session_state_dict=self.state.to_dict(),  # type: ignore[attr-defined]
            )

        return Order(
            order_id=_order_id_from_signal(sig_id),
            signal_id=sig_id,
            instrument=self.instrument,  # type: ignore[attr-defined]
            side=side,
            size=size,
            order_type="limit" if is_lim else "market",
            limit_price=entry_price if is_lim else None,
            stop_price=None,
            sl=sl,
            tp=tp,
            status=OrderStatus.PENDING if is_lim else OrderStatus.FILLED,
            created_at=self.clock.now(),  # type: ignore[attr-defined]
            filled_at=None if is_lim else self.clock.now(),  # type: ignore[attr-defined]
            filled_price=None if is_lim else actual_entry,
            execution_mode="paper",
        )

    async def _emit_current_frame(self, trade_signal: TradeSignal | None = None) -> None:
        if not self._current_bar:  # type: ignore[attr-defined]
            return
        self._update_session_state(self.clock.now())  # type: ignore[attr-defined]
        await self.emitter.emit_frame(  # type: ignore[attr-defined]
            bar=self._current_bar,  # type: ignore[attr-defined]
            technical_signal=self._last_tech_sig,  # type: ignore[attr-defined]
            trade_signal=trade_signal,
            portfolio_state=self.state.current_portfolio,  # type: ignore[attr-defined]
            session_state_dict=self.state.to_dict(),  # type: ignore[attr-defined]
        )

    async def cancel_pending_order(self, order_id: str) -> bool:
        """Cancel a queued limit order before it triggers."""
        exec_engine = self.exec_engine  # type: ignore[attr-defined]
        if not exec_engine:
            return False
        cancelled = exec_engine.cancel_pending_order(order_id)
        if cancelled:
            await self._emit_current_frame()
        return cancelled

    async def modify_pending_order(
        self,
        order_id: str,
        side: OrderSide,
        size: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Update limit price / SL / TP on a queued order."""
        exec_engine = self.exec_engine  # type: ignore[attr-defined]
        if not exec_engine:
            return False
        updated = exec_engine.modify_pending_order(
            order_id,
            side=side,
            size_lots=size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        if updated:
            await self._emit_current_frame()
        return updated

    async def modify_open_leg(
        self,
        leg_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        *,
        clear_sl: bool = False,
        clear_tp: bool = False,
    ) -> bool:
        """Update stop loss / take profit on an open position leg."""
        exec_engine = self.exec_engine  # type: ignore[attr-defined]
        if not exec_engine:
            return False
        updated = exec_engine.modify_position_leg(
            leg_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
            clear_sl=clear_sl,
            clear_tp=clear_tp,
        )
        if updated:
            await self._emit_current_frame()
        return updated

    async def close_leg(self, leg_id: str) -> Order:
        """Close a single open position leg by id."""
        exec_engine = self.exec_engine  # type: ignore[attr-defined]
        if not exec_engine:
            raise ValueError(f"No open leg: {leg_id}")

        resolved_id = exec_engine._resolve_leg_id(leg_id)
        if not resolved_id:
            raise ValueError(f"No open leg: {leg_id}")

        leg = exec_engine.position_legs[resolved_id]
        close_price = (
            self._current_bar.close if self._current_bar else leg["current_price"]  # type: ignore[attr-defined]
        )
        await exec_engine.close_position_leg(resolved_id, close_price, self.clock.now())  # type: ignore[attr-defined]
        await self._emit_current_frame()

        sig_id = new_signal_id()
        return Order(
            order_id=_order_id_from_signal(sig_id),
            signal_id=sig_id,
            instrument=leg["instrument"],
            side=OrderSide.SELL if leg["side"] == OrderSide.BUY else OrderSide.BUY,
            size=leg["size"] / 100_000.0,
            order_type="market",
            limit_price=None,
            stop_price=None,
            sl=None,
            tp=None,
            status=OrderStatus.FILLED,
            created_at=self.clock.now(),  # type: ignore[attr-defined]
            filled_at=self.clock.now(),  # type: ignore[attr-defined]
            filled_price=close_price,
            execution_mode="paper",
        )

    async def close_position(self, instrument: Instrument) -> Order:
        """Publish a neutral TradeSignal to close the position for *instrument*."""
        sig_id = new_signal_id()
        trade_sig = TradeSignal(
            signal_id=sig_id,
            instrument=instrument,
            timestamp=self.clock.now(),  # type: ignore[attr-defined]
            valid_until=self.clock.now(),  # type: ignore[attr-defined]
            direction=Direction.NEUTRAL,
            confidence=1.0,
            strength=SignalStrength.STRONG,
            fundamental_weight=0.0,
            technical_weight=0.0,
            suggested_side=None,
            suggested_entry=self._current_bar.close  # type: ignore[attr-defined]
            if self._current_bar  # type: ignore[attr-defined]
            else 0.0,
            suggested_sl=None,
            suggested_tp=None,
            suggested_size=0.0,
            narrative="Manual position closeout",
            sources=SignalSource(fundamental=None, technical=None),
            model_version="manual",
        )
        await self.bus.publish(BusChannel.TRADE_SIGNAL, trade_sig)  # type: ignore[attr-defined]
        await asyncio.sleep(0.02)  # let exec engine process

        if self._current_bar:  # type: ignore[attr-defined]
            self._update_session_state(self.clock.now())  # type: ignore[attr-defined]
            await self.emitter.emit_frame(  # type: ignore[attr-defined]
                bar=self._current_bar,  # type: ignore[attr-defined]
                technical_signal=self._last_tech_sig,  # type: ignore[attr-defined]
                trade_signal=trade_sig,
                portfolio_state=self.state.current_portfolio,  # type: ignore[attr-defined]
                session_state_dict=self.state.to_dict(),  # type: ignore[attr-defined]
            )

        close_price = (
            self._current_bar.close if self._current_bar else 0.0  # type: ignore[attr-defined]
        )
        return Order(
            order_id=_order_id_from_signal(sig_id),
            signal_id=sig_id,
            instrument=instrument,
            side=OrderSide.SELL,
            size=0.0,
            order_type="market",
            limit_price=None,
            stop_price=None,
            sl=None,
            tp=None,
            status=OrderStatus.FILLED,
            created_at=self.clock.now(),  # type: ignore[attr-defined]
            filled_at=self.clock.now(),  # type: ignore[attr-defined]
            filled_price=close_price,
            execution_mode="paper",
        )
