"""D11-OPS — Paper trading soak tracker for Tier 4 validation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SOAK_TARGET_DAYS = 14
_DEFAULT_STATE_DIR = Path("data/state")


def _state_path(data_dir: str | Path | None = None) -> Path:
    if data_dir:
        return Path(data_dir) / "state" / "paper_soak.json"
    return _DEFAULT_STATE_DIR / "paper_soak.json"


def load_soak_state(data_dir: str | Path | None = None) -> dict[str, Any]:
    path = _state_path(data_dir)
    if not path.exists():
        return {}
    try:
        with open(path) as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def record_soak_start(
    *,
    data_dir: str | Path | None = None,
    target_days: int = _SOAK_TARGET_DAYS,
    mode: str = "paper",
) -> dict[str, Any]:
    """Persist soak start time on first pipeline boot (idempotent)."""
    path = _state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_soak_state(data_dir)
    now = datetime.now(timezone.utc)
    if existing.get("started_at"):
        return existing

    state = {
        "started_at": now.isoformat(),
        "target_days": target_days,
        "mode": mode,
        "last_seen_at": now.isoformat(),
    }
    with open(path, "w") as handle:
        json.dump(state, handle, indent=2)
    return state


def touch_soak_seen(data_dir: str | Path | None = None) -> dict[str, Any]:
    """Update last_seen_at without resetting the soak clock."""
    path = _state_path(data_dir)
    state = load_soak_state(data_dir)
    now = datetime.now(timezone.utc)
    if not state.get("started_at"):
        return record_soak_start(data_dir=data_dir)
    state["last_seen_at"] = now.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        json.dump(state, handle, indent=2)
    return state


def build_soak_report(
    *,
    data_dir: str | Path | None = None,
    pipeline_running: bool = False,
    ops_status: str | None = None,
) -> dict[str, Any]:
    """Human-readable soak progress for /api/health/soak and CLI scripts."""
    state = touch_soak_seen(data_dir) if pipeline_running else load_soak_state(data_dir)
    now = datetime.now(timezone.utc)

    started_raw = state.get("started_at")
    target_days = int(state.get("target_days", _SOAK_TARGET_DAYS))

    if not started_raw:
        return {
            "status": "not_started",
            "message": "Paper soak not started — launch ./scripts/start_webui.sh",
            "target_days": target_days,
            "elapsed_days": 0.0,
            "remaining_days": float(target_days),
            "complete": False,
            "pipeline_running": pipeline_running,
            "ops_status": ops_status,
            "started_at": None,
            "last_seen_at": None,
        }

    started = datetime.fromisoformat(str(started_raw))
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = now - started
    elapsed_days = elapsed.total_seconds() / 86400.0
    remaining_days = max(0.0, target_days - elapsed_days)
    complete = elapsed_days >= target_days

    status = "complete" if complete else "in_progress"
    if not pipeline_running and elapsed_days < target_days:
        status = "paused"

    return {
        "status": status,
        "message": (
            f"Paper soak {elapsed_days:.1f}/{target_days} days"
            + (" — target reached" if complete else f" — {remaining_days:.1f} days remaining")
        ),
        "target_days": target_days,
        "elapsed_days": round(elapsed_days, 2),
        "elapsed_hours": round(elapsed.total_seconds() / 3600.0, 1),
        "remaining_days": round(remaining_days, 2),
        "complete": complete,
        "pipeline_running": pipeline_running,
        "ops_status": ops_status,
        "started_at": started.isoformat(),
        "last_seen_at": state.get("last_seen_at"),
        "mode": state.get("mode", "paper"),
    }