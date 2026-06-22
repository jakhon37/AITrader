"""D03-FUNDAMENTAL — News article filtering logic.

Filters articles based on language (English only), recency, duplicate hashes,
source quality, and instrument keyword relevance.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set

from src.core.contracts import Instrument
from src.core.logging import get_logger
from src.data.models import NewsArticle

_log = get_logger("D03-FUNDAMENTAL")


class NewsFilter:
    """Filters news articles to reduce noise and ensure relevance."""

    def __init__(
        self,
        trusted_sources: List[str] | None = None,
        recency_hours: float = 2.0,
        duplicate_window_hours: float = 6.0,
    ) -> None:
        self.trusted_sources = set(trusted_sources) if trusted_sources else None
        self.recency_hours = recency_hours
        self.duplicate_window_hours = duplicate_window_hours

        # Track duplicates: maps SHA-256 hash to published_at datetime
        self._seen_hashes: Dict[str, datetime] = {}

        # Basic keyword maps for relevance (case-insensitive checks)
        self._instrument_keywords = {
            Instrument.EURUSD: {"eur", "euro", "ecb", "lagarde", "brussels"},
            Instrument.GBPUSD: {"gbp", "pound", "sterling", "boe", "bailey", "uk", "london"},
            Instrument.USDJPY: {"jpy", "yen", "boj", "ueda", "tokyo", "japan"},
            Instrument.XAUUSD: {"xau", "gold", "bullion", "metal", "precious"},
        }
        # Shared USD/Macro keywords
        self._macro_keywords = {
            "usd", "dollar", "fed", "powell", "fomc", "cpi", "nfp", "gdp", "pmi",
            "inflation", "unemployment", "payroll", "yield", "rate decision",
            "hike", "cut", "central bank", "recession", "tariff", "sanction",
            "geopolitical", "risk-on", "risk-off", "safe-haven", "flight to safety",
        }

    def clean_old_duplicates(self, current_time: datetime) -> None:
        """Purge seen hashes that are older than duplicate_window_hours."""
        cutoff = current_time - timedelta(hours=self.duplicate_window_hours)
        self._seen_hashes = {
            h: t for h, t in self._seen_hashes.items() if t >= cutoff
        }

    def is_english(self, text: str) -> bool:
        """Check if text is English.

        Simple heuristic: check if common ASCII characters/words predominate.
        For a production-grade heuristic, we can also check basic character bounds.
        """
        # Basic check to skip heavily non-ASCII content
        try:
            text.encode("ascii")
            return True
        except UnicodeEncodeError:
            # Allow some non-ascii chars (like curly quotes, euros) but verify it's mostly english
            ascii_chars = sum(1 for c in text if ord(c) < 128)
            if len(text) > 0 and (ascii_chars / len(text)) < 0.85:
                return False
            return True

    def get_relevant_instruments(self, article: NewsArticle) -> List[Instrument]:
        """Find which instruments this article is relevant to.

        To be relevant, the headline or body_snippet must mention either the
        instrument-specific keywords OR macro keywords (which makes it relevant to
        all USD/Macro instruments if it's general USD macro news).
        """
        content = f"{article.headline} {article.body_snippet or ''}".lower()
        matched: List[Instrument] = []

        # Parse explicitly listed instruments first
        for inst_str in article.instruments:
            try:
                inst = Instrument(inst_str)
                if inst not in matched:
                    matched.append(inst)
            except ValueError:
                pass

        # Check keyword mappings
        has_macro = any(kw in content for kw in self._macro_keywords)

        for inst in Instrument:
            if inst in matched:
                continue

            # If it mentions instrument-specific keywords, or if it is a macro event
            # that affects USD pairs (all our pairs contain USD)
            keywords = self._instrument_keywords[inst]
            has_inst_kw = any(kw in content for kw in keywords)

            if has_inst_kw or (has_macro and inst in [Instrument.EURUSD, Instrument.GBPUSD, Instrument.USDJPY, Instrument.XAUUSD]):
                matched.append(inst)

        return matched

    def should_keep(self, article: NewsArticle, current_time: datetime) -> bool:
        """Validate if the article passes all filtering criteria."""
        # 1. Source Quality
        if self.trusted_sources and article.source not in self.trusted_sources:
            _log.debug("filter_rejected_source", headline=article.headline, source=article.source)
            return False

        # 2. Recency
        if article.published_at < current_time - timedelta(hours=self.recency_hours):
            _log.debug(
                "filter_rejected_recency",
                headline=article.headline,
                published_at=article.published_at.isoformat(),
            )
            return False

        # 3. English language only
        if not self.is_english(article.headline):
            _log.debug("filter_rejected_language", headline=article.headline)
            return False

        # 4. Relevance
        relevant_instruments = self.get_relevant_instruments(article)
        if not relevant_instruments:
            _log.debug("filter_rejected_relevance", headline=article.headline)
            return False

        # 5. Duplicate checks
        self.clean_old_duplicates(current_time)
        # Hash headline and source
        slug = f"{article.headline.strip()}::{article.source.strip()}"
        hasher = hashlib.sha256(slug.encode("utf-8"))
        h = hasher.hexdigest()

        if h in self._seen_hashes:
            _log.debug("filter_rejected_duplicate", headline=article.headline)
            return False

        # Mark as seen
        self._seen_hashes[h] = article.published_at
        return True
