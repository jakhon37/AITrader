"""D03-FUNDAMENTAL — Event classification logic.

Maps news headlines to FundamentalEventType and determines sentiment direction,
confidence, and signal strength.
"""

from __future__ import annotations

from src.core.contracts import Direction, FundamentalEventType, SignalStrength
from src.data.models import NewsArticle


class EventClassifier:
    """Classifies news articles and maps sentiment scores to trade direction/strength."""

    def __init__(self, neutral_threshold: float = 0.15) -> None:
        self.neutral_threshold = neutral_threshold

        # Event type classification keyword mappings
        self._mappings = [
            (
                FundamentalEventType.CENTRAL_BANK,
                ["rate decision", "hike", "cut", "fomc", "fed ", "boe ", "boj ", "ecb ", "interest rate", "powell", "lagarde", "ueda"],
            ),
            (
                FundamentalEventType.ECONOMIC_DATA,
                ["cpi", "nfp", "gdp", "pmi", "inflation", "unemployment", "payroll", "retail sales"],
            ),
            (
                FundamentalEventType.GEOPOLITICAL,
                ["war", "sanction", "tariff", "geopolitical", "conflict", "election", "brexit"],
            ),
            (
                FundamentalEventType.MARKET_RISK,
                ["risk-off", "risk-on", "flight to safety", "safe-haven", "panic", "rout", "liquidity crisis"],
            ),
        ]

    def classify(self, headline: str) -> FundamentalEventType:
        """Classify a headline into a FundamentalEventType based on keyword matches."""
        lower_headline = headline.lower()

        for event_type, keywords in self._mappings:
            if any(kw in lower_headline for kw in keywords):
                return event_type

        return FundamentalEventType.TECHNICAL_CONF

    def determine_direction(self, score: float) -> Direction:
        """Map sentiment score to Direction (long/short/neutral)."""
        if score > self.neutral_threshold:
            return Direction.LONG
        elif score < -self.neutral_threshold:
            return Direction.SHORT
        return Direction.NEUTRAL

    def determine_strength(self, confidence: float) -> SignalStrength:
        """Map confidence (0.0 to 1.0) to SignalStrength."""
        if confidence > 0.7:
            return SignalStrength.STRONG
        elif confidence >= 0.4:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK
