"""Risk management system."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Risk limit configuration."""

    max_position_size: float = 100000.0  # Max value per position
    max_positions: int = 5  # Max concurrent positions
    max_portfolio_exposure: float = 0.8  # Max 80% of capital
    max_daily_loss: float = 0.02  # Max 2% daily loss
    max_weekly_loss: float = 0.05  # Max 5% weekly loss
    max_drawdown: float = 0.15  # Max 15% drawdown
    max_leverage: float = 1.0  # No leverage


@dataclass
class RiskMetrics:
    """Current risk metrics."""

    portfolio_value: float
    total_exposure: float
    num_positions: int
    daily_pnl: float
    weekly_pnl: float
    drawdown_from_peak: float
    peak_portfolio_value: float
    leverage: float


class RiskViolation(Exception):
    """Raised when a risk limit is violated."""

    pass


class RiskManager:
    """Risk management system."""

    def __init__(self, limits: Optional[RiskLimits] = None, initial_capital: float = 100000.0):
        """Initialize risk manager."""
        self.limits = limits or RiskLimits()
        self.initial_capital = initial_capital
        self.peak_value = initial_capital
        self.daily_reset_time = datetime.now()
        self.weekly_reset_time = datetime.now()
        self.daily_start_value = initial_capital
        self.weekly_start_value = initial_capital
        logger.info(f"Risk manager initialized: ${initial_capital:,.0f}")

    def check_position_size(self, position_value: float) -> None:
        """Check if position size is within limits."""
        if abs(position_value) > self.limits.max_position_size:
            raise RiskViolation(
                f"Position ${abs(position_value):,.0f} exceeds "
                f"${self.limits.max_position_size:,.0f}"
            )

    def check_max_positions(self, num_positions: int) -> None:
        """Check if number of positions is within limits."""
        if num_positions >= self.limits.max_positions:
            raise RiskViolation(f"Max positions {self.limits.max_positions} reached")

    def check_daily_loss(self, current_value: float) -> None:
        """Check if daily loss exceeds limit."""
        now = datetime.now()
        if now.date() > self.daily_reset_time.date():
            self.daily_reset_time = now
            self.daily_start_value = current_value

        daily_return = (current_value - self.daily_start_value) / self.daily_start_value
        if daily_return < -self.limits.max_daily_loss:
            raise RiskViolation(f"Daily loss {abs(daily_return):.2%} exceeds limit")

    def check_weekly_loss(self, current_value: float) -> None:
        """Check if weekly loss exceeds limit."""
        now = datetime.now()
        if (now - self.weekly_reset_time).days >= 7:
            self.weekly_reset_time = now
            self.weekly_start_value = current_value

        weekly_return = (current_value - self.weekly_start_value) / self.weekly_start_value
        if weekly_return < -self.limits.max_weekly_loss:
            raise RiskViolation(f"Weekly loss {abs(weekly_return):.2%} exceeds limit")

    def check_drawdown(self, current_value: float) -> None:
        """Check if drawdown exceeds limit."""
        if current_value > self.peak_value:
            self.peak_value = current_value

        drawdown = (current_value - self.peak_value) / self.peak_value
        if drawdown < -self.limits.max_drawdown:
            raise RiskViolation(f"Drawdown {abs(drawdown):.2%} exceeds limit")

    def check_all_limits(
        self,
        portfolio_value: float,
        total_exposure: float,
        num_positions: int,
        new_position_value: Optional[float] = None,
    ) -> None:
        """Check all risk limits."""
        self.check_daily_loss(portfolio_value)
        self.check_weekly_loss(portfolio_value)
        self.check_drawdown(portfolio_value)

        if new_position_value is not None:
            self.check_position_size(new_position_value)
            self.check_max_positions(num_positions + 1)

    def get_metrics(
        self, portfolio_value: float, total_exposure: float, num_positions: int
    ) -> RiskMetrics:
        """Get current risk metrics."""
        daily_pnl = portfolio_value - self.daily_start_value
        weekly_pnl = portfolio_value - self.weekly_start_value
        drawdown = (portfolio_value - self.peak_value) / self.peak_value
        leverage = total_exposure / portfolio_value if portfolio_value > 0 else 0

        return RiskMetrics(
            portfolio_value=portfolio_value,
            total_exposure=total_exposure,
            num_positions=num_positions,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            drawdown_from_peak=drawdown,
            peak_portfolio_value=self.peak_value,
            leverage=leverage,
        )
