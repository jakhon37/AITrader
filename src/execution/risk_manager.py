"""Risk management system implementing pre-trade validations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Set

from src.core.clock import now
from src.core.config import InstrumentConfig, RiskConfig
from src.core.contracts import Instrument, PortfolioState, TradeSignal
from src.core.session import is_fx_session_open

logger = logging.getLogger(__name__)


class RiskViolation(Exception):
    """Raised when a risk limit is violated."""

    pass


@dataclass
class RiskDecision:
    """Decision made by the risk manager."""

    approved: bool
    reason: Optional[str]
    adjusted_size: float


class RiskManager:
    """Risk management system enforcing pre-trade checks."""

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        min_confidence: float = 0.4,
        max_positions: int = 3,
        correlation_reduction_factor: float = 0.5,
        env: str = "dev",
    ):
        """Initialize risk manager.

        Args:
            config: Risk configuration
            min_confidence: Minimum required confidence threshold (default 0.4)
            max_positions: Maximum concurrent open positions (default 3)
            correlation_reduction_factor: Fraction to reduce size by if correlated pair is open (default 0.5)
            env: Running environment name (e.g. 'dev', 'staging', 'prod')
        """
        self.config = config or RiskConfig()
        self.min_confidence = min_confidence
        self.max_positions = max_positions
        self.correlation_reduction_factor = correlation_reduction_factor
        self.env = env

        # Standard static correlation groups (e.g. EURUSD and GBPUSD tend to be highly correlated)
        self.correlated_groups: list[Set[Instrument]] = [
            {Instrument.EURUSD, Instrument.GBPUSD}
        ]

        logger.info(
            f"RiskManager initialized (min_confidence={self.min_confidence}, "
            f"max_positions={self.max_positions}, env={self.env})"
        )

    def is_market_open(self, dt: datetime) -> bool:
        """Check if Forex/Gold markets are open (UTC session from instruments.yaml)."""
        if self.env != "prod":
            return True

        return is_fx_session_open(dt)

    def validate(
        self,
        signal: TradeSignal,
        portfolio: PortfolioState,
        inst_config: InstrumentConfig,
    ) -> RiskDecision:
        """Validate pre-trade risk constraints.

        Args:
            signal: TradeSignal to validate.
            portfolio: Current PortfolioState.
            inst_config: The configuration block for this instrument.

        Returns:
            RiskDecision containing approval status and adjusted size.
        """
        current_time = now()
        instrument = signal.instrument
        suggested_size = signal.suggested_size or 0.01

        # 1. Signal Age: TradeSignal.valid_until > clock.now()
        if signal.valid_until <= current_time:
            return RiskDecision(
                approved=False,
                reason=f"Signal expired at {signal.valid_until.isoformat()}",
                adjusted_size=0.0,
            )

        # 2. Min confidence: signal.confidence >= risk.min_confidence (default 0.4)
        if signal.confidence < self.min_confidence:
            return RiskDecision(
                approved=False,
                reason=f"Signal confidence {signal.confidence:.2f} below minimum {self.min_confidence}",
                adjusted_size=0.0,
            )

        # 3. Session hours: instrument active market hours only
        if not self.is_market_open(current_time):
            return RiskDecision(
                approved=False,
                reason="Market is closed (weekend halt)",
                adjusted_size=0.0,
            )

        # 4. Max concurrent open positions (default 3 globally)
        open_positions = portfolio.open_positions
        # Check if we already have a position in this instrument
        already_open = any(pos.instrument == instrument for pos in open_positions)
        if not already_open and len(open_positions) >= self.max_positions:
            return RiskDecision(
                approved=False,
                reason=f"Maximum concurrent open positions ({self.max_positions}) reached",
                adjusted_size=0.0,
            )

        # 5. Max position size vs instrument_config.max_position_lots
        adjusted_size = min(suggested_size, inst_config.max_position_lots)

        # 6. Correlation check: reduce size if correlated instrument already open
        # Find if any other open position is correlated with this signal's instrument
        for group in self.correlated_groups:
            if instrument in group:
                for pos in open_positions:
                    if pos.instrument != instrument and pos.instrument in group:
                        # Reduce size due to correlation
                        old_size = adjusted_size
                        adjusted_size *= self.correlation_reduction_factor
                        adjusted_size = round(max(0.01, adjusted_size), 2)
                        logger.info(
                            f"Risk correlation sizing adjustment for {instrument.value}: "
                            f"reduced {old_size} -> {adjusted_size} lots due to open {pos.instrument.value} position"
                        )
                        break

        # 7. Free margin > order_margin * 1.5 (safety factor)
        # Assuming 1:1 leverage default for margin (or full position value)
        entry_price = signal.suggested_entry or 1.0
        order_margin = adjusted_size * inst_config.lot_size * entry_price
        required_margin = order_margin * 1.5

        if portfolio.free_margin < required_margin:
            return RiskDecision(
                approved=False,
                reason=f"Insufficient free margin: need ${required_margin:,.2f}, have ${portfolio.free_margin:,.2f}",
                adjusted_size=0.0,
            )

        return RiskDecision(
            approved=True,
            reason=None,
            adjusted_size=adjusted_size,
        )
