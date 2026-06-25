"""FastAPI router for system health check endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Request

from src.api import state

router = APIRouter(prefix="/health", tags=["health"])


def _pipeline_component(app: object, attr: str) -> dict[str, object]:
    obj = getattr(app.state, attr, None)
    if obj is None:
        return {"running": False, "present": False}
    running = getattr(obj, "is_running", getattr(obj, "_running", True))
    return {"running": bool(running), "present": True}


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


@router.get("/pipeline")
async def get_pipeline_health(request: Request) -> dict[str, object]:
    """D11-OPS: Live pipeline component status for ops dashboards."""
    app = request.app
    scheduler = getattr(app.state, "scheduler", None)
    scheduler_running = getattr(scheduler, "_running", False) if scheduler else False

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "replay_active": getattr(app.state, "active_replay_session", None) is not None,
        "live_signal_pipeline_paused": getattr(app.state, "live_signal_pipeline_paused", False),
        "components": {
            "scheduler": {"running": scheduler_running, "present": scheduler is not None},
            "technical_engine": _pipeline_component(app, "technical_engine"),
            "decision_engine": _pipeline_component(app, "decision_engine"),
            "execution_engine": _pipeline_component(app, "engine"),
            "fundamental_agent": _pipeline_component(app, "fundamental_agent"),
            "notifier": _pipeline_component(app, "notifier"),
            "news_fetcher": _pipeline_component(app, "news_fetcher"),
            "calendar_fetcher": _pipeline_component(app, "calendar_fetcher"),
        },
    }
