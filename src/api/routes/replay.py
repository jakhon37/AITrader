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
    end_date: Optional[str] = Field(None, json_schema_extra={"example": "2024-01-10"})
    initial_capital: float = Field(10000.0)
    mode: str = Field("watch", description="watch | manual")
    speed: float = Field(10.0, description="Speed multiplier for watch mode")
    timeframe: str = Field("1h", description="1m | 5m | 15m | 30m | 1h | 4h | 1d")
    calculate_indicators: bool = Field(True, description="Enable or disable technical indicator calculations")


class ManualOrderRequest(BaseModel):
    side: str = Field(..., description="buy | sell")
    size: float = Field(..., gt=0.0)
    entry_price: Optional[float] = Field(None)
    stop_loss: Optional[float] = Field(None)
    take_profit: Optional[float] = Field(None)


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
    
    data_store = getattr(request.app.state, "data_store", None)
    if not data_store:
        raise HTTPException(status_code=500, detail="DataStore not initialized.")

    if body.end_date:
        end_dt = parse_datetime(body.end_date)
    else:
        # Fallback to the latest available timestamp in the database for the instrument/timeframe
        from src.core.contracts import Timeframe
        try:
            tf_enum = Timeframe(body.timeframe)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid timeframe: {body.timeframe}")
            
        _, last_dt = data_store.list_ohlcv_range(inst, tf_enum)
        
        # If no data for this specific timeframe, try other timeframes in the store
        if not last_dt:
            instrument_root = data_store.base_dir / "raw" / inst.value
            if instrument_root.exists():
                for tf_dir in instrument_root.iterdir():
                    if tf_dir.is_dir():
                        try:
                            other_tf = Timeframe(tf_dir.name)
                            _, other_last = data_store.list_ohlcv_range(inst, other_tf)
                            if other_last and (last_dt is None or other_last > last_dt):
                                last_dt = other_last
                        except ValueError:
                            continue
        
        # If still no data found at all, fallback to current time
        if not last_dt:
            last_dt = datetime.now(timezone.utc)
            logger.warning(f"No database data found for instrument {inst.value}, defaulting end_date to current time.")
        
        end_dt = last_dt

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
            calculate_indicators=body.calculate_indicators,
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
            calculate_indicators=body.calculate_indicators,
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
    
    await session.pause()
    return {"status": "success", "session": session.state.to_dict()}


@router.post("/resume")
async def resume_replay(request: Request) -> Dict[str, Any]:
    """Resume the watch mode replay."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
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

    order = await session.place_order(
        side=side,
        size=body.size,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
    )
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


class ChangeSpeedRequest(BaseModel):
    speed: float = Field(..., gt=0.0, description="Speed multiplier for watch mode")


@router.post("/speed")
async def change_speed(request: Request, body: ChangeSpeedRequest) -> Dict[str, Any]:
    """Change the speed of the active replay session dynamically."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")

    try:
        await session.set_speed(body.speed)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update speed: {e}")

    return {"status": "success", "session": session.state.to_dict()}


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


class ChangeIndicatorsRequest(BaseModel):
    enabled: bool = Field(..., description="Enable or disable technical indicator calculations")


@router.post("/indicators")
async def change_indicators(request: Request, body: ChangeIndicatorsRequest) -> Dict[str, Any]:
    """Enable or disable indicators in the active session dynamically."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        raise HTTPException(status_code=400, detail="No active replay session.")
    
    try:
        await session.set_indicators_enabled(body.enabled)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update indicator status: {e}")
        
    return {"status": "success", "session": session.state.to_dict()}


@router.get("/state")
async def get_state(request: Request) -> Dict[str, Any]:
    """Get status of the active replay session."""
    session = getattr(request.app.state, "active_replay_session", None)
    if not session:
        return {"status": "inactive"}
    return {"status": "active", "session": session.state.to_dict()}
