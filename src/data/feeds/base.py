"""D02-DATA — abstract OHLCV feed protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd

from src.core.contracts import Instrument, OHLCVBar, Timeframe


class OHLCVFeed(ABC):
    """Single-source OHLCV feed interface used by scheduler and gap-fill."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable source identifier (e.g. 'dukascopy')."""

    @abstractmethod
    def fetch_range(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV rows indexed by UTC datetime."""

    def fetch_live_bars(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[OHLCVBar, Optional[OHLCVBar]]:
        """Return (last_completed_bar, active_bar_or_none)."""
        raise NotImplementedError(f"{type(self).__name__} does not support live polling")