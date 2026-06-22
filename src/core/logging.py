"""Structured logging factory for AITrader divisions.

Usage in any division:
    from src.core.logging import get_logger
    log = get_logger("D02-DATA")
    log.info("bar_received", instrument="EURUSD", signal_id=sid)

Every logger is pre-bound with {"division": name} so every log record carries
the originating division automatically.  Signal-scoped logging uses .bind():
    log = log.bind(signal_id=signal.signal_id, instrument=signal.instrument)
    log.info("signal_published")

Output: JSON lines to stdout.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Try structlog; fall back to stdlib JSON logging when structlog isn't installed
# ---------------------------------------------------------------------------
try:
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    def get_logger(division: str) -> Any:  # noqa: ANN401 — structlog is Any-typed
        """Return a structlog BoundLogger pre-bound with the division name."""
        return structlog.get_logger(division).bind(division=division)

except ModuleNotFoundError:  # structlog not installed — use stdlib JSON
    import json

    class _JsonLogger:
        """Minimal JSON-line logger matching structlog's BoundLogger surface."""

        def __init__(self, division: str, extra: dict[str, Any] | None = None) -> None:
            self._division = division
            self._extra: dict[str, Any] = extra or {}

        def bind(self, **kwargs: Any) -> "_JsonLogger":
            return _JsonLogger(self._division, {**self._extra, **kwargs})

        def _emit(self, level: str, event: str, **kwargs: Any) -> None:
            import datetime

            record = {
                "level": level,
                "division": self._division,
                "event": event,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                **self._extra,
                **kwargs,
            }
            print(json.dumps(record), flush=True)

        def debug(self, event: str, **kw: Any) -> None:
            self._emit("debug", event, **kw)

        def info(self, event: str, **kw: Any) -> None:
            self._emit("info", event, **kw)

        def warning(self, event: str, **kw: Any) -> None:
            self._emit("warning", event, **kw)

        def error(self, event: str, **kw: Any) -> None:
            self._emit("error", event, **kw)

        def exception(self, event: str, **kw: Any) -> None:
            import traceback

            self._emit("error", event, exc_info=traceback.format_exc(), **kw)

    def get_logger(division: str) -> _JsonLogger:  # type: ignore[misc]
        """Return a minimal JSON logger pre-bound with the division name."""
        return _JsonLogger(division)
