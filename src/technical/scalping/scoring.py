"""MT4-style scalping bias and entry scoring."""

from __future__ import annotations

import numpy as np

from src.core.contracts import Direction, MarketRegime
from src.technical.scalping.params import (
    DEFAULT_SCORE_WEIGHTS,
    ENTRY_CONFIDENCE_BOOST,
    ENTRY_DIRECTION_THRESHOLD,
    TREND_STRONG_LEVEL,
)


def _vote(value: float, bullish: float, bearish: float) -> float:
    if value > bullish:
        return 1.0
    if value < bearish:
        return -1.0
    return 0.0


def compute_signal_bars_score(indicators: dict[str, float]) -> float:
    """Signal_Bars_v8 row alignment: MACD, STR proxy, EMA."""
    votes: list[float] = []

    macd_hist = indicators.get("sb_macd_hist", 0.0)
    votes.append(_vote(macd_hist, 0.0, 0.0))

    rsi = indicators.get("sb_rsi", 50.0)
    votes.append(_vote(rsi, 55.0, 45.0))

    cci = indicators.get("sb_cci", 0.0)
    votes.append(_vote(cci, 50.0, -50.0))

    ema_fast = indicators.get("sb_ema_fast", 0.0)
    ema_slow = indicators.get("sb_ema_slow", 0.0)
    if ema_fast and ema_slow:
        votes.append(_vote(ema_fast - ema_slow, 0.0, 0.0))

    if not votes:
        return 0.0
    return float(np.mean(votes))


def compute_trend_panel_score(indicators: dict[str, float]) -> tuple[float, float, bool]:
    """FerruFx-style UP/DOWN percentages and strong-trend flag."""
    votes: list[float] = []

    macd_hist = indicators.get("sb_macd_hist", 0.0)
    votes.append(_vote(macd_hist, 0.0, 0.0))

    rsi = indicators.get("sb_rsi", 50.0)
    votes.append(_vote(rsi, 52.0, 48.0))

    cci = indicators.get("sb_cci", 0.0)
    votes.append(_vote(cci, 0.0, 0.0))

    ema_fast = indicators.get("sb_ema_fast", 0.0)
    ema_slow = indicators.get("sb_ema_slow", 0.0)
    if ema_fast and ema_slow:
        votes.append(_vote(ema_fast - ema_slow, 0.0, 0.0))

    hull_slope = indicators.get("hull_slope", 0.0)
    votes.append(_vote(hull_slope, 0.0, 0.0))

    ha = indicators.get("ha_bullish", 0.5)
    votes.append(1.0 if ha >= 0.5 else -1.0)

    joker = indicators.get("joker", 0.5)
    votes.append(_vote(joker, 0.55, 0.45))

    if not votes:
        return 50.0, 50.0, False

    bullish_ratio = sum(1 for v in votes if v > 0) / len(votes)
    up_pct = bullish_ratio * 100.0
    down_pct = 100.0 - up_pct
    strong = max(up_pct, down_pct) >= TREND_STRONG_LEVEL
    return up_pct, down_pct, strong


def compute_structure_score(indicators: dict[str, float]) -> float:
    """Heiken Ashi + Hull agreement."""
    ha = indicators.get("ha_bullish", 0.5)
    hull_slope = indicators.get("hull_slope", 0.0)
    score = 0.0
    if ha >= 0.5:
        score += 0.5
    else:
        score -= 0.5
    score += 0.5 * _vote(hull_slope, 0.0, 0.0)
    return score


def compute_fl_band_score(indicators: dict[str, float]) -> float:
    """Mean-reversion bias near outer FL2 bands (scalp entries at extremes)."""
    band_pos = indicators.get("band_position", 0.5)
    if band_pos <= 0.15:
        return 1.0
    if band_pos >= 0.85:
        return -1.0
    if band_pos < 0.4:
        return 0.5
    if band_pos > 0.6:
        return -0.5
    return 0.0


def compute_joker_score(indicators: dict[str, float]) -> float:
    joker = indicators.get("joker", 0.5)
    return _vote(joker, 0.6, 0.4)


def compute_entry_trigger(indicators: dict[str, float], direction: Direction) -> bool:
    """Proxy for FL03 / BrainTrend arrow alignment."""
    if direction == Direction.NEUTRAL:
        return False

    band_pos = indicators.get("band_position", 0.5)
    ha = indicators.get("ha_bullish", 0.5) >= 0.5
    hull = indicators.get("hull_slope", 0.0)
    joker = indicators.get("joker", 0.5)
    macd_hist = indicators.get("sb_macd_hist", 0.0)

    if direction == Direction.LONG:
        at_support = band_pos <= 0.25
        structure_ok = ha or hull > 0
        momentum_ok = joker >= 0.45 or macd_hist > 0
        return at_support and structure_ok and momentum_ok

    at_resistance = band_pos >= 0.75
    structure_ok = not ha or hull < 0
    momentum_ok = joker <= 0.55 or macd_hist < 0
    return at_resistance and structure_ok and momentum_ok


def compute_scalping_tf_bias(
    indicators: dict[str, float],
    regime: MarketRegime,
) -> tuple[Direction, float, dict[str, float]]:
    """Composite MT4-style per-timeframe bias."""
    if not indicators:
        return Direction.NEUTRAL, 0.0, {}

    weights = DEFAULT_SCORE_WEIGHTS
    signal_bars = compute_signal_bars_score(indicators)
    up_pct, down_pct, strong = compute_trend_panel_score(indicators)
    trend_panel = (up_pct - down_pct) / 100.0
    structure = compute_structure_score(indicators)
    fl_bands = compute_fl_band_score(indicators)
    joker = compute_joker_score(indicators)

    raw = (
        weights.trend_panel * trend_panel
        + weights.signal_bars * signal_bars
        + weights.structure * structure
        + weights.fl_bands * fl_bands
        + weights.joker * joker
    )

    # Regime-aware dampening in volatile chop
    if regime == MarketRegime.VOLATILE:
        raw *= 0.85
    elif regime == MarketRegime.TRENDING and strong:
        raw *= 1.1

    threshold = ENTRY_DIRECTION_THRESHOLD
    if raw > threshold:
        direction = Direction.LONG
        confidence = min(abs(raw), 1.0)
    elif raw < -threshold:
        direction = Direction.SHORT
        confidence = min(abs(raw), 1.0)
    else:
        direction = Direction.NEUTRAL
        confidence = 0.0

    if compute_entry_trigger(indicators, direction):
        confidence = min(confidence + ENTRY_CONFIDENCE_BOOST, 1.0)

    meta = {
        "trend_up_pct": up_pct,
        "trend_down_pct": down_pct,
        "trend_strong": 1.0 if strong else 0.0,
        "signal_bars_score": signal_bars,
        "structure_score": structure,
        "fl_band_score": fl_bands,
        "joker_score": joker,
        "scalping_raw": raw,
        "entry_trigger": 1.0 if compute_entry_trigger(indicators, direction) else 0.0,
    }
    return direction, confidence, meta