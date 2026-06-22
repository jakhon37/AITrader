"""D05-DECISION — Signal fusion combiners.

Combines fundamental and technical inputs to produce a unified directional decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.core.config import InstrumentConfig
from src.core.contracts import Direction, FundamentalSignal, SignalStrength, TechnicalSignal
from src.decision.expiry import effective_confidence, is_valid


@dataclass
class FusionOutput:
    """Dataclass holding combined signal values."""

    direction: Direction
    confidence: float
    strength: SignalStrength
    fundamental_weight: float
    technical_weight: float


def direction_sign(direction: Direction) -> float:
    """Map direction to signed scalar value (+1.0 for LONG, -1.0 for SHORT, 0.0 otherwise)."""
    if direction == Direction.LONG:
        return 1.0
    elif direction == Direction.SHORT:
        return -1.0
    return 0.0


def combine(
    f: FundamentalSignal | None,
    t: TechnicalSignal,
    inst_config: InstrumentConfig,
    current_time: datetime,
) -> FusionOutput:
    """Perform weighted linear combination of technical and fundamental signals."""
    t_sign = direction_sign(t.direction)
    t_score = t.confidence * t_sign

    # Check if fundamental signal exists and is valid
    if f is not None and is_valid(f, current_time):
        f_conf = effective_confidence(f, current_time)
        f_sign = direction_sign(f.direction)
        f_score = f_conf * f_sign

        f_weight = inst_config.fundamental_weight
        t_weight = inst_config.technical_weight

        # Fused score
        raw = f_weight * f_score + t_weight * t_score
    else:
        # If fundamental is missing/expired, technical gets full weight (1.0)
        f_weight = 0.0
        t_weight = 1.0
        raw = t_score

    # Determine final direction using +/-0.15 thresholds
    if raw > 0.15:
        direction = Direction.LONG
    elif raw < -0.15:
        direction = Direction.SHORT
    else:
        direction = Direction.NEUTRAL

    confidence = min(abs(raw), 1.0)

    # Determine strength
    if confidence > 0.7:
        strength = SignalStrength.STRONG
    elif confidence >= 0.4:
        strength = SignalStrength.MODERATE
    else:
        strength = SignalStrength.WEAK

    return FusionOutput(
        direction=direction,
        confidence=confidence,
        strength=strength,
        fundamental_weight=f_weight,
        technical_weight=t_weight,
    )
