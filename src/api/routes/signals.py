"""FastAPI router for signal history endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from src.api import state
from src.core.contracts import Instrument, TradeSignal

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/latest")
async def get_latest_signals(
    instrument: str = Query(..., description="EURUSD, XAUUSD, etc."),
) -> Dict[str, Any]:
    """Latest cached signals for one instrument (populated by live bus + WS bridge)."""
    inst_key = instrument.upper()
    trade: Optional[TradeSignal] = None
    for sig in reversed(state.trade_signal_history):
        if sig.instrument.value == inst_key:
            trade = sig
            break

    technical = state.latest_technical.get(inst_key)
    fundamental = state.latest_fundamental.get(inst_key)

    return {
        "instrument": inst_key,
        "technical": technical.model_dump() if technical else None,
        "fundamental": fundamental.model_dump() if fundamental else None,
        "trade": trade.model_dump() if trade else None,
    }


@router.get("/technical")
async def get_technical_signals() -> List[Dict[str, Any]]:
    """Get technical signals history."""
    return [sig.model_dump() for sig in state.technical_history]


@router.get("/fundamental")
async def get_fundamental_signals() -> List[Dict[str, Any]]:
    """Get fundamental signals history."""
    return [sig.model_dump() for sig in state.fundamental_history]


@router.get("/trade")
async def get_trade_signals() -> List[Dict[str, Any]]:
    """Get final trade signals history."""
    return [sig.model_dump() for sig in state.trade_signal_history]


@router.get("/chart-markers")
async def get_chart_markers(
    instrument: Optional[str] = Query(None, description="EURUSD, XAUUSD, etc."),
    limit: int = Query(200, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Get persisted LONG/SHORT chart flip markers (alternating, no NEUTRAL)."""
    store = getattr(state, "chart_marker_store", None)
    if store is not None:
        inst = Instrument(instrument.upper()) if instrument else None
        markers = store.list_markers(inst, limit=limit)
        return [m.model_dump() for m in markers]

    history = state.chart_marker_history
    if instrument:
        inst_key = instrument.upper()
        history = [m for m in history if m.instrument.value == inst_key]
    return [m.model_dump() for m in history[-limit:]]
