"""Execution engine coordinating all trading operations."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from execution.audit_log import AuditLog, EventType
from execution.circuit_breaker import CircuitBreaker, HaltReason
from execution.position_manager import PositionManager, PositionSide
from execution.risk_manager import RiskManager, RiskViolation

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Execution engine configuration."""

    initial_capital: float = 100000.0
    enable_risk_checks: bool = True
    enable_circuit_breaker: bool = True
    enable_audit_log: bool = True
    dry_run: bool = False  # If True, no actual trades


class ExecutionEngine:
    """Central execution engine.

    Coordinates:
    - Risk management
    - Circuit breaker
    - Position management
    - Audit logging
    """

    def __init__(self, config: Optional[ExecutionConfig] = None):
        """Initialize execution engine."""
        self.config = config or ExecutionConfig()

        # Initialize components
        self.risk_manager = RiskManager(initial_capital=self.config.initial_capital)
        self.circuit_breaker = CircuitBreaker(initial_capital=self.config.initial_capital)
        self.position_manager = PositionManager(initial_capital=self.config.initial_capital)
        self.audit_log = AuditLog() if self.config.enable_audit_log else None

        self.is_running = False

        if self.audit_log:
            self.audit_log.log(
                EventType.SYSTEM_START,
                f"Execution engine initialized (dry_run={self.config.dry_run})",
                {"initial_capital": self.config.initial_capital},
            )

        logger.info(
            f"Execution engine initialized: capital=${self.config.initial_capital:,.0f}, "
            f"dry_run={self.config.dry_run}"
        )

    def start(self) -> None:
        """Start execution engine."""
        if self.is_running:
            logger.warning("Engine already running")
            return

        self.is_running = True
        logger.info("🚀 Execution engine started")

        if self.audit_log:
            self.audit_log.log(EventType.SYSTEM_START, "Engine started", {})

    def stop(self) -> None:
        """Stop execution engine."""
        if not self.is_running:
            logger.warning("Engine not running")
            return

        self.is_running = False
        logger.info("🛑 Execution engine stopped")

        if self.audit_log:
            self.audit_log.log(EventType.SYSTEM_STOP, "Engine stopped", {})

    def execute_signal(
        self, symbol: str, signal: int, price: float, size: float
    ) -> Optional[str]:
        """Execute a trading signal.

        Args:
            symbol: Trading symbol
            signal: 1 (long), -1 (short), 0 (close)
            price: Current price
            size: Position size

        Returns:
            Action taken ("opened", "closed", "skipped", "halted")
        """
        # Check if trading is allowed
        if not self.is_running:
            logger.warning("Engine not running, signal ignored")
            return "skipped"

        # Check circuit breaker
        if self.config.enable_circuit_breaker:
            portfolio_value = self.position_manager.get_portfolio_value()
            should_halt, reason = self.circuit_breaker.check_should_halt(portfolio_value)

            if should_halt:
                self.circuit_breaker.halt(reason, f"Auto-halt on {reason.value}")
                if self.audit_log:
                    self.audit_log.log_circuit_breaker("halt", reason.value)
                logger.warning(f"🛑 Trading halted: {reason.value}")
                return "halted"

        # Log signal
        if self.audit_log:
            self.audit_log.log_signal(symbol, signal)

        # Execute based on signal
        if signal == 0:
            # Close position if exists
            if self.position_manager.has_position(symbol):
                return self._close_position(symbol, price)
            else:
                logger.debug(f"No position to close for {symbol}")
                return "skipped"

        elif signal in [1, -1]:
            # Check if position already exists
            if self.position_manager.has_position(symbol):
                logger.debug(f"Position already exists for {symbol}")
                return "skipped"

            # Open new position
            side = PositionSide.LONG if signal == 1 else PositionSide.SHORT
            return self._open_position(symbol, side, price, size)

        else:
            logger.warning(f"Invalid signal: {signal}")
            return "skipped"

    def _open_position(
        self, symbol: str, side: PositionSide, price: float, size: float
    ) -> str:
        """Open a new position with risk checks."""
        position_value = abs(size * price)

        # Risk checks
        if self.config.enable_risk_checks:
            try:
                portfolio_value = self.position_manager.get_portfolio_value()
                total_exposure = self.position_manager.get_total_exposure()
                num_positions = self.position_manager.get_num_positions()

                self.risk_manager.check_all_limits(
                    portfolio_value, total_exposure, num_positions, position_value
                )

            except RiskViolation as e:
                logger.warning(f"Risk violation: {e}")
                if self.audit_log:
                    self.audit_log.log_risk_violation("position_size", str(e))
                return "skipped"

        # Execute (or simulate in dry run)
        if self.config.dry_run:
            logger.info(
                f"DRY RUN: Would open {side.value} {symbol} @ ${price:.4f}, size={size}"
            )
            return "opened"

        try:
            position = self.position_manager.open_position(
                symbol, side, price, size, datetime.now()
            )

            if self.audit_log:
                self.audit_log.log_position_open(
                    symbol, side.value, price, size, value=position_value
                )

            return "opened"

        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            if self.audit_log:
                self.audit_log.log_error("position_open_failed", str(e), symbol=symbol)

            self.circuit_breaker.record_error()
            return "skipped"

    def _close_position(self, symbol: str, price: float) -> str:
        """Close an existing position."""
        if self.config.dry_run:
            logger.info(f"DRY RUN: Would close {symbol} @ ${price:.4f}")
            return "closed"

        try:
            pnl = self.position_manager.close_position(symbol, price, datetime.now())

            if self.audit_log:
                self.audit_log.log_position_close(symbol, price, pnl)

            # Record outcome for circuit breaker
            self.circuit_breaker.record_trade_outcome(is_win=(pnl > 0))
            self.circuit_breaker.record_success()

            return "closed"

        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            if self.audit_log:
                self.audit_log.log_error("position_close_failed", str(e), symbol=symbol)

            self.circuit_breaker.record_error()
            return "skipped"

    def get_status(self) -> dict:
        """Get engine status."""
        portfolio_value = self.position_manager.get_portfolio_value()
        risk_metrics = self.risk_manager.get_metrics(
            portfolio_value,
            self.position_manager.get_total_exposure(),
            self.position_manager.get_num_positions(),
        )

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
                "daily_pnl": risk_metrics.daily_pnl,
                "drawdown": risk_metrics.drawdown_from_peak,
                "leverage": risk_metrics.leverage,
            },
        }

    def manual_halt(self, reason: str) -> None:
        """Manually halt trading."""
        self.circuit_breaker.halt(HaltReason.MANUAL, reason)
        if self.audit_log:
            self.audit_log.log_circuit_breaker("halt", reason)
        logger.warning(f"🛑 Manual halt: {reason}")

    def manual_resume(self, reason: str) -> None:
        """Manually resume trading."""
        self.circuit_breaker.resume(reason)
        if self.audit_log:
            self.audit_log.log_circuit_breaker("resume", reason)
        logger.info(f"✅ Manual resume: {reason}")
