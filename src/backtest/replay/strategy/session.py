"""Watch-mode replay session: lifecycle controls (start / stop / jump_to).

Loop logic lives in loop.py (StrategyLoopMixin) so it can be swapped
independently when new loop modes are added.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.core.contracts import Instrument, TradeSignal
from src.data.store import DataStore
from src.backtest.replay._base import BaseReplaySession
from src.backtest.replay.strategy.loop import StrategyLoopMixin

logger = logging.getLogger(__name__)


class StrategyReplaySession(StrategyLoopMixin, BaseReplaySession):
    """Watch mode: strategy model trades autonomously; user observes.

    Full pipeline: TechnicalEngine → MockDecisionEngine → MockExecutionEngine
    runs on the isolated in-process bus at configurable speed.
    """

    def __init__(
        self,
        instrument: Instrument,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10_000.0,
        speed: float = 10.0,
        store: Optional[DataStore] = None,
        reports_dir: str = "data/reports",
        timeframe: str = "1h",
        calculate_indicators: bool = True,
    ) -> None:
        super().__init__(
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            mode="watch",
            speed=speed,
            initial_capital=initial_capital,
            store=store,
            reports_dir=reports_dir,
            timeframe=timeframe,
            calculate_indicators=calculate_indicators,
        )
        # Captured by StrategyLoopMixin.on_trade_signal callback
        self._last_trade_sig: Optional[TradeSignal] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Kick off the background replay loop."""
        self.state.update(status="running")
        self._pause_event.set()
        self._run_task = asyncio.create_task(self._replay_loop())

    async def stop(self) -> None:
        """Cancel the loop and mark the session as ended."""
        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
        self.state.update(status="ended")

    # ------------------------------------------------------------------
    # Watch-mode controls
    # ------------------------------------------------------------------

    async def jump_to(self, dt: datetime) -> None:
        """Fast-forward virtual time to *dt*, preserving the running/paused state."""
        was_running = self.state.status == "running"
        await self.pause()
        self.clock.set_replay_time(dt)
        logger.info("Jumped replay time to %s", dt)
        if was_running:
            await self.resume()
