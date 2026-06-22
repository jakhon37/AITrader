"""D07-NOTIFIER — Message routing and filter logic.

Determines if a given bus event should trigger a notification based on quiet hours,
signal confidence, direction, strength thresholds, and event status.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List

from src.core.contracts import (
    Direction,
    FundamentalSignal,
    HealthStatus,
    OrderEvent,
    SignalStrength,
    SystemHealthEvent,
    TradeSignal,
)
from src.core.logging import get_logger

_log = get_logger("D07-NOTIFIER")


class MessageRouter:
    """Evaluates notification filters, including quiet-hours checks and severity filters."""

    def __init__(self, config_dict: Dict[str, Any] | None = None) -> None:
        # Fallback default configuration if not provided in YAML
        self.cfg = config_dict or {
            "telegram": {
                "trade_signal": {
                    "enabled": True,
                    "min_confidence": 0.5,
                    "directions": ["long", "short"],
                },
                "fundamental_signal": {
                    "enabled": True,
                    "min_strength": "strong",
                },
                "technical_signal": {
                    "enabled": False,
                },
                "order_event": {
                    "enabled": True,
                    "event_types": ["filled", "rejected"],
                },
                "system_health": {
                    "enabled": True,
                    "min_status": "degraded",
                },
                "quiet_hours": {
                    "start": "22:00",
                    "end": "06:00",
                    "override_for": ["system_health", "order_event"],
                },
            }
        }

        # Value maps for comparisons
        self._strength_map = {
            SignalStrength.WEAK: 0,
            SignalStrength.MODERATE: 1,
            SignalStrength.STRONG: 2,
        }
        self._strength_str_map = {
            "weak": SignalStrength.WEAK,
            "moderate": SignalStrength.MODERATE,
            "strong": SignalStrength.STRONG,
        }

        self._health_map = {
            HealthStatus.OK: 0,
            HealthStatus.DEGRADED: 1,
            HealthStatus.DOWN: 2,
        }
        self._health_str_map = {
            "ok": HealthStatus.OK,
            "degraded": HealthStatus.DEGRADED,
            "down": HealthStatus.DOWN,
        }

    def in_quiet_hours(self, current_time: datetime) -> bool:
        """Check if the current UTC time is inside configured quiet hours."""
        qh = self.cfg.get("telegram", {}).get("quiet_hours", {})
        if not qh or not qh.get("start") or not qh.get("end"):
            return False

        try:
            start_h, start_m = map(int, qh["start"].split(":"))
            end_h, end_m = map(int, qh["end"].split(":"))
        except (ValueError, AttributeError):
            return False

        t = current_time.time()
        start_t = time(start_h, start_m)
        end_t = time(end_h, end_m)

        if start_t <= end_t:
            return start_t <= t <= end_t
        else:
            # Spans over midnight
            return t >= start_t or t <= end_t

    def _respects_quiet_hours(self, event_type: str, current_time: datetime) -> bool:
        """Return True if quiet hours allow sending this event type."""
        if not self.in_quiet_hours(current_time):
            return True

        qh = self.cfg.get("telegram", {}).get("quiet_hours", {})
        overrides = qh.get("override_for", [])
        return event_type in overrides

    def should_send_trade_signal(self, signal: TradeSignal, current_time: datetime) -> bool:
        """Validate if a TradeSignal should trigger a notification."""
        rules = self.cfg.get("telegram", {}).get("trade_signal", {})
        if not rules.get("enabled", True):
            return False

        if not self._respects_quiet_hours("trade_signal", current_time):
            return False

        # Confidence checks
        if signal.confidence < rules.get("min_confidence", 0.0):
            return False

        # Direction checks
        allowed_dirs = rules.get("directions", ["long", "short"])
        if signal.direction.value not in allowed_dirs:
            return False

        return True

    def should_send_order_event(self, event: OrderEvent, current_time: datetime) -> bool:
        """Validate if an OrderEvent should trigger a notification."""
        rules = self.cfg.get("telegram", {}).get("order_event", {})
        if not rules.get("enabled", True):
            return False

        if not self._respects_quiet_hours("order_event", current_time):
            return False

        allowed_types = rules.get("event_types", ["created", "filled", "cancelled", "rejected"])
        if event.event_type not in allowed_types:
            return False

        return True

    def should_send_fundamental_signal(self, signal: FundamentalSignal, current_time: datetime) -> bool:
        """Validate if a FundamentalSignal should trigger a notification."""
        rules = self.cfg.get("telegram", {}).get("fundamental_signal", {})
        if not rules.get("enabled", True):
            return False

        if not self._respects_quiet_hours("fundamental_signal", current_time):
            return False

        # Strength check
        min_strength_str = rules.get("min_strength", "weak").lower()
        min_strength_enum = self._strength_str_map.get(min_strength_str, SignalStrength.WEAK)

        sig_strength_val = self._strength_map.get(signal.strength, 0)
        min_strength_val = self._strength_map.get(min_strength_enum, 0)

        if sig_strength_val < min_strength_val:
            return False

        return True

    def should_send_system_health(self, event: SystemHealthEvent, current_time: datetime) -> bool:
        """Validate if a SystemHealthEvent should trigger a notification."""
        rules = self.cfg.get("telegram", {}).get("system_health", {})
        if not rules.get("enabled", True):
            return False

        if not self._respects_quiet_hours("system_health", current_time):
            return False

        # Severity check
        min_status_str = rules.get("min_status", "ok").lower()
        min_status_enum = self._health_str_map.get(min_status_str, HealthStatus.OK)

        event_status_val = self._health_map.get(event.status, 0)
        min_status_val = self._health_map.get(min_status_enum, 0)

        if event_status_val < min_status_val:
            return False

        return True
