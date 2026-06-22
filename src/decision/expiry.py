"""D05-DECISION — Signal freshness and confidence decay.

Checks signal validity limits and calculates confidence decay functions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Union

from src.core.clock import now
from src.core.contracts import FundamentalSignal, TechnicalSignal

AnySignal = Union[FundamentalSignal, TechnicalSignal]


def is_valid(signal: AnySignal, current_time: datetime | None = None) -> bool:
    """Check if the signal timestamp is within its valid_until boundary."""
    t = current_time or now()
    return t < signal.valid_until


def effective_confidence(signal: FundamentalSignal, current_time: datetime | None = None) -> float:
    """Calculate decayed confidence linearly from the signal's publication time to expiry."""
    t = current_time or now()
    if t >= signal.valid_until:
        return 0.0

    total = (signal.valid_until - signal.timestamp).total_seconds()
    if total <= 0.0:
        return 0.0

    remaining = (signal.valid_until - t).total_seconds()
    ratio = max(0.0, min(1.0, remaining / total))
    return signal.confidence * ratio
