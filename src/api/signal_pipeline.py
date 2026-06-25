"""Live signal spine helpers — pause/resume around replay sessions."""

from __future__ import annotations

from typing import Any

from src.core.logging import get_logger

_log = get_logger("D10-WEBUI")


async def pause_live_signal_pipeline(app: Any) -> None:
    """Stop live Technical + Decision engines while replay owns the bus pipeline."""
    technical = getattr(app.state, "technical_engine", None)
    decision = getattr(app.state, "decision_engine", None)

    if technical is not None and technical.is_running:
        await technical.stop()
    if decision is not None and decision.is_running:
        await decision.stop()

    app.state.live_signal_pipeline_paused = True
    _log.info("live_signal_pipeline_paused")


async def resume_live_signal_pipeline(app: Any) -> None:
    """Restart live engines after replay ends (no-op if not paused)."""
    if not getattr(app.state, "live_signal_pipeline_paused", False):
        return

    technical = getattr(app.state, "technical_engine", None)
    decision = getattr(app.state, "decision_engine", None)

    if technical is not None:
        await technical.start()
    if decision is not None:
        await decision.start()

    app.state.live_signal_pipeline_paused = False
    _log.info("live_signal_pipeline_resumed")