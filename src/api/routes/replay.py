"""FastAPI routes for replay controls and manual trade execution."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.core.contracts import Instrument, OrderSide
from src.backtest.replay import StrategyReplaySession, ManualReplaySession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/replay", tags=["replay"])


class StartReplayRequest(BaseModel):
    instrument: str = Field(..., json_schema_extra={"example": "EURUSD"})
    start_date: str = Field(..., json_schema_extra={"example": "2024-01-01"})
    end_date: str = Field(..., json_schema_extra={"example": "2024-01-10"})
    initial_capital: float = Field(10000.0)
    mode: str = Field("watch", description="watch | manual")
    speed: float = Field(10.0, description="Speed multiplier for watch mode")
    timeframe: str = Field("1h", description="1m | 5m | 15m | 30m | 1h | 4h | 1d")


class ManualOrderRequest(BaseModel):
    side: str = Field(..., description="buy | sell")
    size: float = Field(..., gt=0.0)


class ClosePositionRequest(BaseModel):
    instrument: str = Field(..., json_schema_extra={"example": "EURUSD"})


def parse_datetime(dt_str: str) -> datetime:
    """Parse ISO datetime string and ensure it is timezone-aware UTC."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid datetime format: '{dt_str}'. Must be ISO 8601 format."
        ) from e


@router.post("/start")
async def start_replay(request: Request, body: StartReplayRequest) -> Dict[str, Any]:
    """Start a new strategy watch or manual trader replay session."""
    # Stop existing session if active
    existing = getattr(request.app.state, "active_replay_session", None)
    if existing:
        try:
            if hasattr(existing, "stop"):
                await existing.stop()
            elif hasattr(existing, "end_session"):
                await existing.end_session()
        except Exception as e:
            logger.warning(f"Error stopping previous replay session: {e}")
        request.app.state.active_replay_session = None

    try:
        inst = Instrument(body.instrument.upper())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid instrument: {body.instrument}")

    start_dt = parse_datetime(body.start_date)
    end_dt = parse_datetime(body.end_date)
    
    data_store = getattr(request.app.state, "data_store", None)
    if not data_store:
        raise HTTPException(status_code=500, detail="DataStore not initialized.")

    import os
    reports_dir = os.path.join(data_store.base_dir, "reports")

    if body.mode == "watch":
        session = StrategyReplaySession(
            instrument=inst,
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=body.initial_capital,
            speed=body.speed,
            store=data_store,
            reports_dir=reports_dir,
            timeframe=body.timeframe,
        )
    elif body.mode == "manual":
        session = ManualReplaySession(
            instrument=inst,
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=body.initial_capital,
            store=data_store,
            reports_dir=reports_dir,
            timeframe=body.timeframe,
        )
    else:
        raise HTTPException(status_code=400, detail="Mode must be 'watch' or 'manual'.")

    request.app.state.active_replay_session = session
    await session.start()

    return {"status": "success", "session": session.state.to_dict()}


@router.post("/pause")
async def pause_replay(request: Request) -> Dict[str, Any]:
    """Pause the watch mode replay."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    if session.state.mode != "watch":
        raise HTTPException(status_code=400, detail="Pause is only supported in watch mode.")

    await session.pause()
    return {"status": "success", "session": session.state.to_dict()}


@router.post("/resume")
async def resume_replay(request: Request) -> Dict[str, Any]:
    """Resume the watch mode replay."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    if session.state.mode != "watch":
        raise HTTPException(status_code=400, detail="Resume is only supported in watch mode.")

    await session.resume()
    return {"status": "success", "session": session.state.to_dict()}


@router.post("/step")
async def step_replay(request: Request) -> Dict[str, Any]:
    """Step forward one bar in manual mode."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    if session.state.mode != "manual":
        raise HTTPException(status_code=400, detail="Step is only supported in manual mode.")

    await session.step()
    return {"status": "success", "session": session.state.to_dict()}


@router.post("/order")
async def place_order(request: Request, body: ManualOrderRequest) -> Dict[str, Any]:
    """Place a manual order in the current manual replay session."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    if session.state.mode != "manual":
        raise HTTPException(status_code=400, detail="Manual trades only supported in manual mode.")

    try:
        side = OrderSide.BUY if body.side.lower() == "buy" else OrderSide.SELL
    except Exception:
        raise HTTPException(status_code=400, detail="Side must be 'buy' or 'sell'.")

    order = await session.place_order(side=side, size=body.size)
    return {"status": "success", "order": order.model_dump(), "session": session.state.to_dict()}


@router.post("/close")
async def close_position(request: Request, body: ClosePositionRequest) -> Dict[str, Any]:
    """Close position for an instrument in the manual replay session."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    if session.state.mode != "manual":
        raise HTTPException(status_code=400, detail="Manual trades only supported in manual mode.")

    try:
        inst = Instrument(body.instrument.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid instrument: {body.instrument}")

    order = await session.close_position(instrument=inst)
    return {"status": "success", "order": order.model_dump(), "session": session.state.to_dict()}


@router.post("/stop")
async def stop_replay(request: Request) -> Dict[str, Any]:
    """Stop the active replay session and return report/scorecard if manual mode."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    report = None
    if session.state.mode == "manual":
        report = await session.end_session()
    else:
        await session.stop()

    request.app.state.active_replay_session = None
    return {"status": "success", "report": report}


class ChangeTimeframeRequest(BaseModel):
    timeframe: str = Field(..., description="1m | 5m | 15m | 30m | 1h | 4h | 1d")


@router.post("/timeframe")
async def change_timeframe(request: Request, body: ChangeTimeframeRequest) -> Dict[str, Any]:
    """Change the timeframe of the active replay session dynamically."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    try:
        await session.update_timeframe(body.timeframe)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update timeframe: {e}")
        
    return {"status": "success", "session": session.state.to_dict()}


@router.get("/state")
async def get_state(request: Request) -> Dict[str, Any]:
    """Get status of the active replay session."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        return {"status": "inactive"}
    return {"status": "active", "session": session.state.to_dict()}
