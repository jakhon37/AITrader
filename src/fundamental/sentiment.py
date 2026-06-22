"""D03-FUNDAMENTAL — Sentiment scoring using FinBERT.

Scores text (headline + body snippet) using ProsusAI/finbert to produce
a sentiment score from -1.0 (strongly negative) to +1.0 (strongly positive).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List

from src.core.logging import get_logger

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
    """Wraps FinBERT model and tokenizer for async-friendly batched inference."""

    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        use_mock: bool = False,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.model_name = model_name
        self.use_mock = use_mock or not _torch_available
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="finbert-worker")

        self.tokenizer = None
        self.model = None
        self.device = "cpu"

        if self.use_mock:
            _log.info("sentiment_scorer_init_mock", reason="Using mock sentiment scorer.")
        else:
            _log.info("sentiment_scorer_init_lazy", model=model_name)

    def load(self) -> None:
        """Eagerly load the model and tokenizer into memory/device."""
        if self.use_mock:
            return

        if self.model is not None:
            return

        _log.info("sentiment_scorer_loading_model", model=self.model_name)
        try:
            # Set stubs or load weights
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model.to(self.device)
            self.model.eval()
            _log.info("sentiment_scorer_loaded", device=self.device)
        except Exception as e:
            _log.error("sentiment_scorer_load_failed", error=str(e))
            _log.warning("sentiment_scorer_falling_back_to_mock")
            self.use_mock = True

    def _score_batch_sync(self, texts: List[str]) -> List[float]:
        """Synchronous CPU/GPU sentiment scoring execution."""
        if self.use_mock:
            return self._score_batch_mock(texts)

        self.load()

        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        # Move tensors to device
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            # FinBERT labels: [positive, negative, neutral]
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

        # positive_prob - negative_prob
        # ProsusAI/finbert outputs: index 0 = positive, index 1 = negative, index 2 = neutral
        pos = probs[:, 0].cpu().numpy()
        neg = probs[:, 1].cpu().numpy()
        scores = pos - neg

        return [float(s) for s in scores]

    def _score_batch_mock(self, texts: List[str]) -> List[float]:
        """Simple rule-based heuristic fallback for unit tests and environment bypass."""
        scores = []
        for text in texts:
            lower_text = text.lower()
            score = 0.0
            # Simple keyword counts
            positive_words = [
                "bullish", "hike", "strong", "growth", "beat", "positive", "raise", "increase",
                "upward", "gain", "recover", "expansion", "hawkish"
            ]
            negative_words = [
                "bearish", "cut", "weak", "decline", "miss", "negative", "lower", "decrease",
                "downward", "loss", "drop", "contraction", "dovish", "tariff", "war", "sanction"
            ]

            pos_count = sum(lower_text.count(w) for w in positive_words)
            neg_count = sum(lower_text.count(w) for w in negative_words)

            if pos_count > neg_count:
                score = 0.4 + 0.1 * min(pos_count - neg_count, 5)
            elif neg_count > pos_count:
                score = -0.4 - 0.1 * min(neg_count - pos_count, 5)

            scores.append(max(-1.0, min(1.0, score)))
        return scores

    async def score_batch(self, texts: List[str], batch_size: int = 8) -> List[float]:
        """Run batched inference asynchronously in a thread executor."""
        if not texts:
            return []

        loop = asyncio.get_running_loop()
        results: List[float] = []

        # Batch texts to prevent OOM
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_scores = await loop.run_in_executor(
                self.executor,
                self._score_batch_sync,
                batch,
            )
            results.extend(batch_scores)

        return results
