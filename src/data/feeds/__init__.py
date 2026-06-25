"""D02-DATA — market data feed adapters."""

from src.data.feeds.base import OHLCVFeed
from src.data.feeds.dukascopy import DukascopyFeed

__all__ = ["OHLCVFeed", "DukascopyFeed"]