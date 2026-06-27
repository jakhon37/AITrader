"""Display-time formatting — UTC storage, user-facing chart timezone output."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_DISPLAY_TIMEZONE = "UTC"


def resolve_display_timezone(tz_name: str | None) -> str:
    """Return a valid IANA timezone name for formatting."""
    if not tz_name or not tz_name.strip():
        return DEFAULT_DISPLAY_TIMEZONE
    name = tz_name.strip()
    try:
        ZoneInfo(name)
        return name
    except ZoneInfoNotFoundError:
        return DEFAULT_DISPLAY_TIMEZONE


def timezone_label(tz_name: str) -> str:
    """Short timezone label (e.g. KST, EST) for display suffixes."""
    resolved = resolve_display_timezone(tz_name)
    try:
        label = datetime.now(timezone.utc).astimezone(ZoneInfo(resolved)).strftime("%Z")
        return label if label else resolved
    except Exception:
        return resolved


def format_chart_time(
    dt: datetime,
    tz_name: str | None,
    *,
    include_date: bool = False,
    include_seconds: bool = False,
) -> str:
    """Format a UTC-aware datetime in the user's chart timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    resolved = resolve_display_timezone(tz_name)
    local = dt.astimezone(ZoneInfo(resolved))
    if include_date:
        fmt = "%Y-%m-%d %H:%M"
    else:
        fmt = "%H:%M"
    if include_seconds:
        fmt += ":%S"
    return f"{local.strftime(fmt)} {timezone_label(resolved)}"