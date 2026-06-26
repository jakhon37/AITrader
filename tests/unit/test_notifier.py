"""Unit tests for D07-NOTIFIER."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone, timedelta
from typing import Any, List
import pytest

from src.core.clock import LiveClock
from src.core.config import AppConfig
from src.core.contracts import (
    BusChannel,
    Direction,
    FundamentalEventType,
    FundamentalSignal,
    HealthStatus,
    Instrument,
    Order,
    OrderEvent,
    OrderSide,
    OrderStatus,
    PortfolioState,
    PromotionStage,
    SignalSource,
    SignalStrength,
    SystemHealthEvent,
    TradeSignal,
)
from src.core.ids import new_signal_id
from src.notifier.aggregator import MessageAggregator
from src.notifier.commands import CommandCache, CommandProcessor
from src.notifier.formatters import (
    format_fundamental_signal,
    format_order_event,
    format_system_health,
    format_trade_signal,
)
from src.notifier.router import MessageRouter
from src.notifier.telegram import TelegramClient


# ── Formatters Test ───────────────────────────────────────────────────────────

def test_formatters() -> None:
    now_utc = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

    # 1. TradeSignal
    trade_sig = TradeSignal(
        signal_id=new_signal_id(),
        instrument=Instrument.EURUSD,
        timestamp=now_utc,
        valid_until=now_utc,
        direction=Direction.LONG,
        confidence=0.85,
        strength=SignalStrength.STRONG,
        fundamental_weight=0.3,
        technical_weight=0.7,
        suggested_side=OrderSide.BUY,
        suggested_entry=1.0850,
        suggested_sl=1.0800,
        suggested_tp=1.0950,
        suggested_size=0.5,
        narrative="EURUSD technical indicators bullish.",
        sources=SignalSource(fundamental=None, technical=None),
        model_version=None,
    )
    formatted = format_trade_signal(trade_sig)
    assert "🟢 <b>BUY EURUSD</b>" in formatted
    assert "STRONG (85%)" in formatted
    assert "Valid until:</b> 12:00 UTC" in formatted

    # 2. OrderEvent
    order = Order(
        order_id="ord1",
        signal_id="sig12345678",
        instrument=Instrument.EURUSD,
        side=OrderSide.BUY,
        size=1.0,
        order_type="market",
        limit_price=None,
        stop_price=None,
        sl=1.0800,
        tp=1.0900,
        status=OrderStatus.FILLED,
        created_at=now_utc,
        filled_at=now_utc,
        filled_price=1.0855,
        execution_mode="paper",
    )
    order_event = OrderEvent(
        signal_id="sig12345678",
        event_type="filled",
        order=order,
        timestamp=now_utc,
    )
    formatted_order = format_order_event(order_event)
    assert "✅ <b>Order FILLED</b>" in formatted_order
    assert "Size:</b> 1.00 lots" in formatted_order
    assert "Price:</b> 1.08550" in formatted_order

    # 3. FundamentalSignal
    fund_sig = FundamentalSignal(
        signal_id=new_signal_id(),
        instrument=Instrument.GBPUSD,
        timestamp=now_utc,
        valid_until=now_utc,
        direction=Direction.SHORT,
        confidence=0.9,
        strength=SignalStrength.STRONG,
        sentiment_score=-0.75,
        event_type=FundamentalEventType.ECONOMIC_DATA,
        source_headline="UK GDP falls unexpectedly in Q1",
        source_url=None,
        decay_hours=4.0,
        narrative="GDP contraction boosts rate cut bets.",
        triggering_event=None,
    )
    formatted_fund = format_fundamental_signal(fund_sig)
    assert "📰 <b>Fundamental Signal</b>" in formatted_fund
    assert "🔴 <b>GBPUSD</b> — STRONG" in formatted_fund
    assert "UK GDP falls unexpectedly" in formatted_fund

    # 4. SystemHealth
    health_event = SystemHealthEvent(
        signal_id=new_signal_id(),
        division="D02-DATA",
        status=HealthStatus.DEGRADED,
        timestamp=now_utc,
        message="Database latency exceeds threshold.",
        metrics={},
    )
    formatted_health = format_system_health(health_event)
    assert "⚠️ <b>System Health: DEGRADED</b>" in formatted_health
    assert "D02-DATA" in formatted_health


# ── Router Test ───────────────────────────────────────────────────────────────

def test_message_router() -> None:
    now_utc = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    router = MessageRouter()

    # In quiet hours check
    # Default quiet hours: 22:00 to 06:00
    assert router.in_quiet_hours(datetime(2026, 6, 20, 23, 0, 0, tzinfo=timezone.utc)) is True
    assert router.in_quiet_hours(datetime(2026, 6, 20, 8, 0, 0, tzinfo=timezone.utc)) is False

    # TradeSignal filtering
    ts = TradeSignal(
        signal_id="1", instrument=Instrument.EURUSD, timestamp=now_utc, valid_until=now_utc,
        direction=Direction.LONG, confidence=0.3, strength=SignalStrength.WEAK,
        fundamental_weight=0.0, technical_weight=1.0, suggested_side=OrderSide.BUY,
        suggested_entry=None, suggested_sl=None, suggested_tp=None, suggested_size=None,
        narrative=None, sources=SignalSource(fundamental=None, technical=None), model_version=None
    )
    # Low confidence should block (default threshold: 0.5)
    assert router.should_send_trade_signal(ts, now_utc) is False

    ts.confidence = 0.8
    assert router.should_send_trade_signal(ts, now_utc) is True

    # Quiet hours check for trade signals (should block by default)
    qh_time = datetime(2026, 6, 20, 23, 30, 0, tzinfo=timezone.utc)
    assert router.should_send_trade_signal(ts, qh_time) is False


# ── Aggregator Test ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregator() -> None:
    sent_msgs = []
    async def mock_send(msg: str) -> None:
        sent_msgs.append(msg)

    agg = MessageAggregator(send_callback=mock_send, tech_batch_window=0.1)

    now_utc = datetime.now(timezone.utc)
    sig = FundamentalSignal(
        signal_id="1", instrument=Instrument.EURUSD, timestamp=now_utc, valid_until=now_utc,
        direction=Direction.LONG, confidence=0.8, strength=SignalStrength.STRONG,
        sentiment_score=0.6, event_type=FundamentalEventType.ECONOMIC_DATA,
        source_headline="News headline", source_url=None, decay_hours=1.0, narrative=None, triggering_event=None
    )

    # 1. Fundamental throttling
    assert agg.should_send_fundamental(sig, now_utc) is True
    # Immediate second check should be throttled
    assert agg.should_send_fundamental(sig, now_utc) is False

    # 5 minutes later should pass
    future_time = now_utc + timedelta(minutes=6)
    assert agg.should_send_fundamental(sig, future_time) is True

    # 2. Technical batching
    await agg.add_technical_signal(Instrument.EURUSD, "Bullish crossover")
    await agg.add_technical_signal(Instrument.EURUSD, "RSI oversold")

    # Let the timer run out (0.1 seconds)
    await asyncio.sleep(0.15)

    assert len(sent_msgs) == 1
    assert "📊 <b>Technical Batch Alert (EURUSD)</b>" in sent_msgs[0]
    assert "RSI oversold" in sent_msgs[0]

    await agg.cancel_all_timers()


# ── Commands Test ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_command_processor() -> None:
    from src.core.config import AppConfig
    cfg = AppConfig()
    cfg.core.execution_mode = "paper"

    from tests.unit.test_fundamental import MockBus
    bus = MockBus()
    cache = CommandCache()
    proc = CommandProcessor(bus=bus, config=cfg, cache=cache)

    sent_replies = []
    async def mock_reply(msg: str) -> None:
        sent_replies.append(msg)

    # 1. Test /help and /start alias
    await proc.handle_message({"text": "/help", "from": {"id": 123}}, mock_reply)
    assert len(sent_replies) == 1
    assert "/status" in sent_replies[0]
    assert "/message" in sent_replies[0]

    sent_replies.clear()
    await proc.handle_message(
        {"text": "/start", "from": {"id": 123, "first_name": "Jahon"}},
        mock_reply,
    )
    assert len(sent_replies) == 1
    assert "Welcome, Jahon" in sent_replies[0]
    assert "Quick commands" in sent_replies[0]
    assert "/help for the full command reference" in sent_replies[0]

    # 2. Test /status
    sent_replies.clear()
    await proc.handle_message({"text": "/status", "from": {"id": 123}}, mock_reply)
    assert "Execution Mode:</b> <code>PAPER" in sent_replies[0]

    # 3. Test /halt confirmation flow
    sent_replies.clear()
    await proc.handle_message({"text": "/halt", "from": {"id": 123}}, mock_reply)
    assert "Manual Trading Halt Requested" in sent_replies[0]
    assert 123 in proc._pending_confirmations

    # Confirm action
    sent_replies.clear()
    await proc.handle_message({"text": "CONFIRM", "from": {"id": 123}}, mock_reply)
    assert "manually HALTED" in sent_replies[0]
    assert len(bus.published) == 1
    chan, event = bus.published[0]
    assert chan == BusChannel.SYSTEM_HEALTH
    assert event.status == HealthStatus.DOWN
    assert event.division == "MANUAL_CONTROL"
