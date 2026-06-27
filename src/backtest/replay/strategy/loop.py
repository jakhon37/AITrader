"""Strategy loop mixin: the speed-controlled pipeline drive loop.

Kept in its own module so alternative loop modes (event-driven, tick-by-tick,
multi-instrument) can be swapped in without touching session lifecycle code.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.core.contracts import (
    BusChannel,
    ExecutionMode,
    PortfolioState,
    PositionSummary,
    TechnicalSignal,
    TradeSignal,
)
from src.backtest.feed import DataFeed
from src.backtest.engine import MockDecisionEngine, MockExecutionEngine
from src.backtest.replay._utils import get_buffer_duration
from src.technical.engine import TechnicalEngine
from src.fundamental.agent import FundamentalAgent
from src.fundamental.sentiment import SentimentScorer
from src.core.config import load_config

if TYPE_CHECKING:
    pass  # avoid circular imports; mixin relies on BaseReplaySession attrs at runtime

logger = logging.getLogger(__name__)

_MIN_SLEEP = 0.02  # batch micro-sleeps to avoid asyncio overhead per bar


class StrategyLoopMixin:
    """Provides _replay_loop() for StrategyReplaySession.

    Depends on attributes provided by BaseReplaySession:
        bus, store, inst_configs, state, clock, instrument, timeframe_enum,
        start_date, end_date, initial_capital, emitter,
        _bars, _current_idx, _current_bar, _last_tech_sig, _pause_event,
        _load_next_bars_chunk()

    And on the attribute injected by StrategyReplaySession.__init__:
        _last_trade_sig
    """

    async def _replay_loop(self) -> None:  # noqa: C901
        """Drive OHLCV bars through the full strategy pipeline at the configured speed."""

        # ── Engine setup ────────────────────────────────────────────────
        self.tech_engine = TechnicalEngine(  # type: ignore[attr-defined]
            bus=self.bus,  # type: ignore[attr-defined]
            store=self.store,  # type: ignore[attr-defined]
            instruments_config=self.inst_configs,  # type: ignore[attr-defined]
        )
        self.tech_engine.enabled = self.state.calculate_indicators  # type: ignore[attr-defined]
        decision_engine = MockDecisionEngine(self.bus)  # type: ignore[attr-defined]
        exec_engine = MockExecutionEngine(
            self.bus, initial_capital=self.initial_capital  # type: ignore[attr-defined]
        )

        # ── Signal capture callbacks ─────────────────────────────────────
        async def on_tech_signal(payload: TechnicalSignal) -> None:
            self._last_tech_sig = payload  # type: ignore[attr-defined]

        async def on_trade_signal(payload: TradeSignal) -> None:
            self._last_trade_sig = payload  # type: ignore[attr-defined]

        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)  # type: ignore[attr-defined]
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)  # type: ignore[attr-defined]

        await self.tech_engine.start()
        await decision_engine.start()
        await exec_engine.start()

        # D03 Fundamental for replay (mock scorer for deterministic historical runs)
        fund_agent: FundamentalAgent | None = None
        try:
            replay_cfg = load_config()
            fund_agent = FundamentalAgent(
                config=replay_cfg,
                bus=self.bus,  # type: ignore[attr-defined]
                store=self.store,  # type: ignore[attr-defined]
                sentiment_scorer=SentimentScorer(backend="mock"),
            )
            await fund_agent.start()
        except Exception as exc:
            logger.warning("Replay fundamental agent failed to start: %s", exc)

        # ── Initial bar buffer ───────────────────────────────────────────
        buffer_dur = get_buffer_duration(self.timeframe_enum)  # type: ignore[attr-defined]
        initial_end = min(self.end_date, self.start_date + buffer_dur)  # type: ignore[attr-defined]
        feed = DataFeed(
            store=self.store,  # type: ignore[attr-defined]
            instrument=self.instrument,  # type: ignore[attr-defined]
            timeframes=[self.timeframe_enum],  # type: ignore[attr-defined]
            start=self.start_date,  # type: ignore[attr-defined]
            end=initial_end,
            clock=self.clock,  # type: ignore[attr-defined]
        )
        self._bars = feed._load_all_bars()  # type: ignore[attr-defined]
        self.state.update(total_bars=len(self._bars))  # type: ignore[attr-defined]
        self._current_idx = 0  # type: ignore[attr-defined]

        # Accurate total count fetched in background (non-blocking)
        async def _fetch_total() -> None:
            try:
                df = await asyncio.to_thread(
                    self.store.get_ohlcv,  # type: ignore[attr-defined]
                    self.instrument,  # type: ignore[attr-defined]
                    self.timeframe_enum,  # type: ignore[attr-defined]
                    self.start_date,  # type: ignore[attr-defined]
                    self.end_date,  # type: ignore[attr-defined]
                )
                is_weekend = (
                    (df.index.weekday == 5) |
                    ((df.index.weekday == 4) & (df.index.hour >= 22)) |
                    ((df.index.weekday == 6) & (df.index.hour < 22))
                )
                is_empty = (df["volume"] == 0) & (df["open"] == df["close"])
                df_filtered = df[~(is_weekend | is_empty)]
                self.state.update(total_bars=len(df_filtered))  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("Could not fetch total bar count: %s", exc)
                self.state.update(total_bars=len(self._bars))  # type: ignore[attr-defined]

        asyncio.create_task(_fetch_total())

        # ── Main drive loop ──────────────────────────────────────────────
        accumulated_sleep = 0.0
        try:
            while self._current_idx < len(self._bars):  # type: ignore[attr-defined]
                close_time, bar = self._bars[self._current_idx]  # type: ignore[attr-defined]

                # 1. Respect pause gate
                await self._pause_event.wait()  # type: ignore[attr-defined]

                # 2. Speed throttle — batch micro-sleeps
                speed = self.state.speed  # type: ignore[attr-defined]
                if speed > 0.0:
                    accumulated_sleep += 1.0 / speed
                    if accumulated_sleep >= _MIN_SLEEP:
                        await asyncio.sleep(accumulated_sleep)
                        accumulated_sleep = 0.0

                # 3. Advance virtual clock and publish bar
                self._current_bar = bar  # type: ignore[attr-defined]
                self.clock.set_replay_time(close_time)  # type: ignore[attr-defined]
                await self.bus.publish(BusChannel.OHLCV_BAR, bar)  # type: ignore[attr-defined]

                # 4. Build portfolio snapshot
                open_positions = [
                    PositionSummary(
                        instrument=leg["instrument"],
                        side=leg["side"],
                        size=leg["size"],
                        entry_price=leg["entry_price"],
                        current_price=leg["current_price"],
                        unrealized_pnl=exec_engine._calculate_pnl(leg),
                        open_since=leg["entry_time"],
                        leg_id=leg_id,
                        sl=leg.get("sl"),
                        tp=leg.get("tp"),
                    )
                    for leg_id, leg in exec_engine.position_legs.items()
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

                self._current_idx += 1  # type: ignore[attr-defined]

                # 5. Prefetch next buffer chunk when approaching the end
                if self._current_idx >= len(self._bars) - 50:  # type: ignore[attr-defined]
                    await self._load_next_bars_chunk()  # type: ignore[attr-defined]

                # 6. Update shared state and push WebSocket frame
                self.state.update(  # type: ignore[attr-defined]
                    current_time=close_time,
                    current_bar_index=self._current_idx,  # type: ignore[attr-defined]
                    open_positions=open_positions,
                    trade_history=exec_engine.trade_history,
                    current_portfolio=portfolio,
                )
                await self.emitter.emit_frame(  # type: ignore[attr-defined]
                    bar=bar,
                    technical_signal=self._last_tech_sig,  # type: ignore[attr-defined]
                    trade_signal=self._last_trade_sig,  # type: ignore[attr-defined]
                    portfolio_state=portfolio,
                    session_state_dict=self.state.to_dict(),  # type: ignore[attr-defined]
                )

        except asyncio.CancelledError:
            pass
        finally:
            if fund_agent is not None:
                await fund_agent.stop()
            if self.tech_engine:  # type: ignore[attr-defined]
                await self.tech_engine.stop()
            await decision_engine.stop()
            await exec_engine.stop()
            await self.bus.unsubscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)  # type: ignore[attr-defined]
            await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)  # type: ignore[attr-defined]
