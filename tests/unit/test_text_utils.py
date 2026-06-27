"""Tests for LLM narrative plain-text sanitization."""

from src.fundamental.text_utils import is_safety_classifier_response, sanitize_llm_narrative


def test_is_safety_classifier_response_detects_metadata() -> None:
    assert is_safety_classifier_response("User Safety: safe") is True
    assert is_safety_classifier_response("User Safety: safe\nResponse Safety: safe") is True
    assert is_safety_classifier_response("Hi there, your equity is $100k.") is False


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