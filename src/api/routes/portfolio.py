"""FastAPI router for portfolio and order history endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/state")
async def get_portfolio_state(request: Request) -> Dict[str, Any]:
    """Current portfolio from execution database."""
    store = getattr(request.app.state, "execution_store", None)
    if store is not None:
        portfolio = store.get_latest_portfolio()
        if portfolio is not None:
            return portfolio.model_dump()

    engine = getattr(request.app.state, "engine", None)
    if engine is not None:
        portfolio = await engine.position_manager.get_portfolio_state(signal_id="webui-query")
        if portfolio is not None:
            return portfolio.model_dump()

    return {
        "signal_id": "initial",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "execution_mode": "paper",
        "balance": 100000.0,
        "equity": 100000.0,
        "margin_used": 0.0,
        "free_margin": 100000.0,
        "open_positions": [],
        "realized_pnl_today": 0.0,
        "drawdown_pct": 0.0,
    }


@router.get("/orders")
async def get_orders(request: Request, limit: int = 50) -> List[Dict[str, Any]]:
    """Order events from execution database."""
    store = getattr(request.app.state, "execution_store", None)
    if store is None:
        raise HTTPException(status_code=500, detail="Execution store not initialized.")
    return store.list_order_events(limit=limit)


@router.get("/trades")
async def get_closed_trades(request: Request, limit: int = 50) -> List[Dict[str, Any]]:
    """Closed trades from execution database."""
    store = getattr(request.app.state, "execution_store", None)
    if store is None:
        return []
    return store.list_closed_trades(limit=limit)