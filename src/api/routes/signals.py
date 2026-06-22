"""FastAPI router for signal history endpoints."""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter

from src.api import state

router = APIRouter(prefix="/signals", tags=["signals"])


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
