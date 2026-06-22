"""D05-DECISION — Narrative generation logic.

Synthesizes descriptive summary narratives of combined trading decisions
suitable for external alerts (e.g. Telegram length limits).
"""

from __future__ import annotations

from src.core.contracts import Direction, FundamentalSignal, TechnicalSignal


def build_narrative(
    f: FundamentalSignal | None,
    t: TechnicalSignal,
    fused_direction: Direction,
) -> str:
    """Build a concise decision narrative under 280 characters."""
    # 1. Fundamental overview
    fund_part = ""
    if f is not None:
        if f.narrative:
            fund_part = f.narrative.strip()
        else:
            fund_part = f"Fundamental {f.direction.value} bias ({f.event_type.value})"

    # 2. Technical indicators extraction
    tech_indicators = []
    for tf_bias in t.per_timeframe:
        for name, val in tf_bias.indicators.items():
            # Gather top indicators (e.g. RSI, MACD, etc.)
            if name.lower() in ("rsi", "macd", "macd_hist", "ema", "sma", "atr", "adx"):
                tech_indicators.append(f"{name.upper()}={val:.1f}")
                if len(tech_indicators) >= 2:
                    break
        if len(tech_indicators) >= 2:
            break

    if tech_indicators:
        tech_part = "Tech confirms: " + ", ".join(tech_indicators)
    else:
        tech_part = f"Tech: {t.direction.value} bias ({t.regime.value})"

    # 3. Combine into final summary
    dir_str = fused_direction.value.upper()
    header = f"Decision: {dir_str} {t.instrument.value}"

    parts = [header]
    if fund_part:
        parts.append(fund_part)
    parts.append(tech_part)

    combined = " | ".join(parts)
    if len(combined) > 277:
        combined = combined[:274] + "..."

    return combined
