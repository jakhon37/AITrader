"""FastAPI router for system health check endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter

from src.api import state

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_health() -> Dict[str, Any]:
    """Retrieve system health aggregated by division."""
    latest_events = state.health_history
    if not latest_events:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "divisions": {},
        }

    divisions = {}
    for evt in latest_events:
        divisions[evt.division] = {
            "status": evt.status.value,
            "message": evt.message,
            "metrics": evt.metrics,
            "timestamp": evt.timestamp.isoformat(),
        }

    overall_status = "ok"
    for info in divisions.values():
        if info["status"] == "down":
            overall_status = "down"
            break
        elif info["status"] == "degraded":
            overall_status = "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "divisions": divisions,
    }
