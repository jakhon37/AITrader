"""FastAPI router for signal history endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from src.api import state
from src.core.contracts import TradeSignal

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
