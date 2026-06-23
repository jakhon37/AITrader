"""Trader-training replay session: model is silent, user enters trades manually."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from src.core.contracts import (
    BusChannel,
    Direction,
    ExecutionMode,
    Instrument,
    Order,
    OrderSide,
    OrderStatus,
    PortfolioState,
    PositionSummary,
    SignalSource,
    SignalStrength,
    TradeSignal,
)
from src.core.ids import new_signal_id
from src.data.store import DataStore
from src.backtest.engine import MockExecutionEngine
from src.backtest.feed import DataFeed
from src.backtest.scorer import ReplayScorer
from src.backtest.replay._utils import get_buffer_duration
from src.backtest.replay._base import BaseReplaySession
from src.technical.engine import TechnicalEngine

logger = logging.getLogger(__name__)


class ManualReplaySession(BaseReplaySession):
    """Trader-training mode: DecisionEngine is silent; user places all orders.

    The user steps through bars manually (step / step_multiple), places orders
    via place_order(), and closes positions via close_position().  At the end,
    end_session() scores the run and writes an HTML report.
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
    # Flow control overrides
    # ------------------------------------------------------------------

    async def resume(self) -> None:
        """Resume the loop; resets speed to 1× when it was set to 0 (frozen)."""
        if self.state.speed == 0.0:
            self.state.update(speed=1.0)
        self._pause_event.set()
        self.state.update(status="running")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise engines, load the first bar buffer, and kick off the loop."""
        self.tech_engine = TechnicalEngine(
            bus=self.bus,
            store=self.store,
            instruments_config=self.inst_configs,
        )
        self.tech_engine.enabled = self.state.calculate_indicators
        # Decision engine deliberately omitted — user provides all signals
        self.exec_engine = MockExecutionEngine(self.bus, initial_capital=self.initial_capital)

        async def on_tech_signal(payload: Any) -> None:
            self._last_tech_sig = payload

        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)
        await self.tech_engine.start()
        await self.exec_engine.start()

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

        # Accurate total count (background)
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

        # Publish the first bar so the UI has something to render
        if self._bars:
            await self.step()

        self._run_task = asyncio.create_task(self._replay_loop())

    # ------------------------------------------------------------------
    # Manual stepping
    # ------------------------------------------------------------------

    async def step(self) -> None:
        """Advance one primary-timeframe bar."""
        if self._current_idx >= len(self._bars):
            await self.end_session()
            return

        close_time, bar = self._bars[self._current_idx]
        self._current_bar = bar
        self.clock.set_replay_time(close_time)
        await self.bus.publish(BusChannel.OHLCV_BAR, bar)

        self._current_idx += 1
        if self._current_idx >= len(self._bars) - 50:
            await self._load_next_bars_chunk()

        self._update_session_state(close_time)
        await self.emitter.emit_frame(
            bar=bar,
            technical_signal=self._last_tech_sig,
            trade_signal=None,
            portfolio_state=self.state.current_portfolio,
            session_state_dict=self.state.to_dict(),
        )

    async def step_multiple(self, n: int) -> None:
        """Advance *n* bars sequentially."""
        for _ in range(n):
            if self.state.status == "ended":
                break
            await self.step()

    # ------------------------------------------------------------------
    # Trading operations
    # ------------------------------------------------------------------

    async def place_order(self, side: OrderSide, size: float) -> Order:
        """Publish a manual TradeSignal and return the simulated filled Order."""
        if not self._current_bar:
            raise ValueError("No active bar — cannot determine entry price.")

        entry_price = self._current_bar.close
        sig_id = new_signal_id()

        pip = 0.0001 if self.instrument != Instrument.USDJPY else 0.01
        sl = entry_price - (50 * pip) if side == OrderSide.BUY else entry_price + (50 * pip)
        tp = entry_price + (100 * pip) if side == OrderSide.BUY else entry_price - (100 * pip)

        trade_sig = TradeSignal(
            signal_id=sig_id,
            instrument=self.instrument,
            timestamp=self.clock.now(),
            valid_until=self.clock.now() + timedelta(hours=1),
            direction=Direction.LONG if side == OrderSide.BUY else Direction.SHORT,
            confidence=1.0,
            strength=SignalStrength.STRONG,
            fundamental_weight=0.0,
            technical_weight=0.0,
            suggested_side=side,
            suggested_entry=entry_price,
            suggested_sl=sl,
            suggested_tp=tp,
            suggested_size=size,
            narrative="Manual trader execution",
            sources=SignalSource(fundamental=None, technical=None),
            model_version="manual",
        )
        await self.bus.publish(BusChannel.TRADE_SIGNAL, trade_sig)
        await asyncio.sleep(0.02)  # let exec engine process

        if self._current_bar:
            self._update_session_state(self.clock.now())
            await self.emitter.emit_frame(
                bar=self._current_bar,
                technical_signal=self._last_tech_sig,
                trade_signal=trade_sig,
                portfolio_state=self.state.current_portfolio,
                session_state_dict=self.state.to_dict(),
            )

        return Order(
            order_id=sig_id[:8],
            signal_id=sig_id,
            instrument=self.instrument,
            side=side,
            size=size,
            order_type="market",
            limit_price=None,
            stop_price=None,
            sl=sl,
            tp=tp,
            status=OrderStatus.FILLED,
            created_at=self.clock.now(),
            filled_at=self.clock.now(),
            filled_price=entry_price,
            execution_mode="paper",
        )

    async def close_position(self, instrument: Instrument) -> Order:
        """Publish a neutral TradeSignal to close the active position."""
        sig_id = new_signal_id()
        trade_sig = TradeSignal(
            signal_id=sig_id,
            instrument=instrument,
            timestamp=self.clock.now(),
            valid_until=self.clock.now(),
            direction=Direction.NEUTRAL,
            confidence=1.0,
            strength=SignalStrength.STRONG,
            fundamental_weight=0.0,
            technical_weight=0.0,
            suggested_side=None,
            suggested_entry=self._current_bar.close if self._current_bar else 0.0,
            suggested_sl=None,
            suggested_tp=None,
            suggested_size=0.0,
            narrative="Manual position closeout",
            sources=SignalSource(fundamental=None, technical=None),
            model_version="manual",
        )
        await self.bus.publish(BusChannel.TRADE_SIGNAL, trade_sig)
        await asyncio.sleep(0.02)  # let exec engine process

        if self._current_bar:
            self._update_session_state(self.clock.now())
            await self.emitter.emit_frame(
                bar=self._current_bar,
                technical_signal=self._last_tech_sig,
                trade_signal=trade_sig,
                portfolio_state=self.state.current_portfolio,
                session_state_dict=self.state.to_dict(),
            )

        return Order(
            order_id=sig_id[:8],
            signal_id=sig_id,
            instrument=instrument,
            side=OrderSide.SELL,
            size=0.0,
            order_type="market",
            limit_price=None,
            stop_price=None,
            sl=None,
            tp=None,
            status=OrderStatus.FILLED,
            created_at=self.clock.now(),
            filled_at=self.clock.now(),
            filled_price=self._current_bar.close if self._current_bar else 0.0,
            execution_mode="paper",
        )

    # ------------------------------------------------------------------
    # Session teardown
    # ------------------------------------------------------------------

    async def end_session(self) -> Dict[str, Any]:
        """Cancel loop, score the session, and write the HTML report."""
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

        times, values = (
            zip(*equity_hist) if equity_hist else ([self.start_date], [self.initial_capital])
        )
        equity_curve = pd.Series(values, index=pd.to_datetime(times))

        scorecard = ReplayScorer.calculate_metrics(
            trades=history,  # type: ignore[arg-type]
            equity_curve=equity_curve,
            initial_capital=self.initial_capital,
        )

        self.reporter.generate(
            mode="manual",
            instrument=self.instrument,
            start_date=self.start_date,
            end_date=self.end_date,
            metrics=scorecard,
            trades=[
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "size": t.size,
                    "side": t.side,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                }
                for t in history
            ],
            equity_curve=equity_curve,
        )
        return scorecard

    # ------------------------------------------------------------------
    # Internal loop & helpers
    # ------------------------------------------------------------------

    async def _replay_loop(self) -> None:
        """Speed-controlled auto-advance loop for non-zero speed."""
        accumulated_sleep = 0.0
        MIN_SLEEP = 0.02
        try:
            while self._current_idx < len(self._bars):
                await self._pause_event.wait()

                speed = self.state.speed
                if speed > 0.0:
                    accumulated_sleep += 1.0 / speed
                    if accumulated_sleep >= MIN_SLEEP:
                        await asyncio.sleep(accumulated_sleep)
                        accumulated_sleep = 0.0
                else:
                    # Speed == 0 means step-only mode; freeze the loop
                    self._pause_event.clear()
                    self.state.update(status="paused")
                    continue

                await self.step()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Error in manual replay loop: %s", exc)

    def _update_session_state(self, current_time: datetime) -> None:
        """Rebuild and persist the portfolio snapshot into shared session state."""
        if not self.exec_engine:
            return

        open_positions = [
            PositionSummary(
                instrument=inst,
                side=p["side"],
                size=p["size"],
                entry_price=p["entry_price"],
                current_price=p["current_price"],
                unrealized_pnl=self.exec_engine._calculate_pnl(p),
                open_since=p["entry_time"],
            )
            for inst, p in self.exec_engine.positions.items()
        ]

        portfolio = PortfolioState(
            signal_id=self._current_bar.signal_id if self._current_bar else "manual",
            timestamp=current_time,
            execution_mode=ExecutionMode.PAPER,
            balance=self.exec_engine.balance,
            equity=self.exec_engine.equity,
            margin_used=0.0,
            free_margin=self.exec_engine.equity,
            open_positions=open_positions,
            realized_pnl_today=sum(t.pnl for t in self.exec_engine.trade_history),
            drawdown_pct=0.0,
        )

        self.state.update(
            current_time=current_time,
            current_bar_index=self._current_idx,
            open_positions=open_positions,
            trade_history=self.exec_engine.trade_history,
            current_portfolio=portfolio,
        )
