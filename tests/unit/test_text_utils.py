"""Tests for LLM narrative plain-text sanitization."""

from src.fundamental.text_utils import sanitize_llm_narrative


def test_sanitize_llm_narrative_strips_markdown() -> None:
    raw = (
        "**Why it matters:** A high‑impact FOMC member's speech can shift expectations. "
        "**Directional bias:** - **"
    )
    cleaned = sanitize_llm_narrative(raw)
    assert "**" not in cleaned
    assert "Why it matters:" in cleaned
    assert cleaned.endswith("expectations.") or "expectations" in cleaned
    assert not cleaned.endswith("-")