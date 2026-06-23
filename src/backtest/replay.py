"""Replay session engines for strategy watch and manual trader training modes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, List, Optional
import pandas as pd

from src.core.bus import Bus, InProcessBus
from src.core.clock import ReplayClock, set_clock
from src.core.contracts import (
    BusChannel,
    Direction,
    Instrument,
    Order,
    OrderSide,
    OrderStatus,
    PortfolioState,
    PositionSummary,
    TechnicalSignal,
    TradeSignal,
    SignalStrength,
    SignalSource,
    ExecutionMode,
)
from src.core.ids import new_signal_id
from src.data.store import DataStore
from src.technical.engine import TechnicalEngine
from src.backtest.feed import DataFeed
from src.backtest.engine import MockDecisionEngine, MockExecutionEngine
from src.backtest.session_state import ReplaySessionState
from src.backtest.scorer import ReplayScorer
from src.backtest.reporter import ReplayReporter
from src.backtest.websocket import ReplayWebSocketEmitter

logger = logging.getLogger(__name__)


class StrategyReplaySession:
    """Watch mode: model trades, user observes signals at human speed."""

    def __init__(
        self,
        instrument: Instrument,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        speed: float = 10.0,
        store: Optional[DataStore] = None,
        reports_dir: str = "data/reports",
        timeframe: str = "1h",
    ) -> None:
        self.reporter = ReplayReporter(reports_dir=reports_dir)
        self.instrument = instrument
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        
        self.clock = ReplayClock(start_date)
        set_clock(self.clock)
        
        self.bus = InProcessBus()
        self.store = store or DataStore()
        
        from src.core.contracts import Timeframe
        self.timeframe_enum = Timeframe(timeframe)
        
        # Session state
        self.state = ReplaySessionState(
            mode="watch",
            instrument=instrument,
            speed=speed,
            timeframe=timeframe,
        )
        self.emitter = ReplayWebSocketEmitter()
        
        self._current_bar: Optional[Any] = None
        self._last_tech_sig: Optional[TechnicalSignal] = None
        self._last_trade_sig: Optional[TradeSignal] = None
        self._bars: List[tuple[datetime, Any]] = []
        self._current_idx = 0
        
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Start unpaused
        
        self._run_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the replay session background loop."""
        self.state.update(status="running")
        self._pause_event.set()
        self._run_task = asyncio.create_task(self._replay_loop())

    async def pause(self) -> None:
        """Pause execution."""
        self._pause_event.clear()
        self.state.update(status="paused")

    async def resume(self) -> None:
        """Resume execution."""
        self._pause_event.set()
        self.state.update(status="running")

    async def set_speed(self, multiplier: float) -> None:
        """Set replay speed."""
        self.state.update(speed=multiplier)

    async def jump_to(self, dt: datetime) -> None:
        """Fast-forward virtual time to target datetime."""
        # Pause while jumping
        was_running = self.state.status == "running"
        await self.pause()
        
        self.clock.set_replay_time(dt)
        logger.info(f"Jumped replay time to {dt}")
        
        if was_running:
            await self.resume()

    async def stop(self) -> None:
        """Terminate the session."""
        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
        self.state.update(status="ended")

    async def update_timeframe(self, timeframe: str) -> None:
        """Switch session timeframe dynamically."""
        from src.core.contracts import Timeframe
        new_tf_enum = Timeframe(timeframe)
        if new_tf_enum == self.timeframe_enum:
            return
            
        self.timeframe_enum = new_tf_enum
        self.state.update(timeframe=timeframe)
        
        # Reload bars from the current clock time to the end date
        feed = DataFeed(
            store=self.store,
            instrument=self.instrument,
            timeframes=[self.timeframe_enum],
            start=self.clock.now(),
            end=self.end_date,
            clock=self.clock,
        )
        self._bars = feed._load_all_bars()
        self._current_idx = 0
        self.state.update(total_bars=len(self._bars), current_bar_index=0)

    async def _replay_loop(self) -> None:
        """Main simulation execution loop."""
        # Load configs
        from src.core.config import load_instruments
        inst_configs = load_instruments()
        
        # Setup engines
        tech_engine = TechnicalEngine(
            bus=self.bus,
            store=self.store,
            instruments_config=inst_configs,
        )
        decision_engine = MockDecisionEngine(self.bus)
        exec_engine = MockExecutionEngine(self.bus, initial_capital=self.initial_capital)
        
        # Subscribe locally to keep state updated
        async def on_tech_signal(payload: TechnicalSignal) -> None:
            self._last_tech_sig = payload
            
        async def on_trade_signal(payload: TradeSignal) -> None:
            self._last_trade_sig = payload

        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)

        # Start engines
        await tech_engine.start()
        await decision_engine.start()
        await exec_engine.start()

        # Instantiate feed
        feed = DataFeed(
            store=self.store,
            instrument=self.instrument,
            timeframes=[self.timeframe_enum],
            start=self.start_date,
            end=self.end_date,
            clock=self.clock,
        )
        
        self._bars = feed._load_all_bars()
        self.state.update(total_bars=len(self._bars))
        self._current_idx = 0
        
        try:
            while self._current_idx < len(self._bars):
                close_time, bar = self._bars[self._current_idx]
                # 1. Handle Pausing
                await self._pause_event.wait()
                
                # 2. Dynamic Speed Control
                speed = self.state.speed
                if speed > 0.0:
                    await asyncio.sleep(1.0 / speed)
                
                # 3. Step forward
                self._current_bar = bar
                self.clock.set_replay_time(close_time)
                
                # Publish OHLCV bar to trigger tech/decision/exec pipelines
                await self.bus.publish(BusChannel.OHLCV_BAR, bar)
                
                # Update shared thread-safe state
                open_positions = []
                for inst, p in exec_engine.positions.items():
                    open_positions.append(PositionSummary(
                        instrument=inst,
                        side=p["side"],
                        size=p["size"],
                        entry_price=p["entry_price"],
                        current_price=p["current_price"],
                        unrealized_pnl=exec_engine._calculate_pnl(p),
                        open_since=p["entry_time"],
                    ))
                
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
                
                self.state.update(
                    current_time=close_time,
                    current_bar_index=self._current_idx,
                    open_positions=open_positions,
                    trade_history=exec_engine.trade_history,
                    current_portfolio=portfolio,
                )
                
                # Emit WebSocket frame
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
            # Stop components
            await tech_engine.stop()
            await decision_engine.stop()
            await exec_engine.stop()
            await self.bus.unsubscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)
            await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)


class ManualReplaySession:
    """Trader training mode: DecisionEngine is silent, user enters trades manually."""

    def __init__(
        self,
        instrument: Instrument,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        store: Optional[DataStore] = None,
        reports_dir: str = "data/reports",
        timeframe: str = "1h",
    ) -> None:
        self.reporter = ReplayReporter(reports_dir=reports_dir)
        self.instrument = instrument
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        
        self.clock = ReplayClock(start_date)
        set_clock(self.clock)
        
        self.bus = InProcessBus()
        self.store = store or DataStore()
        
        from src.core.contracts import Timeframe
        self.timeframe_enum = Timeframe(timeframe)
        
        self.state = ReplaySessionState(
            mode="manual",
            instrument=instrument,
            speed=1.0,  # Start with default speed of 1.0
            timeframe=timeframe,
        )
        self.emitter = ReplayWebSocketEmitter()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Start unpaused by default
        self._run_task: Optional[asyncio.Task] = None
        
        self._current_bar: Optional[Any] = None
        self._last_tech_sig: Optional[TechnicalSignal] = None
        self._bars: List[tuple[datetime, Any]] = []
        self._current_idx = 0
        
        self.tech_engine: Optional[TechnicalEngine] = None
        self.exec_engine: Optional[MockExecutionEngine] = None

    async def start(self) -> None:
        """Start manual training session."""
        from src.core.config import load_instruments
        inst_configs = load_instruments()
        
        self.tech_engine = TechnicalEngine(
            bus=self.bus,
            store=self.store,
            instruments_config=inst_configs,
        )
        # Decision engine is omitted in manual mode
        self.exec_engine = MockExecutionEngine(self.bus, initial_capital=self.initial_capital)
        
        async def on_tech_signal(payload: TechnicalSignal) -> None:
            self._last_tech_sig = payload
            
        await self.bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_tech_signal)
        
        await self.tech_engine.start()
        await self.exec_engine.start()
        
        feed = DataFeed(
            store=self.store,
            instrument=self.instrument,
            timeframes=[self.timeframe_enum],
            start=self.start_date,
            end=self.end_date,
            clock=self.clock,
        )
        self._bars = feed._load_all_bars()
        self._current_idx = 0
        self.state.update(status="running", total_bars=len(self._bars))
        
        # Load the very first bar to kick off
        if self._bars:
            await self.step()
            
        self._run_task = asyncio.create_task(self._replay_loop())

    async def step(self) -> None:
        """Advance one primary timeframe bar."""
        if self._current_idx >= len(self._bars):
            await self.end_session()
            return
            
        close_time, bar = self._bars[self._current_idx]
        self._current_bar = bar
        self.clock.set_replay_time(close_time)
        
        # Publish bar
        await self.bus.publish(BusChannel.OHLCV_BAR, bar)
        
        self._current_idx += 1
        
        # Update state
        self._update_session_state(close_time)
        
        # Emit WebSocket frame
        await self.emitter.emit_frame(
            bar=bar,
            technical_signal=self._last_tech_sig,
            trade_signal=None,
            portfolio_state=self.state.current_portfolio,
            session_state_dict=self.state.to_dict(),
        )

    async def step_multiple(self, n: int) -> None:
        """Advance multiple bars sequentially."""
        for _ in range(n):
            if self.state.status == "ended":
                break
            await self.step()

    async def pause(self) -> None:
        """Pause manual execution loop."""
        self._pause_event.clear()
        self.state.update(status="paused")

    async def resume(self) -> None:
        """Resume manual execution loop."""
        if self.state.speed == 0.0:
            self.state.update(speed=1.0)
        self._pause_event.set()
        self.state.update(status="running")

    async def set_speed(self, multiplier: float) -> None:
        """Set manual replay speed multiplier."""
        self.state.update(speed=multiplier)

    async def _replay_loop(self) -> None:
        """Main manual simulation background loop."""
        try:
            while self._current_idx < len(self._bars):
                # 1. Handle Pausing
                await self._pause_event.wait()
                
                # 2. Dynamic Speed Control
                speed = self.state.speed
                if speed > 0.0:
                    await asyncio.sleep(1.0 / speed)
                else:
                    self._pause_event.clear()
                    self.state.update(status="paused")
                    continue
                
                # 3. Advance bar
                await self.step()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in manual replay loop: {e}")

    async def place_order(self, side: OrderSide, size: float) -> Order:
        """Place manual trade order (publishes TradeSignal to isolated bus)."""
        if not self._current_bar:
            raise ValueError("No active bar to reference for entry price")
            
        entry_price = self._current_bar.close
        sig_id = new_signal_id()
        
        # Use simple stop loss / take profit default estimates (e.g. 50 pips)
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
        
        # Let the execution engine process the order
        await asyncio.sleep(0.02)
        
        # Update state and broadcast frame
        if self._current_bar:
            self._update_session_state(self.clock.now())
            await self.emitter.emit_frame(
                bar=self._current_bar,
                technical_signal=self._last_tech_sig,
                trade_signal=trade_sig,
                portfolio_state=self.state.current_portfolio,
                session_state_dict=self.state.to_dict(),
            )
            
        # Construct and return simulated Order object
        order = Order(
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
        return order

    async def close_position(self, instrument: Instrument) -> Order:
        """Close position for selected instrument (publishes Neutral TradeSignal)."""
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
        
        # Let the execution engine process the order
        await asyncio.sleep(0.02)
        
        # Update state and broadcast frame
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
            side=OrderSide.SELL,  # Dummy side
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

    async def end_session(self) -> Dict[str, Any]:
        """Terminate session and run performance scorer."""
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
            
        # Calculate scorecard metrics
        history = self.exec_engine.trade_history if self.exec_engine else []
        equity_hist = self.exec_engine.equity_history if self.exec_engine else []
        
        times, values = zip(*equity_hist) if equity_hist else ([self.start_date], [self.initial_capital])
        equity_curve = pd.Series(values, index=pd.to_datetime(times))
        
        scorecard = ReplayScorer.calculate_metrics(
            trades=history,  # type: ignore
            equity_curve=equity_curve,
            initial_capital=self.initial_capital,
        )
        
        # Write reports
        trades_list = []
        for t in history:
            trades_list.append({
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size": t.size,
                "side": t.side,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
            })
            
        self.reporter.generate(
            mode="manual",
            instrument=self.instrument,
            start_date=self.start_date,
            end_date=self.end_date,
            metrics=scorecard,
            trades=trades_list,
            equity_curve=equity_curve,
        )
        
        return scorecard

    async def update_timeframe(self, timeframe: str) -> None:
        """Switch session timeframe dynamically."""
        from src.core.contracts import Timeframe
        new_tf_enum = Timeframe(timeframe)
        if new_tf_enum == self.timeframe_enum:
            return
            
        self.timeframe_enum = new_tf_enum
        self.state.update(timeframe=timeframe)
        
        # Reload bars from the current clock time to the end date
        feed = DataFeed(
            store=self.store,
            instrument=self.instrument,
            timeframes=[self.timeframe_enum],
            start=self.clock.now(),
            end=self.end_date,
            clock=self.clock,
        )
        self._bars = feed._load_all_bars()
        self._current_idx = 0
        self.state.update(total_bars=len(self._bars), current_bar_index=0)

    def _update_session_state(self, current_time: datetime) -> None:
        """Update shared state container helper."""
        if not self.exec_engine:
            return
            
        open_positions = []
        for inst, p in self.exec_engine.positions.items():
            open_positions.append(PositionSummary(
                instrument=inst,
                side=p["side"],
                size=p["size"],
                entry_price=p["entry_price"],
                current_price=p["current_price"],
                unrealized_pnl=self.exec_engine._calculate_pnl(p),
                open_since=p["entry_time"],
            ))
            
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
