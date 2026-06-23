"""Watch-mode replay session: model trades, user observes at configurable speed."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.core.contracts import (
    BusChannel,
    ExecutionMode,
    Instrument,
    PortfolioState,
    PositionSummary,
    TechnicalSignal,
    TradeSignal,
)
from src.data.store import DataStore
from src.backtest.feed import DataFeed
from src.backtest.engine import MockDecisionEngine, MockExecutionEngine
from src.backtest.replay._utils import get_buffer_duration
from src.backtest.replay._base import BaseReplaySession
from src.technical.engine import TechnicalEngine

logger = logging.getLogger(__name__)


class StrategyReplaySession(BaseReplaySession):
    """Watch mode: the strategy model trades autonomously; the user observes.

    The full pipeline (TechnicalEngine → MockDecisionEngine → MockExecutionEngine)
    runs on the isolated bus.  Speed is configurable (default 10 bars/sec).
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
        # Watch-mode only: capture the latest trade signal for WS emission
        self._last_trade_sig: Optional[TradeSignal] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the replay session background loop."""
        self.state.update(status="running")
        self._pause_event.set()
        self._run_task = asyncio.create_task(self._replay_loop())

    async def stop(self) -> None:
        """Cancel the replay loop and mark session as ended."""
        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
        self.state.update(status="ended")

    # ------------------------------------------------------------------
    # Watch-mode control
    # ------------------------------------------------------------------

    async def jump_to(self, dt: datetime) -> None:
        """Fast-forward virtual time to *dt*, keeping pause state."""
        was_running = self.state.status == "running"
        await self.pause()
        self.clock.set_replay_time(dt)
        logger.info("Jumped replay time to %s", dt)
        if was_running:
            await self.resume()

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _replay_loop(self) -> None:  # noqa: C901
        """Drive bars through the full pipeline at the requested speed."""
        # --- Engine setup ---
        self.tech_engine = TechnicalEngine(
            bus=self.bus,
            store=self.store,
            instruments_config=self.inst_configs,
        )
        self.tech_engine.enabled = self.state.calculate_indicators
        decision_engine = MockDecisionEngine(self.bus)
        exec_engine = MockExecutionEngine(self.bus, initial_capital=self.initial_capital)

        # --- Local signal capture ---
        async def on_tech_signal(payload: TechnicalSignal) -> None:
            self._last_tech_sig = payload

        async def on_trade_signal(payload: TradeSignal) -> None:
            self._last_trade_sig = payload

        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)

        await self.tech_engine.start()
        await decision_engine.start()
        await exec_engine.start()

        # --- Initial bar buffer ---
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
        self.state.update(total_bars=len(self._bars))
        self._current_idx = 0

        # Accurate total bar count (background)
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
                self.state.update(total_bars=len(self._bars))

        asyncio.create_task(_fetch_total())

        # --- Main loop ---
        accumulated_sleep = 0.0
        MIN_SLEEP = 0.02
        try:
            while self._current_idx < len(self._bars):
                close_time, bar = self._bars[self._current_idx]

                # 1. Respect pause
                await self._pause_event.wait()

                # 2. Speed throttle (batch micro-sleeps)
                speed = self.state.speed
                if speed > 0.0:
                    accumulated_sleep += 1.0 / speed
                    if accumulated_sleep >= MIN_SLEEP:
                        await asyncio.sleep(accumulated_sleep)
                        accumulated_sleep = 0.0

                # 3. Advance virtual clock and publish bar
                self._current_bar = bar
                self.clock.set_replay_time(close_time)
                await self.bus.publish(BusChannel.OHLCV_BAR, bar)

                # 4. Build portfolio snapshot
                open_positions = [
                    PositionSummary(
                        instrument=inst,
                        side=p["side"],
                        size=p["size"],
                        entry_price=p["entry_price"],
                        current_price=p["current_price"],
                        unrealized_pnl=exec_engine._calculate_pnl(p),
                        open_since=p["entry_time"],
                    )
                    for inst, p in exec_engine.positions.items()
                ]
                portfolio = PortfolioState(
                    signal_id=bar.signal_id,
                    timestamp=close_time,
                    execution_mode=ExecutionMode.PAPER,
                    balance=exec_engine.balance,
                    equity=exec_engine.equity,
                    margin_used=0.0,
                    free_margin=exec_engine.equity,
                    open_positions=open_positions,
                    realized_pnl_today=sum(t.pnl for t in exec_engine.trade_history),
                    drawdown_pct=0.0,
                )

                self._current_idx += 1

                # 5. Prefetch next chunk when near end of buffer
                if self._current_idx >= len(self._bars) - 50:
                    await self._load_next_bars_chunk()

                # 6. Update shared state + emit WebSocket frame
                self.state.update(
                    current_time=close_time,
                    current_bar_index=self._current_idx,
                    open_positions=open_positions,
                    trade_history=exec_engine.trade_history,
                    current_portfolio=portfolio,
                )
                await self.emitter.emit_frame(
                    bar=bar,
                    technical_signal=self._last_tech_sig,
                    trade_signal=self._last_trade_sig,
                    portfolio_state=portfolio,
                    session_state_dict=self.state.to_dict(),
                )

        except asyncio.CancelledError:
            pass
        finally:
            if self.tech_engine:
                await self.tech_engine.stop()
            await decision_engine.stop()
            await exec_engine.stop()
            await self.bus.unsubscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)
            await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)
