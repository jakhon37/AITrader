"""D07-NOTIFIER — Message formatters for Telegram HTML styling.

Converts trading and infrastructure events into descriptive HTML alerts.
"""

from __future__ import annotations

from src.core.display_time import DEFAULT_DISPLAY_TIMEZONE, format_chart_time
from src.core.contracts import (
    Direction,
    FundamentalSignal,
    HealthStatus,
    OrderEvent,
    SystemHealthEvent,
    TradeSignal,
)


def format_trade_signal(
    signal: TradeSignal,
    tz_name: str | None = DEFAULT_DISPLAY_TIMEZONE,
) -> str:
    """Format a D05-DECISION TradeSignal into HTML."""
    emoji = "🟢" if signal.direction == Direction.LONG else "🔴" if signal.direction == Direction.SHORT else "⚪"
    side_str = signal.suggested_side.value.upper() if signal.suggested_side else "NEUTRAL"
    strength_str = signal.strength.value.upper()
    confidence_pct = int(signal.confidence * 100)

    lines = [
        f"{emoji} <b>{side_str} {signal.instrument.value}</b> — {strength_str} ({confidence_pct}%)"
    ]

    # Include Technical overview details if available
    if signal.sources.technical:
        tech = signal.sources.technical
        tech_dir = tech.direction.value.upper()
        tech_conf = int(tech.confidence * 100)
        lines.append(
            f"📈 <b>Technical:</b> {tech_dir} (conf {tech_conf}%), {tech.regime.value} regime"
        )

    # Include Fundamental overview details if available
    if signal.sources.fundamental:
        fund = signal.sources.fundamental
        fund_dir = fund.direction.value.upper()
        lines.append(
            f"📰 <b>Fundamental:</b> {fund_dir} (score {fund.sentiment_score:+.2f}): {fund.source_headline[:80]}"
        )

    # Entry/SL/TP parameters
    if signal.suggested_side:
        entry = f"{signal.suggested_entry:.5f}" if signal.suggested_entry else "Mkt"
        sl = f"{signal.suggested_sl:.5f}" if signal.suggested_sl else "None"
        tp = f"{signal.suggested_tp:.5f}" if signal.suggested_tp else "None"
        size = f"{signal.suggested_size:.2f} lots" if signal.suggested_size else "N/A"
        lines.append(f"⚡ <b>Entry:</b> {entry} | <b>SL:</b> {sl} | <b>TP:</b> {tp} (Size: {size})")

    valid_str = format_chart_time(signal.valid_until, tz_name)
    lines.append(f"🕒 <b>Valid until:</b> {valid_str}")

    if signal.narrative:
        lines.append(f"\n<i>{signal.narrative[:180]}</i>")

    return "\n".join(lines)


def format_order_event(event: OrderEvent) -> str:
    """Format a D06-EXECUTION OrderEvent into HTML."""
    order = event.order
    emoji = "🔔"

    if event.event_type == "filled":
        emoji = "✅"
    elif event.event_type == "cancelled":
        emoji = "❌"
    elif event.event_type == "rejected":
        emoji = "⚠️"

    sig_suffix = order.signal_id[-8:] if order.signal_id else "unknown"

    lines = [
        f"{emoji} <b>Order {event.event_type.upper()}</b>",
        f"<b>Instrument:</b> {order.instrument.value}",
        f"<b>Side:</b> {order.side.value.upper()} | <b>Size:</b> {order.size:.2f} lots",
    ]

    if order.filled_price:
        lines.append(f"<b>Price:</b> {order.filled_price:.5f}")
    elif order.limit_price:
        lines.append(f"<b>Limit Price:</b> {order.limit_price:.5f}")

    lines.append(f"<b>SL:</b> {order.sl or 'None'} | <b>TP:</b> {order.tp or 'None'}")
    lines.append(f"<b>ID:</b> ...{sig_suffix} ({order.execution_mode.value})")

    if event.detail:
        lines.append(f"<b>Reason:</b> {event.detail}")

    return "\n".join(lines)


def format_calendar_briefing(
    signal: FundamentalSignal,
    tz_name: str | None = DEFAULT_DISPLAY_TIMEZONE,
) -> str:
    """Format a pre-release calendar briefing for Telegram."""
    event = signal.triggering_event
    impact = event.impact.upper() if event else "UNKNOWN"
    emoji = "🔴" if impact == "HIGH" else "🟠" if impact == "MEDIUM" else "🟡"
    release_ts = (
        format_chart_time(event.timestamp, tz_name) if event else "TBD"
    )
    mins = ""
    if event and signal.source_headline.startswith("Upcoming:"):
        mins = signal.source_headline.split("in ", 1)[-1] if "in " in signal.source_headline else ""

    lines = [
        "📅 <b>Calendar Alert</b>",
        f"{emoji} <b>{event.name if event else signal.source_headline}</b> — {impact} impact",
        f"<b>Instrument:</b> {signal.instrument.value}",
        f"<b>Release:</b> {release_ts}" + (f" ({mins})" if mins else ""),
    ]

    if event:
        if event.forecast is not None:
            lines.append(f"<b>Forecast:</b> {event.forecast}")
        if event.previous is not None:
            lines.append(f"<b>Previous:</b> {event.previous}")

    if signal.narrative:
        lines.append(f"\n<i>{signal.narrative[:320]}</i>")

    return "\n".join(lines)


def format_fundamental_signal(
    signal: FundamentalSignal,
    tz_name: str | None = DEFAULT_DISPLAY_TIMEZONE,
) -> str:
    """Format a D03-FUNDAMENTAL FundamentalSignal into HTML."""
    emoji = "🟢" if signal.direction == Direction.LONG else "🔴" if signal.direction == Direction.SHORT else "⚪"
    strength_str = signal.strength.value.upper()
    confidence_pct = int(signal.confidence * 100)

    time_str = format_chart_time(signal.timestamp, tz_name)
    lines = [
        "📰 <b>Fundamental Signal</b>",
        f"{emoji} <b>{signal.instrument.value}</b> — {strength_str} ({confidence_pct}%)",
        f"<b>Time:</b> {time_str}",
        f"<b>Event:</b> {signal.event_type.value.upper()}",
        f"<b>Score:</b> {signal.sentiment_score:+.2f}",
        f"<b>Headline:</b> {signal.source_headline[:120]}",
    ]

    if signal.narrative:
        lines.append(f"<b>Summary:</b> <i>{signal.narrative[:180]}</i>")

    return "\n".join(lines)


def format_system_health(
    event: SystemHealthEvent,
    tz_name: str | None = DEFAULT_DISPLAY_TIMEZONE,
) -> str:
    """Format a D11-OPS or infrastructure SystemHealthEvent into HTML."""
    emoji = "🟢" if event.status == HealthStatus.OK else "⚠️" if event.status == HealthStatus.DEGRADED else "🚨"
    ts_str = format_chart_time(
        event.timestamp, tz_name, include_date=True, include_seconds=True
    )

    lines = [
        f"{emoji} <b>System Health: {event.status.value.upper()}</b>",
        f"<b>Division:</b> {event.division}",
        f"<b>Time:</b> {ts_str}",
        f"<b>Message:</b> {event.message or 'No details'}",
    ]

    return "\n".join(lines)
