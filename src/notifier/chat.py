"""D07-NOTIFIER — OpenRouter Q&A assistant with live DB + cache context."""

from __future__ import annotations

import html
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional

import httpx

if TYPE_CHECKING:
    from src.data.store import DataStore
    from src.execution.store import ExecutionStore
    from src.fundamental.synthesizer import NarrativeSynthesizer
    from src.signals.registry import SignalStores

from src.core.clock import now
from src.core.contracts import Direction, HealthStatus
from src.core.display_time import format_chart_time
from src.core.logging import get_logger
from src.fundamental.openrouter_models import (
    mark_model_failed,
    mark_model_success,
    select_validated_free_model,
)
from src.fundamental.synthesizer import extract_openrouter_content
from src.fundamental.text_utils import is_safety_classifier_response, sanitize_llm_narrative

_log = get_logger("D07-NOTIFIER")

CHAT_SESSION_TIMEOUT = timedelta(minutes=30)
MAX_CONTEXT_CHARS = 12_000
MAX_HISTORY_TURNS = 4
CHAT_LLM_TIMEOUT_SEC = 25.0
CHAT_MAX_MODEL_ATTEMPTS = 8
CHAT_MAX_TOKENS = 500
CHAT_ERROR_MARKERS = (
    "sorry, the llm",
    "no validated openrouter",
    "openrouter daily budget",
    "openrouter api key",
    "timed out",
    "something went wrong",
)

def _token_matches_keyword(token: str, keyword: str) -> bool:
    if token == keyword:
        return True
    if token.endswith("s") and token[:-1] == keyword:
        return True
    if keyword.endswith("s") and keyword[:-1] == token:
        return True
    return False


def _question_matches(question: str, keywords: tuple[str, ...]) -> bool:
    lower = question.lower()
    tokens = set(re.findall(r"[a-z0-9']+", lower))
    for word in keywords:
        if " " in word:
            if word in lower:
                return True
        elif any(_token_matches_keyword(token, word) for token in tokens):
            return True
    return False


def _build_chat_system_prompt(context: str, *, model_id: Optional[str] = None) -> str:
    model_line = model_id or "selecting on first request"
    return (
        "You are AITrader's Telegram trading assistant for a forex/commodities paper-trading system. "
        "Answer every question using the LIVE CONTEXT below — portfolio, trade signals, news headlines "
        "(from news.db, ingested via Finnhub API and RSS), economic calendar, and division health. "
        "You can list data, analyze it, give opinions, and answer follow-ups conversationally. "
        "When asked about news sources, explain they come from the local news.db database. "
        "When asked which model you use, say you run on OpenRouter free models with validation "
        f"(current chat model: {model_line}). "
        "Be helpful and concise (under 250 words). Plain text only — no markdown, no asterisks, "
        "no bullet lists. Do not invent trades, prices, headlines, or events not in the context. "
        "If context lacks data, say so clearly.\n\n"
        f"--- LIVE CONTEXT ---\n{context}\n--- END CONTEXT ---"
    )


def try_emergency_data_fallback(
    question: str,
    *,
    signal_stores: Optional["SignalStores"] = None,
    execution_store: Optional["ExecutionStore"] = None,
    data_store: Optional["DataStore"] = None,
    tz_name: str = "UTC",
) -> Optional[str]:
    """Last-resort SQLite snippet when all OpenRouter models fail."""
    store = execution_store
    if store is None and signal_stores is not None:
        store = signal_stores.execution

    if _question_matches(
        question,
        ("portfolio", "equity", "balance", "margin", "position", "p&l", "pnl", "account"),
    ):
        if store is None:
            return "Portfolio data is not available yet."
        p_state = store.get_latest_portfolio()
        if p_state is None:
            return "No portfolio snapshot is stored yet."
        lines = [
            f"Balance ${p_state.balance:,.2f}, equity ${p_state.equity:,.2f}, "
            f"free margin ${p_state.free_margin:,.2f}.",
            f"Today's realized P&L is ${p_state.realized_pnl_today:+,.2f} "
            f"({p_state.drawdown_pct:+.2%} drawdown).",
            f"Open positions: {len(p_state.open_positions)}.",
        ]
        for pos in p_state.open_positions:
            lines.append(
                f"{pos.instrument.value} {pos.side.value.upper()} {pos.size:.2f} lots "
                f"@ {pos.entry_price:.5f} (uPnL ${pos.unrealized_pnl:+,.2f})."
            )
        return " ".join(lines)

    if _question_matches(
        question,
        ("trade database", "closed trade", "trade history", "my trades", "order history", "orders"),
    ):
        if store is None:
            return "Execution database is not wired yet."
        trades = store.list_closed_trades(limit=5)
        orders = store.list_order_events(limit=5)
        if not trades and not orders:
            return "The execution database has no closed trades or recent order events yet."
        parts: list[str] = []
        if trades:
            parts.append(f"Last {len(trades)} closed trades:")
            for t in trades:
                parts.append(
                    f"{t['instrument']} {t['side'].upper()} {t['size']:.2f} lots "
                    f"P&L ${t['realized_pnl']:+,.2f} ({str(t['closed_at'])[:16]})."
                )
        if orders:
            parts.append(f"Last {len(orders)} order events:")
            for o in orders:
                order = o.get("order", {})
                parts.append(
                    f"{o.get('event_type', '?')} {order.get('instrument', '?')} "
                    f"{order.get('status', '?')} ({str(o.get('timestamp', ''))[:16]})."
                )
        return " ".join(parts)

    if _question_matches(question, ("signal", "trade idea", "setup")):
        if signal_stores is None:
            return "Trade signal store is unavailable."
        signals = signal_stores.trade.list_recent(limit=5, as_of=now())
        if not signals:
            return "No trade signals are stored yet."
        parts = [f"Latest {len(signals)} trade signals:"]
        for sig in signals:
            side = sig.suggested_side.value.upper() if sig.suggested_side else "NEUTRAL"
            ts = format_chart_time(sig.timestamp, tz_name, include_date=True)
            parts.append(
                f"{sig.instrument.value} {side} conf {int(sig.confidence * 100)}% at {ts}."
            )
        return " ".join(parts)

    if _question_matches(question, ("news", "headline", "article")):
        if data_store is None:
            return "News store is not wired yet."
        current = now()
        articles = data_store.get_news(
            instrument=None,
            start=current - timedelta(hours=48),
            end=current,
        )
        if not articles:
            return "No news articles in the database for the last 48 hours."
        parts = [f"Latest {min(5, len(articles))} headlines:"]
        for art in articles[-5:]:
            ts = format_chart_time(art.published_at, tz_name, include_date=True)
            pairs = ", ".join(art.instruments) if art.instruments else "general"
            parts.append(f"[{ts}] {art.source}: {art.headline} (pairs: {pairs}).")
        return " ".join(parts)

    return None


def _is_chat_error_response(answer: str) -> bool:
    lower = answer.strip().lower()
    return any(lower.startswith(marker) for marker in CHAT_ERROR_MARKERS)


def build_trading_context(
    config: Any,
    *,
    signal_stores: Optional["SignalStores"] = None,
    data_store: Optional["DataStore"] = None,
    execution_store: Optional["ExecutionStore"] = None,
    tz_name: str = "UTC",
) -> str:
    """Assemble a plain-text snapshot from SQLite stores."""
    sections: list[str] = []
    current = now()

    mode_val = getattr(getattr(config, "core", None), "execution_mode", "paper")
    mode_label = mode_val.value.upper() if hasattr(mode_val, "value") else str(mode_val).upper()
    env_label = getattr(config, "env", "dev")
    sections.append(f"Environment: {env_label} | Execution mode: {mode_label}")

    health_states = signal_stores.health.get_all() if signal_stores else {}
    manual = health_states.get("MANUAL_CONTROL")
    trading_halted = manual is not None and manual.status == HealthStatus.DOWN
    sections.append(f"Trading halted (manual): {'yes' if trading_halted else 'no'}")

    store = execution_store
    if store is None and signal_stores is not None:
        store = signal_stores.execution
    p_state = store.get_latest_portfolio() if store is not None else None

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
                    ts = format_chart_time(
                        ev.timestamp, tz_name, include_date=True
                    )
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
                    ts = format_chart_time(
                        art.published_at, tz_name, include_date=True
                    )
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

    if signal_stores is not None:
        trade_sigs = signal_stores.trade.list_recent(limit=8, as_of=current)
        if trade_sigs:
            sig_lines = []
            for sig in trade_sigs:
                side = sig.suggested_side.value.upper() if sig.suggested_side else "NEUTRAL"
                sig_lines.append(
                    f"  [{format_chart_time(sig.timestamp, tz_name, include_date=True)}] "
                    f"{sig.instrument.value} {side} conf {int(sig.confidence * 100)}% "
                    f"dir {sig.direction.value}"
                )
            sections.append("Recent trade signals:\n" + "\n".join(sig_lines))

        fund_sigs = signal_stores.fundamental.get_latest_by_instrument(as_of=current)
        if fund_sigs:
            fund_lines = []
            for sig in fund_sigs.values():
                fund_lines.append(
                    f"  {sig.instrument.value} {sig.event_type.value} "
                    f"score {sig.sentiment_score:+.2f} {sig.direction.value} — "
                    f"{(sig.source_headline or sig.narrative or '')[:100]}"
                )
            sections.append("Fundamental signals:\n" + "\n".join(fund_lines))

        if health_states:
            health_lines = []
            for div, event in sorted(health_states.items()):
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
    signal_stores: Optional["SignalStores"] = None,
    execution_store: Optional["ExecutionStore"] = None,
    data_store: Optional["DataStore"] = None,
    tz_name: str = "UTC",
) -> str:
    """Call OpenRouter with full DB context — primary path for all chat and analysis."""
    if not synthesizer.api_key:
        return (
            "OpenRouter API key is not configured. "
            "Set OPENROUTER_API_KEY in .env to enable chat Q&A."
        )

    if not synthesizer.budget_available():
        return "OpenRouter daily budget exhausted. Try again tomorrow or raise OPENROUTER_DAILY_BUDGET."

    trimmed_history = history[-MAX_HISTORY_TURNS * 2 :] if history else []
    tried_models: set[str] = set()
    timeout = max(float(synthesizer.timeout), CHAT_LLM_TIMEOUT_SEC)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = {
                "Authorization": f"Bearer {synthesizer.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jakhon37/AITrader",
                "X-Title": "AITrader System",
            }

            for attempt in range(CHAT_MAX_MODEL_ATTEMPTS):
                current_model = await select_validated_free_model(
                    synthesizer.api_key or "",
                    preferred=synthesizer._preferred_models,  # noqa: SLF001
                    exclude=tried_models,
                    purpose="chat",
                    suitable_only=True,
                    force_refresh=attempt >= 2,
                )
                if not current_model:
                    break
                tried_models.add(current_model)
                synthesizer._model = current_model  # noqa: SLF001
                synthesizer._last_model_selection = now()  # noqa: SLF001
                synthesizer._cost_per_call = 0.0 if ":free" in current_model else 0.0005  # noqa: SLF001

                system_prompt = _build_chat_system_prompt(
                    context, model_id=current_model
                )
                messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
                if trimmed_history:
                    messages.extend(trimmed_history)
                messages.append({"role": "user", "content": question})

                payload = {
                    "model": current_model,
                    "messages": messages,
                    "temperature": 0.45,
                    "max_tokens": CHAT_MAX_TOKENS,
                }

                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    raw_content = extract_openrouter_content(response.json())
                    if raw_content and not is_safety_classifier_response(raw_content):
                        content = sanitize_llm_narrative(raw_content)
                        if content:
                            synthesizer._daily_spend += synthesizer._cost_per_call  # noqa: SLF001
                            mark_model_success(current_model, purpose="chat")
                            synthesizer._model = current_model  # noqa: SLF001
                            synthesizer._last_model_selection = now()  # noqa: SLF001
                            return content

                    _log.warning(
                        "chat_empty_content",
                        model=current_model,
                        attempt=attempt + 1,
                        safety_only=bool(
                            raw_content and is_safety_classifier_response(raw_content)
                        ),
                    )
                    mark_model_failed(current_model, hard=False)
                    synthesizer._last_model_selection = None  # noqa: SLF001
                    continue

                if response.status_code in (400, 404, 429):
                    mark_model_failed(current_model, hard=True)
                    synthesizer._last_model_selection = None  # noqa: SLF001
                _log.warning(
                    "chat_api_error",
                    status_code=response.status_code,
                    model=current_model,
                    attempt=attempt + 1,
                )

            fallback = try_emergency_data_fallback(
                question,
                signal_stores=signal_stores,
                execution_store=execution_store,
                data_store=data_store,
                tz_name=tz_name,
            )
            if fallback is not None:
                return (
                    f"{fallback} "
                    "(OpenRouter models unavailable — this is a raw database fallback.)"
                )

            return (
                "No validated OpenRouter free model is responding right now. "
                "Please retry in a few minutes."
            )

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