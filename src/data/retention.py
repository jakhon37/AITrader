"""D02-DATA — retention windows for SQLite news/calendar stores."""

from __future__ import annotations

from datetime import timedelta

from src.core.clock import VirtualClock
from src.data.store import DataStore

NEWS_RETENTION_DAYS = 30
CALENDAR_RETENTION_DAYS = 14
FUNDAMENTAL_SIGNAL_RETENTION_DAYS = 14


def purge_stale_news(store: DataStore, clock: VirtualClock) -> int:
    cutoff = clock.now() - timedelta(days=NEWS_RETENTION_DAYS)
    return store.purge_news_older_than(cutoff)


def purge_stale_calendar(store: DataStore, clock: VirtualClock) -> int:
    cutoff = clock.now() - timedelta(days=CALENDAR_RETENTION_DAYS)
    return store.purge_calendar_older_than(cutoff)