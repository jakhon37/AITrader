"""D11-OPS — Signal flow checks via API state cache."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.api import state as api_state
from src.core.contracts import Instrument
from src.core.session import is_instrument_session_open


class SignalFlowProbe:
    """Verify technical signals are flowing during active sessions."""

    def __init__(self, stale_minutes: float = 120.0) -> None:
        self._stale_minutes = stale_minutes

    def check(
        self,
        instruments: list[Instrument],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        state = api_state
        per_instrument: list[dict[str, Any]] = []
        worst = "ok"

        for inst in instruments:
            if not is_instrument_session_open(now, inst):
                per_instrument.append({
                    "instrument": inst.value,
                    "status": "ok",
                    "message": "Market closed — signal check skipped",
                })
                continue

            sig = state.latest_technical.get(inst.value)
            if sig is None:
                per_instrument.append({
                    "instrument": inst.value,
                    "status": "degraded",
                    "message": "No technical signal received yet",
                })
                worst = "degraded"
                continue

            age_min = (now - sig.timestamp).total_seconds() / 60.0
            row_status = "ok"
            message = f"Last technical signal {age_min:.0f}m ago"
            if age_min > self._stale_minutes:
                row_status = "degraded"
                message = (
                    f"Technical signals stale: {age_min:.0f}m "
                    f"(>{self._stale_minutes:.0f}m)"
                )
                worst = "degraded"

            per_instrument.append({
                "instrument": inst.value,
                "status": row_status,
                "last_signal_at": sig.timestamp.isoformat(),
                "age_minutes": round(age_min, 1),
                "message": message,
            })

        return {
            "status": worst,
            "instruments": per_instrument,
            "trade_signals_buffered": len(state.trade_signal_history),
        }