"""Immutable audit log for all trading actions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.core.clock import now
from src.core.logging import get_logger

_log = get_logger("D06-EXECUTION")


class EventType(Enum):
    """Audit event types."""

    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    POSITION_OPEN = "position_open"
    POSITION_CLOSE = "position_close"
    SIGNAL_GENERATED = "signal_generated"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    RISK_VIOLATION = "risk_violation"
    CIRCUIT_BREAKER_HALT = "circuit_breaker_halt"
    CIRCUIT_BREAKER_RESUME = "circuit_breaker_resume"
    ERROR = "error"
    CONFIG_CHANGE = "config_change"


@dataclass
class AuditEvent:
    """Single audit event."""

    timestamp: datetime
    event_type: EventType
    message: str
    signal_id: str
    data: dict[str, Any]
    user: str = "system"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "message": self.message,
            "signal_id": self.signal_id,
            "data": self.data,
            "user": self.user,
        }


class AuditLog:
    """Immutable audit log.

    Writes all trading actions to an append-only log file
    for compliance and debugging.
    """

    def __init__(self, log_dir: str = "logs", log_name: str = "audit.jsonl"):
        """Initialize audit log.

        Args:
            log_dir: Directory for log files
            log_name: Log file name
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / log_name

        # Create log file if it doesn't exist
        if not self.log_file.exists():
            self.log_file.touch()

        _log.info("audit_log_initialized", path=str(self.log_file))

        # Log initialization
        self.log(EventType.SYSTEM_START, "Audit log initialized", "unknown", {})

    def log(
        self,
        event_type: EventType,
        message: str,
        signal_id: str = "unknown",
        data: Optional[dict[str, Any]] = None,
        user: str = "system",
    ) -> None:
        """Write event to audit log.

        Args:
            event_type: Type of event
            message: Human-readable message
            signal_id: Signal correlation ID
            data: Additional data to log
            user: User who triggered the event
        """
        event = AuditEvent(
            timestamp=now(),
            event_type=event_type,
            message=message,
            signal_id=signal_id,
            data=data or {},
            user=user,
        )

        # Append to file (atomic operation)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

        # Also log to standard logger
        _log.info(
            "audit_event_recorded",
            event_type=event_type.value,
            message=message,
            signal_id=signal_id,
        )

    def log_position_open(
        self, symbol: str, side: str, price: float, size: float, signal_id: str = "unknown", **kwargs: Any
    ) -> None:
        """Log position opening."""
        self.log(
            EventType.POSITION_OPEN,
            f"Opened {side} position: {symbol}",
            signal_id,
            {"symbol": symbol, "side": side, "price": price, "size": size, **kwargs},
        )

    def log_position_close(
        self, symbol: str, price: float, pnl: float, signal_id: str = "unknown", **kwargs: Any
    ) -> None:
        """Log position closing."""
        self.log(
            EventType.POSITION_CLOSE,
            f"Closed position: {symbol}, PnL=${pnl:,.2f}",
            signal_id,
            {"symbol": symbol, "price": price, "pnl": pnl, **kwargs},
        )

    def log_signal(self, symbol: str, signal: int, confidence: float = 0.0, signal_id: str = "unknown") -> None:
        """Log trading signal generation."""
        self.log(
            EventType.SIGNAL_GENERATED,
            f"Signal generated: {symbol} = {signal}",
            signal_id,
            {"symbol": symbol, "signal": signal, "confidence": confidence},
        )

    def log_risk_violation(self, violation_type: str, details: str, signal_id: str = "unknown") -> None:
        """Log risk violation."""
        self.log(
            EventType.RISK_VIOLATION,
            f"Risk violation: {violation_type}",
            signal_id,
            {"violation_type": violation_type, "details": details},
        )

    def log_circuit_breaker(self, action: str, reason: str, signal_id: str = "unknown") -> None:
        """Log circuit breaker action."""
        event_type = (
            EventType.CIRCUIT_BREAKER_HALT
            if action == "halt"
            else EventType.CIRCUIT_BREAKER_RESUME
        )
        self.log(event_type, f"Circuit breaker {action}", signal_id, {"reason": reason})

    def log_error(self, error_type: str, error_message: str, signal_id: str = "unknown", **kwargs: Any) -> None:
        """Log error."""
        self.log(
            EventType.ERROR,
            f"Error: {error_type}",
            signal_id,
            {"error_type": error_type, "error_message": error_message, **kwargs},
        )

    def read_events(
        self,
        event_type: Optional[EventType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Read events from audit log.

        Args:
            event_type: Filter by event type
            start_time: Filter events after this time
            end_time: Filter events before this time
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        events = []

        with open(self.log_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue

                event = json.loads(line)

                # Apply filters
                if event_type and event["event_type"] != event_type.value:
                    continue

                event_time = datetime.fromisoformat(event["timestamp"])

                if start_time and event_time < start_time:
                    continue

                if end_time and event_time > end_time:
                    continue

                events.append(event)

                if limit and len(events) >= limit:
                    break

                # Force timezone-aware matching
        return events

    def get_stats(self) -> dict:
        """Get audit log statistics."""
        event_counts = {}
        total_events = 0

        with open(self.log_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue

                event = json.loads(line)
                event_type = event["event_type"]
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
                total_events += 1

        return {"total_events": total_events, "event_counts": event_counts}
