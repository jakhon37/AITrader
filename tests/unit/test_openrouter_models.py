"""Tests for OpenRouter model validation and failover."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from src.fundamental.openrouter_models import (
    clear_model_registry,
    is_narrative_suitable_model,
    mark_model_failed,
    select_validated_free_model,
    validate_openrouter_model,
)
from src.fundamental.synthesizer import is_chat_suitable_model


def test_unsuitable_models_filtered() -> None:
    assert is_chat_suitable_model("cohere/north-mini-code:free") is False
    assert is_narrative_suitable_model("cohere/north-mini-code:free") is False
    assert is_chat_suitable_model("mistralai/mistral-7b-instruct:free") is True


def test_validate_openrouter_model_accepts_real_reply() -> None:
    async def _run() -> None:
        clear_model_registry()
        response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.fundamental.openrouter_models.httpx.AsyncClient", return_value=mock_client):
            ok = await validate_openrouter_model(
                "mistralai/mistral-7b-instruct:free",
                "test-key",
            )
        assert ok is True

    asyncio.run(_run())


def test_select_validated_free_model_skips_failed_models() -> None:
    async def _run() -> None:
        clear_model_registry()
        mark_model_failed("mistralai/mistral-7b-instruct:free", hard=True)

        good_response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=good_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "src.fundamental.openrouter_models.get_available_free_models",
                new=AsyncMock(
                    return_value=[
                        "mistralai/mistral-7b-instruct:free",
                        "google/gemma-2-9b-it:free",
                    ]
                ),
            ),
            patch("src.fundamental.openrouter_models.httpx.AsyncClient", return_value=mock_client),
        ):
            model = await select_validated_free_model(
                "test-key",
                purpose="chat",
            )

        assert model == "google/gemma-2-9b-it:free"

    asyncio.run(_run())