"""D03-FUNDAMENTAL — Macro regime detector.

Tracks rolling sentiment from news articles to classify the market regime as
Risk-On/Risk-Off and determine the Dollar Index (DXY) directional bias.
"""

from __future__ import annotations

from collections import deque
from typing import List

from src.core.contracts import Direction, FundamentalEventType
from src.core.logging import get_logger
from src.fundamental.models import ScoredArticle

_log = get_logger("D03-FUNDAMENTAL")


class MacroRegimeDetector:
    """Tracks historical scored articles to calculate USD and global risk regimes."""

    def __init__(self, window_size: int = 50) -> None:
        self.window_size = window_size
        self._history: deque[ScoredArticle] = deque(maxlen=window_size)

    def add_article(self, scored_article: ScoredArticle) -> None:
        """Append a newly processed article to the rolling history."""
        self._history.append(scored_article)

    def get_dxy_bias(self) -> Direction:
        """Determine whether the Dollar Index (DXY) is bias-long/short/neutral.

        Calculated as the average sentiment score of all USD/Fed/US CPI/NFP articles.
        """
        usd_keywords = ["usd", "dollar", "fed", "fomc", "powell", "treasury", "yield", "greenback"]
        scores: List[float] = []

        for sa in self._history:
            content = f"{sa.article.headline} {sa.article.body_snippet or ''}".lower()
            if any(kw in content for kw in usd_keywords):
                scores.append(sa.sentiment_score)

        if not scores:
            return Direction.NEUTRAL

        avg_score = sum(scores) / len(scores)
        if avg_score > 0.15:
            return Direction.LONG
        elif avg_score < -0.15:
            return Direction.SHORT
        return Direction.NEUTRAL

    def is_risk_on(self) -> bool:
        """Classify the global macro regime as Risk-On (True) or Risk-Off (False).

        A Risk-Off regime is triggered when average sentiment of GEOPOLITICAL
        or MARKET_RISK events falls significantly below neutral.
        """
        risk_scores: List[float] = []

        for sa in self._history:
            if sa.event_type in (FundamentalEventType.GEOPOLITICAL, FundamentalEventType.MARKET_RISK):
                risk_scores.append(sa.sentiment_score)

        if not risk_scores:
            return True  # Default to Risk-On

        avg_score = sum(risk_scores) / len(risk_scores)
        # Negative sentiment for risk/geopolitical articles implies Risk-Off.
        is_on = avg_score >= -0.10

        _log.debug("macro_regime_risk_check", avg_risk_sentiment=avg_score, risk_on=is_on)
        return is_on
