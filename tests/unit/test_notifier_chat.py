"""Unit tests for Telegram chat Q&A mode."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

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
from src.fundamental.synthesizer import extract_openrouter_content, is_chat_suitable_model
from src.notifier.chat import (
    answer_trading_question,
    build_trading_context,
    format_chat_reply,
    try_emergency_data_fallback,
)
from src.execution.store import ExecutionStore
from src.notifier.commands import CommandProcessor
from src.ops.health_store import SystemHealthStore
from src.signals.registry import SignalStores
from src.signals.stores import TechnicalSignalStore, TradeSignalStore
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


def test_build_trading_context_includes_portfolio_and_signals(tmp_path) -> None:
    from src.fundamental.signal_store import FundamentalSignalStore

    exec_store = ExecutionStore(tmp_path / "execution.db")
    exec_store.save_portfolio_snapshot(_portfolio())
    state_dir = tmp_path / "state"
    stores = SignalStores(
        fundamental=FundamentalSignalStore(state_dir / "fundamental.db"),
        technical=TechnicalSignalStore(state_dir / "technical.db"),
        trade=TradeSignalStore(state_dir / "trade.db"),
        health=SystemHealthStore(state_dir / "health.db"),
        execution=exec_store,
    )
    stores.trade.upsert_signal(
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
    stores.health.upsert(
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
    context = build_trading_context(cfg, signal_stores=stores, execution_store=exec_store)

    assert "Portfolio:" in context
    assert "Equity $100,250.00" in context
    assert "EURUSD" in context
    assert "D04-TECHNICAL: OK" in context


def test_emergency_fallback_portfolio(tmp_path) -> None:
    exec_store = ExecutionStore(tmp_path / "execution.db")
    exec_store.save_portfolio_snapshot(_portfolio())
    answer = try_emergency_data_fallback(
        "What is my portfolio?",
        execution_store=exec_store,
    )
    assert answer is not None
    assert "equity $100,250.00" in answer
    assert "Open positions: 0" in answer


def test_question_matches_avoids_substring_false_positives() -> None:
    from src.notifier.chat import _question_matches

    assert _question_matches("What is the outlook for EURUSD this week?", ("hi",)) is False
    assert _question_matches("Hi there", ("hi",)) is True
    assert _question_matches("Any signals", ("signal",)) is True


def test_emergency_fallback_trade_database(tmp_path) -> None:
    exec_store = ExecutionStore(tmp_path / "execution.db")
    answer = try_emergency_data_fallback(
        "Can you read my trade database?",
        execution_store=exec_store,
    )
    assert answer is not None
    assert "no closed trades" in answer.lower()


def test_format_chat_reply_escapes_html() -> None:
    assert format_chat_reply("P&L <script>") == "💬 P&amp;L &lt;script&gt;"


def test_extract_openrouter_content_handles_null_and_text() -> None:
    assert extract_openrouter_content({"choices": [{"message": {"content": None}}]}) is None
    assert (
        extract_openrouter_content({"choices": [{"message": {"content": "Hello"}}]})
        == "Hello"
    )


def test_is_chat_suitable_model_filters_code_models() -> None:
    assert is_chat_suitable_model("mistralai/mistral-7b-instruct:free") is True
    assert is_chat_suitable_model("cohere/north-mini-code:free") is False


def test_answer_trading_question_retries_on_safety_classifier_output() -> None:
    async def _run() -> None:
        from src.fundamental.synthesizer import NarrativeSynthesizer

        synthesizer = NarrativeSynthesizer(api_key="test-key", model="mistralai/mistral-7b-instruct:free")

        safety_response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "User Safety: safe\nResponse Safety: safe"}}]},
        )
        good_response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Yes, I am here."}}]},
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[safety_response, good_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "src.notifier.chat.select_validated_free_model",
                new=AsyncMock(
                    side_effect=[
                        "mistralai/mistral-7b-instruct:free",
                        "google/gemma-2-9b-it:free",
                    ]
                ),
            ),
            patch("src.notifier.chat.httpx.AsyncClient", return_value=mock_client),
        ):
            answer = await answer_trading_question(
                "What is the outlook for EURUSD this week?",
                "Portfolio: equity $100k",
                synthesizer,
            )

        assert answer == "Yes, I am here."

    asyncio.run(_run())


def test_answer_trading_question_retries_on_empty_content() -> None:
    async def _run() -> None:
        from src.fundamental.synthesizer import NarrativeSynthesizer

        synthesizer = NarrativeSynthesizer(api_key="test-key", model="mistralai/mistral-7b-instruct:free")

        empty_response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": None}}]},
        )
        good_response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Hi there, trader."}}]},
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[empty_response, good_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "src.notifier.chat.select_validated_free_model",
                new=AsyncMock(
                    side_effect=[
                        "cohere/north-mini-code:free",
                        "mistralai/mistral-7b-instruct:free",
                    ]
                ),
            ),
            patch("src.notifier.chat.httpx.AsyncClient", return_value=mock_client),
        ):
            answer = await answer_trading_question(
                "Summarize the macro backdrop for gold.",
                "Portfolio: equity $100k",
                synthesizer,
            )

        assert answer == "Hi there, trader."

    asyncio.run(_run())


def test_message_command_activates_chat_mode() -> None:
    async def _run() -> None:
        cfg = AppConfig()
        bus = MockBus()
        proc = CommandProcessor(bus=bus, config=cfg)

        replies: list[str] = []

        async def mock_reply(msg: str) -> None:
            replies.append(msg)

        await proc.handle_message({"text": "/message", "from": {"id": 42}}, mock_reply)
        assert proc._chat_mode_active(42)
        assert "Chat mode ON" in replies[0]

    asyncio.run(_run())


def test_portfolio_chat_uses_llm_not_direct_shortcut(tmp_path) -> None:
    async def _run() -> None:
        cfg = AppConfig()
        bus = MockBus()
        exec_store = ExecutionStore(tmp_path / "execution.db")
        exec_store.save_portfolio_snapshot(_portfolio())
        mock_agent = MagicMock()
        mock_agent.synthesizer.api_key = "test-key"
        mock_agent.synthesizer.timeout = 5.0
        mock_agent.synthesizer.budget_available.return_value = True
        mock_agent.synthesizer._preferred_models = ["mistralai/mistral-7b-instruct:free"]
        mock_agent.synthesizer._cost_per_call = 0.0
        mock_agent.synthesizer._daily_spend = 0.0
        mock_agent.synthesizer._last_model_selection = None

        proc = CommandProcessor(
            bus=bus,
            config=cfg,
            execution_store=exec_store,
            fundamental_agent=mock_agent,
            data_store=None,
        )
        from src.core.clock import now as clock_now

        proc._chat_mode_users[42] = clock_now()

        replies: list[str] = []

        async def mock_reply(msg: str) -> None:
            replies.append(msg)

        with patch(
            "src.notifier.commands.answer_trading_question",
            new=AsyncMock(
                return_value="Your equity is $100,250 with no open positions."
            ),
        ) as mock_llm:
            await proc.handle_message(
                {"text": "My portfolio", "from": {"id": 42}},
                mock_reply,
            )

        mock_llm.assert_awaited_once()
        assert any("100,250" in r for r in replies)

    asyncio.run(_run())


def test_free_text_routed_in_chat_mode(tmp_path) -> None:
    async def _run() -> None:
        cfg = AppConfig()
        bus = MockBus()
        exec_store = ExecutionStore(tmp_path / "execution.db")
        exec_store.save_portfolio_snapshot(_portfolio())
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
            execution_store=exec_store,
            fundamental_agent=mock_agent,
        )
        from src.core.clock import now as clock_now

        proc._chat_mode_users[42] = clock_now()

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
        proc = CommandProcessor(bus=bus, config=cfg)
        from src.core.clock import now as clock_now

        proc._chat_mode_users[7] = clock_now()

        replies: list[str] = []

        async def mock_reply(msg: str) -> None:
            replies.append(msg)

        await proc.handle_message({"text": "/done", "from": {"id": 7}}, mock_reply)
        assert not proc._chat_mode_active(7)
        assert "OFF" in replies[0]

    asyncio.run(_run())