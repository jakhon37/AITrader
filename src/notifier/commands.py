"""D07-NOTIFIER — Telegram command processor.

Parses and responds to inbound control commands (/status, /portfolio, /signals,
/halt, /resume) from authorized users.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.core.clock import now
from src.core.contracts import (
    BusChannel,
    Direction,
    FundamentalSignal,
    HealthStatus,
    PortfolioState,
    SystemHealthEvent,
    TradeSignal,
)
from src.core.ids import new_signal_id
from src.core.logging import get_logger

_log = get_logger("D07-NOTIFIER")


class CommandCache:
    """Stores the latest state snapshots received from the bus for remote commands."""

    def __init__(self) -> None:
        self.health_states: Dict[str, SystemHealthEvent] = {}
        self.portfolio_state: Optional[PortfolioState] = None
        self.trade_signals: List[TradeSignal] = []
        self.fundamental_signals: Dict[str, FundamentalSignal] = {}

    def add_health(self, event: SystemHealthEvent) -> None:
        self.health_states[event.division] = event

    def add_trade_signal(self, signal: TradeSignal) -> None:
        self.trade_signals.append(signal)
        # Keep only the last 20 signals to save memory
        if len(self.trade_signals) > 20:
            self.trade_signals.pop(0)

    def add_fundamental_signal(self, signal: FundamentalSignal) -> None:
        self.fundamental_signals[signal.instrument.value] = signal


class CommandProcessor:
    """Processes inbound Telegram updates, handles security, and runs commands."""

    def __init__(self, bus: Any, config: Any, cache: CommandCache) -> None:
        self.bus = bus
        self.config = config
        self.cache = cache

        # Track confirmation states: user_id -> (command_name, trigger_time)
        self._pending_confirmations: Dict[int, tuple[str, datetime]] = {}

    async def handle_message(self, message: Dict[str, Any], send_callback: Any) -> None:
        """Main routing function for inbound authorized message text."""
        text = message.get("text", "").strip()
        user_id = message.get("from", {}).get("id")

        if not text or not user_id:
            return

        _log.debug("telegram_command_received", user_id=user_id, text=text)

        # Check for active confirmations
        if text.upper() == "CONFIRM":
            await self._process_confirmation(user_id, send_callback)
            return

        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        # Clear any pending confirmation if a new command is issued
        self._pending_confirmations.pop(user_id, None)

        if cmd == "/help":
            await self._cmd_help(send_callback)
        elif cmd == "/status":
            await self._cmd_status(send_callback)
        elif cmd == "/portfolio":
            await self._cmd_portfolio(send_callback)
        elif cmd == "/signals":
            await self._cmd_signals(args, send_callback)
        elif cmd == "/fundamental":
            await self._cmd_fundamental(args, send_callback)
        elif cmd == "/halt":
            await self._cmd_halt(user_id, send_callback)
        elif cmd == "/resume":
            await self._cmd_resume(user_id, send_callback)
        elif cmd.startswith("/"):
            await send_callback(
                f"❓ Unknown command: {cmd}. Type /help to see all available commands."
            )

    async def _cmd_help(self, send_callback: Any) -> None:
        msg = (
            "🤖 <b>AITrader Remote Control Help</b>\n\n"
            "/status - View system status and division health\n"
            "/portfolio - View account balance, open positions, P&L\n"
            "/signals [N] - View the last N trade signals (default 5)\n"
            "/fundamental [pair] - View the latest fundamental signal\n"
            "/halt - Halt all trading execution\n"
            "/resume - Resume trading execution"
        )
        await send_callback(msg)

    async def _cmd_status(self, send_callback: Any) -> None:
        mode_val = self.config.core.execution_mode
        mode = mode_val.value.upper() if hasattr(mode_val, "value") else str(mode_val).upper()
        pos_count = len(self.cache.portfolio_state.open_positions) if self.cache.portfolio_state else 0

        # Predefined list of platform divisions to query
        divisions = [
            "D01-CORE", "D02-DATA", "D03-FUNDAMENTAL", "D04-TECHNICAL",
            "D05-DECISION", "D06-EXECUTION", "D07-NOTIFIER", "D11-OPS"
        ]

        health_lines = []
        for div in divisions:
            event = self.cache.health_states.get(div)
            status_str = event.status.value.upper() if event else "UNKNOWN"
            emoji = "🟢" if status_str == "OK" else "⚠️" if status_str == "DEGRADED" else "🚨" if status_str == "DOWN" else "⚪"
            health_lines.append(f"{emoji} {div[4:]}: <b>{status_str}</b>")

        msg = (
            f"🤖 <b>System Status</b>\n"
            f"<b>Execution Mode:</b> <code>{mode}</code>\n"
            f"<b>Open Positions:</b> {pos_count}\n\n"
            f"<b>Division Health:</b>\n" + "\n".join(health_lines)
        )
        await send_callback(msg)

    async def _cmd_portfolio(self, send_callback: Any) -> None:
        p_state = self.cache.portfolio_state
        if not p_state:
            await send_callback("📭 No portfolio state updates received yet.")
            return

        lines = [
            "💼 <b>Portfolio Summary</b>",
            f"<b>Balance:</b> ${p_state.balance:,.2f}",
            f"<b>Equity:</b> ${p_state.equity:,.2f}",
            f"<b>Free Margin:</b> ${p_state.free_margin:,.2f}",
            f"<b>Today's P&L:</b> ${p_state.realized_pnl_today:+,.2f} ({p_state.drawdown_pct:+.2%})",
            f"<b>Active Positions:</b> {len(p_state.open_positions)}",
        ]

        if p_state.open_positions:
            lines.append("\n<b>Positions:</b>")
            for pos in p_state.open_positions:
                p_emoji = "🟢" if pos.side.value == "buy" else "🔴"
                lines.append(
                    f"{p_emoji} {pos.instrument.value} {pos.side.value.upper()} "
                    f"{pos.size:.2f} lots @ {pos.entry_price:.5f} (P&L: ${pos.unrealized_pnl:+,.2f})"
                )

        await send_callback("\n".join(lines))

    async def _cmd_signals(self, args: List[str], send_callback: Any) -> None:
        # Default display count of 5
        count = 5
        if args:
            try:
                count = min(20, max(1, int(args[0])))
            except ValueError:
                pass

        signals = self.cache.trade_signals[-count:]
        if not signals:
            await send_callback("📭 No trade signals recorded in cache.")
            return

        lines = [f"📊 <b>Last {len(signals)} Trade Signals:</b>"]
        for s in reversed(signals):
            emoji = "🟢" if s.direction == Direction.LONG else "🔴" if s.direction == Direction.SHORT else "⚪"
            side = s.suggested_side.value.upper() if s.suggested_side else "NEUTRAL"
            time_str = s.timestamp.strftime("%m-%d %H:%M")
            lines.append(
                f"[{time_str}] {emoji} <b>{s.instrument.value}</b>: {side} (conf: {int(s.confidence*100)}%)"
            )

        await send_callback("\n".join(lines))

    async def _cmd_fundamental(self, args: List[str], send_callback: Any) -> None:
        if args:
            inst_query = args[0].upper().replace("/", "").replace("_", "")
            signal = self.cache.fundamental_signals.get(inst_query)
            if not signal:
                await send_callback(f"📭 No fundamental signal cache for instrument: {inst_query}")
                return
            signals_to_show = [signal]
        else:
            signals_to_show = list(self.cache.fundamental_signals.values())

        if not signals_to_show:
            await send_callback("📭 No fundamental signals recorded in cache.")
            return

        lines = ["📰 <b>Latest Fundamental Views:</b>"]
        for s in signals_to_show:
            emoji = "🟢" if s.direction == Direction.LONG else "🔴" if s.direction == Direction.SHORT else "⚪"
            lines.append(
                f"{emoji} <b>{s.instrument.value}</b> ({s.event_type.value.upper()}): "
                f"score {s.sentiment_score:+.2f} | strength {s.strength.value.upper()}"
            )
            if s.source_headline:
                lines.append(f"  └ <i>{s.source_headline[:80]}...</i>")

        await send_callback("\n".join(lines))

    async def _cmd_halt(self, user_id: int, send_callback: Any) -> None:
        self._pending_confirmations[user_id] = ("halt", now())
        await send_callback(
            "⚠️ <b>WARNING: Manual Trading Halt Requested</b>\n\n"
            "This will immediately halt all order processing. "
            "Please reply with exactly <b>CONFIRM</b> within 30 seconds to proceed."
        )

    async def _cmd_resume(self, user_id: int, send_callback: Any) -> None:
        self._pending_confirmations[user_id] = ("resume", now())
        await send_callback(
            "⚠️ <b>Manual Trading Resume Requested</b>\n\n"
            "This will resume signal and order processing. "
            "Please reply with exactly <b>CONFIRM</b> within 30 seconds to proceed."
        )

    async def _process_confirmation(self, user_id: int, send_callback: Any) -> None:
        pending = self._pending_confirmations.pop(user_id, None)
        if not pending:
            await send_callback("❌ No pending confirmation request found.")
            return

        command, trigger_time = pending
        if now() - trigger_time > timedelta(seconds=30):
            await send_callback("❌ Confirmation timeout. Please run the command again.")
            return

        if command == "halt":
            # Publish system health degraded/down status to trigger circuit breaker
            event = SystemHealthEvent(
                signal_id=new_signal_id(),
                division="MANUAL_CONTROL",
                status=HealthStatus.DOWN,
                timestamp=now(),
                message="Trading execution manually halted by user command.",
                metrics={},
            )
            await self.bus.publish(BusChannel.SYSTEM_HEALTH, event)
            await send_callback("🛑 <b>Trading execution has been manually HALTED.</b>")
            _log.info("manual_halt_executed", user_id=user_id)

        elif command == "resume":
            # Publish system health OK status to reset circuit breaker
            event = SystemHealthEvent(
                signal_id=new_signal_id(),
                division="MANUAL_CONTROL",
                status=HealthStatus.OK,
                timestamp=now(),
                message="Trading execution manually resumed by user command.",
                metrics={},
            )
            await self.bus.publish(BusChannel.SYSTEM_HEALTH, event)
            await send_callback("✅ <b>Trading execution has been manually RESUMED.</b>")
            _log.info("manual_resume_executed", user_id=user_id)
