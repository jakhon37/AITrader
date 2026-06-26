"""Unit tests for Telegram chat Q&A mode."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.config import AppConfig
from src.core.contracts import (
    BusChannel,
    Direction,
    ExecutionMode,
    FundamentalEventType,
    FundamentalSignal,
    HealthStatus,
    Instrument,
    OrderSide,
    PortfolioState,
    SignalSource,
    SignalStrength,
    SystemHealthEvent,
    TradeSignal,
)
from src.core.ids import new_signal_id
from src.notifier.chat import build_trading_context, format_chat_reply
from src.notifier.commands import CommandCache, CommandProcessor
from tests.unit.test_fundamental import MockBus


def _portfolio() -> PortfolioState:
    now_utc = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)
    return PortfolioState(
        signal_id="ps1",
        timestamp=now_utc,
        execution_mode=ExecutionMode.PAPER,
        balance=100_000.0,
        equity=100_250.0,
        margin_used=0.0,
        free_margin=100_000.0,
        open_positions=[],
        realized_pnl_today=250.0,
        drawdown_pct=0.0,
    )


def test_build_trading_context_includes_portfolio_and_signals() -> None:
    cache = CommandCache()
    cache.portfolio_state = _portfolio()
    cache.add_trade_signal(
        TradeSignal(
            signal_id=new_signal_id(),
            instrument=Instrument.EURUSD,
            timestamp=datetime(2026, 6, 26, 11, 0, 0, tzinfo=timezone.utc),
            valid_until=datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc),
            direction=Direction.LONG,
            confidence=0.72,
            strength=SignalStrength.MODERATE,
            fundamental_weight=0.3,
            technical_weight=0.7,
            suggested_side=OrderSide.BUY,
            suggested_entry=None,
            suggested_sl=None,
            suggested_tp=None,
            suggested_size=None,
            narrative=None,
            sources=SignalSource(fundamental=None, technical=None),
            model_version=None,
        )
    )
    cache.add_health(
        SystemHealthEvent(
            signal_id=new_signal_id(),
            division="D04-TECHNICAL",
            status=HealthStatus.OK,
            timestamp=datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc),
            message="ok",
            metrics={},
        )
    )

    cfg = AppConfig()
    context = build_trading_context(cache, cfg)

    assert "Portfolio:" in context
    assert "Equity $100,250.00" in context
    assert "EURUSD" in context
    assert "D04-TECHNICAL: OK" in context


def test_format_chat_reply_escapes_html() -> None:
    assert format_chat_reply("P&L <script>") == "💬 P&amp;L &lt;script&gt;"


def test_message_command_activates_chat_mode() -> None:
    async def _run() -> None:
        cfg = AppConfig()
        bus = MockBus()
        cache = CommandCache()
        proc = CommandProcessor(bus=bus, config=cfg, cache=cache)

        replies: list[str] = []

        async def mock_reply(msg: str) -> None:
            replies.append(msg)

        await proc.handle_message({"text": "/message", "from": {"id": 42}}, mock_reply)
        assert proc._chat_mode_active(42)
        assert "Chat mode ON" in replies[0]

    asyncio.run(_run())


def test_free_text_routed_in_chat_mode() -> None:
    async def _run() -> None:
        cfg = AppConfig()
        bus = MockBus()
        cache = CommandCache()
        cache.portfolio_state = _portfolio()

        mock_agent = MagicMock()
        mock_agent.synthesizer.api_key = "test-key"
        mock_agent.synthesizer.timeout = 5.0
        mock_agent.synthesizer.model = AsyncMock(return_value="test/model:free")
        mock_agent.synthesizer.budget_available.return_value = True
        mock_agent.synthesizer._cost_per_call = 0.0
        mock_agent.synthesizer._daily_spend = 0.0
        mock_agent.synthesizer._last_model_selection = None

        proc = CommandProcessor(
            bus=bus,
            config=cfg,
            cache=cache,
            fundamental_agent=mock_agent,
        )
        proc._chat_mode_users[42] = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)

        replies: list[str] = []

        async def mock_reply(msg: str) -> None:
            replies.append(msg)

        with patch(
            "src.notifier.commands.answer_trading_question",
            new=AsyncMock(return_value="You have no open positions."),
        ):
            await proc.handle_message(
                {"text": "What is my equity?", "from": {"id": 42}},
                mock_reply,
            )

        assert any("Thinking" in r for r in replies)
        assert any("no open positions" in r for r in replies)

    asyncio.run(_run())


def test_message_off_deactivates_chat_mode() -> None:
    async def _run() -> None:
        cfg = AppConfig()
        bus = MockBus()
        proc = CommandProcessor(bus=bus, config=cfg, cache=CommandCache())
        proc._chat_mode_users[7] = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)

        replies: list[str] = []

        async def mock_reply(msg: str) -> None:
            replies.append(msg)

        await proc.handle_message({"text": "/done", "from": {"id": 7}}, mock_reply)
        assert not proc._chat_mode_active(7)
        assert "OFF" in replies[0]

    asyncio.run(_run())