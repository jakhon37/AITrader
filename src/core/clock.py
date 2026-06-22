"""VirtualClock — all current-time access goes through here.

BANNED everywhere outside this file:
    datetime.utcnow()
    datetime.now()          (without explicit tz)
    time.time()

CORRECT usage from any division:
    from src.core.clock import now
    ts = now()   # always UTC, always timezone-aware

D08-BACKTEST is the ONLY division allowed to call ControllableClock methods
(set_replay_time, advance, reset_to_live). All other divisions just call now().
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol, runtime_checkable


# ── Enums ─────────────────────────────────────────────────────────────────────

class ClockMode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"


# ── Protocols ─────────────────────────────────────────────────────────────────

@runtime_checkable
class VirtualClock(Protocol):
    """Read-only clock protocol. All divisions depend only on this."""

    def now(self) -> datetime:
        """Return current time as UTC timezone-aware datetime."""
        ...

    def mode(self) -> ClockMode:
        """Return LIVE or REPLAY."""
        ...


@runtime_checkable
class ControllableClock(VirtualClock, Protocol):
    """Extended clock protocol. D08-BACKTEST only.

    Within D08's feed loop, advance() MUST be called and awaited
    before bus.publish() — reversing this order opens look-ahead bias.
    """

    def set_replay_time(self, dt: datetime) -> None:
        """Jump the replay clock to the given UTC datetime."""
        ...

    def advance(self, delta: timedelta) -> None:
        """Advance the replay clock by the given timedelta."""
        ...

    def reset_to_live(self) -> None:
        """Switch back to live mode and discard the replay time."""
        ...


# ── Implementations ───────────────────────────────────────────────────────────

class LiveClock:
    """Returns real UTC wall-clock time. Default for production."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def mode(self) -> ClockMode:
        return ClockMode.LIVE


class ReplayClock:
    """Controllable clock for backtesting / replay.

    Thread-safe: a threading.Lock covers both reads AND writes to _replay_time,
    preventing torn reads under concurrent D08 feed loop + D10 WebSocket threads.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._mode: ClockMode = ClockMode.REPLAY
        self._replay_time: datetime = (
            start if start is not None else datetime.now(timezone.utc)
        )
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._replay_time

    def mode(self) -> ClockMode:
        return self._mode

    def set_replay_time(self, dt: datetime) -> None:
        """Jump to the given UTC datetime. Raises ValueError if not UTC-aware."""
        if dt.tzinfo is None:
            raise ValueError("set_replay_time requires a timezone-aware UTC datetime.")
        with self._lock:
            self._replay_time = dt.astimezone(timezone.utc)
            self._mode = ClockMode.REPLAY

    def advance(self, delta: timedelta) -> None:
        """Advance replay time by delta. Must be called before bus.publish() in feed loop."""
        with self._lock:
            self._replay_time += delta

    def reset_to_live(self) -> None:
        """Discard replay time and return to LIVE mode."""
        with self._lock:
            self._mode = ClockMode.LIVE
            self._replay_time = datetime.now(timezone.utc)


# ── Module-level singleton and accessor ───────────────────────────────────────

# The global clock instance.  Replaced at startup by the composition root:
#   from src.core.clock import set_clock
#   set_clock(LiveClock())          # live trading
#   set_clock(ReplayClock(start))   # backtesting
_clock: VirtualClock = LiveClock()


def set_clock(clock: VirtualClock) -> None:
    """Called once at application startup to inject the clock implementation."""
    global _clock  # noqa: PLW0603
    _clock = clock


def now() -> datetime:
    """Return current time from the active VirtualClock.

    This is the ONLY way to get the current time in any division.
    datetime.now() and datetime.utcnow() are banned outside this file.
    """
    return _clock.now()


def clock_mode() -> ClockMode:
    """Return LIVE or REPLAY mode of the current clock."""
    return _clock.mode()


def get_clock() -> VirtualClock:
    """Return the current clock instance (needed by D08 for ControllableClock casts)."""
    return _clock
