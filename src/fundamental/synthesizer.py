"""D03-FUNDAMENTAL — AI News narrative synthesis.

Sends scored news events to OpenRouter to produce concise qualitative summaries
for traders. Enforces budget caps and fails safe (returns local template narrative)
on error/timeout.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Dict, List

import httpx

from src.core.clock import now
from src.core.contracts import Direction, Instrument
from src.core.logging import get_logger

_log = get_logger("D03-FUNDAMENTAL")


class NarrativeSynthesizer:
    """Best-effort async client for OpenRouter to synthesize sentiment narratives."""

    def __init__(
        self,
        api_key: str | None = None,
        daily_budget: float = 1.0,
        model: str = "mistralai/mistral-7b-instruct:free",
        timeout: float = 8.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.timeout = timeout

        try:
            self.budget_cap = float(os.getenv("OPENROUTER_DAILY_BUDGET", str(daily_budget)))
        except ValueError:
            self.budget_cap = daily_budget

        self._daily_spend = 0.0
        self._current_date: date = now().date()

        # Hardcoded cost estimates to avoid complex calculations
        # mistralai/mistral-7b-instruct:free -> 0.0
        # For standard non-free models (e.g. Claude Haiku), estimate $0.0005 per call.
        self._cost_per_call = 0.0 if ":free" in self.model else 0.0005

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
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You provide short, professional financial insights."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 100,
                }

                _log.debug("synthesizer_api_request", instrument=instrument.value, model=self.model)
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    self._daily_spend += self._cost_per_call
                    _log.debug("synthesizer_api_success", spend=self._daily_spend)
                    return content
                else:
                    _log.warning(
                        "synthesizer_api_error_code",
                        status_code=response.status_code,
                        response=response.text[:200],
                    )
                    return fallback

        except httpx.TimeoutException:
            _log.warning("synthesizer_api_timeout", timeout=self.timeout)
            return fallback
        except Exception as e:
            _log.error("synthesizer_api_failed", error=str(e))
            return fallback
