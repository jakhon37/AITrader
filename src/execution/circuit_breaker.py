"""Circuit breaker for automatic trading halt."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from src.core.clock import now
from src.core.contracts import EconomicEvent, Instrument

logger = logging.getLogger(__name__)


class HaltReason(Enum):
    """Reason for trading halt."""

    MANUAL = "manual"
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    RAPID_LOSSES = "rapid_losses"
    EXECUTION_ERROR = "execution_error"
    DATA_ANOMALY = "data_anomaly"
    RISK_VIOLATION = "risk_violation"
    NEWS_HALT = "news_halt"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    # Loss-based triggers
    max_daily_loss: float = 0.03  # 3% daily loss triggers halt
    max_consecutive_losses: int = 3  # 3 losses in a row triggers halt (per spec)
    rapid_loss_threshold: float = 0.02  # 2% loss in short period
    rapid_loss_period: int = 300  # 5 minutes

    # Execution-based triggers
    max_consecutive_errors: int = 3  # 3 errors in a row triggers halt

    # Auto-resume settings
    auto_resume_enabled: bool = False
    auto_resume_delay: int = 3600  # 1 hour


@dataclass
class CircuitBreakerState:
    """Current circuit breaker state."""

    is_halted: bool
    halt_reason: Optional[HaltReason]
    halt_time: Optional[datetime]
    consecutive_losses: int
    consecutive_errors: int
    last_loss_times: List[datetime]
    resume_time: Optional[datetime]


class CircuitBreaker:
    """Circuit breaker for automatic trading halt.

    Monitors trading activity and automatically halts trading
    when dangerous conditions are detected.
    """

    def __init__(
        self,
        config: Optional[CircuitBreakerConfig] = None,
        initial_capital: float = 100000.0,
    ):
        """Initialize circuit breaker."""
        self.config = config or CircuitBreakerConfig()
        self.initial_capital = initial_capital
        self.is_halted = False
        self.halt_reason: Optional[HaltReason] = None
        self.halt_time: Optional[datetime] = None
        self.resume_time: Optional[datetime] = None

        # Track consecutive events
        self.consecutive_losses = 0
        self.consecutive_errors = 0
        self.last_loss_times: List[datetime] = []

        # Track daily stats
        self.daily_reset_time = now()
        self.daily_start_value = initial_capital

        # Track instrument-specific news halts: Instrument -> list of (start_time, end_time)
        self._news_halts: Dict[Instrument, List[tuple[datetime, datetime]]] = {}

        logger.info("Circuit breaker initialized")

    def check_should_halt(self, portfolio_value: float) -> tuple[bool, Optional[HaltReason]]:
        """Check if trading should be halted.

        Args:
            portfolio_value: Current portfolio value

        Returns:
            Tuple of (should_halt, reason)
        """
        current_time = now()

        # Check auto-resume first
        if self.is_halted and self.resume_time and current_time >= self.resume_time:
            self.resume("Auto-resume timer expired")

        # Already halted
        if self.is_halted:
            return True, self.halt_reason

        # Check daily reset
        if current_time.date() > self.daily_reset_time.date():
            self.daily_reset_time = current_time
            self.daily_start_value = portfolio_value

        daily_loss = (portfolio_value - self.daily_start_value) / self.daily_start_value
        if daily_loss < -self.config.max_daily_loss:
            return True, HaltReason.MAX_DAILY_LOSS

        # Check consecutive losses
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            return True, HaltReason.RAPID_LOSSES

        # Check rapid losses (multiple losses in short period)
        if len(self.last_loss_times) >= 3:
            time_span = (self.last_loss_times[-1] - self.last_loss_times[0]).total_seconds()
            if time_span < self.config.rapid_loss_period:
                return True, HaltReason.RAPID_LOSSES

        # Check consecutive errors
        if self.consecutive_errors >= self.config.max_consecutive_errors:
            return True, HaltReason.EXECUTION_ERROR

        return False, None

    def record_trade_outcome(self, is_win: bool) -> None:
        """Record trade outcome.

        Args:
            is_win: Whether the trade was profitable
        """
        current_time = now()
        if is_win:
            self.consecutive_losses = 0
            self.last_loss_times = []
        else:
            self.consecutive_losses += 1
            self.last_loss_times.append(current_time)

            # Keep only recent losses
            cutoff_time = current_time - timedelta(seconds=self.config.rapid_loss_period)
            self.last_loss_times = [t for t in self.last_loss_times if t > cutoff_time]

    def record_error(self) -> None:
        """Record execution error."""
        self.consecutive_errors += 1
        logger.warning(f"Execution error recorded: {self.consecutive_errors} consecutive")

    def record_success(self) -> None:
        """Record successful execution."""
        self.consecutive_errors = 0

    def halt(self, reason: HaltReason, message: Optional[str] = None) -> None:
        """Halt trading.

        Args:
            reason: Reason for halt
            message: Optional additional message
        """
        if self.is_halted:
            logger.warning("Trading already halted")
            return

        current_time = now()
        self.is_halted = True
        self.halt_reason = reason
        self.halt_time = current_time

        # Set auto-resume if enabled, or if it's consecutive losses (RAPID_LOSSES)
        if reason == HaltReason.RAPID_LOSSES:
            self.resume_time = current_time + timedelta(hours=2)
            logger.warning(f"🛑 TRADING HALTED due to consecutive losses (auto-resume in 2 hours)")
        elif self.config.auto_resume_enabled:
            self.resume_time = current_time + timedelta(
                seconds=self.config.auto_resume_delay
            )
            logger.warning(
                f"🛑 TRADING HALTED: {reason.value} - {message or ''} "
                f"(auto-resume at {self.resume_time})"
            )
        else:
            self.resume_time = None
            logger.warning(f"🛑 TRADING HALTED: {reason.value} - {message or ''}")

    def resume(self, message: Optional[str] = None) -> None:
        """Resume trading.

        Args:
            message: Optional message
        """
        if not self.is_halted:
            logger.warning("Trading is not halted")
            return

        logger.info(f"✅ TRADING RESUMED: {message or 'Manual resume'}")

        self.is_halted = False
        self.halt_reason = None
        self.halt_time = None
        self.resume_time = None

        # Reset counters
        self.consecutive_losses = 0
        self.consecutive_errors = 0
        self.last_loss_times = []

    def handle_economic_event(self, event: EconomicEvent, news_halt_minutes: int) -> None:
        """Record a scheduled high-impact news event window to restrict trading on affected pairs."""
        if event.impact != "high":
            return

        # Start and end boundaries of the news halt
        start = event.timestamp - timedelta(minutes=news_halt_minutes)
        end = event.timestamp + timedelta(minutes=news_halt_minutes)

        for inst in event.affected_pairs:
            if inst not in self._news_halts:
                self._news_halts[inst] = []
            self._news_halts[inst].append((start, end))

        logger.info(
            "circuit_breaker_news_halt_scheduled",
            event=event.name,
            start=start.isoformat(),
            end=end.isoformat(),
            pairs=[p.value for p in event.affected_pairs],
        )

    def clean_old_halts(self, current_time: datetime) -> None:
        """Purge past news halt intervals to conserve memory."""
        for inst in list(self._news_halts.keys()):
            self._news_halts[inst] = [
                (start, end) for start, end in self._news_halts[inst] if end >= current_time
            ]

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return CircuitBreakerState(
            is_halted=self.is_halted,
            halt_reason=self.halt_reason,
            halt_time=self.halt_time,
            consecutive_losses=self.consecutive_losses,
            consecutive_errors=self.consecutive_errors,
            last_loss_times=self.last_loss_times.copy(),
            resume_time=self.resume_time,
        )

    def is_trading_allowed(self, instrument: Optional[Instrument] = None, current_time: Optional[datetime] = None) -> bool:
        """Check if trading is currently allowed, accounting for manual halts and active news halts."""
        if self.is_halted:
            return False

        if instrument is not None:
            t = current_time or now()
            self.clean_old_halts(t)

            windows = self._news_halts.get(instrument, [])
            for start, end in windows:
                if start <= t <= end:
                    logger.warning(f"Trading blocked on {instrument.value} due to active news halt.")
                    return False

        return True
