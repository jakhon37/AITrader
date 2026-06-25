"""Unit tests for D03-FUNDAMENTAL."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, List
import pytest

from src.core.clock import LiveClock, ReplayClock
from src.core.config import InstrumentConfig, SignalDecayConfig
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
from src.data.models import NewsArticle
from src.fundamental.agent import FundamentalAgent
from src.fundamental.classifier import EventClassifier
from src.fundamental.decay import compute_valid_until, get_decay_hours
from src.fundamental.filter import NewsFilter
from src.fundamental.sentiment import SentimentScorer


# ── Mocks ─────────────────────────────────────────────────────────────────────

class MockBus:
    def __init__(self) -> None:
        self.published: List[tuple[BusChannel, Any]] = []
        self.subscriptions: dict[BusChannel, List[Any]] = {}

    async def publish(self, channel: BusChannel, payload: Any) -> None:
        self.published.append((channel, payload))
        handlers = self.subscriptions.get(channel, [])
        for h in handlers:
            await h(payload)

    async def subscribe(self, channel: BusChannel, handler: Any) -> None:
        self.subscriptions.setdefault(channel, []).append(handler)

    async def unsubscribe(self, channel: BusChannel, handler: Any) -> None:
        if channel in self.subscriptions:
            self.subscriptions[channel] = [h for h in self.subscriptions[channel] if h != handler]


class MockDataStore:
    def __init__(self) -> None:
        self.news_database: List[NewsArticle] = []

    def write_news(self, articles: List[NewsArticle]) -> None:
        self.news_database.extend(articles)

    def get_news(self, instrument: Any, start: datetime, end: datetime) -> List[NewsArticle]:
        return [
            art
            for art in self.news_database
            if start <= art.published_at <= end
        ]


class MockSynthesizer:
    async def get_narrative(self, instrument: Instrument, direction: Direction, headline: str, score: float, body_snippet: str | None = None) -> str:
        return f"Mocked narrative for {instrument.value}: {direction.value}"

    async def get_calendar_briefing(self, instrument: Instrument, event: EconomicEvent, minutes_until: int) -> str:
        return f"Mock briefing for {instrument.value}: {event.name} in {minutes_until}m"


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_news_filter() -> None:
    now_utc = datetime.now(timezone.utc)
    filt = NewsFilter(recency_hours=2.0, duplicate_window_hours=6.0)

    # 1. Recency check
    old_article = NewsArticle(
        article_id="1",
        headline="EUR Interest Rate Decision",
        source="newsapi",
        published_at=now_utc - timedelta(hours=3),
        instruments=["EURUSD"],
    )
    assert filt.should_keep(old_article, now_utc) is False

    # 2. English check
    non_eng = NewsArticle(
        article_id="2",
        headline="Инфляция в США растет быстрее ожиданий",
        source="newsapi",
        published_at=now_utc - timedelta(minutes=10),
        instruments=["EURUSD"],
    )
    assert filt.should_keep(non_eng, now_utc) is False

    # 3. Relevance check (no match)
    irrelevant = NewsArticle(
        article_id="3",
        headline="Apple launches new iPhone",
        source="newsapi",
        published_at=now_utc - timedelta(minutes=5),
        instruments=[],
    )
    assert filt.should_keep(irrelevant, now_utc) is False

    # 4. Valid article
    valid = NewsArticle(
        article_id="4",
        headline="Fed Chair Powell signals interest rate cuts are coming",
        source="newsapi",
        published_at=now_utc - timedelta(minutes=15),
        instruments=["EURUSD"],
    )
    assert filt.should_keep(valid, now_utc) is True

    # 5. Duplicate check
    assert filt.should_keep(valid, now_utc) is False  # Already seen


def test_event_classifier() -> None:
    classifier = EventClassifier()

    assert classifier.classify("Fed rate decision expected today") == FundamentalEventType.CENTRAL_BANK
    assert classifier.classify("US CPI inflation reaches 3.2%") == FundamentalEventType.ECONOMIC_DATA
    assert classifier.classify("Tensions rise as trade war tariffs are announced") == FundamentalEventType.GEOPOLITICAL
    assert classifier.classify("Markets face heavy risk-off session") == FundamentalEventType.MARKET_RISK
    assert classifier.classify("Gold price breaks resistance level") == FundamentalEventType.TECHNICAL_CONF

    # Sentiment logic
    assert classifier.determine_direction(0.4) == Direction.LONG
    assert classifier.determine_direction(-0.25) == Direction.SHORT
    assert classifier.determine_direction(0.05) == Direction.NEUTRAL

    assert classifier.determine_strength(0.8) == SignalStrength.STRONG
    assert classifier.determine_strength(0.5) == SignalStrength.MODERATE
    assert classifier.determine_strength(0.2) == SignalStrength.WEAK


def test_signal_decay() -> None:
    now_utc = datetime.now(timezone.utc)
    decay_cfg = SignalDecayConfig(central_bank=24.0, economic_data=2.0)
    inst_cfg = InstrumentConfig(
        pip_size=0.0001,
        lot_size=100000.0,
        session_hours={"open": "22:00", "close": "22:00"},
        active_timeframes=[],
        primary_timeframe=Timeframe.H1,
        signal_decay=decay_cfg,
    )

    assert get_decay_hours(FundamentalEventType.CENTRAL_BANK, inst_cfg) == 24.0
    assert get_decay_hours(FundamentalEventType.ECONOMIC_DATA, inst_cfg) == 2.0

    valid_until = compute_valid_until(FundamentalEventType.ECONOMIC_DATA, inst_cfg, now_utc)
    assert valid_until == now_utc + timedelta(hours=2)


def test_sentiment_scorer_mock() -> None:
    scorer = SentimentScorer(use_mock=True)
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        res = loop.run_until_complete(scorer.score_batch(["extremely bullish hike", "terrible drop and cut"]))
        assert len(res) == 2
        assert res[0] > 0.0
        assert res[1] < 0.0
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_agent_news_polling() -> None:
    # Set up configs
    from src.core.config import AppConfig
    cfg = AppConfig()
    cfg.core.execution_mode = "paper"

    bus = MockBus()
    store = MockDataStore()
    scorer = SentimentScorer(use_mock=True)
    synthesizer = MockSynthesizer()

    agent = FundamentalAgent(
        config=cfg,
        bus=bus,
        store=store,
        sentiment_scorer=scorer,
        synthesizer=synthesizer,
    )

    # Insert mock news
    now_utc = datetime.now(timezone.utc)
    art1 = NewsArticle(
        article_id="art1",
        headline="ECB comments on Euro growth",
        source="reuters",
        published_at=now_utc - timedelta(minutes=5),
        instruments=["EURUSD"],
    )
    store.write_news([art1])

    # Run news polling
    agent._last_poll_time = now_utc - timedelta(minutes=30)
    await agent.poll_news()

    # Check published signals
    assert len(bus.published) == 1
    chan, sig = bus.published[0]
    assert chan == BusChannel.FUNDAMENTAL_SIGNAL
    assert isinstance(sig, FundamentalSignal)
    assert sig.instrument == Instrument.EURUSD
    assert sig.direction in (Direction.LONG, Direction.SHORT)
    assert sig.event_type == FundamentalEventType.CENTRAL_BANK


@pytest.mark.asyncio
async def test_agent_economic_event_trigger() -> None:
    from src.core.config import AppConfig
    cfg = AppConfig()

    bus = MockBus()
    store = MockDataStore()
    agent = FundamentalAgent(
        config=cfg,
        bus=bus,
        store=store,
        sentiment_scorer=SentimentScorer(use_mock=True),
        synthesizer=MockSynthesizer(),
    )

    await agent.start()

    # Create mock EconomicEvent
    now_utc = datetime.now(timezone.utc)
    event = EconomicEvent(
        signal_id="evt1",
        timestamp=now_utc,
        name="US CPI YoY Inflation",
        impact="high",
        affected_pairs=[Instrument.EURUSD],
        actual=3.4,
        forecast=3.1,
        previous=3.2,
        surprise_pct=0.0967,  # Positive surprise
    )

    # Publish economic event (Path 2 trigger)
    await bus.publish(BusChannel.ECONOMIC_EVENT, event)

    # Verify immediate scoring and emission
    # EURUSD is a USD quote pair, so a positive USD surprise should trigger Direction.SHORT
    assert len(bus.published) > 1  # 1 for ECONOMIC_EVENT, 1 for FUNDAMENTAL_SIGNAL
    signals = [p[1] for p in bus.published if p[0] == BusChannel.FUNDAMENTAL_SIGNAL]
    assert len(signals) == 1
    sig = signals[0]
    assert sig.instrument == Instrument.EURUSD
    assert sig.direction == Direction.SHORT
    assert sig.event_type == FundamentalEventType.ECONOMIC_DATA
    assert sig.triggering_event.signal_id == "evt1"

    await agent.stop()


@pytest.mark.asyncio
async def test_agent_pre_release_calendar_briefing() -> None:
    from src.core.config import AppConfig

    cfg = AppConfig()
    cfg.fundamental.calendar_briefing_enabled = True
    cfg.fundamental.calendar_min_impact = "medium"

    bus = MockBus()
    store = MockDataStore()
    agent = FundamentalAgent(
        config=cfg,
        bus=bus,
        store=store,
        sentiment_scorer=SentimentScorer(use_mock=True),
        synthesizer=MockSynthesizer(),
    )

    await agent.start()

    release_at = datetime.now(timezone.utc) + timedelta(minutes=45)
    event = EconomicEvent(
        signal_id="evt-pre",
        timestamp=release_at,
        name="US CPI YoY",
        impact="high",
        affected_pairs=[Instrument.EURUSD, Instrument.GBPUSD],
        actual=None,
        forecast=3.1,
        previous=3.2,
        surprise_pct=None,
    )

    await bus.publish(BusChannel.ECONOMIC_EVENT, event)

    signals = [p[1] for p in bus.published if p[0] == BusChannel.FUNDAMENTAL_SIGNAL]
    assert len(signals) == 2
    for sig in signals:
        assert sig.direction == Direction.NEUTRAL
        assert sig.source_headline.startswith("Upcoming:")
        assert "Mock briefing" in (sig.narrative or "")
        assert sig.triggering_event is not None
        assert sig.triggering_event.actual is None

    await agent.stop()


@pytest.mark.asyncio
async def test_agent_pre_release_skips_low_impact() -> None:
    from src.core.config import AppConfig

    cfg = AppConfig()
    cfg.fundamental.calendar_min_impact = "high"

    bus = MockBus()
    agent = FundamentalAgent(
        config=cfg,
        bus=bus,
        store=MockDataStore(),
        sentiment_scorer=SentimentScorer(use_mock=True),
        synthesizer=MockSynthesizer(),
    )
    await agent.start()

    event = EconomicEvent(
        signal_id="evt-low",
        timestamp=datetime.now(timezone.utc) + timedelta(minutes=30),
        name="Minor PMI",
        impact="medium",
        affected_pairs=[Instrument.EURUSD],
        actual=None,
    )
    await bus.publish(BusChannel.ECONOMIC_EVENT, event)

    signals = [p[1] for p in bus.published if p[0] == BusChannel.FUNDAMENTAL_SIGNAL]
    assert len(signals) == 0

    await agent.stop()
