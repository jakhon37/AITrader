"""Unit tests for OpenRouter status reporting."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.fundamental.openrouter_status import (
    OpenRouterStatus,
    format_openrouter_status_oneline,
    format_openrouter_status_telegram,
)


def test_format_openrouter_status_without_api_key() -> None:
    status = OpenRouterStatus(
        api_key_configured=False,
        narrative_enabled=False,
        narrative_model=None,
        narrative_model_error=None,
        narrative_budget_used=0.0,
        narrative_budget_cap=1.0,
        sentiment_backend="mock",
        sentiment_openrouter_active=False,
        sentiment_model=None,
        sentiment_model_error=None,
    )
    text = format_openrouter_status_telegram(status)
    assert "API key: <b>not set</b>" in text
    assert "MOCK" in text


def test_format_openrouter_status_oneline() -> None:
    status = OpenRouterStatus(
        api_key_configured=True,
        narrative_enabled=True,
        narrative_model="cohere/north-mini-code:free",
        narrative_model_error=None,
        narrative_budget_used=0.0,
        narrative_budget_cap=2.0,
        sentiment_backend="mock",
        sentiment_openrouter_active=False,
        sentiment_model=None,
        sentiment_model_error=None,
    )
    assert "cohere/north-mini-code:free" in format_openrouter_status_oneline(status)


def test_format_openrouter_status_active_narrative() -> None:
    status = OpenRouterStatus(
        api_key_configured=True,
        narrative_enabled=True,
        narrative_model="mistralai/mistral-7b-instruct:free",
        narrative_model_error=None,
        narrative_budget_used=0.0,
        narrative_budget_cap=1.0,
        sentiment_backend="mock",
        sentiment_openrouter_active=False,
        sentiment_model=None,
        sentiment_model_error=None,
    )
    text = format_openrouter_status_telegram(status)
    assert "Narrative: <b>ACTIVE</b>" in text
    assert "mistralai/mistral-7b-instruct:free" in text
    assert "not using OpenRouter" in text


@pytest.mark.asyncio
async def test_status_command_includes_openrouter_block() -> None:
    from src.core.config import AppConfig
    from src.notifier.commands import CommandCache, CommandProcessor
    from tests.unit.test_fundamental import MockBus

    cfg = AppConfig()
    agent = MagicMock()
    agent.get_openrouter_status = AsyncMock(
        return_value=OpenRouterStatus(
            api_key_configured=True,
            narrative_enabled=True,
            narrative_model="google/gemma-2-9b-it:free",
            narrative_model_error=None,
            narrative_budget_used=0.0,
            narrative_budget_cap=1.0,
            sentiment_backend="mock",
            sentiment_openrouter_active=False,
            sentiment_model=None,
            sentiment_model_error=None,
        )
    )

    proc = CommandProcessor(
        bus=MockBus(),
        config=cfg,
        cache=CommandCache(),
        fundamental_agent=agent,
    )

    replies: list[str] = []

    async def capture(msg: str) -> None:
        replies.append(msg)

    await proc.handle_message({"text": "/status", "from": {"id": 1}}, capture)
    assert len(replies) == 1
    assert "OpenRouter LLM" in replies[0]
    assert "google/gemma-2-9b-it:free" in replies[0]