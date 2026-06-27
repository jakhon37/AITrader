"""D07-NOTIFIER — Telegram command processor.

Parses and responds to inbound control commands (/status, /portfolio, /signals,
/halt, /resume) from authorized users.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.api.display_prefs import DisplayPrefs
    from src.data.store import DataStore
    from src.execution.store import ExecutionStore
    from src.fundamental.agent import FundamentalAgent
    from src.signals.registry import SignalStores

from src.core.clock import now
from src.core.display_time import format_chart_time
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
from src.notifier.chat import (
    CHAT_SESSION_TIMEOUT,
    MAX_HISTORY_TURNS,
    answer_trading_question,
    build_trading_context,
    format_chat_reply,
)

_log = get_logger("D07-NOTIFIER")


class CommandProcessor:
    """Processes inbound Telegram updates, handles security, and runs commands."""

    def __init__(
        self,
        bus: Any,
        config: Any,
        signal_stores: Optional["SignalStores"] = None,
        execution_store: Optional["ExecutionStore"] = None,
        fundamental_agent: Optional["FundamentalAgent"] = None,
        data_store: Optional["DataStore"] = None,
        display_prefs: Optional["DisplayPrefs"] = None,
    ) -> None:
        self.bus = bus
        self.config = config
        self.signal_stores = signal_stores
        self.execution_store = execution_store
        self.fundamental_agent = fundamental_agent
        self.data_store = data_store
        self.display_prefs = display_prefs

        # Track confirmation states: user_id -> (command_name, trigger_time)
        self._pending_confirmations: Dict[int, tuple[str, datetime]] = {}
        # Chat Q&A mode: user_id -> last activity time
        self._chat_mode_users: Dict[int, datetime] = {}
        self._chat_history: Dict[int, List[dict[str, str]]] = {}

    def _chart_timezone(self) -> str:
        if self.display_prefs is not None:
            return self.display_prefs.get_chart_timezone()
        return "UTC"

    async def handle_message(self, message: Dict[str, Any], send_callback: Any) -> None:
        """Main routing function for inbound authorized message text."""
        text = message.get("text", "").strip()
        user_id = message.get("from", {}).get("id")

        if not text or not user_id:
            return

        _log.debug("telegram_command_received", user_id=user_id, text=text)

        # Check for active confirmations (takes priority over chat mode)
        if text.upper() == "CONFIRM":
            await self._process_confirmation(user_id, send_callback)
            return

        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        # Free-text Q&A when chat mode is active (commands still work below)
        if self._chat_mode_active(user_id) and not text.startswith("/"):
            await self._handle_chat_message(user_id, text, send_callback)
            return

        # Clear any pending confirmation if a new command is issued
        self._pending_confirmations.pop(user_id, None)

        if cmd == "/start":
            await self._cmd_start(message, send_callback)
        elif cmd == "/help":
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
        elif cmd == "/message":
            await self._cmd_message(user_id, args, send_callback)
        elif cmd == "/done":
            await self._cmd_message_off(user_id, send_callback)
        elif cmd.startswith("/"):
            await send_callback(
                f"❓ Unknown command: {cmd}. Type /help to see all available commands."
            )

    def _portfolio_state(self) -> Optional[PortfolioState]:
        store = self.execution_store
        if store is None and self.signal_stores is not None:
            store = self.signal_stores.execution
        if store is not None:
            return store.get_latest_portfolio()
        return None

    def _health_states(self) -> dict[str, SystemHealthEvent]:
        if self.signal_stores is None:
            return {}
        return self.signal_stores.health.get_all()

    def _execution_mode_label(self) -> str:
        mode_val = self.config.core.execution_mode
        return mode_val.value.upper() if hasattr(mode_val, "value") else str(mode_val).upper()

    def _health_counts(self) -> tuple[int, int, int]:
        ok = degraded = down = 0
        for event in self._health_states().values():
            if event.status == HealthStatus.OK:
                ok += 1
            elif event.status == HealthStatus.DEGRADED:
                degraded += 1
            elif event.status == HealthStatus.DOWN:
                down += 1
        return ok, degraded, down

    def _trading_halted(self) -> bool:
        manual = self._health_states().get("MANUAL_CONTROL")
        return manual is not None and manual.status == HealthStatus.DOWN

    def _next_upcoming_headline(self) -> Optional[str]:
        if self.signal_stores is None:
            return None
        for sig in self.signal_stores.fundamental.get_latest_by_instrument(as_of=now()).values():
            headline = sig.source_headline or ""
            if headline.startswith("Upcoming:"):
                return headline
        return None

    def _last_trade_signal_line(self) -> Optional[str]:
        if self.signal_stores is None:
            return None
        signals = self.signal_stores.trade.list_recent(limit=1, as_of=now())
        if not signals:
            return None
        sig = signals[0]
        emoji = "🟢" if sig.direction == Direction.LONG else "🔴" if sig.direction == Direction.SHORT else "⚪"
        side = sig.suggested_side.value.upper() if sig.suggested_side else "NEUTRAL"
        time_str = format_chart_time(sig.timestamp, self._chart_timezone())
        return (
            f"{emoji} <b>{sig.instrument.value}</b> {side} "
            f"({int(sig.confidence * 100)}%) · {time_str}"
        )

    async def _openrouter_oneline(self) -> str:
        if self.fundamental_agent is None:
            return "LLM: unavailable"
        try:
            from src.fundamental.openrouter_status import (
                build_openrouter_status,
                format_openrouter_status_oneline,
            )

            status = await build_openrouter_status(
                self.config,
                self.fundamental_agent.synthesizer,
                self.fundamental_agent.sentiment_scorer,
            )
            return format_openrouter_status_oneline(status)
        except Exception as exc:  # noqa: BLE001
            _log.warning("openrouter_oneline_failed", error=str(exc))
            return "LLM: status unavailable"

    async def _cmd_start(self, message: Dict[str, Any], send_callback: Any) -> None:
        user = message.get("from", {})
        name = user.get("first_name") or user.get("username") or "trader"
        env_label = getattr(self.config, "env", "dev")
        mode = self._execution_mode_label()
        ts = format_chart_time(now(), self._chart_timezone(), include_date=True)

        p_state = self._portfolio_state()
        equity_line = "Portfolio: warming up…"
        if p_state is not None:
            equity_line = (
                f"Equity <b>${p_state.equity:,.2f}</b> · "
                f"{len(p_state.open_positions)} open position"
                f"{'' if len(p_state.open_positions) == 1 else 's'}"
            )

        ok, degraded, down = self._health_counts()
        health_bits = [f"{ok} OK"]
        if degraded:
            health_bits.append(f"{degraded} degraded")
        if down:
            health_bits.append(f"{down} down")
        health_line = " · ".join(health_bits) if self._health_states() else "awaiting heartbeats"

        trading_line = (
            "🛑 <b>Trading HALTED</b> (manual)"
            if self._trading_halted()
            else "✅ Trading <b>ACTIVE</b>"
        )

        llm_line = await self._openrouter_oneline()
        signal_line = self._last_trade_signal_line()
        upcoming = self._next_upcoming_headline()

        web_ui = os.environ.get("WEB_UI_URL", "").strip()
        dashboard_line = f"\n🖥 Dashboard: {web_ui}" if web_ui else ""

        msg = (
            f"👋 <b>Welcome, {name}!</b>\n\n"
            f"<b>AITrader Remote Control</b> · <code>{mode}</code> · <code>{env_label}</code>\n"
            f"🕐 {ts}\n\n"
            f"<b>📊 Snapshot</b>\n"
            f"• {equity_line}\n"
            f"• Health: {health_line}\n"
            f"• {trading_line}\n"
            f"• 🤖 {llm_line}"
        )

        if signal_line:
            msg += f"\n\n<b>📈 Last signal:</b> {signal_line}"
        if upcoming:
            msg += f"\n<b>📰 Calendar:</b> <i>{upcoming[:100]}</i>"

        msg += (
            f"{dashboard_line}\n\n"
            "<b>Quick commands</b>\n"
            "/status · /portfolio · /signals · /fundamental · /message\n"
            "/halt · /resume\n\n"
            "Type /help for the full command reference."
        )
        await send_callback(msg)

    async def _cmd_help(self, send_callback: Any) -> None:
        msg = (
            "🤖 <b>AITrader Remote Control Help</b>\n\n"
            "/start - Welcome + live snapshot\n"
            "/help - This command list\n"
            "/status - View system status and division health\n"
            "/portfolio - View account balance, open positions, P&L\n"
            "/signals [N] - View the last N trade signals (default 5)\n"
            "/fundamental [pair] - View the latest fundamental signal\n"
            "/message - Start chat Q&A (portfolio, news, calendar, signals)\n"
            "/message off - Exit chat mode\n"
            "/done - Exit chat mode\n"
            "/halt - Halt all trading execution\n"
            "/resume - Resume trading execution"
        )
        await send_callback(msg)

    def _chat_mode_active(self, user_id: int) -> bool:
        last_active = self._chat_mode_users.get(user_id)
        if last_active is None:
            return False
        if now() - last_active > CHAT_SESSION_TIMEOUT:
            self._chat_mode_users.pop(user_id, None)
            self._chat_history.pop(user_id, None)
            return False
        return True

    async def _cmd_message(self, user_id: int, args: List[str], send_callback: Any) -> None:
        if args and args[0].lower() in ("off", "stop", "exit", "end"):
            await self._cmd_message_off(user_id, send_callback)
            return

        self._chat_mode_users[user_id] = now()
        self._chat_history.setdefault(user_id, [])

        if self.fundamental_agent is None or not self.fundamental_agent.synthesizer.api_key:
            await send_callback(
                "💬 <b>Chat mode ON</b> — but OpenRouter is not configured.\n"
                "Set <code>OPENROUTER_API_KEY</code> in .env, then try again.\n\n"
                "Type /message off or /done to exit."
            )
            return

        await send_callback(
            "💬 <b>Chat mode ON</b>\n\n"
            "OpenRouter LLM chat with live DB context (portfolio, signals, news, calendar). "
            "Ask for lists, analysis, or follow-ups — all handled by the model.\n\n"
            "Commands still work (e.g. /portfolio). "
            "Type <b>/message off</b> or <b>/done</b> to exit."
        )

    async def _cmd_message_off(self, user_id: int, send_callback: Any) -> None:
        was_active = user_id in self._chat_mode_users
        self._chat_mode_users.pop(user_id, None)
        self._chat_history.pop(user_id, None)
        if was_active:
            await send_callback("💬 Chat mode <b>OFF</b>. Back to command mode.")
        else:
            await send_callback("💬 Chat mode was not active.")

    async def _handle_chat_message(
        self, user_id: int, text: str, send_callback: Any
    ) -> None:
        self._chat_mode_users[user_id] = now()

        if self.fundamental_agent is None:
            await send_callback("💬 LLM assistant unavailable (fundamental agent not wired).")
            return

        synthesizer = self.fundamental_agent.synthesizer
        context = build_trading_context(
            self.config,
            signal_stores=self.signal_stores,
            data_store=self.data_store,
            execution_store=self.execution_store,
            tz_name=self._chart_timezone(),
        )
        history = self._chat_history.get(user_id, [])

        await send_callback("💬 Thinking…")

        from src.notifier.chat import _is_chat_error_response

        answer = await answer_trading_question(
            text,
            context,
            synthesizer,
            history=history,
            signal_stores=self.signal_stores,
            execution_store=self.execution_store,
            data_store=self.data_store,
            tz_name=self._chart_timezone(),
        )
        await send_callback(format_chat_reply(answer))

        if not _is_chat_error_response(answer):
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": answer})
            self._chat_history[user_id] = history[-(MAX_HISTORY_TURNS * 2) :]

    async def _cmd_status(self, send_callback: Any) -> None:
        mode = self._execution_mode_label()
        p_state = self._portfolio_state()
        pos_count = len(p_state.open_positions) if p_state else 0

        # Predefined list of platform divisions to query
        divisions = [
            "D01-CORE", "D02-DATA", "D03-FUNDAMENTAL", "D04-TECHNICAL",
            "D05-DECISION", "D06-EXECUTION", "D07-NOTIFIER", "D09-TRAINER", "D11-OPS"
        ]

        health_lines = []
        for div in divisions:
            event = self._health_states().get(div)
            status_str = event.status.value.upper() if event else "UNKNOWN"
            emoji = "🟢" if status_str == "OK" else "⚠️" if status_str == "DEGRADED" else "🚨" if status_str == "DOWN" else "⚪"
            health_lines.append(f"{emoji} {div[4:]}: <b>{status_str}</b>")

        openrouter_block = await self._openrouter_status_block()

        msg = (
            f"🤖 <b>System Status</b>\n"
            f"<b>Execution Mode:</b> <code>{mode}</code>\n"
            f"<b>Open Positions:</b> {pos_count}\n\n"
            f"<b>Division Health:</b>\n" + "\n".join(health_lines)
        )
        if openrouter_block:
            msg += f"\n\n{openrouter_block}"
        await send_callback(msg)

    async def _openrouter_status_block(self) -> str:
        if self.fundamental_agent is None:
            return ""
        try:
            from src.fundamental.openrouter_status import (
                format_openrouter_status_telegram,
            )

            status = await self.fundamental_agent.get_openrouter_status()
            return format_openrouter_status_telegram(status)
        except Exception as exc:  # noqa: BLE001
            _log.warning("openrouter_status_failed", error=str(exc))
            return "<b>OpenRouter LLM:</b>\n⚠️ Status unavailable"

    async def _cmd_portfolio(self, send_callback: Any) -> None:
        p_state = self._portfolio_state()
        if not p_state:
            await send_callback("📭 No portfolio state available yet.")
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

        if self.signal_stores is None:
            await send_callback("📭 Trade signal store unavailable.")
            return
        signals = self.signal_stores.trade.list_recent(limit=count, as_of=now())
        if not signals:
            await send_callback("📭 No trade signals recorded yet.")
            return

        lines = [f"📊 <b>Last {len(signals)} Trade Signals:</b>"]
        for s in reversed(signals):
            emoji = "🟢" if s.direction == Direction.LONG else "🔴" if s.direction == Direction.SHORT else "⚪"
            side = s.suggested_side.value.upper() if s.suggested_side else "NEUTRAL"
            time_str = format_chart_time(
                s.timestamp, self._chart_timezone(), include_date=True
            )
            lines.append(
                f"[{time_str}] {emoji} <b>{s.instrument.value}</b>: {side} (conf: {int(s.confidence*100)}%)"
            )

        await send_callback("\n".join(lines))

    async def _cmd_fundamental(self, args: List[str], send_callback: Any) -> None:
        if self.signal_stores is None:
            await send_callback("📭 Fundamental signal store unavailable.")
            return

        latest = self.signal_stores.fundamental.get_latest_by_instrument(as_of=now())
        if args:
            inst_query = args[0].upper().replace("/", "").replace("_", "")
            signal = latest.get(inst_query)
            if not signal:
                await send_callback(f"📭 No fundamental signal for instrument: {inst_query}")
                return
            signals_to_show = [signal]
        else:
            signals_to_show = list(latest.values())

        if not signals_to_show:
            await send_callback("📭 No fundamental signals recorded yet.")
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
