import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
import asyncio

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["data"])


# yfinance symbol mapping
SYMBOL_MAP = {
    Instrument.EURUSD: "EURUSD=X",
    Instrument.GBPUSD: "GBPUSD=X",
    Instrument.USDJPY: "USDJPY=X",
    Instrument.XAUUSD: "GC=F",
}

# Timeframe mapping
TF_MAP = {
    Timeframe.M1:  "1m",
    Timeframe.M5:  "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1:  "1h",
    Timeframe.H4:  "1h",   # resample from 1h
    Timeframe.D1:  "1d",
    Timeframe.W1:  "1wk",
}


def _resample_df_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    resampled = pd.DataFrame()
    resampled['open'] = df['open'].resample('4h').first()
    resampled['high'] = df['high'].resample('4h').max()
    resampled['low'] = df['low'].resample('4h').min()
    resampled['close'] = df['close'].resample('4h').last()
    if 'volume' in df.columns:
        resampled['volume'] = df['volume'].resample('4h').sum()
    else:
        resampled['volume'] = 0.0
    return resampled.dropna()


async def fill_data_gaps(
    data_store: Any,
    instrument: Instrument,
    timeframe: Timeframe,
    start_dt: datetime,
    end_dt: datetime,
) -> None:
    """Check data store for gaps and download missing candles from Yahoo Finance."""
    now_dt = datetime.now(timezone.utc)
    start_dt = start_dt.astimezone(timezone.utc)
    end_dt = min(end_dt.astimezone(timezone.utc), now_dt)

    first_ts, last_ts = data_store.list_ohlcv_range(instrument, timeframe)
    
    # Decide what range we need to download
    download_start = start_dt
    download_end = end_dt

    if last_ts is not None:
        last_ts = last_ts.astimezone(timezone.utc)
        if last_ts < end_dt:
            download_start = last_ts
        else:
            first_ts = first_ts.astimezone(timezone.utc)
            if start_dt < first_ts:
                download_start = start_dt
                download_end = first_ts
            else:
                return

    # Check yfinance limits for the timeframe
    timeframe_limits_days = {
        Timeframe.M1: 7,
        Timeframe.M5: 59,
        Timeframe.M15: 59,
        Timeframe.M30: 59,
        Timeframe.H1: 729,
        Timeframe.H4: 729,
    }
    limit_days = timeframe_limits_days.get(timeframe)
    if limit_days is not None:
        earliest_allowed = now_dt - timedelta(days=limit_days)
        if download_start < earliest_allowed:
            download_start = earliest_allowed

    if download_start >= download_end:
        return

    symbol = SYMBOL_MAP.get(instrument)
    interval = TF_MAP.get(timeframe)
    if not symbol or not interval:
        logger.warning(f"No yfinance mapping for {instrument} or {timeframe}")
        return

    logger.info(f"Downloading gap data for {instrument.value} ({symbol}) [{download_start} -> {download_end}] interval={interval}")

    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(
                symbol,
                start=download_start,
                end=download_end,
                interval=interval,
                progress=False,
            )
        )

        if df.empty:
            logger.info(f"No data returned from yfinance for {symbol} interval={interval} in range [{download_start} -> {download_end}]")
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(col).lower() for col in df.columns]

        required_cols = {"open", "high", "low", "close"}
        if not required_cols.issubset(set(df.columns)):
            logger.error(f"yfinance missing required columns for {symbol}. Got: {list(df.columns)}")
            return

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        if timeframe == Timeframe.H4 and interval == "1h":
            df = _resample_df_to_4h(df)

        if "volume" not in df.columns:
            df["volume"] = 0.0
        else:
            df["volume"] = df["volume"].astype(float).fillna(0.0)

        data_store.write_ohlcv(instrument, timeframe, df)
        logger.info(f"Successfully backfilled {len(df)} candles for {instrument.value} ({timeframe.value})")

    except Exception as exc:
        logger.exception(f"Failed to fetch/save gap data for {instrument.value} ({timeframe.value}): {exc}")


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

    # Fill gaps dynamically using yfinance
    try:
        await fill_data_gaps(data_store, inst, tf, start_dt, end_dt)
    except Exception as exc:
        logger.exception(f"Failed during fill_data_gaps check: {exc}")

    # Register the pair with the DataScheduler for live streaming
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        scheduler.add_active_pair(inst, tf)

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
