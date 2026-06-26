"""D11-OPS — Execution and audit log health checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class ExecutionProbe:
    """Summarize paper-trading activity from the audit log."""

    def __init__(
        self,
        audit_path: str | Path = "logs/audit.jsonl",
        drawdown_degraded_pct: float = 10.0,
        drawdown_down_pct: float = 15.0,
    ) -> None:
        self._audit_path = Path(audit_path)
        self._drawdown_degraded_pct = drawdown_degraded_pct
        self._drawdown_down_pct = drawdown_down_pct

    def check(
        self,
        *,
        drawdown_pct: float | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        counts = {
            "position_open": 0,
            "position_close": 0,
            "order_filled": 0,
            "risk_violation": 0,
            "circuit_breaker_halt": 0,
            "error": 0,
        }
        last_event_at: datetime | None = None

        if self._audit_path.exists():
            with open(self._audit_path) as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    event_type = row.get("event_type", "")
                    if event_type in counts:
                        counts[event_type] += 1
                    ts_raw = row.get("timestamp")
                    if ts_raw:
                        try:
                            last_event_at = datetime.fromisoformat(ts_raw)
                        except ValueError:
                            pass

        status = "ok"
        messages: list[str] = []

        if counts["error"] > 0:
            status = "degraded"
            messages.append(f"{counts['error']} error event(s) in audit log")
        if counts["circuit_breaker_halt"] > 0:
            status = "degraded"
            messages.append(f"{counts['circuit_breaker_halt']} circuit breaker halt(s)")

        if drawdown_pct is not None:
            if drawdown_pct >= self._drawdown_down_pct:
                status = "down"
                messages.append(f"Drawdown {drawdown_pct:.1f}% >= {self._drawdown_down_pct}%")
            elif drawdown_pct >= self._drawdown_degraded_pct:
                if status != "down":
                    status = "degraded"
                messages.append(
                    f"Drawdown {drawdown_pct:.1f}% >= {self._drawdown_degraded_pct}%"
                )

        return {
            "status": status,
            "audit_path": str(self._audit_path),
            "audit_exists": self._audit_path.exists(),
            "event_counts": counts,
            "last_event_at": last_event_at.isoformat() if last_event_at else None,
            "drawdown_pct": drawdown_pct,
            "message": "; ".join(messages) if messages else "Execution audit healthy",
            "checked_at": now.isoformat(),
        }