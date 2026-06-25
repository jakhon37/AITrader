"""D03-FUNDAMENTAL — AI News narrative synthesis.

Sends scored news events to OpenRouter to produce concise qualitative summaries
for traders. Enforces budget caps and fails safe (returns local template narrative)
on error/timeout.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from src.core.clock import now
from src.core.contracts import Direction, EconomicEvent, Instrument
from src.core.logging import get_logger

_log = get_logger("D03-FUNDAMENTAL")

# Preferred free models on OpenRouter (ordered by preference/quality)
# These are commonly available on free tier but can go offline.
PREFERRED_FREE_MODELS: List[str] = [
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-2-9b-it:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "huggingfaceh4/zephyr-7b-beta:free",
]

# Simple cache for available models
_available_models_cache: Dict[str, Any] = {"models": [], "fetched_at": None}
_CACHE_TTL = timedelta(minutes=15)


async def _fetch_available_models(api_key: Optional[str] = None) -> List[str]:
    """Fetch list of models from OpenRouter and return their IDs."""
    url = "https://openrouter.ai/api/v1/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
    except Exception as e:
        _log.warning("openrouter_models_fetch_failed", error=str(e))
        return []


async def get_available_free_models(api_key: Optional[str] = None, force_refresh: bool = False) -> List[str]:
    """Return currently available free models on OpenRouter (cached)."""
    now_dt = now()
    cache = _available_models_cache

    if (
        not force_refresh
        and cache["models"]
        and cache["fetched_at"]
        and (now_dt - cache["fetched_at"]) < _CACHE_TTL
    ):
        return cache["models"]

    all_models = await _fetch_available_models(api_key)
    free_models = [m for m in all_models if ":free" in m or m.endswith(":free")]

    cache["models"] = free_models
    cache["fetched_at"] = now_dt
    _log.info("openrouter_free_models_refreshed", count=len(free_models))
    return free_models


async def select_available_free_model(
    preferred: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> str:
    """Pick the first preferred free model that is currently available.
    Falls back to first available free model or a hardcoded default.
    """
    prefs = preferred or PREFERRED_FREE_MODELS
    available_free = await get_available_free_models(api_key)

    # Try preferred first
    for model in prefs:
        if model in available_free:
            return model

    # Any free model as fallback
    if available_free:
        # Prefer ones with good context if possible, but simple pick first
        return available_free[0]

    # Ultimate fallback
    _log.warning("openrouter_no_free_models_found", using_fallback=prefs[0])
    return prefs[0]


class NarrativeSynthesizer:
    """Best-effort async client for OpenRouter to synthesize sentiment narratives."""

    def __init__(
        self,
        api_key: str | None = None,
        daily_budget: float = 1.0,
        model: str | None = None,  # If None, will auto-select an available free model
        timeout: float = 8.0,
        preferred_models: Optional[List[str]] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self._preferred_models = preferred_models or PREFERRED_FREE_MODELS
        self.timeout = timeout

        # Model selection is lazy/dynamic to handle availability
        self._model: Optional[str] = model
        self._last_model_selection: Optional[datetime] = None

        try:
            self.budget_cap = float(os.getenv("OPENROUTER_DAILY_BUDGET", str(daily_budget)))
        except ValueError:
            self.budget_cap = daily_budget

        self._daily_spend = 0.0
        self._current_date: date = now().date()

        # Will be set when first used
        self._cost_per_call: float = 0.0

    @property
    async def model(self) -> str:
        """Return a currently available free model (auto-selects if needed)."""
        now_dt = now()
        if (
            self._model is None
            or self._last_model_selection is None
            or (now_dt - self._last_model_selection) > timedelta(minutes=10)
        ):
            self._model = await select_available_free_model(
                preferred=self._preferred_models,
                api_key=self.api_key,
            )
            self._last_model_selection = now_dt
            self._cost_per_call = 0.0 if ":free" in self._model else 0.0005
            _log.info("openrouter_model_selected", model=self._model)

        return self._model

    def _update_and_check_budget(self) -> bool:
        """Reset budget daily and check if budget has been exceeded."""
        today = now().date()
        if today != self._current_date:
            self._current_date = today
            self._daily_spend = 0.0

        if self._daily_spend >= self.budget_cap:
            _log.warning(
                "synthesizer_budget_exceeded",
                spend=self._daily_spend,
                cap=self.budget_cap,
            )
            return False
        return True

    def _generate_fallback_narrative(
        self,
        instrument: Instrument,
        direction: Direction,
        headline: str,
        score: float,
    ) -> str:
        """Generate a basic rule-based template summary if LLM call is bypassed/fails."""
        dir_word = "bullish" if direction == Direction.LONG else "bearish" if direction == Direction.SHORT else "neutral"
        return (
            f"Sentiment for {instrument.value} is currently {dir_word} "
            f"(FinBERT score: {score:+.2f}) driven by headline: '{headline[:120]}...'"
        )

    async def get_narrative(
        self,
        instrument: Instrument,
        direction: Direction,
        headline: str,
        score: float,
        body_snippet: str | None = None,
    ) -> str:
        """Call OpenRouter to synthesize narrative, fallback to template on failure."""
        fallback = self._generate_fallback_narrative(instrument, direction, headline, score)

        if not self.api_key:
            _log.debug("synthesizer_skip_no_api_key")
            return fallback

        if not self._update_and_check_budget():
            return fallback

        current_model = await self.model  # dynamic selection of available free model

        prompt = (
            f"You are a professional Forex research analyst. Synthesize a concise market narrative "
            f"(under 60 words) for a trader monitoring {instrument.value}. "
            f"The primary news trigger is: '{headline}' "
            f"with scoring {direction.value.upper()} (Sentiment index {score:+.2f}). "
            f"Snippet: '{body_snippet or ''}'"
            f"Summarize what this means for {instrument.value} pricing and macro expectations."
        )

        try:
            # We construct a client manually to allow customized timeouts and error management
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/jakhon37/AITrader",
                    "X-Title": "AITrader System",
                }
                payload = {
                    "model": current_model,
                    "messages": [
                        {"role": "system", "content": "You provide short, professional financial insights."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 100,
                }

                _log.debug("synthesizer_api_request", instrument=instrument.value, model=current_model)
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    self._daily_spend += self._cost_per_call
                    _log.debug("synthesizer_api_success", spend=self._daily_spend, model=current_model)
                    return content
                else:
                    if response.status_code in (400, 404):  # model likely unavailable
                        self._last_model_selection = None  # force reselect next time
                    _log.warning(
                        "synthesizer_api_error_code",
                        status_code=response.status_code,
                        response=response.text[:200],
                        model=current_model,
                    )
                    return fallback

        except httpx.TimeoutException:
            _log.warning("synthesizer_api_timeout", timeout=self.timeout)
            return fallback
        except Exception as e:
            _log.error("synthesizer_api_failed", error=str(e))
            return fallback

    def _generate_fallback_calendar_briefing(
        self,
        instrument: Instrument,
        event: EconomicEvent,
        minutes_until: int,
    ) -> str:
        """Rule-based pre-release briefing when OpenRouter is unavailable."""
        impact = event.impact.upper()
        pairs = ", ".join(i.value for i in event.affected_pairs) or instrument.value
        forecast = event.forecast if event.forecast is not None else "n/a"
        previous = event.previous if event.previous is not None else "n/a"
        return (
            f"{impact} impact event '{event.name}' in ~{minutes_until}m. "
            f"Watch {pairs}. Forecast {forecast}, prior {previous}. "
            f"Expect elevated volatility around release; reduce size or widen stops."
        )

    async def get_calendar_briefing(
        self,
        instrument: Instrument,
        event: EconomicEvent,
        minutes_until: int,
    ) -> str:
        """Synthesize a pre-release calendar briefing for traders."""
        fallback = self._generate_fallback_calendar_briefing(instrument, event, minutes_until)

        if not self.api_key:
            _log.debug("synthesizer_calendar_skip_no_api_key")
            return fallback

        if not self._update_and_check_budget():
            return fallback

        current_model = await self.model
        pairs = ", ".join(i.value for i in event.affected_pairs) or instrument.value
        forecast = event.forecast if event.forecast is not None else "unknown"
        previous = event.previous if event.previous is not None else "unknown"

        prompt = (
            f"You are a professional FX macro strategist. An economic release is scheduled in "
            f"{minutes_until} minutes.\n"
            f"Event: {event.name}\n"
            f"Impact: {event.impact}\n"
            f"Affected pairs: {pairs}\n"
            f"Forecast: {forecast} | Previous: {previous}\n"
            f"Focus instrument: {instrument.value}\n\n"
            f"In under 80 words, explain: (1) why this matters, (2) directional bias if "
            f"forecast is met vs beat/miss, (3) practical risk for {instrument.value} traders."
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/jakhon37/AITrader",
                    "X-Title": "AITrader System",
                }
                payload = {
                    "model": current_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You provide concise, actionable pre-event macro briefings.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.25,
                    "max_tokens": 140,
                }

                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    self._daily_spend += self._cost_per_call
                    return content

                if response.status_code in (400, 404):
                    self._last_model_selection = None
                _log.warning(
                    "synthesizer_calendar_api_error",
                    status_code=response.status_code,
                    model=current_model,
                )
                return fallback

        except httpx.TimeoutException:
            _log.warning("synthesizer_calendar_timeout", timeout=self.timeout)
            return fallback
        except Exception as e:
            _log.error("synthesizer_calendar_failed", error=str(e))
            return fallback
