"""DataScheduler — candle-close timer and OHLCVBar bus publisher."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

from src.core.bus import Bus
from src.core.clock import VirtualClock
from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.data.feeds.base import OHLCVFeed
from src.data.scheduler.fetcher import OHLCVFetcher
from src.data.scheduler.live import LiveSchedulerMixin
from src.data.scheduler.replay import ReplaySchedulerMixin
from src.data.scheduler.store_ops import bars_from_store
from src.data.scheduler.types import (
    BACKGROUND_POLL_INTERVAL_SEC,
    FOCUSED_POLL_INTERVAL_SEC,
    INTRADAY_FOCUS_TFS,
    PairLiveStatus,
)
from src.data.store import DataStore

_log = get_logger("D02-DATA")


class DataScheduler(ReplaySchedulerMixin, LiveSchedulerMixin):
    """Candle-close event scheduler for D02-DATA.

    Live mode: ``run()`` polls Dukascopy and publishes OHLCVBar events.
    Replay mode: ``tick()`` emits bars from the store on virtual clock steps.
    """

    def __init__(
        self,
        bus: Bus,
        store: DataStore,
        clock: VirtualClock,
        fetcher: Optional[OHLCVFetcher] = None,
        feed: Optional[OHLCVFeed] = None,
        data_source: str = "dukascopy",
        active_pairs: Optional[list[tuple[Instrument, Timeframe]]] = None,
        focused_poll_interval_sec: float = FOCUSED_POLL_INTERVAL_SEC,
        background_poll_interval_sec: float = BACKGROUND_POLL_INTERVAL_SEC,
        m1_poll_interval_sec: float = 60.0,
        live_poll_adaptive: bool = True,
    ) -> None:
        self._bus = bus
        self._store = store
        self._clock = clock
        self._fetcher = fetcher or OHLCVFetcher(feed=feed, source=data_source)
        self._m1_poll_interval_sec = m1_poll_interval_sec
        self._active_pairs: list[tuple[Instrument, Timeframe]] = (
            active_pairs
            if active_pairs is not None
            else [
                (Instrument.EURUSD, Timeframe.H1),
                (Instrument.GBPUSD, Timeframe.H1),
                (Instrument.USDJPY, Timeframe.H1),
                (Instrument.XAUUSD, Timeframe.H1),
            ]
        )
        self._bootstrap_pairs: tuple[tuple[Instrument, Timeframe], ...] = tuple(
            self._active_pairs
        )
        self._focused_pair: Optional[tuple[Instrument, Timeframe]] = None
        self._focused_poll_interval_sec = focused_poll_interval_sec
        self._background_poll_interval_sec = background_poll_interval_sec
        self._live_poll_adaptive = live_poll_adaptive
        self._running = False
        self._last_emitted: dict[tuple[Instrument, Timeframe], datetime] = {}
        self._pair_status: dict[str, PairLiveStatus] = {}
        self._last_global_error: Optional[str] = None
        self._last_global_poll_at: Optional[datetime] = None
        self._focus_wake_pairs: list[tuple[Instrument, Timeframe]] = []
        self._last_immediate_poll_mono: dict[
            tuple[Instrument, Timeframe], float
        ] = {}

    def stop(self) -> None:
        """Signal the live loop to stop after the current sleep."""
        self._running = False
        _log.info("scheduler_stop_requested")

    def reset_last_emitted(self) -> None:
        """Clear emission tracking — used by D08 when starting a new replay session."""
        self._last_emitted.clear()

    def add_active_pair(self, instrument: Instrument, timeframe: Timeframe) -> None:
        """Dynamically add an instrument/timeframe pair to the scheduling loop."""
        pair = (instrument, timeframe)
        if pair not in self._active_pairs:
            self._active_pairs.append(pair)
            _log.info(
                "scheduler_pair_added",
                instrument=instrument.value,
                timeframe=timeframe.value,
            )

    def is_intraday_focused(self) -> bool:
        """True when the chart is on an intraday timeframe (M1–M30)."""
        if self._focused_pair is None:
            return False
        return self._focused_pair[1] in INTRADAY_FOCUS_TFS

    def set_focused_pair(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> bool:
        """Mark the chart's active pair for faster polling. Returns True if focus changed."""
        pair = (instrument, timeframe)
        if pair == self._focused_pair:
            return False

        merged = list(self._bootstrap_pairs)
        if pair not in merged:
            merged.append(pair)
        removed = [p for p in self._active_pairs if p not in merged]
        self._active_pairs = merged
        self._focused_pair = pair
        if removed:
            _log.info(
                "scheduler_pairs_pruned",
                removed=[(i.value, tf.value) for i, tf in removed],
            )
        _log.info(
            "scheduler_pair_focused",
            instrument=instrument.value,
            timeframe=timeframe.value,
        )
        self._focus_wake_pairs.append(pair)
        return True

    def drain_focus_wake_pairs(self) -> list[tuple[Instrument, Timeframe]]:
        """Pairs to poll immediately on the next live-loop tick (chart focus change)."""
        pairs = list(self._focus_wake_pairs)
        self._focus_wake_pairs.clear()
        return pairs

    def _hydrate_focused_pair_status(self) -> None:
        """Seed pair status from Parquet so the UI is not blank before first poll."""
        if self._focused_pair is None:
            return
        inst, tf = self._focused_pair
        key = self._pair_key(inst, tf)
        existing = self._pair_status.get(key, {})
        if existing.get("last_bar_at"):
            return
        try:
            completed, active = bars_from_store(self._store, inst, tf)
            latest = (
                active
                if active is not None and active.timestamp > completed.timestamp
                else completed
            )
            status = self._pair_status.setdefault(key, {})
            status.setdefault("last_bar_at", latest.timestamp.isoformat())
            status.setdefault("close", latest.close)
            status.setdefault("source", latest.source)
        except DataError:
            pass

    def get_live_status(self) -> dict[str, Any]:
        """Return scheduler health for the terminal live-chart status UI."""
        self._hydrate_focused_pair_status()
        focused: Optional[dict[str, str]] = None
        focused_poll_interval_sec: Optional[float] = None
        if self._focused_pair is not None:
            inst, tf = self._focused_pair
            focused = {"instrument": inst.value, "timeframe": tf.value}
            focused_poll_interval_sec = self._poll_interval_for(inst, tf)

        return {
            "running": self._running,
            "focused_pair": focused,
            "focused_poll_interval_sec": focused_poll_interval_sec,
            "active_pairs": [
                {"instrument": i.value, "timeframe": tf.value}
                for i, tf in self._active_pairs
            ],
            "data_source": getattr(
                getattr(self._fetcher, "_feed", self._fetcher),
                "source_name",
                "dukascopy",
            ),
            "live_poll_adaptive": self._live_poll_adaptive,
            "poll_interval_focused_sec": self._focused_poll_interval_sec,
            "poll_interval_background_sec": self._background_poll_interval_sec,
            "poll_interval_m1_sec": self._m1_poll_interval_sec,
            "last_poll_at": (
                self._last_global_poll_at.isoformat()
                if self._last_global_poll_at is not None
                else None
            ),
            "last_error": self._last_global_error,
            "pairs": dict(self._pair_status),
        }

    @staticmethod
    def _pair_key(instrument: Instrument, timeframe: Timeframe) -> str:
        return f"{instrument.value}/{timeframe.value}"

    @property
    def active_pairs(self) -> list[tuple[Instrument, Timeframe]]:
        return list(self._active_pairs)

    @property
    def focused_pair(self) -> Optional[tuple[Instrument, Timeframe]]:
        return self._focused_pair