"""Unit tests for chart display timezone formatting."""

from __future__ import annotations

from datetime import datetime, timezone

from src.core.display_time import format_chart_time, resolve_display_timezone


def test_resolve_display_timezone_fallback() -> None:
    assert resolve_display_timezone("Not/A/Zone") == "UTC"
    assert resolve_display_timezone("Asia/Seoul") == "Asia/Seoul"


def test_format_chart_time_uses_zone() -> None:
    dt = datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)
    formatted = format_chart_time(dt, "Asia/Seoul", include_date=True)
    assert "2026-06-27" in formatted
    assert "21:00" in formatted