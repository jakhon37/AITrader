"""D03-FUNDAMENTAL — Sentiment scoring using pluggable backends.

Supported backends (via config.fundamental.sentiment_backend):
  - "finbert": Local ProsusAI/finbert (best on GPU, ~700MB RAM)
  - "mock": Fast rule-based (default for low-resource dev machines)
  - "openrouter": Structured LLM call via OpenRouter (cheap/free tier models)

The scorer automatically falls back to mock on load errors.
"""

from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import httpx

from src.core.logging import get_logger
from src.fundamental.synthesizer import (
    get_available_free_models,
    PREFERRED_FREE_MODELS,
    select_available_free_model,
)

_log = get_logger("D03-FUNDAMENTAL")

# Lazy import torch & transformers to avoid blocking startup
_torch_available = False
try:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    _torch_available = True
except ImportError:
    pass


class SentimentScorer:
    """Pluggable sentiment scorer supporting finbert, mock, and openrouter backends.

    Usage from agent:
        scorer = SentimentScorer(backend="openrouter", openrouter_api_key=...)
        scores = await scorer.score_batch(texts, article_ids=ids)  # optional for cache
    """

    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        backend: str = "mock",          # "finbert" | "mock" | "openrouter"
        use_mock: bool = False,         # legacy compat
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,  # None = auto-select available free model
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        # Normalize backend
        if use_mock:
            backend = "mock"
        self.backend = backend.lower() if backend else "mock"

        self.model_name = model_name
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentiment-worker")

        # OpenRouter setup (for "openrouter" backend)
        self._openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self._openrouter_model = openrouter_model  # if None, will auto-select
        self._openrouter_timeout = 8.0
        self._openrouter_preferred = PREFERRED_FREE_MODELS

        # FinBERT state (lazy)
        self.tokenizer = None
        self.model = None
        self.device = "cpu"
        self._finbert_available = _torch_available and self.backend == "finbert"

        # Simple in-memory cache: article_id -> score (or text hash fallback)
        self._cache: Dict[str, float] = {}

        if self.backend == "mock":
            _log.info("sentiment_scorer_init", backend="mock", reason="Using fast rule-based mock scorer (recommended for dev on limited hardware)")
        elif self.backend == "openrouter":
            _log.info("sentiment_scorer_init", backend="openrouter", model=self._openrouter_model or "auto (will select available free)")
        else:
            _log.info("sentiment_scorer_init", backend="finbert", model=model_name)

    def _get_cache_key(self, text: str, article_id: Optional[str] = None) -> str:
        if article_id:
            return f"id:{article_id}"
        # Fallback stable key for text
        return "txt:" + str(hash(text[:200]))  # short hash for demo; use better in prod if needed

    async def score_batch(
        self, texts: List[str], batch_size: int = 8, article_ids: Optional[List[str]] = None
    ) -> List[float]:
        """Score a batch of texts. Returns list of scores in [-1.0, 1.0]."""
        if not texts:
            return []

        results: List[float] = []
        to_score: List[tuple[str, Optional[str], int]] = []  # (text, article_id, original_idx)

        article_ids = article_ids or [None] * len(texts)

        for idx, (text, aid) in enumerate(zip(texts, article_ids)):
            key = self._get_cache_key(text, aid)
            if key in self._cache:
                results.append(self._cache[key])
            else:
                # placeholder, will fill later
                results.append(0.0)
                to_score.append((text, aid, idx))

        if not to_score:
            return results

        # Route by backend
        if self.backend == "finbert":
            new_scores = await self._score_finbert([t for t, _, _ in to_score], batch_size)
        elif self.backend == "openrouter":
            new_scores = await self._score_openrouter([t for t, _, _ in to_score])
        else:
            new_scores = self._score_batch_mock([t for t, _, _ in to_score])

        # Fill results + cache
        for (text, aid, orig_idx), score in zip(to_score, new_scores):
            key = self._get_cache_key(text, aid)
            self._cache[key] = score
            results[orig_idx] = score

        return results

    # ── Backend implementations ───────────────────────────────────────────────

    async def _score_finbert(self, texts: List[str], batch_size: int) -> List[float]:
        """FinBERT path (runs in thread pool)."""
        if not _torch_available:
            _log.warning("finbert_unavailable_falling_back", reason="torch/transformers not installed")
            return self._score_batch_mock(texts)

        loop = asyncio.get_running_loop()

        def _run():
            self._load_finbert()
            # reuse similar logic
            inputs = self.tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            pos = probs[:, 0].cpu().numpy()
            neg = probs[:, 1].cpu().numpy()
            return [float(p - n) for p, n in zip(pos, neg)]

        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_scores = await loop.run_in_executor(self.executor, _run)
            results.extend(batch_scores)
        return results

    def _load_finbert(self) -> None:
        """Internal FinBERT loader (called from thread)."""
        if self.model is not None:
            return
        _log.info("sentiment_loading_finbert", model=self.model_name)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            import torch as _torch  # local import in thread ok
            self.device = "cuda" if _torch.cuda.is_available() else "cpu"
            self.model.to(self.device)
            self.model.eval()
            _log.info("sentiment_finbert_loaded", device=self.device)
        except Exception as e:
            _log.error("sentiment_finbert_load_failed", error=str(e))
            raise

    async def _score_openrouter(self, texts: List[str]) -> List[float]:
        """Use OpenRouter with structured prompt to get sentiment score.
        Dynamically selects an available free model if none was specified.
        """
        if not self._openrouter_api_key:
            _log.debug("openrouter_no_key_fallback_mock")
            return self._score_batch_mock(texts)

        # Dynamic model selection for availability
        if not self._openrouter_model:
            try:
                model_to_use = await select_available_free_model(
                    preferred=self._openrouter_preferred,
                    api_key=self._openrouter_api_key,
                )
            except Exception:
                model_to_use = self._openrouter_preferred[0]
        else:
            model_to_use = self._openrouter_model

        scores: List[float] = []
        for text in texts:
            prompt = (
                "You are a precise financial sentiment analyzer for Forex and Gold. "
                "Return ONLY a JSON object with a single field 'score' (float between -1.0 and 1.0). "
                f"Text: {text[:800]}"
            )
            try:
                async with httpx.AsyncClient(timeout=self._openrouter_timeout) as client:
                    headers = {
                        "Authorization": f"Bearer {self._openrouter_api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/jakhon37/AITrader",
                    }
                    payload = {
                        "model": model_to_use,
                        "messages": [
                            {"role": "system", "content": "Respond with valid JSON only: {\"score\": <float>}"},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 30,
                    }
                    resp = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"].strip()
                        # Try to parse JSON
                        data = json.loads(content)
                        score = float(data.get("score", 0.0))
                        scores.append(max(-1.0, min(1.0, score)))
                    else:
                        if resp.status_code in (400, 404):
                            # model unavailable -> next call will reselect
                            self._openrouter_model = None
                        _log.warning(
                            "openrouter_sentiment_error_code",
                            status_code=resp.status_code,
                            response=resp.text[:200],
                            model=model_to_use,
                        )
                        scores.append(0.0)
            except Exception as e:
                _log.warning("openrouter_sentiment_failed", error=str(e)[:100], model=model_to_use)
                scores.append(0.0)
        return scores

    def _score_batch_mock(self, texts: List[str]) -> List[float]:
        """Rule-based mock (always fast, deterministic)."""
        scores = []
        for text in texts:
            lower_text = text.lower()
            score = 0.0
            positive_words = [
                "bullish", "hike", "strong", "growth", "beat", "positive", "raise", "increase",
                "upward", "gain", "recover", "expansion", "hawkish", "rate decision"
            ]
            negative_words = [
                "bearish", "cut", "weak", "decline", "miss", "negative", "lower", "decrease",
                "downward", "loss", "drop", "contraction", "dovish", "tariff", "war", "sanction", "recession"
            ]
            pos_count = sum(lower_text.count(w) for w in positive_words)
            neg_count = sum(lower_text.count(w) for w in negative_words)
            if pos_count > neg_count:
                score = 0.4 + 0.1 * min(pos_count - neg_count, 5)
            elif neg_count > pos_count:
                score = -0.4 - 0.1 * min(neg_count - pos_count, 5)
            scores.append(max(-1.0, min(1.0, score)))
        return scores

    def clear_cache(self) -> None:
        self._cache.clear()
