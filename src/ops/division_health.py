"""D11-OPS — Periodic division health heartbeats for Telegram /status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.core.bus import Bus
from src.core.contracts import BusChannel, HealthStatus, SystemHealthEvent
from src.core.ids import new_signal_id
from src.core.logging import get_logger

_log = get_logger("D11-OPS")

_STATUS_MAP = {
    "ok": HealthStatus.OK,
    "degraded": HealthStatus.DEGRADED,
    "down": HealthStatus.DOWN,
}


def _to_health(status: str) -> HealthStatus:
    return _STATUS_MAP.get(status, HealthStatus.DEGRADED)


async def publish_division_heartbeats(
    bus: Bus,
    snapshot: dict[str, Any],
    *,
    notifier_active: bool = False,
    fundamental_active: bool = False,
    decision_active: bool = True,
) -> None:
    """Publish per-division SystemHealthEvent so /status is never all UNKNOWN."""
    now = datetime.now(timezone.utc)
    overall = snapshot.get("status", "ok")
    data = snapshot.get("data_freshness", {})
    signals = snapshot.get("signal_flow", {})
    execution = snapshot.get("execution", {})
    model = snapshot.get("model_registry", {})

    divisions: list[tuple[str, HealthStatus, str]] = [
        ("D01-CORE", HealthStatus.OK, "Application runtime active"),
        ("D02-DATA", _to_health(data.get("status", "ok")), data.get("message", "Data pipeline")),
        (
            "D03-FUNDAMENTAL",
            HealthStatus.OK if fundamental_active else HealthStatus.DEGRADED,
            "Fundamental agent running" if fundamental_active else "Fundamental agent inactive",
        ),
        (
            "D04-TECHNICAL",
            _to_health(signals.get("status", "ok")),
            signals.get("message", "Technical signal flow"),
        ),
        (
            "D05-DECISION",
            HealthStatus.OK if decision_active else HealthStatus.DEGRADED,
            "Decision engine active" if decision_active else "Decision engine inactive",
        ),
        (
            "D06-EXECUTION",
            _to_health(execution.get("status", "ok")),
            execution.get("message", "Execution engine"),
        ),
        (
            "D07-NOTIFIER",
            HealthStatus.OK if notifier_active else HealthStatus.DEGRADED,
            "Telegram notifier active" if notifier_active else "Telegram notifier inactive",
        ),
        ("D11-OPS", _to_health(overall), f"Ops monitor: {overall}"),
    ]

    if model.get("status") == "down":
        divisions.append(
            ("D09-TRAINER", HealthStatus.DOWN, model.get("message", "Model registry issue"))
        )
    elif model.get("status") == "degraded":
        divisions.append(
            ("D09-TRAINER", HealthStatus.DEGRADED, model.get("message", "Model registry degraded"))
        )
    else:
        divisions.append(
            ("D09-TRAINER", HealthStatus.OK, model.get("message", "Model registry ok"))
        )

    for division, status, message in divisions:
        event = SystemHealthEvent(
            signal_id=new_signal_id(),
            division=division,
            status=status,
            timestamp=now,
            message=message,
            metrics={},
        )
        await bus.publish(BusChannel.SYSTEM_HEALTH, event)

    _log.debug(
        "division_heartbeats_published",
        overall=overall,
        divisions=len(divisions),
    )