"""Plain-text cleanup for LLM narratives shown in UI and Telegram."""

from __future__ import annotations

import re


def sanitize_llm_narrative(text: str) -> str:
    """Strip markdown artifacts from model output for plain-text surfaces."""
    if not text:
        return text

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")

    # **bold** and *italic*
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)

    # Markdown headings
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)

    # Bullet / numbered list prefixes
    cleaned = re.sub(r"^[\s]*[-*•]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\d+\.\s+", "", cleaned, flags=re.MULTILINE)

    # Dangling emphasis markers (truncated output)
    cleaned = re.sub(r"\*+\s*$", "", cleaned)
    cleaned = re.sub(r"[-•]\s*$", "", cleaned)

    # Collapse whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()