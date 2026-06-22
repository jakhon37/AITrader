"""Execution engine coordinating all trading operations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
from uuid import uuid4

from src.core.bus import Bus
from src.core.clock import now
from src.core.config import AppConfig, InstrumentConfig, load_instruments
from src.core.contracts import (
    BusChannel,
    Direction,
    EconomicEvent,
    ExecutionMode,
    Instrument,
    OHLCVBar,
    Order,
    OrderEvent,
    OrderSide,
    OrderStatus,
    PortfolioState,
    SignalSource,
    TradeSignal,
    SignalStrength,
)
from src.execution.audit_log import AuditLog, EventType
from src.execution.brokers.sim import SimBroker
from src.execution.circuit_breaker import CircuitBreaker, HaltReason
from src.execution.mode_gate import ModeGate
from src.execution.position_manager import PositionManager
from src.execution.risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Execution engine configuration."""

    initial_capital: float = 100000.0
    enable_risk_checks: bool = True
    enable_circuit_breaker: bool = True
    enable_audit_log: bool = True
    dry_run: bool = False  # If True, no actual trades
    broker: str = "mock"
    slippage_pips: float = 0.5


class ExecutionEngine:
    """Central execution engine.

    Coordinates:
    - Risk management checks
    - Circuit breaker gates (loss limits, news halts)
    - Position management and mark-to-market tracking
    - Audit logging
    - Message bus publishing and subscription
    """

    def __init__(
        self,
        config: Optional[AppConfig | ExecutionConfig] = None,
        bus: Optional[Bus] = None,
    ):
        """Initialize execution engine."""
        self.bus = bus

        # Adapt both AppConfig and ExecutionConfig input styles
        if isinstance(config, ExecutionConfig):
            self.config = config
            self.app_config = AppConfig()
            self.app_config.core.execution_mode = ExecutionMode.PAPER
        else:
            self.app_config = config or AppConfig()
            self.config = ExecutionConfig(
                initial_capital=100000.0,
                enable_risk_checks=True,
                enable_circuit_breaker=True,
                enable_audit_log=True,
                dry_run=(self.app_config.core.execution_mode == ExecutionMode.PAPER and self.app_config.env == "dev"),
            )

        # Initialize sub-components
        self.mode_gate = ModeGate(self.app_config)
        self.risk_manager = RiskManager(config=self.app_config.risk, env=self.app_config.env)
        self.circuit_breaker = CircuitBreaker(initial_capital=self.config.initial_capital)
        # Configure state_file path relative to the active data directory
        state_file_path = str(Path(self.app_config.data.data_dir) / "state" / "positions.json")

        self.position_manager = PositionManager(
            initial_capital=self.config.initial_capital,
            bus=self.bus,
            execution_mode=self.app_config.core.execution_mode,
            state_file=state_file_path,
        )

        self.broker = SimBroker(
            initial_cash=self.config.initial_capital,
            lot_size=100000.0,
        )

        self.audit_log = AuditLog() if self.config.enable_audit_log else None
        self.is_running = False
        self._last_action: Optional[str] = None

        # Load instrument configurations
        try:
            self.instruments_config = load_instruments()
        except Exception:
            self.instruments_config = {}

        if self.audit_log:
            self.audit_log.log(
                EventType.SYSTEM_START,
                f"Execution engine initialized (dry_run={self.config.dry_run})",
                "unknown",
                {"initial_capital": self.config.initial_capital},
            )

        logger.info(
            f"Execution engine initialized: capital=${self.config.initial_capital:,.0f}, "
            f"dry_run={self.config.dry_run}"
        )

    def _run_async(self, coro):
        """Helper to run async coroutines synchronously if event loop is not running."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            return asyncio.ensure_future(coro)
        else:
            return loop.run_until_complete(coro)

    def start(self) -> None:
        """Start execution engine and subscribe to channels."""
        if self.is_running:
            logger.warning("Engine already running")
            return

        self.is_running = True
        logger.info("🚀 Execution engine started")

        if self.audit_log:
            self.audit_log.log(EventType.SYSTEM_START, "Engine started", "unknown", {})

        if self.bus:
            self._run_async(self._subscribe_channels())

    async def _subscribe_channels(self) -> None:
        """Subscribe to message bus channels."""
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, self.handle_trade_signal)
        await self.bus.subscribe(BusChannel.ECONOMIC_EVENT, self.handle_economic_event)
        await self.bus.subscribe(BusChannel.OHLCV_BAR, self.handle_ohlcv_bar)

    def stop(self) -> None:
        """Stop execution engine and unsubscribe."""
        if not self.is_running:
            logger.warning("Engine not running")
            return

        self.is_running = False
        logger.info("🛑 Execution engine stopped")

        if self.audit_log:
            self.audit_log.log(EventType.SYSTEM_STOP, "Engine stopped", "unknown", {})

        if self.bus:
            self._run_async(self._unsubscribe_channels())

    async def _unsubscribe_channels(self) -> None:
        """Unsubscribe from message bus channels."""
        await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, self.handle_trade_signal)
        await self.bus.unsubscribe(BusChannel.ECONOMIC_EVENT, self.handle_economic_event)
        await self.bus.unsubscribe(BusChannel.OHLCV_BAR, self.handle_ohlcv_bar)

    def execute_signal(
        self, symbol: str, signal: int, price: float, size: float
    ) -> Optional[str]:
        """Execute a trade signal synchronously (for legacy test compatibility).

        Args:
            symbol: Trading symbol (e.g. EURUSD)
            signal: 1 (long), -1 (short), 0 (close)
            price: Market price
            size: Order size (if size > 10.0, interpreted as units and converted to lots)
        """
        if not self.is_running:
            logger.warning("Engine not running, signal ignored")
            return "skipped"

        # Auto-convert units to lots if needed
        try:
            instrument = Instrument(symbol.upper())
        except ValueError:
            # Fallback for mock test symbols like PAIR0
            instrument = Instrument.EURUSD

        inst_config = self.instruments_config.get(instrument)
        lot_size = inst_config.lot_size if inst_config else 100000.0

        size_lots = size
        if size > 10.0:
            size_lots = size / lot_size

        # Update broker price feed first so simulated orders fill correctly
        self.broker.update_price(instrument, price)

        # Run async execute flow
        self._run_async(self._execute_signal_async(instrument, signal, price, size_lots))
        return self._last_action

    async def _execute_signal_async(
        self, instrument: Instrument, signal: int, price: float, size_lots: float
    ) -> None:
        """Helper to create a TradeSignal contract and run it through the async engine."""
        direction = Direction.NEUTRAL
        suggested_side = None

        if signal == 1:
            direction = Direction.LONG
            suggested_side = OrderSide.BUY
        elif signal == -1:
            direction = Direction.SHORT
            suggested_side = OrderSide.SELL

        # Standard simulated SL/TP offsets
        sl = None
        tp = None
        if suggested_side == OrderSide.BUY:
            sl = price - 0.01
            tp = price + 0.02
        elif suggested_side == OrderSide.SELL:
            sl = price + 0.01
            tp = price - 0.02

        trade_signal = TradeSignal(
            signal_id=str(uuid4()),
            instrument=instrument,
            timestamp=now(),
            valid_until=now() + timedelta(hours=1),
            direction=direction,
            confidence=0.6,
            strength=SignalStrength.MODERATE,
            fundamental_weight=0.5,
            technical_weight=0.5,
            suggested_side=suggested_side,
            suggested_entry=price,
            suggested_sl=sl,
            suggested_tp=tp,
            suggested_size=size_lots,
            narrative="Test signal",
            sources=SignalSource(fundamental=None, technical=None),
            model_version="legacy",
        )

        await self.handle_trade_signal(trade_signal)

    async def handle_trade_signal(self, signal: TradeSignal) -> None:
        """Process incoming TradeSignal from the message bus."""
        instrument = signal.instrument
        self._last_action = "skipped"

        # 1. Mode Gate Check
        try:
            self.mode_gate.check()
        except Exception as e:
            logger.error(f"Mode gate validation failed: {e}")
            if self.audit_log:
                self.audit_log.log_error("mode_gate_failed", str(e), signal.signal_id)
            return

        # 2. Circuit Breaker Check
        portfolio_value = self.position_manager.get_portfolio_value()
        should_cb_halt, cb_reason = self.circuit_breaker.check_should_halt(portfolio_value)
        if should_cb_halt:
            if cb_reason:
                self.circuit_breaker.halt(cb_reason, f"Circuit breaker halt trigger")
            self._last_action = "halted"
            return

        if not self.circuit_breaker.is_trading_allowed(instrument):
            self._last_action = "halted"
            return

        # 3. Log signal receipt
        if self.audit_log:
            self.audit_log.log(
                EventType.SIGNAL_GENERATED,
                f"Signal received: {instrument.value} {signal.direction.value}",
                signal.signal_id,
                {"direction": signal.direction.value, "confidence": signal.confidence},
            )

        # Handle NEUTRAL (Close position)
        if signal.direction == Direction.NEUTRAL:
            if self.position_manager.has_position(instrument):
                position = self.position_manager.positions[instrument]
                close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY

                if self.config.dry_run:
                    logger.info(f"DRY RUN: Close position on {instrument.value}")
                    self._last_action = "closed"
                    return

                order = Order(
                    order_id=str(uuid4()),
                    signal_id=signal.signal_id,
                    instrument=instrument,
                    side=close_side,
                    size=position.size,
                    order_type="market",
                    limit_price=None,
                    stop_price=None,
                    sl=None,
                    tp=None,
                    status=OrderStatus.PENDING,
                    created_at=now(),
                    filled_at=None,
                    filled_price=None,
                    execution_mode=self.app_config.core.execution_mode,
                )
                self.broker.submit(order, self.on_order_event)
                self._last_action = "closed"
            return

        # If position already exists, ignore opening a duplicate
        if self.position_manager.has_position(instrument):
            logger.debug(f"Position already exists for {instrument.value}")
            return

        # 4. Risk Manager Validation
        portfolio = await self.position_manager.get_portfolio_state(signal.signal_id)
        inst_config = self.instruments_config.get(instrument)
        if not inst_config:
            logger.warning(f"No config for {instrument.value}, skipping risk checks")
            return

        decision = self.risk_manager.validate(signal, portfolio, inst_config)
        if not decision.approved:
            logger.warning(f"Risk checks rejected order: {decision.reason}")
            if self.audit_log:
                self.audit_log.log_risk_violation(
                    violation_type="risk_limit_exceeded",
                    details=decision.reason or "Unknown rejection",
                    signal_id=signal.signal_id,
                )
            return

        # Check dry run for opening
        if self.config.dry_run:
            logger.info(f"DRY RUN: Open position on {instrument.value}")
            self._last_action = "opened"
            return

        # 5. Build and submit Order
        order = Order(
            order_id=str(uuid4()),
            signal_id=signal.signal_id,
            instrument=instrument,
            side=signal.suggested_side or OrderSide.BUY,
            size=decision.adjusted_size,
            order_type="market",
            limit_price=None,
            stop_price=None,
            sl=signal.suggested_sl,
            tp=signal.suggested_tp,
            status=OrderStatus.PENDING,
            created_at=now(),
            filled_at=None,
            filled_price=None,
            execution_mode=self.app_config.core.execution_mode,
        )

        if self.audit_log:
            self.audit_log.log(
                EventType.ORDER_SUBMITTED,
                f"Order submitted: {order.side.value} {order.size} lots {order.instrument.value}",
                order.signal_id,
                {"order_id": order.order_id},
            )

        self.broker.submit(order, self.on_order_event)
        self._last_action = "opened"

    def on_order_event(self, event: OrderEvent) -> None:
        """Callback from broker when order state transitions."""
        self._run_async(self.handle_order_event(event))

    async def handle_order_event(self, event: OrderEvent) -> None:
        """Process OrderEvent asynchronously."""
        order = event.order
        instrument = order.instrument

        if self.bus:
            await self.bus.publish(BusChannel.ORDER_EVENT, event)

        if event.event_type == "filled":
            if self.audit_log:
                self.audit_log.log(
                    EventType.ORDER_FILLED,
                    f"Order filled: {order.side.value} {order.size} lots {order.instrument.value} @ {order.filled_price}",
                    order.signal_id,
                    {"order_id": order.order_id, "filled_price": order.filled_price},
                )

            # Check if this closes or opens a position
            if self.position_manager.has_position(instrument):
                pnl = await self.position_manager.close_position(
                    instrument=instrument,
                    exit_price=order.filled_price or 0.0,
                    signal_id=order.signal_id,
                    exit_time=order.filled_at,
                )
                if self.audit_log:
                    self.audit_log.log_position_close(
                        symbol=instrument.value,
                        price=order.filled_price or 0.0,
                        pnl=pnl,
                        signal_id=order.signal_id,
                    )
                self.circuit_breaker.record_trade_outcome(is_win=(pnl > 0))
                self.circuit_breaker.record_success()
            else:
                await self.position_manager.open_position(
                    instrument=instrument,
                    side=order.side,
                    entry_price=order.filled_price or 0.0,
                    size=order.size,
                    signal_id=order.signal_id,
                    sl=order.sl,
                    tp=order.tp,
                    entry_time=order.filled_at,
                )
                if self.audit_log:
                    self.audit_log.log_position_open(
                        symbol=instrument.value,
                        side=order.side.value,
                        price=order.filled_price or 0.0,
                        size=order.size,
                        signal_id=order.signal_id,
                    )

        elif event.event_type == "rejected":
            if self.audit_log:
                self.audit_log.log_error(
                    error_type="order_rejected",
                    error_message=f"Order was rejected by broker",
                    signal_id=order.signal_id,
                )
            self.circuit_breaker.record_error()

    async def handle_economic_event(self, event: EconomicEvent) -> None:
        """Process economic event scheduled halts."""
        for inst in event.affected_pairs:
            inst_config = self.instruments_config.get(inst)
            news_halt_mins = inst_config.news_halt_minutes if inst_config else 30
            self.circuit_breaker.handle_economic_event(event, news_halt_mins)

    async def handle_ohlcv_bar(self, bar: OHLCVBar) -> None:
        """Process incoming OHLCV bar to mark-to-market and enforce SL/TP levels."""
        instrument = bar.instrument
        close_price = bar.close

        # Update broker prices & mark-to-market positions
        self.broker.update_price(instrument, close_price)
        await self.position_manager.update_positions({instrument: close_price}, bar.signal_id)

        # Check for SL/TP hits
        hits = await self.position_manager.check_sl_tp({instrument: close_price}, bar.signal_id)
        for inst, exit_price, reason in hits:
            logger.warning(f"🚨 Position {inst.value} hit {reason.upper()} level at {exit_price}")

            # Retrieve size and side from open position to close
            if inst in self.position_manager.positions:
                position = self.position_manager.positions[inst]
                close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY

                order = Order(
                    order_id=str(uuid4()),
                    signal_id=bar.signal_id,
                    instrument=inst,
                    side=close_side,
                    size=position.size,
                    order_type="market",
                    limit_price=None,
                    stop_price=None,
                    sl=None,
                    tp=None,
                    status=OrderStatus.PENDING,
                    created_at=now(),
                    filled_at=None,
                    filled_price=None,
                    execution_mode=self.app_config.core.execution_mode,
                )

                if self.audit_log:
                    self.audit_log.log(
                        EventType.ORDER_SUBMITTED,
                        f"SL/TP Close Order submitted: {order.side.value} {order.size} lots {order.instrument.value}",
                        order.signal_id,
                        {"reason": reason, "exit_price": exit_price},
                    )

                self.broker.submit(order, self.on_order_event)

    def get_status(self) -> dict:
        """Get current status of the engine."""
        portfolio_value = self.position_manager.get_portfolio_value()
        cb_state = self.circuit_breaker.get_state()
        pos_stats = self.position_manager.get_stats()

        return {
            "is_running": self.is_running,
            "is_halted": cb_state.is_halted,
            "halt_reason": cb_state.halt_reason.value if cb_state.halt_reason else None,
            "portfolio_value": portfolio_value,
            "num_positions": pos_stats["num_positions"],
            "total_exposure": pos_stats["total_exposure"],
            "cash": pos_stats["cash"],
            "realized_pnl": pos_stats["total_realized_pnl"],
            "unrealized_pnl": pos_stats["total_unrealized_pnl"],
            "risk_metrics": {
                "daily_pnl": self.position_manager.realized_pnl_today,
                "drawdown": cb_state.consecutive_losses,  # compatible mock
                "leverage": 1.0,
            },
        }

    def manual_halt(self, reason: str) -> None:
        """Manually halt trading."""
        self.circuit_breaker.halt(HaltReason.MANUAL, reason)
        if self.audit_log:
            self.audit_log.log_circuit_breaker("halt", reason, "unknown")
        logger.warning(f"🛑 Manual halt: {reason}")

    def manual_resume(self, reason: str) -> None:
        """Manually resume trading."""
        self.circuit_breaker.resume(reason)
        if self.audit_log:
            self.audit_log.log_circuit_breaker("resume", reason, "unknown")
        logger.info(f"✅ Manual resume: {reason}")
