"""D07-NOTIFIER — OpenRouter Q&A assistant with live DB + cache context."""

from __future__ import annotations

import html
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional

import httpx

if TYPE_CHECKING:
    from src.data.store import DataStore
    from src.execution.store import ExecutionStore
    from src.fundamental.synthesizer import NarrativeSynthesizer
    from src.notifier.commands import CommandCache

from src.core.clock import now
from src.core.contracts import Direction, HealthStatus
from src.core.logging import get_logger
from src.fundamental.text_utils import sanitize_llm_narrative

_log = get_logger("D07-NOTIFIER")

CHAT_SESSION_TIMEOUT = timedelta(minutes=30)
MAX_CONTEXT_CHARS = 12_000
MAX_HISTORY_TURNS = 4


def build_trading_context(
    cache: "CommandCache",
    config: Any,
    data_store: Optional["DataStore"] = None,
    execution_store: Optional["ExecutionStore"] = None,
) -> str:
    """Assemble a plain-text snapshot from SQLite stores and live bus cache."""
    sections: list[str] = []
    current = now()

    mode_val = getattr(getattr(config, "core", None), "execution_mode", "paper")
    mode_label = mode_val.value.upper() if hasattr(mode_val, "value") else str(mode_val).upper()
    env_label = getattr(config, "env", "dev")
    sections.append(f"Environment: {env_label} | Execution mode: {mode_label}")

    manual = cache.health_states.get("MANUAL_CONTROL")
    trading_halted = manual is not None and manual.status == HealthStatus.DOWN
    sections.append(f"Trading halted (manual): {'yes' if trading_halted else 'no'}")

    p_state = cache.portfolio_state
    if p_state is None and execution_store is not None:
        p_state = execution_store.get_latest_portfolio()

    if p_state is not None:
        pos_lines = []
        for pos in p_state.open_positions:
            pos_lines.append(
                f"  {pos.instrument.value} {pos.side.value.upper()} "
                f"{pos.size:.2f} lots @ {pos.entry_price:.5f} "
                f"(uPnL ${pos.unrealized_pnl:+,.2f})"
            )
        sections.append(
            "Portfolio:\n"
            f"  Balance ${p_state.balance:,.2f} | Equity ${p_state.equity:,.2f} | "
            f"Free margin ${p_state.free_margin:,.2f}\n"
            f"  Today P&L ${p_state.realized_pnl_today:+,.2f} "
            f"(drawdown {p_state.drawdown_pct:+.2%})\n"
            f"  Open positions ({len(p_state.open_positions)}):\n"
            + ("\n".join(pos_lines) if pos_lines else "  (none)")
        )
    else:
        sections.append("Portfolio: no snapshot available yet.")

    if execution_store is not None:
        trades = execution_store.list_closed_trades(limit=5)
        if trades:
            trade_lines = []
            for t in trades:
                trade_lines.append(
                    f"  {t['instrument']} {t['side'].upper()} "
                    f"{t['size']:.2f} lots P&L ${t['realized_pnl']:+,.2f} "
                    f"({t['closed_at'][:16]})"
                )
            sections.append("Recent closed trades:\n" + "\n".join(trade_lines))

        orders = execution_store.list_order_events(limit=5)
        if orders:
            order_lines = []
            for o in orders:
                order = o.get("order", {})
                ts = str(o.get("timestamp", ""))[:16]
                order_lines.append(
                    f"  {o.get('event_type', '?')} "
                    f"{order.get('instrument', '?')} {order.get('status', '?')} "
                    f"({ts})"
                )
            sections.append("Recent order events:\n" + "\n".join(order_lines))

    if data_store is not None:
        cal_start = current - timedelta(hours=24)
        cal_end = current + timedelta(hours=48)
        try:
            events = data_store.get_economic_events(cal_start, cal_end)
            if events:
                cal_lines = []
                for ev in events[:20]:
                    ts = ev.timestamp.strftime("%Y-%m-%d %H:%M UTC")
                    pairs = ", ".join(ev.instruments) if ev.instruments else "—"
                    cal_lines.append(
                        f"  [{ts}] {ev.impact.upper()} {ev.name} "
                        f"(pairs: {pairs}; fcst {ev.forecast}, prev {ev.previous})"
                    )
                sections.append(
                    f"Economic calendar ({len(events)} events, next 48h / past 24h):\n"
                    + "\n".join(cal_lines)
                )
            else:
                sections.append("Economic calendar: no events in window.")
        except Exception as exc:  # noqa: BLE001
            _log.warning("chat_context_calendar_failed", error=str(exc))
            sections.append("Economic calendar: unavailable.")

        news_start = current - timedelta(hours=48)
        try:
            articles = data_store.get_news(instrument=None, start=news_start, end=current)
            if articles:
                news_lines = []
                for art in articles[-15:]:
                    ts = art.published_at.strftime("%Y-%m-%d %H:%M UTC")
                    pairs = ", ".join(art.instruments) if art.instruments else "general"
                    snippet = (art.body_snippet or "")[:120]
                    news_lines.append(
                        f"  [{ts}] {art.source}: {art.headline} "
                        f"(pairs: {pairs}) {snippet}"
                    )
                sections.append(
                    f"News articles ({len(articles)} in last 48h, showing latest):\n"
                    + "\n".join(news_lines)
                )
            else:
                sections.append("News: no articles in last 48h.")
        except Exception as exc:  # noqa: BLE001
            _log.warning("chat_context_news_failed", error=str(exc))
            sections.append("News: unavailable.")

    if cache.trade_signals:
        sig_lines = []
        for sig in cache.trade_signals[-8:]:
            side = sig.suggested_side.value.upper() if sig.suggested_side else "NEUTRAL"
            sig_lines.append(
                f"  [{sig.timestamp.strftime('%m-%d %H:%M')}] "
                f"{sig.instrument.value} {side} conf {int(sig.confidence * 100)}% "
                f"dir {sig.direction.value}"
            )
        sections.append("Recent trade signals:\n" + "\n".join(sig_lines))

    if cache.fundamental_signals:
        fund_lines = []
        for sig in cache.fundamental_signals.values():
            fund_lines.append(
                f"  {sig.instrument.value} {sig.event_type.value} "
                f"score {sig.sentiment_score:+.2f} {sig.direction.value} — "
                f"{(sig.source_headline or sig.narrative or '')[:100]}"
            )
        sections.append("Fundamental signals:\n" + "\n".join(fund_lines))

    if cache.health_states:
        health_lines = []
        for div, event in sorted(cache.health_states.items()):
            health_lines.append(f"  {div}: {event.status.value.upper()}")
        sections.append("Division health:\n" + "\n".join(health_lines))

    context = "\n\n".join(sections)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[: MAX_CONTEXT_CHARS - 40] + "\n\n[context truncated]"
    return context


async def answer_trading_question(
    question: str,
    context: str,
    synthesizer: "NarrativeSynthesizer",
    *,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """Call OpenRouter with DB context to answer a trader question."""
    if not synthesizer.api_key:
        return (
            "OpenRouter API key is not configured. "
            "Set OPENROUTER_API_KEY in .env to enable chat Q&A."
        )

    if not synthesizer.budget_available():
        return "OpenRouter daily budget exhausted. Try again tomorrow or raise OPENROUTER_DAILY_BUDGET."

    current_model = await synthesizer.model

    system_prompt = (
        "You are AITrader's Telegram assistant for a forex/commodities paper-trading system. "
        "Answer using ONLY the live context below. If data is missing, say so clearly. "
        "Be concise (under 200 words). Plain text only — no markdown, no asterisks, no bullet lists. "
        "Do not invent trades, prices, or events not in the context.\n\n"
        f"--- LIVE CONTEXT ---\n{context}\n--- END CONTEXT ---"
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-MAX_HISTORY_TURNS * 2 :])
    messages.append({"role": "user", "content": question})

    try:
        async with httpx.AsyncClient(timeout=synthesizer.timeout) as client:
            headers = {
                "Authorization": f"Bearer {synthesizer.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jakhon37/AITrader",
                "X-Title": "AITrader System",
            }
            payload = {
                "model": current_model,
                "messages": messages,
                "temperature": 0.35,
                "max_tokens": 350,
            }

            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                content = sanitize_llm_narrative(
                    data["choices"][0]["message"]["content"].strip()
                )
                synthesizer._daily_spend += synthesizer._cost_per_call  # noqa: SLF001
                return content

            if response.status_code in (400, 404):
                synthesizer._last_model_selection = None  # noqa: SLF001
            _log.warning(
                "chat_api_error",
                status_code=response.status_code,
                model=current_model,
            )
            return "Sorry, the LLM request failed. Please try again in a moment."

    except httpx.TimeoutException:
        _log.warning("chat_api_timeout", timeout=synthesizer.timeout)
        return "Sorry, the LLM timed out. Please try a shorter question."
    except Exception as exc:  # noqa: BLE001
        _log.error("chat_api_failed", error=str(exc))
        return "Sorry, something went wrong processing your question."


def format_chat_reply(answer: str) -> str:
    """Escape LLM text for Telegram HTML parse mode."""
    safe = html.escape(answer)
    return f"💬 {safe}"