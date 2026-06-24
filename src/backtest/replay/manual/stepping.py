"""Stepping mixin: bar-advance controls and session-state synchronisation.

Owns:
- step()                  — advance one bar, publish to bus, emit WS frame
- step_multiple(n)        — convenience multi-step
- _replay_loop()          — speed-controlled auto-advance background coroutine
- _update_session_state() — rebuild PortfolioState from exec_engine and persist

Future additions: step_back(), fast_forward_to(), playback_rate_ramp()
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from src.core.contracts import (
    BusChannel,
    ExecutionMode,
    PortfolioState,
    PositionSummary,
)

logger = logging.getLogger(__name__)

_MIN_SLEEP = 0.02  # batch micro-sleeps threshold


class SteppingMixin:
    """Bar-advance controls for ManualReplaySession.

    All attribute access (bus, clock, state, emitter, exec_engine, etc.)
    is satisfied by BaseReplaySession and ManualReplaySession at runtime.
    """

    async def step(self) -> None:
        """Advance one primary-timeframe bar and emit a WebSocket frame."""
        if self._current_idx >= len(self._bars):  # type: ignore[attr-defined]
            await self.end_session()  # type: ignore[attr-defined]
            return

        close_time, bar = self._bars[self._current_idx]  # type: ignore[attr-defined]
        self._current_bar = bar  # type: ignore[attr-defined]
        self.clock.set_replay_time(close_time)  # type: ignore[attr-defined]
        await self.bus.publish(BusChannel.OHLCV_BAR, bar)  # type: ignore[attr-defined]

        self._current_idx += 1  # type: ignore[attr-defined]
        if self._current_idx >= len(self._bars) - 50:  # type: ignore[attr-defined]
            await self._load_next_bars_chunk()  # type: ignore[attr-defined]

        self._update_session_state(close_time)
        await self.emitter.emit_frame(  # type: ignore[attr-defined]
            bar=bar,
            technical_signal=self._last_tech_sig,  # type: ignore[attr-defined]
            trade_signal=None,
            portfolio_state=self.state.current_portfolio,  # type: ignore[attr-defined]
            session_state_dict=self.state.to_dict(),  # type: ignore[attr-defined]
        )

    async def step_multiple(self, n: int) -> None:
        """Advance *n* bars sequentially, stopping early if the session ends."""
        for _ in range(n):
            if self.state.status == "ended":  # type: ignore[attr-defined]
                break
            await self.step()

    async def _replay_loop(self) -> None:
        """Speed-controlled auto-advance loop; pauses when speed == 0 (step-only mode)."""
        accumulated_sleep = 0.0
        try:
            while self._current_idx < len(self._bars):  # type: ignore[attr-defined]
                await self._pause_event.wait()  # type: ignore[attr-defined]

                speed = self.state.speed  # type: ignore[attr-defined]
                if speed > 0.0:
                    accumulated_sleep += 1.0 / speed
                    if accumulated_sleep >= _MIN_SLEEP:
                        await asyncio.sleep(accumulated_sleep)
                        accumulated_sleep = 0.0
                else:
                    # speed == 0: freeze loop; user steps manually
                    self._pause_event.clear()  # type: ignore[attr-defined]
                    self.state.update(status="paused")  # type: ignore[attr-defined]
                    continue

                await self.step()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Error in manual replay loop: %s", exc)

    def _update_session_state(self, current_time: datetime) -> None:
        """Rebuild PortfolioState from exec_engine and persist it to shared state."""
        exec_engine = self.exec_engine  # type: ignore[attr-defined]
        if not exec_engine:
            return

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
            signal_id=self._current_bar.signal_id  # type: ignore[attr-defined]
            if self._current_bar  # type: ignore[attr-defined]
            else "manual",
            timestamp=current_time,
            execution_mode=ExecutionMode.PAPER,
            balance=exec_engine.balance,
            equity=exec_engine.equity,
            margin_used=0.0,
            free_margin=exec_engine.equity,
            open_positions=open_positions,
            realized_pnl_today=sum(t.pnl for t in exec_engine.trade_history),
            drawdown_pct=0.0,
        )

        self.state.update(  # type: ignore[attr-defined]
            current_time=current_time,
            current_bar_index=self._current_idx,  # type: ignore[attr-defined]
            open_positions=open_positions,
            trade_history=exec_engine.trade_history,
            pending_orders=exec_engine.get_pending_orders_serializable(),
            current_portfolio=portfolio,
        )
