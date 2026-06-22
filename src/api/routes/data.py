"""FastAPI data endpoints serving historical charts, news, and economic events."""

from __future__ import annotations

import logging
import pandas as pd
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["data"])


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


@router.get("/ohlcv")
async def get_ohlcv(
    request: Request,
    instrument: str = Query(..., description="EURUSD, GBPUSD, etc."),
    timeframe: str = Query(..., description="1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
    start: str = Query(..., description="ISO 8601 start timestamp"),
    end: str = Query(..., description="ISO 8601 end timestamp"),
) -> List[Dict[str, Any]]:
    """Retrieve historical OHLCV data from the Parquet store, formatted for Lightweight Charts."""
    data_store = getattr(request.app.state, "data_store", None)
    if not data_store:
        raise HTTPException(status_code=500, detail="DataStore not initialized in application state.")

    try:
        inst = Instrument(instrument.upper())
        tf = Timeframe(timeframe)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)

    try:
        df = data_store.get_ohlcv(inst, tf, start_dt, end_dt)
        if df.empty:
            return []

        # Ensure index is named 'timestamp' before resetting index
        df = df.copy()
        df.index.name = "timestamp"
        df_reset = df.reset_index()
        # Convert timestamp to Unix seconds for Lightweight Charts compatibility
        ts_ns = pd.to_datetime(df_reset["timestamp"], utc=True).astype("datetime64[ns, UTC]")
        df_reset["time"] = ts_ns.astype("int64") // 10**9

        candles = df_reset[["time", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
        return candles
    except DataError as e:
        logger.warning(f"DataError retrieving OHLCV: {e}")
        return []
    except Exception as e:
        logger.error(f"Error retrieving OHLCV: {e}")
        raise HTTPException(status_code=500, detail="Internal server error retrieving chart data.")


@router.get("/news")
async def get_news(
    request: Request,
    instrument: str = Query(..., description="EURUSD, GBPUSD, etc."),
    start: str = Query(..., description="ISO 8601 start timestamp"),
    end: str = Query(..., description="ISO 8601 end timestamp"),
) -> List[Dict[str, Any]]:
    """Retrieve historical news articles for an instrument."""
    data_store = getattr(request.app.state, "data_store", None)
    if not data_store:
        raise HTTPException(status_code=500, detail="DataStore not initialized.")

    try:
        inst = Instrument(instrument.upper())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)

    try:
        articles = data_store.get_news(inst, start_dt, end_dt)
        # Convert Pydantic models to dicts
        return [art.model_dump() if hasattr(art, "model_dump") else dict(art) for art in articles]
    except Exception as e:
        logger.error(f"Error retrieving news: {e}")
        return []


@router.get("/economic_events")
async def get_economic_events(
    request: Request,
    start: str = Query(..., description="ISO 8601 start timestamp"),
    end: str = Query(..., description="ISO 8601 end timestamp"),
    impact: Optional[str] = Query(None, description="Comma-separated list, e.g. 'high,medium'"),
) -> List[Dict[str, Any]]:
    """Retrieve economic calendar events."""
    data_store = getattr(request.app.state, "data_store", None)
    if not data_store:
        raise HTTPException(status_code=500, detail="DataStore not initialized.")

    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)
    impact_filter = [i.strip() for i in impact.split(",")] if impact else None

    try:
        events = data_store.get_economic_events(start_dt, end_dt, impact_filter=impact_filter)
        return [evt.model_dump() if hasattr(evt, "model_dump") else dict(evt) for evt in events]
    except Exception as e:
        logger.error(f"Error retrieving economic events: {e}")
        return []
