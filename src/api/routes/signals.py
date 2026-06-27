"""FastAPI router for signal history endpoints (SQLite source of truth)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request

from src.api import state
from src.core.clock import now
from src.core.contracts import Instrument
from src.signals.registry import SignalStores

router = APIRouter(prefix="/signals", tags=["signals"])


def _stores(request: Request) -> SignalStores:
    stores = getattr(request.app.state, "signal_stores", None)
    if stores is None:
        raise HTTPException(status_code=500, detail="Signal stores not initialized.")
    return stores


@router.get("/latest")
async def get_latest_signals(
    request: Request,
    instrument: str = Query(..., description="EURUSD, XAUUSD, etc."),
) -> Dict[str, Any]:
    """Latest persisted signals for one instrument."""
    stores = _stores(request)
    inst_key = instrument.upper()
    try:
        inst = Instrument(inst_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    current = now()
    technical = stores.technical.get_latest(inst, as_of=current)
    fundamental = stores.fundamental.list_recent(
        limit=1,
        instrument=inst,
        valid_only=True,
        as_of=current,
    )
    trade = stores.trade.get_latest_for_instrument(inst, as_of=current)

    return {
        "instrument": inst_key,
        "technical": technical.model_dump() if technical else None,
        "fundamental": fundamental[0].model_dump() if fundamental else None,
        "trade": trade.model_dump() if trade else None,
    }


@router.get("/technical")
async def get_technical_signals(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
    valid_only: bool = Query(True),
) -> List[Dict[str, Any]]:
    """Technical signal history (newest first)."""
    stores = _stores(request)
    signals = stores.technical.list_recent(
        limit=limit,
        valid_only=valid_only,
        as_of=now(),
    )
    return [sig.model_dump() for sig in signals]


@router.get("/fundamental")
async def get_fundamental_signals(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
    valid_only: bool = Query(True, description="Exclude expired signals"),
) -> List[Dict[str, Any]]:
    """Fundamental signal history (newest first)."""
    stores = _stores(request)
    signals = stores.fundamental.list_recent(
        limit=limit,
        valid_only=valid_only,
        as_of=now(),
    )
    return [sig.model_dump() for sig in signals]


@router.get("/trade")
async def get_trade_signals(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
    valid_only: bool = Query(True),
) -> List[Dict[str, Any]]:
    """Trade signal history (newest first)."""
    stores = _stores(request)
    signals = stores.trade.list_recent(
        limit=limit,
        valid_only=valid_only,
        as_of=now(),
    )
    return [sig.model_dump() for sig in signals]


@router.get("/chart-markers")
async def get_chart_markers(
    instrument: Optional[str] = Query(None, description="EURUSD, XAUUSD, etc."),
    limit: int = Query(200, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Persisted LONG/SHORT chart flip markers."""
    store = getattr(state, "chart_marker_store", None)
    if store is None:
        return []
    inst = Instrument(instrument.upper()) if instrument else None
    markers = store.list_markers(inst, limit=limit)
    return [m.model_dump() for m in markers]