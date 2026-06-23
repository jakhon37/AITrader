"""D02-DATA — internal data models.

These are NOT shared contracts (they live in src.core.contracts).
They are D02-private storage / ingestion models:

  NewsArticle      — raw article as fetched and deduplicated by news_fetcher.py
  RawCalendarEvent — raw calendar row before it is promoted to an EconomicEvent

Only src.data.* modules should import from here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── NewsArticle ───────────────────────────────────────────────────────────────

class NewsArticle(BaseModel):
    """A raw news article stored in D02's SQLite news table.

    Populated by src.data.sources.news_fetcher (Phase 1b).
    Used as input to D03-FUNDAMENTAL's FinBERT scorer.

    Deduplication key: hash(headline, published_at).
    """

    article_id:   str                        # SHA-256 of (headline + published_at ISO)
    headline:     str                        # first 500 chars max
    url:          Optional[str]  = None
    source:       str            = "unknown" # "newsapi" | "reuters_rss" | "bloomberg_rss"
    published_at: datetime                   # UTC, timezone-aware
    instruments:  list[str]      = Field(default_factory=list)
                                             # e.g. ["EURUSD", "XAUUSD"] — raw strings;
                                             # validated to Instrument enum by D03
    body_snippet: Optional[str]  = None      # first 1000 chars if available
    fetched_at:   datetime = Field(
        default_factory=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
    )


# ── RawCalendarEvent ──────────────────────────────────────────────────────────

class RawCalendarEvent(BaseModel):
    """A raw economic calendar row from Forex Factory / Investing.com.

    Populated by src.data.sources.calendar (Phase 1b).
    Promoted to an EconomicEvent (contracts.py) when published to the bus.

    Lifecycle:
      1. Pre-release: stored with actual=None; EconomicEvent published 60 min before.
      2. Post-release: actual + surprise_pct filled in; EconomicEvent re-published.
    """

    event_id:       str           # "{name}_{timestamp_iso}" slug
    name:           str           # "US CPI YoY", "FOMC Rate Decision"
    timestamp:      datetime      # scheduled release time, UTC, timezone-aware
    impact:         Literal["low", "medium", "high"]
    instruments:    list[str]     = Field(default_factory=list)
                                  # affected pair strings e.g. ["EURUSD", "GBPUSD"]
    actual:         Optional[float] = None
    forecast:       Optional[float] = None
    previous:       Optional[float] = None
    surprise_pct:   Optional[float] = None  # (actual - forecast) / |forecast| post-release
    fetched_at:     datetime = Field(
        default_factory=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
    )
    pre_release_notified:  bool = False  # True once 60-min-early EconomicEvent is published
    post_release_notified: bool = False  # True once actual EconomicEvent is published
