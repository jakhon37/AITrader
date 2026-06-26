"""OpenRouter LLM status helpers for Telegram /status and ops probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.core.config import AppConfig
from src.fundamental.sentiment import SentimentScorer
from src.fundamental.synthesizer import NarrativeSynthesizer, select_available_free_model


@dataclass(frozen=True)
class OpenRouterStatus:
    api_key_configured: bool
    narrative_enabled: bool
    narrative_model: Optional[str]
    narrative_model_error: Optional[str]
    narrative_budget_used: float
    narrative_budget_cap: float
    sentiment_backend: str
    sentiment_openrouter_active: bool
    sentiment_model: Optional[str]
    sentiment_model_error: Optional[str]

    @property
    def narrative_active(self) -> bool:
        return self.api_key_configured and self.narrative_enabled and self.narrative_model is not None

    @property
    def any_openrouter_active(self) -> bool:
        return self.narrative_active or self.sentiment_openrouter_active


async def build_openrouter_status(
    config: AppConfig,
    synthesizer: NarrativeSynthesizer,
    sentiment_scorer: SentimentScorer,
) -> OpenRouterStatus:
    """Resolve current OpenRouter usage for narrative + sentiment backends."""
    fund = getattr(config, "fundamental", None)
    sentiment_backend = getattr(fund, "sentiment_backend", "mock") if fund else "mock"

    api_key = synthesizer.api_key
    api_key_configured = bool(api_key)

    narrative_model: Optional[str] = None
    narrative_error: Optional[str] = None
    budget_used, budget_cap = synthesizer.budget_snapshot()

    if api_key_configured and synthesizer.budget_available():
        try:
            narrative_model = await synthesizer.model
        except Exception as exc:  # noqa: BLE001
            narrative_error = str(exc)[:120]
            narrative_model = synthesizer.cached_model_id()
    elif api_key_configured:
        narrative_error = "daily budget exhausted"

    sentiment_model: Optional[str] = None
    sentiment_error: Optional[str] = None
    sentiment_or_active = False

    if sentiment_backend == "openrouter" and sentiment_scorer.openrouter_key_configured():
        sentiment_or_active = True
        cached = sentiment_scorer.cached_openrouter_model()
        if cached:
            sentiment_model = cached
        else:
            try:
                from src.fundamental.synthesizer import PREFERRED_FREE_MODELS

                sentiment_model = await select_available_free_model(
                    preferred=PREFERRED_FREE_MODELS,
                    api_key=sentiment_scorer.openrouter_api_key(),
                )
            except Exception as exc:  # noqa: BLE001
                sentiment_error = str(exc)[:120]

    return OpenRouterStatus(
        api_key_configured=api_key_configured,
        narrative_enabled=api_key_configured,
        narrative_model=narrative_model,
        narrative_model_error=narrative_error,
        narrative_budget_used=budget_used,
        narrative_budget_cap=budget_cap,
        sentiment_backend=sentiment_backend,
        sentiment_openrouter_active=sentiment_or_active and sentiment_model is not None,
        sentiment_model=sentiment_model,
        sentiment_model_error=sentiment_error,
    )


def format_openrouter_status_telegram(status: OpenRouterStatus) -> str:
    """Format OpenRouter block for Telegram HTML /status."""
    lines = ["<b>OpenRouter LLM:</b>"]

    if not status.api_key_configured:
        lines.append("🔑 API key: <b>not set</b> (template narratives only)")
        lines.append(
            f"📊 Sentiment backend: <code>{status.sentiment_backend.upper()}</code>"
        )
        return "\n".join(lines)

    lines.append("🔑 API key: <b>configured</b>")

    if status.narrative_active:
        lines.append(
            f"📝 Narrative: <b>ACTIVE</b> — <code>{status.narrative_model}</code>"
        )
        lines.append(
            f"   Budget today: ${status.narrative_budget_used:.2f} / "
            f"${status.narrative_budget_cap:.2f}"
        )
    elif status.narrative_model_error:
        lines.append(f"📝 Narrative: <b>INACTIVE</b> — {status.narrative_model_error}")
    else:
        lines.append("📝 Narrative: <b>INACTIVE</b>")

    if status.sentiment_backend == "openrouter":
        if status.sentiment_openrouter_active and status.sentiment_model:
            lines.append(
                f"📊 Sentiment: <b>ACTIVE</b> — <code>{status.sentiment_model}</code>"
            )
        elif status.sentiment_model_error:
            lines.append(f"📊 Sentiment: <b>INACTIVE</b> — {status.sentiment_model_error}")
        else:
            lines.append("📊 Sentiment: <b>openrouter</b> (model not selected yet)")
    else:
        lines.append(
            f"📊 Sentiment: <code>{status.sentiment_backend.upper()}</code> "
            "(not using OpenRouter)"
        )

    return "\n".join(lines)


def format_openrouter_status_oneline(status: OpenRouterStatus) -> str:
    """Single-line OpenRouter summary for /start welcome."""
    if not status.api_key_configured:
        return "LLM: off (no API key — template narratives only)"
    if status.narrative_active and status.narrative_model:
        return f"LLM: <code>{status.narrative_model}</code> (narrative active)"
    if status.sentiment_openrouter_active and status.sentiment_model:
        return f"LLM: <code>{status.sentiment_model}</code> (sentiment active)"
    if status.narrative_model_error:
        return f"LLM: inactive ({status.narrative_model_error[:60]})"
    return "LLM: key set, awaiting model selection"