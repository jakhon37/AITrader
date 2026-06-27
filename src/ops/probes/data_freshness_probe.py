"""D11-OPS — Live data freshness checks against the Parquet store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.candle import TF_DURATION
from src.core.contracts import Instrument, Timeframe
from src.core.logging import get_logger
from src.core.session import is_instrument_session_open
from src.data.store import DataStore

_log = get_logger("D11-OPS")

_TF_MINUTES: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
}


class DataFreshnessProbe:
    """Alert when the latest stored bar is older than expected during market hours."""

    def __init__(
        self,
        store: DataStore,
        stale_multiplier: float = 2.0,
    ) -> None:
        self._store = store
        self._stale_multiplier = stale_multiplier

    @staticmethod
    def _bar_close_time(bar_open: datetime, timeframe: Timeframe) -> datetime:
        """Freshness is measured from candle close, not open."""
        if bar_open.tzinfo is None:
            bar_open = bar_open.replace(tzinfo=timezone.utc)
        return bar_open + TF_DURATION.get(timeframe, TF_DURATION[Timeframe.H1])

    def _age_minutes(
        self,
        bar_open: datetime,
        timeframe: Timeframe,
        now: datetime,
    ) -> float:
        close_ts = self._bar_close_time(bar_open, timeframe)
        return (now - close_ts).total_seconds() / 60.0

    def check_pair(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        *,
        now: datetime | None = None,
        live_last_bar_at: datetime | None = None,
        live_last_error: str | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        candle_min = _TF_MINUTES.get(timeframe, 60)
        max_age_min = candle_min * self._stale_multiplier

        if not is_instrument_session_open(now, instrument):
            return {
                "status": "ok",
                "instrument": instrument.value,
                "timeframe": timeframe.value,
                "message": "Market closed — freshness check skipped",
                "age_minutes": None,
            }

        # Prefer scheduler live bar — avoids heavy Parquet scans on the API event loop.
        if live_last_bar_at is not None:
            live_ts = live_last_bar_at
            if live_ts.tzinfo is None:
                live_ts = live_ts.replace(tzinfo=timezone.utc)
            live_age = self._age_minutes(live_ts, timeframe, now)
            if live_age <= max_age_min:
                return {
                    "status": "ok",
                    "instrument": instrument.value,
                    "timeframe": timeframe.value,
                    "last_bar_at": live_ts.isoformat(),
                    "age_minutes": round(live_age, 1),
                    "threshold_minutes": max_age_min,
                    "source": "live_poll",
                    "message": (
                        f"Last bar {live_age:.0f}m ago (live_poll, "
                        f"threshold {max_age_min:.0f}m)"
                    ),
                }

        try:
            last_stored, _ = self._store.peek_latest_ohlcv(instrument, timeframe)
            if last_stored is not None:
                last_ts = last_stored.astimezone(timezone.utc)
                age_min = self._age_minutes(last_ts, timeframe, now)
                effective_ts = last_ts
                source = "parquet_tail"
                if live_last_bar_at is not None:
                    live_ts = live_last_bar_at
                    if live_ts.tzinfo is None:
                        live_ts = live_ts.replace(tzinfo=timezone.utc)
                    if live_ts > last_ts:
                        effective_ts = live_ts
                        age_min = self._age_minutes(live_ts, timeframe, now)
                        source = "live_poll"
                status = "ok" if age_min <= max_age_min else "degraded"
                message = (
                    f"Last bar {age_min:.0f}m ago ({source}, "
                    f"threshold {max_age_min:.0f}m)"
                )
                if status == "degraded" and live_last_error:
                    message = f"{message}; fetch error: {live_last_error[:120]}"
                return {
                    "status": status,
                    "instrument": instrument.value,
                    "timeframe": timeframe.value,
                    "last_bar_at": effective_ts.isoformat(),
                    "parquet_last_bar_at": last_ts.isoformat(),
                    "age_minutes": round(age_min, 1),
                    "threshold_minutes": max_age_min,
                    "source": source,
                    "message": message,
                }

            start = now - timedelta(hours=6)
            df = self._store.get_ohlcv(instrument, timeframe, start, now)
        except Exception as exc:
            _log.warning(
                "data_freshness_probe_error",
                instrument=instrument.value,
                timeframe=timeframe.value,
                error=str(exc),
            )
            return {
                "status": "down",
                "instrument": instrument.value,
                "timeframe": timeframe.value,
                "message": f"No readable data: {exc}",
                "age_minutes": None,
            }

        if df.empty:
            return {
                "status": "down",
                "instrument": instrument.value,
                "timeframe": timeframe.value,
                "message": "Partition exists but returned zero rows",
                "age_minutes": None,
            }

        last_ts = df.index[-1]
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        age_min = self._age_minutes(last_ts, timeframe, now)

        effective_ts = last_ts
        source = "parquet"
        if live_last_bar_at is not None:
            live_ts = live_last_bar_at
            if live_ts.tzinfo is None:
                live_ts = live_ts.replace(tzinfo=timezone.utc)
            live_age = self._age_minutes(live_ts, timeframe, now)
            if live_ts > last_ts:
                effective_ts = live_ts
                age_min = live_age
                source = "live_poll"

        status = "ok"
        message = f"Last bar {age_min:.0f}m ago ({source}, threshold {max_age_min:.0f}m)"
        if age_min > max_age_min:
            status = "degraded"
            message = (
                f"Stale data: last bar {age_min:.0f}m ago ({source}) "
                f"(>{max_age_min:.0f}m during session)"
            )
            if live_last_error:
                message = f"{message}; fetch error: {live_last_error[:120]}"

        return {
            "status": status,
            "instrument": instrument.value,
            "timeframe": timeframe.value,
            "last_bar_at": effective_ts.isoformat(),
            "parquet_last_bar_at": last_ts.isoformat(),
            "age_minutes": round(age_min, 1),
            "threshold_minutes": max_age_min,
            "source": source,
            "message": message,
        }

    def check_all(
        self,
        pairs: list[tuple[Instrument, Timeframe]],
        *,
        now: datetime | None = None,
        scheduler_pairs: dict[str, dict[str, Any]] | None = None,
        scheduler_error: str | None = None,
    ) -> dict[str, Any]:
        scheduler_pairs = scheduler_pairs or {}
        results = []
        for inst, tf in pairs:
            key = f"{inst.value}/{tf.value}"
            live = scheduler_pairs.get(key, {})
            if not live.get("last_bar_at"):
                # Bootstrap polls H1; use that live bar when M1 key is absent.
                live = scheduler_pairs.get(f"{inst.value}/1h", live)
            live_at_raw = live.get("last_bar_at")
            live_at: datetime | None = None
            if live_at_raw:
                try:
                    live_at = datetime.fromisoformat(str(live_at_raw))
                except ValueError:
                    live_at = None
            results.append(
                self.check_pair(
                    inst,
                    tf,
                    now=now,
                    live_last_bar_at=live_at,
                    live_last_error=live.get("last_error") or scheduler_error,
                )
            )
        worst = "ok"
        for row in results:
            if row["status"] == "down":
                worst = "down"
                break
            if row["status"] == "degraded":
                worst = "degraded"

        return {
            "status": worst,
            "pairs": results,
            "checked": len(results),
        }