"""D02-DATA — DataScheduler package.

Public API (unchanged from monolithic scheduler.py):

    from src.data.scheduler import DataScheduler, OHLCVFetcher

    await scheduler.run()       # live mode
    await scheduler.tick()      # replay mode
    scheduler.stop()
"""

from src.core.candle import candle_open_time as _candle_open_time
from src.core.candle import next_candle_close as _next_candle_close
from src.data.scheduler.core import DataScheduler
from src.data.scheduler.fetcher import OHLCVFetcher, create_ohlcv_feed

__all__ = [
    "DataScheduler",
    "OHLCVFetcher",
    "create_ohlcv_feed",
    "_candle_open_time",
    "_next_candle_close",
]