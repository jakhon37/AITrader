"""D03-FUNDAMENTAL — Signal decay calculations.

Computes how long a fundamental signal remains valid based on its
FundamentalEventType and the per-instrument configuration.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.core.config import InstrumentConfig
from src.core.contracts import FundamentalEventType


def get_decay_hours(
    event_type: FundamentalEventType,
    instrument_config: InstrumentConfig,
) -> float:
    """Extract decay hours from InstrumentConfig for a given FundamentalEventType."""
    decay_cfg = instrument_config.signal_decay

    if event_type == FundamentalEventType.CENTRAL_BANK:
        return decay_cfg.central_bank
    elif event_type == FundamentalEventType.ECONOMIC_DATA:
        return decay_cfg.economic_data
    elif event_type == FundamentalEventType.GEOPOLITICAL:
        return decay_cfg.geopolitical
    elif event_type == FundamentalEventType.MARKET_RISK:
        return decay_cfg.market_risk
    elif event_type == FundamentalEventType.TECHNICAL_CONF:
        return decay_cfg.technical_conf

    return 1.0  # Safe default fallback


def compute_valid_until(
    event_type: FundamentalEventType,
    instrument_config: InstrumentConfig,
    base_time: datetime,
) -> datetime:
    """Calculate the expiration timestamp (valid_until) for a fundamental signal."""
    hours = get_decay_hours(event_type, instrument_config)
    return base_time + timedelta(hours=hours)
