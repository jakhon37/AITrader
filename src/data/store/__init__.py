"""D02-DATA — Unified Parquet + SQLite Data Access Layer."""

from src.data.store._base import BaseStore
from src.data.store.ohlcv import OHLCVMixin
from src.data.store.news import NewsMixin
from src.data.store.calendar import CalendarMixin

class DataStore(OHLCVMixin, NewsMixin, CalendarMixin, BaseStore):
    """Unified Parquet + SQLite data access layer for D02-DATA.

    Provides high-performance Parquet storage for OHLCV bars and
    SQLite storage for news articles and economic calendar events.
    """
    pass

__all__ = ["DataStore"]
