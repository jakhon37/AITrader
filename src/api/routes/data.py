import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
import asyncio

from src.core.clock import now
from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.instruments import get_enabled_instruments
from src.core.session import is_chart_bar
from src.core.gap_fill import store_needs_gap_fill

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["data"])


from src.data.feeds.dukascopy import DukascopyFeed
from src.data.feeds.lock import DUKASCOPY_EXECUTOR

_TF_STEP = {
    Timeframe.M1:  timedelta(minutes=1),
    Timeframe.M5:  timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1:  timedelta(hours=1),
    Timeframe.H4:  timedelta(hours=4),
    Timeframe.D1:  timedelta(days=1),
    Timeframe.W1:  timedelta(weeks=1),
}

# Intraday candles must be backfilled across the full requested window — not just
# the tail after last_ts — or 1m charts show multi-day holes (e.g. Jun 22–24 missing).
_INTRADAY_TIMEFRAMES = {
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.M30,
}

_gap_fill_inflight: set[str] = set()


async def fill_data_gaps(
    data_store: Any,
    instrument: Instrument,
    timeframe: Timeframe,
    start_dt: datetime,
    end_dt: datetime,
    feed: Optional[DukascopyFeed] = None,
) -> None:
    """Check data store for gaps and download missing candles from Dukascopy."""
    now_dt = datetime.now(timezone.utc)
    start_dt = start_dt.astimezone(timezone.utc)
    end_dt = min(end_dt.astimezone(timezone.utc), now_dt)

    first_ts, last_ts = data_store.list_ohlcv_range(instrument, timeframe)

    timeframe_limits_days = {
        Timeframe.M1: 7,
        Timeframe.M5: 59,
        Timeframe.M15: 59,
        Timeframe.M30: 59,
        Timeframe.H1: 729,
        Timeframe.H4: 729,
    }
    limit_days = timeframe_limits_days.get(timeframe)
    earliest_allowed = (
        now_dt - timedelta(days=limit_days) if limit_days is not None else start_dt
    )
    window_start = max(start_dt, earliest_allowed)
    download_end = end_dt

    if window_start >= download_end:
        return

    # Intraday: tail-fill only — never block chart loads on a multi-day first fetch.
    _INTRADAY_EMPTY_TAIL_DAYS = {
        Timeframe.M1: 2,
        Timeframe.M5: 3,
        Timeframe.M15: 5,
        Timeframe.M30: 7,
    }
    if timeframe in _INTRADAY_TIMEFRAMES:
        if last_ts is None:
            tail_days = _INTRADAY_EMPTY_TAIL_DAYS.get(timeframe, 2)
            download_start = max(
                window_start,
                now_dt - timedelta(days=tail_days),
            )
        else:
            last_ts = last_ts.astimezone(timezone.utc)
            download_start = last_ts
            if download_start >= download_end:
                return
    elif last_ts is None:
        download_start = window_start
    else:
        last_ts = last_ts.astimezone(timezone.utc)
        if last_ts < download_end:
            download_start = last_ts + _TF_STEP.get(timeframe, timedelta(hours=1))
            if download_start < window_start:
                download_start = window_start
        else:
            first_ts = first_ts.astimezone(timezone.utc) if first_ts is not None else None
            if first_ts is not None and window_start < first_ts:
                download_start = window_start
                download_end = first_ts
            else:
                return

    if download_start >= download_end:
        return

    duka = feed or DukascopyFeed()
    logger.info(
        f"Downloading gap data from Dukascopy for {instrument.value} "
        f"[{download_start} -> {download_end}] tf={timeframe.value}"
    )

    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            DUKASCOPY_EXECUTOR,
            lambda: duka.fetch_range(
                instrument,
                timeframe,
                download_start,
                download_end,
                allow_empty=True,
            ),
        )

        if df.empty:
            logger.info(
                f"No Dukascopy data for {instrument.value} "
                f"in range [{download_start.date()} -> {download_end.date()}] — skipping"
            )
            return

        data_store.write_ohlcv(instrument, timeframe, df)
        logger.info(
            f"Successfully backfilled {len(df)} candles for "
            f"{instrument.value} ({timeframe.value}) from Dukascopy"
        )

    except DataError as exc:
        logger.info(
            f"Gap fill skipped for {instrument.value} ({timeframe.value}): {exc}"
        )
    except Exception as exc:
        logger.warning(
            f"Failed to fetch/save gap data for {instrument.value} ({timeframe.value}): {exc}"
        )


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


def _schedule_focus_poll(
    scheduler: Any,
    inst: Instrument,
    tf: Timeframe,
) -> bool:
    """Register chart focus and kick one light live poll. Returns True if focus changed."""
    if scheduler.set_focused_pair(inst, tf):

        async def _kick_focus_poll() -> None:
            try:
                await scheduler.poll_pair_now(inst, tf, light=True)
            except Exception as exc:
                logger.warning(
                    "focus_poll_failed instrument=%s tf=%s error=%s",
                    inst.value,
                    tf.value,
                    exc,
                )

        asyncio.create_task(_kick_focus_poll())
        return True
    return False


@router.post("/focus")
async def focus_chart_pair(
    request: Request,
    instrument: str = Query(..., description="EURUSD, GBPUSD, etc."),
    timeframe: str = Query(..., description="1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
) -> Dict[str, Any]:
    """Tell the scheduler which pair the chart is viewing (one call per instrument/TF change)."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler not initialized.")
    replay_active = getattr(request.app.state, "active_replay_session", None) is not None
    if replay_active:
        return {"status": "skipped", "reason": "replay_active"}

    try:
        inst = Instrument(instrument.upper())
        tf = Timeframe(timeframe)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    changed = _schedule_focus_poll(scheduler, inst, tf)
    return {
        "status": "ok",
        "focused": f"{inst.value}/{tf.value}",
        "changed": changed,
    }


@router.get("/ohlcv")
async def get_ohlcv(
    request: Request,
    instrument: str = Query(..., description="EURUSD, GBPUSD, etc."),
    timeframe: str = Query(..., description="1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
    start: str = Query(..., description="ISO 8601 start timestamp"),
    end: str = Query(..., description="ISO 8601 end timestamp"),
    focus: bool = Query(
        False,
        description="When true, also register scheduler focus (prefer POST /data/focus)",
    ),
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

    if focus:
        scheduler = getattr(request.app.state, "scheduler", None)
        replay_active = getattr(request.app.state, "active_replay_session", None) is not None
        if scheduler and not replay_active:
            _schedule_focus_poll(scheduler, inst, tf)

    app_config = getattr(request.app.state, "app_config", None)
    auto_refresh = (
        app_config is not None
        and app_config.data.pipeline.auto_refresh
        and app_config.data.source == "dukascopy"
    )
    if store_needs_gap_fill(data_store, inst, tf, end_dt, auto_refresh=auto_refresh):
        shared_feed = getattr(request.app.state, "dukascopy_feed", None)

        gap_key = f"{inst.value}/{tf.value}"

        async def _run_gap_fill() -> None:
            if gap_key in _gap_fill_inflight:
                return
            _gap_fill_inflight.add(gap_key)
            try:
                await fill_data_gaps(
                    data_store, inst, tf, start_dt, end_dt, feed=shared_feed
                )
            except Exception as exc:
                logger.exception(f"Failed during fill_data_gaps check: {exc}")
            finally:
                _gap_fill_inflight.discard(gap_key)

        # Intraday + auto-refresh: never block the chart HTTP request on Dukascopy.
        if auto_refresh and tf in _INTRADAY_TIMEFRAMES:
            asyncio.create_task(_run_gap_fill())
        else:
            await _run_gap_fill()

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

        records = df_reset[["time", "open", "high", "low", "close", "volume"]].to_dict(
            orient="records"
        )
        candles = []
        for row in records:
            ts = pd.to_datetime(row["time"], unit="s", utc=True).to_pydatetime()
            if is_chart_bar(
                ts,
                inst,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row.get("volume", 0) or 0),
            ):
                candles.append(row)
        return candles
    except DataError as e:
        logger.warning(f"DataError retrieving OHLCV: {e}")
        return []
    except Exception as e:
        logger.error(f"Error retrieving OHLCV: {e}")
        raise HTTPException(status_code=500, detail="Internal server error retrieving chart data.")


@router.get("/live-status")
async def get_live_status(request: Request) -> Dict[str, Any]:
    """Return DataScheduler health for the terminal live-chart status UI."""
    import asyncio

    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler not initialized.")
    replay_active = getattr(request.app.state, "active_replay_session", None) is not None
    status = scheduler.get_live_status()
    status["replay_active"] = replay_active
    refresh_worker = getattr(request.app.state, "refresh_worker", None)
    if refresh_worker is not None:
        status["data_refresh"] = refresh_worker.get_status()
    status["enabled_instruments"] = [inst.value for inst in get_enabled_instruments()]
    return status


@router.get("/instruments")
async def list_data_instruments() -> Dict[str, Any]:
    """Return instruments enabled for Dukascopy refresh and live scheduling."""
    from src.core.config import load_instruments

    configs = load_instruments()
    enabled = get_enabled_instruments()
    return {
        "enabled": [inst.value for inst in enabled],
        "supported": [inst.value for inst in Instrument],
        "configs": {
            inst.value: {
                "enabled": cfg.enabled,
                "pip_size": cfg.pip_size,
                "session_hours": cfg.session_hours,
                "daily_break": (
                    {"start": cfg.daily_break.start, "end": cfg.daily_break.end}
                    if cfg.daily_break
                    else None
                ),
                "primary_timeframe": cfg.primary_timeframe.value,
            }
            for inst, cfg in configs.items()
        },
    }


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


_IMPACT_RANK = {"low": 0, "medium": 1, "high": 2}


def _impact_meets_minimum(level: str, minimum: str) -> bool:
    return _IMPACT_RANK.get(level, 0) >= _IMPACT_RANK.get(minimum, 0)


@router.get("/calendar/upcoming")
async def get_upcoming_calendar(
    request: Request,
    hours: int = Query(48, ge=1, le=168, description="Look-ahead window in hours"),
    min_impact: str = Query("low", description="Minimum impact: low | medium | high"),
) -> List[Dict[str, Any]]:
    """Upcoming economic calendar events with countdown and volatility indicators."""
    data_store = getattr(request.app.state, "data_store", None)
    if not data_store:
        raise HTTPException(status_code=500, detail="DataStore not initialized.")

    if min_impact not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="min_impact must be low, medium, or high")

    current = now()
    end = current + timedelta(hours=hours)

    try:
        events = data_store.get_economic_events(current, end, impact_filter=None)
    except Exception as e:
        logger.error(f"Error retrieving upcoming calendar: {e}")
        return []

    payload: list[dict[str, Any]] = []
    for evt in events:
        if not _impact_meets_minimum(evt.impact, min_impact):
            continue

        minutes_until = max(0, int((evt.timestamp - current).total_seconds() // 60))
        released = evt.actual is not None and evt.timestamp <= current
        status = "released" if released else "upcoming"

        payload.append(
            {
                "event_id": evt.event_id,
                "name": evt.name,
                "timestamp": evt.timestamp.isoformat(),
                "impact": evt.impact,
                "instruments": evt.instruments,
                "forecast": evt.forecast,
                "previous": evt.previous,
                "actual": evt.actual,
                "minutes_until": minutes_until,
                "status": status,
                "volatility_risk": evt.impact,
            }
        )

    return payload
