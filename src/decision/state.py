"""D05-DECISION — Signal state tracking.

Stores the latest fundamental and technical signals per instrument.
"""

from __future__ import annotations

from typing import Dict, Optional

from src.core.contracts import Direction, FundamentalSignal, Instrument, TechnicalSignal


class SignalState:
    """In-memory cache for tracking rolling instrument signal histories."""

    def __init__(self) -> None:
        # Latest fundamental signal per instrument
        self.fundamental: Dict[Instrument, FundamentalSignal] = {}

        # Latest technical signal per instrument
        self.technical: Dict[Instrument, TechnicalSignal] = {}

        # Track if the prior generated TradeSignal for an instrument was directional (LONG or SHORT)
        # Used to identify when we transition from a active trade stance to a neutral stance,
        # which requires publishing a neutral cancellation signal.
        self.prior_was_directional: Dict[Instrument, bool] = {}

        # Last published trade direction per instrument (dedupe repeated neutral updates)
        self.last_published_direction: Dict[Instrument, Direction] = {}

        # Technical signal id last fused into a trade publish (per instrument)
        self.last_fused_technical_id: Dict[Instrument, str] = {}
