"""Technical analysis division (D04) for AITrader.

This division is responsible for calculating technical indicators, market regimes,
multi-timeframe confluence, and emitting consensus TechnicalSignals onto the bus.
"""

from __future__ import annotations

from src.technical.engine import TechnicalEngine
from src.technical.loader import TechnicalDataLoader, MultiTFDataset
from src.technical.indicators import compute_indicators
from src.technical.regime import detect_regime

__all__ = [
    "TechnicalEngine",
    "TechnicalDataLoader",
    "MultiTFDataset",
    "compute_indicators",
    "detect_regime",
]
