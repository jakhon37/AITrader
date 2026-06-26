"""FastAPI router for portfolio and order history endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from fastapi import APIRouter, Request

from src.api import state

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/state")
async def get_portfolio_state(request: Request) -> Dict[str, Any]:
    """Get the current active portfolio state (cash, positions, margins)."""
    portfolio = state.latest_portfolio

    if not portfolio:
        store = getattr(request.app.state, "execution_store", None)
        if store is not None:
            portfolio = store.get_latest_portfolio()

    # Fallback to live execution engine query if store is empty
    if not portfolio:
        engine = getattr(request.app.state, "engine", None)
        if engine:
            portfolio = await engine.position_manager.get_portfolio_state(signal_id="webui-query")

    if not portfolio:
        # Initial empty mock state
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

    return portfolio.model_dump()


@router.get("/orders")
async def get_orders(request: Request, limit: int = 50) -> List[Dict[str, Any]]:
    """Get order events history."""
    store = getattr(request.app.state, "execution_store", None)
    if store is not None:
        db_orders = store.list_order_events(limit=limit)
        if db_orders:
            return db_orders
    return [evt.model_dump() for evt in state.order_event_history[-limit:]]


@router.get("/trades")
async def get_closed_trades(request: Request, limit: int = 50) -> List[Dict[str, Any]]:
    """Get closed trade history from execution database."""
    store = getattr(request.app.state, "execution_store", None)
    if store is None:
        return []
    return store.list_closed_trades(limit=limit)
