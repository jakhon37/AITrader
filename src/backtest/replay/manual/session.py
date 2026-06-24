"""Manual replay session: lifecycle only (start / end_session / resume override).

Stepping logic  → stepping.py  (SteppingMixin)
Trading logic   → trading.py   (TradingMixin)
Shared controls → _base.py     (BaseReplaySession: pause, set_speed, update_timeframe …)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from src.core.contracts import BusChannel, Instrument
from src.data.store import DataStore
from src.backtest.engine import MockExecutionEngine
from src.backtest.feed import DataFeed

from src.backtest.replay._utils import get_buffer_duration
from src.backtest.replay._base import BaseReplaySession
from src.backtest.replay.analytics import build_manual_session_analytics
from src.backtest.replay.manual.stepping import SteppingMixin
from src.backtest.replay.manual.trading import TradingMixin
from src.technical.engine import TechnicalEngine

logger = logging.getLogger(__name__)


class ManualReplaySession(SteppingMixin, TradingMixin, BaseReplaySession):
    """Trader-training mode: model is silent; user controls every trade.

    MRO: ManualReplaySession → SteppingMixin → TradingMixin → BaseReplaySession

    Responsibilities of this file (session.py)
    -------------------------------------------
    - __init__           : declare exec_engine; delegate rest to BaseReplaySession
    - resume()           : override to reset speed==0 back to 1×
    - start()            : wire engines, load first bar buffer, launch loop
    - end_session()      : teardown, score, write HTML report
    """

    def __init__(
        self,
        instrument: Instrument,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10_000.0,
        store: Optional[DataStore] = None,
        reports_dir: str = "data/reports",
        timeframe: str = "1h",
        calculate_indicators: bool = True,
    ) -> None:
        super().__init__(
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            mode="manual",
            speed=1.0,
            initial_capital=initial_capital,
            store=store,
            reports_dir=reports_dir,
            timeframe=timeframe,
            calculate_indicators=calculate_indicators,
        )
        self.exec_engine: Optional[MockExecutionEngine] = None

    # ------------------------------------------------------------------
    # Flow control override
    # ------------------------------------------------------------------

    async def resume(self) -> None:
        """Resume; resets speed to 1× if the session was frozen at speed=0."""
        if self.state.speed == 0.0:
            self.state.update(speed=1.0)
        self._pause_event.set()
        self.state.update(status="running")

    # ------------------------------------------------------------------
    # Lifecycle — start
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Wire engines, load the first bar buffer, and launch the replay loop."""
        self.tech_engine = TechnicalEngine(
            bus=self.bus,
            store=self.store,
            instruments_config=self.inst_configs,
        )
        self.tech_engine.enabled = self.state.calculate_indicators
        # DecisionEngine intentionally omitted — user provides all trade signals
        self.exec_engine = MockExecutionEngine(self.bus, initial_capital=self.initial_capital)

        async def on_tech_signal(payload: Any) -> None:
            self._last_tech_sig = payload

        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)
        await self.tech_engine.start()
        await self.exec_engine.start()

        # Initial bar buffer
        buffer_dur = get_buffer_duration(self.timeframe_enum)
        initial_end = min(self.end_date, self.start_date + buffer_dur)
        feed = DataFeed(
            store=self.store,
            instrument=self.instrument,
            timeframes=[self.timeframe_enum],
            start=self.start_date,
            end=initial_end,
            clock=self.clock,
        )
        self._bars = feed._load_all_bars()
        self._current_idx = 0
        self.state.update(status="running", total_bars=len(self._bars))

        # Accurate total bar count in background
        async def _fetch_total() -> None:
            try:
                df = await asyncio.to_thread(
                    self.store.get_ohlcv,
                    self.instrument,
                    self.timeframe_enum,
                    self.start_date,
                    self.end_date,
                )
                self.state.update(total_bars=len(df))
            except Exception as exc:
                logger.warning("Could not fetch total bar count: %s", exc)

        asyncio.create_task(_fetch_total())

        # Publish first bar so the UI has something to render immediately
        if self._bars:
            await self.step()

        self._run_task = asyncio.create_task(self._replay_loop())

    # ------------------------------------------------------------------
    # Lifecycle — teardown
    # ------------------------------------------------------------------

    async def end_session(self) -> Dict[str, Any]:
        """Cancel loop, stop engines, score the session, write the HTML report."""
        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
        self.state.update(status="ended")

        if self.tech_engine:
            await self.tech_engine.stop()
        if self.exec_engine:
            await self.exec_engine.stop()

        history = self.exec_engine.trade_history if self.exec_engine else []
        equity_hist = self.exec_engine.equity_history if self.exec_engine else []
        open_count = len(self.exec_engine.position_legs) if self.exec_engine else 0

        analytics = build_manual_session_analytics(
            trade_history=history,
            equity_history=equity_hist,
            initial_capital=self.initial_capital,
            instrument=self.instrument,
            start_date=self.start_date,
            current_time=self.state.current_time,
            open_positions_count=open_count,
            session_status="ended",
        )

        times, values = (
            zip(*equity_hist) if equity_hist else ([self.start_date], [self.initial_capital])
        )
        equity_curve = pd.Series(values, index=pd.to_datetime(times))

        self.reporter.generate(
            mode="manual",
            instrument=self.instrument,
            start_date=self.start_date,
            end_date=self.end_date,
            metrics={k: v for k, v in analytics.items() if k not in ("trades", "equity_curve", "trade_pnls", "summary")},
            trades=analytics["trades"],
            equity_curve=equity_curve,
        )
        return analytics

    def build_live_analytics(self) -> Dict[str, Any]:
        """Score the current session without tearing it down (for in-session review)."""
        history = self.exec_engine.trade_history if self.exec_engine else []
        equity_hist = self.exec_engine.equity_history if self.exec_engine else []
        open_count = len(self.exec_engine.position_legs) if self.exec_engine else 0
        return build_manual_session_analytics(
            trade_history=history,
            equity_history=equity_hist,
            initial_capital=self.initial_capital,
            instrument=self.instrument,
            start_date=self.start_date,
            current_time=self.state.current_time,
            open_positions_count=open_count,
            session_status=self.state.status,
        )
