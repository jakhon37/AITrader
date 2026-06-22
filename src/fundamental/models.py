"""Internal data models for D03-FUNDAMENTAL.

These models are private to this division and not exposed on the shared bus.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from src.core.contracts import Instrument, FundamentalEventType, Direction, SignalStrength
from src.data.models import NewsArticle


class ScoredArticle(BaseModel):
    """An individual news article scored with sentiment and classified by event type."""

    article: NewsArticle
    sentiment_score: float  # FinBERT output, -1.0 to 1.0
    event_type: FundamentalEventType
    instruments: List[Instrument]
    confidence: float
    strength: SignalStrength


class RawSignalCandidate(BaseModel):
    """Aggregated candidate signal per instrument over an aggregation window."""

    instrument: Instrument
    sentiment_scores: List[float] = Field(default_factory=list)
    event_type: FundamentalEventType
    articles: List[NewsArticle] = Field(default_factory=list)
    direction: Direction
    confidence: float
    strength: SignalStrength
