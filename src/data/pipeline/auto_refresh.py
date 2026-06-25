"""D02-DATA — background Parquet refresh worker for the API backend."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from src.core.config import AppConfig

if TYPE_CHECKING:
    from src.data.scheduler import DataScheduler
from src.core.logging import get_logger
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.pipeline.refresh import refresh_all_enabled, refresh_slow_resample_all
from src.data.store import DataStore

_log = get_logger("D02-DATA")


class DataRefreshWorker:
    """Runs Dukascopy tail refresh on startup and on timeframe-aware intervals."""

    def __init__(
        self,
        store: DataStore,
        cfg: AppConfig,
        feed: Optional[DukascopyFeed] = None,
        scheduler: Optional["DataScheduler"] = None,
        *,
        startup_grace_sec: float = 90.0,
    ) -> None:
        self._store = store
        self._cfg = cfg
        self._feed = feed or DukascopyFeed()
        self._scheduler = scheduler
        self._startup_grace_sec = startup_grace_sec
        self._started_at_mono = time.monotonic()
        pipeline = cfg.data.pipeline
        self._fast_interval_sec = pipeline.tail_refresh_interval_sec
        self._slow_interval_sec = pipeline.tail_resample_slow_interval_sec
        self._enabled = pipeline.auto_refresh and cfg.data.source == "dukascopy"
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._last_fast_refresh_at: Optional[datetime] = None
        self._last_slow_resample_at: Optional[datetime] = None
        self._last_refresh_error: Optional[str] = None
        self._last_refresh_rows: dict[str, int] = {}
        self._last_slow_rows: dict[str, int] = {}
        self._refresh_in_progress = False
        self._last_fast_mono = 0.0
        self._last_slow_mono = 0.0

    async def start(self) -> None:
        if not self._enabled:
            _log.info("data_refresh_worker_disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        _log.info(
            "data_refresh_worker_started",
            fast_interval_sec=self._fast_interval_sec,
            slow_interval_sec=self._slow_interval_sec,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _log.info("data_refresh_worker_stopped")

    async def _loop(self) -> None:
        while self._running:
            await self._run_due_jobs()
            try:
                await asyncio.sleep(self._sleep_until_next_job())
            except asyncio.CancelledError:
                break

    def _sleep_until_next_job(self) -> float:
        now = time.monotonic()
        fast_due = self._fast_interval_sec - (now - self._last_fast_mono)
        slow_due = self._slow_interval_sec - (now - self._last_slow_mono)
        return max(30.0, min(fast_due, slow_due, 300.0))

    def _should_defer_refresh(self) -> bool:
        """Yield Dukascopy lock to live intraday polls after startup / chart focus."""
        if self._scheduler is not None and self._scheduler.is_intraday_focused():
            return True
        if self._scheduler is not None:
            elapsed = time.monotonic() - self._started_at_mono
            if (
                elapsed < self._startup_grace_sec
                and self._scheduler.focused_pair is not None
            ):
                return True
        return False

    async def _run_due_jobs(self) -> None:
        if self._refresh_in_progress:
            return
        if self._should_defer_refresh():
            _log.debug("data_refresh_deferred_live_priority")
            return
        now_mono = time.monotonic()
        run_fast = (now_mono - self._last_fast_mono) >= self._fast_interval_sec
        run_slow = (now_mono - self._last_slow_mono) >= self._slow_interval_sec
        if not run_fast and not run_slow:
            return

        self._refresh_in_progress = True
        self._last_refresh_error = None
        try:
            loop = asyncio.get_running_loop()
            if run_fast:
                results = await loop.run_in_executor(
                    None,
                    lambda: refresh_all_enabled(
                        self._store, self._feed, self._cfg, mode="tail"
                    ),
                )
                self._last_refresh_rows = results
                self._last_fast_refresh_at = datetime.now(timezone.utc)
                self._last_fast_mono = now_mono
                _log.info("data_refresh_fast_complete", rows=results)

            if run_slow:
                slow_results = await loop.run_in_executor(
                    None,
                    lambda: refresh_slow_resample_all(self._store, self._cfg),
                )
                self._last_slow_rows = slow_results
                self._last_slow_resample_at = datetime.now(timezone.utc)
                self._last_slow_mono = now_mono
                _log.info("data_refresh_slow_complete", rows=slow_results)
        except Exception as exc:
            self._last_refresh_error = str(exc)
            _log.error("data_refresh_worker_failed", error=str(exc))
        finally:
            self._refresh_in_progress = False

    async def _run_tail_refresh(self) -> None:
        """Backward-compatible entry for tests."""
        self._last_fast_mono = 0.0
        await self._run_due_jobs()

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "running": self._running,
            "in_progress": self._refresh_in_progress,
            "fast_interval_sec": self._fast_interval_sec,
            "slow_interval_sec": self._slow_interval_sec,
            "last_refresh_at": (
                self._last_fast_refresh_at.isoformat()
                if self._last_fast_refresh_at
                else None
            ),
            "last_slow_resample_at": (
                self._last_slow_resample_at.isoformat()
                if self._last_slow_resample_at
                else None
            ),
            "last_refresh_error": self._last_refresh_error,
            "last_refresh_rows": self._last_refresh_rows,
            "last_slow_rows": self._last_slow_rows,
        }