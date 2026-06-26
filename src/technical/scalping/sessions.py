"""Trading session windows from MT4 i-Sessions indicator."""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from src.technical.scalping.params import ASIA_SESSION, EU_SESSION, US_SESSION


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _in_window(clock: time, start: str, end: str) -> bool:
    start_t = _parse_hhmm(start)
    end_t = _parse_hhmm(end)
    if start_t <= end_t:
        return start_t <= clock <= end_t
    # Overnight wrap (not used in template, but safe)
    return clock >= start_t or clock <= end_t


def active_scalping_session(dt: datetime) -> Optional[str]:
    """Return active session label (asia/eu/us) or None.

    Uses the clock time of ``dt`` (broker/server timezone should be applied
    upstream if offsets differ from stored bar timestamps).
    """
    clock = dt.time().replace(second=0, microsecond=0)
    if _in_window(clock, *ASIA_SESSION):
        return "asia"
    if _in_window(clock, *EU_SESSION):
        return "eu"
    if _in_window(clock, *US_SESSION):
        return "us"
    return None


def is_scalping_session_open(dt: datetime) -> bool:
    """True when price action falls inside any MT4 template session box."""
    return active_scalping_session(dt) is not None