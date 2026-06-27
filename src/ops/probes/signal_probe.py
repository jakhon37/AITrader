"""D11-OPS — Signal flow checks via persisted technical signal store."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.core.contracts import Instrument
from src.core.session import is_instrument_session_open
from src.signals.registry import SignalStores
from src.signals.stores import TechnicalSignalStore


class SignalFlowProbe:
    """Verify technical signals are flowing during active sessions."""

    def __init__(
        self,
        technical_store: Optional[TechnicalSignalStore] = None,
        *,
        signal_stores: Optional[SignalStores] = None,
        stale_minutes: float = 120.0,
    ) -> None:
        self._technical_store = (
            technical_store or (signal_stores.technical if signal_stores else None)
        )
        self._signal_stores = signal_stores
        self._stale_minutes = stale_minutes

    def check(
        self,
        instruments: list[Instrument],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        per_instrument: list[dict[str, Any]] = []
        worst = "ok"
        trade_count = 0
        if self._signal_stores is not None:
            trade_count = self._signal_stores.trade.count()

        for inst in instruments:
            if not is_instrument_session_open(now, inst):
                per_instrument.append({
                    "instrument": inst.value,
                    "status": "ok",
                    "message": "Market closed — signal check skipped",
                })
                continue

            sig = (
                self._technical_store.get_latest(inst, as_of=now)
                if self._technical_store is not None
                else None
            )
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

        stale = [r for r in per_instrument if r.get("status") == "degraded"]
        message = "Technical signals flowing"
        if worst == "degraded":
            if stale:
                message = stale[0].get("message", "Technical signal flow degraded")
            else:
                message = "Technical signal flow degraded"

        return {
            "status": worst,
            "message": message,
            "instruments": per_instrument,
            "trade_signals_stored": trade_count,
        }