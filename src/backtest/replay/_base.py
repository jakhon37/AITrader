"""Base replay session: shared initialisation, controls, and data-loading helpers.

All concrete session classes (StrategyReplaySession, ManualReplaySession) inherit
from BaseReplaySession to eliminate duplicated clock/bus/store setup, chunk-loading,
and timeframe-switching logic.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional

from src.core.bus import InProcessBus
from src.core.clock import ReplayClock, set_clock
from src.core.contracts import BusChannel, Instrument, TechnicalSignal
from src.data.store import DataStore
from src.backtest.feed import DataFeed
from src.backtest.session_state import ReplaySessionState
from src.backtest.reporter import ReplayReporter
from src.backtest.websocket import ReplayWebSocketEmitter
from src.backtest.replay._utils import get_buffer_duration

logger = logging.getLogger(__name__)


class BaseReplaySession:
    """Shared foundation for all replay session modes.

    Owns:
    - Clock / bus / store bootstrap
    - Instrument config wiring
    - Pause / resume / speed / indicator controls
    - Sliding-window bar-chunk loader
    - Dynamic timeframe switching
    """

    def __init__(
        self,
        instrument: Instrument,
        start_date: datetime,
        end_date: datetime,
        mode: str,
        speed: float,
        initial_capital: float = 10_000.0,
        store: Optional[DataStore] = None,
        reports_dir: str = "data/reports",
        timeframe: str = "1h",
        calculate_indicators: bool = True,
    ) -> None:
        self.reporter = ReplayReporter(reports_dir=reports_dir)
        self.instrument = instrument
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital

        # Clock & event bus — isolated per session
        self.clock = ReplayClock(start_date)
        set_clock(self.clock)
        self.bus = InProcessBus()
        self.store = store or DataStore()

        # Timeframe wiring
        from src.core.contracts import Timeframe

        self.timeframe_enum = Timeframe(timeframe)

        from src.core.config import load_instruments

        self.inst_configs = load_instruments()
        if self.instrument in self.inst_configs:
            self.inst_configs[self.instrument].primary_timeframe = self.timeframe_enum
            if self.timeframe_enum not in self.inst_configs[self.instrument].active_timeframes:
                self.inst_configs[self.instrument].active_timeframes.append(self.timeframe_enum)

        # Shared session bookkeeping
        self.state = ReplaySessionState(
            mode=mode,
            instrument=instrument,
            speed=speed,
            timeframe=timeframe,
            calculate_indicators=calculate_indicators,
        )
        self.emitter = ReplayWebSocketEmitter()
        self.tech_engine = None  # set by subclass in start()

        # Bar buffer
        self._current_bar: Optional[Any] = None
        self._last_tech_sig: Optional[TechnicalSignal] = None
        self._bars: List[tuple[datetime, Any]] = []
        self._current_idx = 0

        # Flow control
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # start unpaused
        self._run_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Flow controls (shared; ManualReplaySession overrides resume)
    # ------------------------------------------------------------------

    async def pause(self) -> None:
        """Pause the replay loop."""
        self._pause_event.clear()
        self.state.update(status="paused")

    async def resume(self) -> None:
        """Resume the replay loop."""
        self._pause_event.set()
        self.state.update(status="running")

    async def set_speed(self, multiplier: float) -> None:
        """Adjust replay speed multiplier."""
        self.state.update(speed=multiplier)

    async def set_indicators_enabled(self, enabled: bool) -> None:
        """Toggle indicator computation on the fly."""
        self.state.update(calculate_indicators=enabled)
        if self.tech_engine:
            self.tech_engine.enabled = enabled

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    async def _load_next_bars_chunk(self) -> None:
        """Fetch the next sliding-window chunk and append it to the bar buffer."""
        if not self._bars:
            return

        last_close_time, _ = self._bars[-1]
        start_time = last_close_time + timedelta(seconds=1)
        if start_time >= self.end_date:
            return

        buffer_dur = get_buffer_duration(self.timeframe_enum)
        end_time = min(self.end_date, start_time + buffer_dur)

        def _load() -> list:
            feed = DataFeed(
                store=self.store,
                instrument=self.instrument,
                timeframes=[self.timeframe_enum],
                start=start_time,
                end=end_time,
                clock=self.clock,
            )
            return feed._load_all_bars()

        next_bars = await asyncio.to_thread(_load)
        if next_bars:
            self._bars.extend(next_bars)

    async def update_timeframe(self, timeframe: str) -> None:
        """Switch the session timeframe dynamically without restarting."""
        from src.core.contracts import Timeframe

        new_tf = Timeframe(timeframe)
        if new_tf == self.timeframe_enum:
            return

        self.timeframe_enum = new_tf
        self.state.update(timeframe=timeframe)

        if self.instrument in self.inst_configs:
            self.inst_configs[self.instrument].primary_timeframe = self.timeframe_enum
            if self.timeframe_enum not in self.inst_configs[self.instrument].active_timeframes:
                self.inst_configs[self.instrument].active_timeframes.append(self.timeframe_enum)

        # Reload bars from current virtual clock position
        buffer_dur = get_buffer_duration(self.timeframe_enum)
        current_time = self.clock.now()
        initial_end = min(self.end_date, current_time + buffer_dur)

        feed = DataFeed(
            store=self.store,
            instrument=self.instrument,
            timeframes=[self.timeframe_enum],
            start=current_time,
            end=initial_end,
            clock=self.clock,
        )
        self._bars = feed._load_all_bars()
        self._current_idx = 0
        self.state.update(total_bars=len(self._bars), current_bar_index=0)

        # Refresh accurate total in background
        async def _fetch_total() -> None:
            try:
                df = await asyncio.to_thread(
                    self.store.get_ohlcv,
                    self.instrument,
                    self.timeframe_enum,
                    current_time,
                    self.end_date,
                )
                is_weekend = (
                    (df.index.weekday == 5) |
                    ((df.index.weekday == 4) & (df.index.hour >= 22)) |
                    ((df.index.weekday == 6) & (df.index.hour < 22))
                )
                is_empty = (df["volume"] == 0) & (df["open"] == df["close"])
                df_filtered = df[~(is_weekend | is_empty)]
                self.state.update(total_bars=len(df_filtered))
            except Exception as exc:
                logger.warning("Failed to refresh total bar count: %s", exc)

        asyncio.create_task(_fetch_total())
