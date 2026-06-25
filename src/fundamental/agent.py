"""D03-FUNDAMENTAL — Fundamental agent coordinator.

Orchestrates news polling loops and responds to immediate economic release events
to emit structured FundamentalSignals on the bus.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.core.clock import now
from src.core.config import AppConfig, InstrumentConfig, load_instruments
from src.core.contracts import (
    BusChannel,
    Direction,
    EconomicEvent,
    FundamentalEventType,
    FundamentalSignal,
    Instrument,
    SignalStrength,
    Timeframe,
)
from src.core.ids import new_signal_id
from src.core.logging import get_logger
from src.data.store import DataStore
from src.fundamental.classifier import EventClassifier
from src.fundamental.decay import compute_valid_until, get_decay_hours
from src.fundamental.filter import NewsFilter
from src.fundamental.macro_regime import MacroRegimeDetector
from src.fundamental.models import ScoredArticle
from src.fundamental.sentiment import SentimentScorer

_log = get_logger("D03-FUNDAMENTAL")


class FundamentalAgent:
    """Coordinates fundamental data processing, sentiment analysis, and signal emission."""

    def __init__(
        self,
        config: AppConfig,
        bus: Any,  # Bus protocol
        store: DataStore,
        sentiment_scorer: SentimentScorer | None = None,
        classifier: EventClassifier | None = None,
        news_filter: NewsFilter | None = None,
        synthesizer: Any | None = None,  # NarrativeSynthesizer
        regime_detector: MacroRegimeDetector | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.store = store

        # Component instances (use parameter injection or default to standard configurations)
        if sentiment_scorer is None:
            backend = getattr(getattr(config, "fundamental", None), "sentiment_backend", "mock")
            api_key = os.environ.get("OPENROUTER_API_KEY") if backend == "openrouter" else None
            self.sentiment_scorer = SentimentScorer(backend=backend, openrouter_api_key=api_key)
        else:
            self.sentiment_scorer = sentiment_scorer
        self.classifier = classifier or EventClassifier()
        self.filter = news_filter or NewsFilter()

        # Import locally to avoid circular dependencies
        if synthesizer is None:
            from src.fundamental.synthesizer import NarrativeSynthesizer
            self.synthesizer = NarrativeSynthesizer()
        else:
            self.synthesizer = synthesizer

        self.regime_detector = regime_detector or MacroRegimeDetector()

        # Load configurations
        try:
            self.instrument_configs = load_instruments()
        except Exception:
            _log.warning("fundamental_agent_instruments_load_fallback", details="Could not load config/instruments.yaml, using empty configs.")
            self.instrument_configs = {}

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._poll_interval: int = 600
        self._last_poll_time = now() - timedelta(minutes=15)

    async def start(self) -> None:
        """Start the agent background loop and event subscriptions."""
        if self._running:
            return
        self._running = True

        # Subscribe to immediate economic events (Path 2)
        await self.bus.subscribe(BusChannel.ECONOMIC_EVENT, self.handle_economic_event)

        # Start periodic news poll loop (Path 1)
        fund = getattr(self.config, "fundamental", None)
        if fund is not None:
            self._poll_interval = getattr(fund, "poll_interval_seconds", 600)
        self._poll_task = asyncio.create_task(self._poll_loop())
        _log.info("fundamental_agent_started")

    async def stop(self) -> None:
        """Stop the background tasks and clean up resources."""
        if not self._running:
            return
        self._running = False

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        await self.bus.unsubscribe(BusChannel.ECONOMIC_EVENT, self.handle_economic_event)
        _log.info("fundamental_agent_stopped")

    async def _poll_loop(self) -> None:
        """Infinite polling loop checking news database every 10 minutes (Path 1)."""
        while self._running:
            try:
                await self.poll_news()
            except Exception as e:
                _log.error("fundamental_agent_poll_error", error=str(e))

            # Sleep according to config
            await asyncio.sleep(self._poll_interval)

    async def poll_news(self) -> None:
        """Query news from DataStore since last poll time and score/publish signals."""
        current_time = now()
        start_time = self._last_poll_time
        _log.debug("fundamental_agent_poll_news", start=start_time.isoformat(), end=current_time.isoformat())

        # Retrieve new articles from store
        raw_articles = self.store.get_news(instrument=None, start=start_time, end=current_time)
        self._last_poll_time = current_time

        if not raw_articles:
            _log.debug("fundamental_agent_no_new_articles")
            return

        # 1. Filter articles
        kept_articles = []
        for art in raw_articles:
            if self.filter.should_keep(art, current_time):
                kept_articles.append(art)

        if not kept_articles:
            _log.debug("fundamental_agent_no_articles_after_filtering")
            return

        # 2. Score articles (run in thread pool executor)
        texts_to_score = [f"{art.headline} {art.body_snippet or ''}" for art in kept_articles]
        article_ids = [art.article_id for art in kept_articles]
        scores = await self.sentiment_scorer.score_batch(texts_to_score, article_ids=article_ids)

        # 3. Classify and process into ScoredArticles
        scored_articles: List[ScoredArticle] = []
        for art, score in zip(kept_articles, scores):
            event_type = self.classifier.classify(art.headline)
            direction = self.classifier.determine_direction(score)
            confidence = abs(score)
            strength = self.classifier.determine_strength(confidence)
            instruments = self.filter.get_relevant_instruments(art)

            sa = ScoredArticle(
                article=art,
                sentiment_score=score,
                event_type=event_type,
                instruments=instruments,
                confidence=confidence,
                strength=strength,
            )
            scored_articles.append(sa)
            self.regime_detector.add_article(sa)

        # 4. Group articles per instrument
        instrument_groups: Dict[Instrument, List[ScoredArticle]] = {}
        for sa in scored_articles:
            for inst in sa.instruments:
                instrument_groups.setdefault(inst, []).append(sa)

        # 5. Aggregate and publish signals per instrument
        for inst, group in instrument_groups.items():
            await self._aggregate_and_publish_signal(inst, group, current_time)

    async def _aggregate_and_publish_signal(
        self,
        instrument: Instrument,
        articles: List[ScoredArticle],
        current_time: datetime,
    ) -> None:
        """Combine multiple articles for an instrument into a single signal."""
        # Average sentiment scores
        avg_score = sum(sa.sentiment_score for sa in articles) / len(articles)
        direction = self.classifier.determine_direction(avg_score)
        confidence = abs(avg_score)
        strength = self.classifier.determine_strength(confidence)

        min_conf = getattr(getattr(self.config, "fundamental", None), "min_confidence_to_emit", 0.25)
        if confidence < min_conf:
            _log.debug("fundamental_signal_skipped_low_confidence", instrument=instrument.value, confidence=confidence)
            return

        # Find the article with the highest absolute sentiment (the primary catalyst)
        primary_sa = max(articles, key=lambda sa: abs(sa.sentiment_score))
        event_type = primary_sa.event_type

        # Fetch config for instrument
        inst_config = self.instrument_configs.get(instrument)
        if not inst_config:
            # Safe default fallback config
            inst_config = InstrumentConfig(
                pip_size=0.0001,
                lot_size=100000,
                session_hours={"open": "22:00", "close": "22:00"},
                active_timeframes=[],
                primary_timeframe=Timeframe.H1,
            )

        decay_hours = get_decay_hours(event_type, inst_config)
        valid_until = compute_valid_until(event_type, inst_config, current_time)

        # Async fire-and-forget OpenRouter narrative synthesis
        narrative = await self.synthesizer.get_narrative(
            instrument=instrument,
            direction=direction,
            headline=primary_sa.article.headline,
            score=avg_score,
            body_snippet=primary_sa.article.body_snippet,
        )

        signal = FundamentalSignal(
            signal_id=new_signal_id(),
            instrument=instrument,
            timestamp=current_time,
            valid_until=valid_until,
            direction=direction,
            confidence=confidence,
            strength=strength,
            sentiment_score=avg_score,
            event_type=event_type,
            source_headline=primary_sa.article.headline[:200],
            source_url=primary_sa.article.url,
            decay_hours=decay_hours,
            narrative=narrative,
            triggering_event=None,
        )

        await self.bus.publish(BusChannel.FUNDAMENTAL_SIGNAL, signal)
        _log.info(
            "fundamental_signal_published",
            instrument=instrument.value,
            direction=direction.value,
            score=f"{avg_score:.2f}",
            event_type=event_type.value,
        )

    async def handle_economic_event(self, event: EconomicEvent) -> None:
        """Immediate event-driven Path 2: Respond to post-release calendar updates."""
        if event.actual is None:
            # Ignore pre-releases for signal generation
            return

        _log.info("fundamental_agent_economic_event_received", event_id=event.signal_id, name=event.name)

        current_time = now()
        surprise_pct = event.surprise_pct or 0.0

        # Determine which currency is responsible for the release
        currency = "USD"
        name_lower = event.name.lower()
        if any(w in name_lower for w in ["eur", "ecb", "germany", "france", "eurozone"]):
            currency = "EUR"
        elif any(w in name_lower for w in ["gbp", "boe", "uk ", "united kingdom"]):
            currency = "GBP"
        elif any(w in name_lower for w in ["jpy", "boj", "japan"]):
            currency = "JPY"

        # Produce a fundamental signal for each affected instrument
        for inst in event.affected_pairs:
            inst_config = self.instrument_configs.get(inst)
            if not inst_config:
                inst_config = InstrumentConfig(
                    pip_size=0.0001,
                    lot_size=100000,
                    session_hours={"open": "22:00", "close": "22:00"},
                    active_timeframes=[],
                    primary_timeframe=Timeframe.H1,
                )

            # Map the economic surprise to raw sentiment score
            # A positive surprise generally strengthens the base currency and weakens the quote currency.
            is_base = inst.value.startswith(currency)
            is_quote = inst.value.endswith(currency)

            sentiment_score = 0.0
            if is_base:
                # Surprise is positive: bullish for instrument. Negative surprise: bearish.
                sentiment_score = min(1.0, max(-1.0, surprise_pct * 10.0))
            elif is_quote:
                # Surprise is positive: bearish for instrument (quote currency strengthens).
                sentiment_score = min(1.0, max(-1.0, -surprise_pct * 10.0))

            # Apply high impact multiplier
            impact_confidence = 0.8 if event.impact == "high" else 0.5 if event.impact == "medium" else 0.2
            confidence = min(1.0, abs(sentiment_score) * 0.5 + impact_confidence * 0.5)

            min_conf = getattr(getattr(self.config, "fundamental", None), "min_confidence_to_emit", 0.25)
            if confidence < min_conf:
                _log.debug("fundamental_econ_signal_skipped_low_conf", instrument=inst.value, confidence=confidence)
                continue

            direction = self.classifier.determine_direction(sentiment_score)
            strength = self.classifier.determine_strength(confidence)

            decay_hours = get_decay_hours(FundamentalEventType.ECONOMIC_DATA, inst_config)
            valid_until = compute_valid_until(FundamentalEventType.ECONOMIC_DATA, inst_config, current_time)

            narrative = (
                f"Economic calendar event '{event.name}' surprise of {surprise_pct:+.2%}. "
                f"Actual: {event.actual}, Forecast: {event.forecast}, Previous: {event.previous}."
            )

            signal = FundamentalSignal(
                signal_id=new_signal_id(),
                instrument=inst,
                timestamp=current_time,
                valid_until=valid_until,
                direction=direction,
                confidence=confidence,
                strength=strength,
                sentiment_score=sentiment_score,
                event_type=FundamentalEventType.ECONOMIC_DATA,
                source_headline=f"Calendar: {event.name} released",
                source_url=None,
                decay_hours=decay_hours,
                narrative=narrative,
                triggering_event=event,
            )

            await self.bus.publish(BusChannel.FUNDAMENTAL_SIGNAL, signal)
            _log.info(
                "fundamental_economic_signal_published",
                instrument=inst.value,
                direction=direction.value,
                surprise=f"{surprise_pct:+.2%}",
                impact=event.impact,
            )
