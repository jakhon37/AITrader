"""Technical analysis confluence engine for AITrader.

Combines directional biases across multiple timeframes to compute
consensus direction, confidence, and confluence score.
"""

from __future__ import annotations

import numpy as np
from src.core.contracts import Direction, Timeframe, MarketRegime, TimeframeBias


DEFAULT_WEIGHTS = {
    # Position trading (primary=4H/1D)
    Timeframe.D1: {Timeframe.D1: 0.35, Timeframe.H4: 0.30, Timeframe.H1: 0.20, Timeframe.M15: 0.15},
    Timeframe.H4: {Timeframe.D1: 0.35, Timeframe.H4: 0.30, Timeframe.H1: 0.20, Timeframe.M15: 0.15},
    # Intraday (primary=1H)
    Timeframe.H1: {Timeframe.H4: 0.40, Timeframe.H1: 0.35, Timeframe.M15: 0.20, Timeframe.M5: 0.05},
    # Scalping (primary=5M/15M)
    Timeframe.M15: {Timeframe.H1: 0.35, Timeframe.M15: 0.30, Timeframe.M5: 0.25, Timeframe.M1: 0.10},
    Timeframe.M5: {Timeframe.H1: 0.35, Timeframe.M15: 0.30, Timeframe.M5: 0.25, Timeframe.M1: 0.10},
    Timeframe.M1: {Timeframe.H1: 0.35, Timeframe.M15: 0.30, Timeframe.M5: 0.25, Timeframe.M1: 0.10},
    # Fallbacks for other timeframes
    Timeframe.M30: {Timeframe.H4: 0.40, Timeframe.H1: 0.35, Timeframe.M30: 0.20, Timeframe.M5: 0.05},
    Timeframe.W1: {Timeframe.W1: 0.50, Timeframe.D1: 0.35, Timeframe.H4: 0.15},
}


def compute_tf_bias(
    tf: Timeframe,
    indicators: dict[str, float],
    regime: MarketRegime,
) -> tuple[Direction, float]:
    """Determine directional bias and confidence for a single timeframe based on its indicators."""
    if not indicators:
        return Direction.NEUTRAL, 0.0

    # Trend component (40% weight)
    trend_score = 0.0
    ema_20 = indicators.get("ema_20", 0.0)
    ema_50 = indicators.get("ema_50", 0.0)
    ema_200 = indicators.get("ema_200", 0.0)
    close = indicators.get("close", 0.0)

    if ema_20 != 0.0 and ema_50 != 0.0:
        if ema_20 > ema_50:
            trend_score += 0.5
        elif ema_20 < ema_50:
            trend_score -= 0.5

    if ema_200 != 0.0 and close != 0.0:
        if close > ema_200:
            trend_score += 0.5
        elif close < ema_200:
            trend_score -= 0.5

    # Momentum component (40% weight)
    mom_score = 0.0
    rsi = indicators.get("rsi", 50.0)
    if rsi > 55:
        mom_score += 0.33
    elif rsi < 45:
        mom_score -= 0.33

    macd_hist = indicators.get("macd_hist", 0.0)
    if macd_hist > 0:
        mom_score += 0.33
    elif macd_hist < 0:
        mom_score -= 0.33

    stoch_k = indicators.get("stoch_k", 50.0)
    stoch_d = indicators.get("stoch_d", 50.0)
    if stoch_k > stoch_d:
        mom_score += 0.34
    elif stoch_k < stoch_d:
        mom_score -= 0.34

    # Structure / BB component (20% weight)
    bb_score = 0.0
    bb_mid = indicators.get("bb_middle", 0.0)
    if bb_mid != 0.0 and close != 0.0:
        if close > bb_mid:
            bb_score = 1.0
        elif close < bb_mid:
            bb_score = -1.0

    raw_score = 0.4 * trend_score + 0.4 * mom_score + 0.2 * bb_score

    # Determine direction and confidence
    if raw_score > 0.15:
        direction = Direction.LONG
        confidence = min(abs(raw_score), 1.0)
    elif raw_score < -0.15:
        direction = Direction.SHORT
        confidence = min(abs(raw_score), 1.0)
    else:
        direction = Direction.NEUTRAL
        confidence = 0.0

    return direction, confidence


class ConfluenceCombiner:
    """Combines multi-timeframe biases into a single consensus technical signal."""

    def __init__(self, primary_tf: Timeframe, weights: dict[Timeframe, float] | None = None) -> None:
        self.primary_tf = primary_tf
        # Load default weights if not custom provided
        self.raw_weights = weights or DEFAULT_WEIGHTS.get(primary_tf, {primary_tf: 1.0})

    def combine(
        self,
        tf_biases: list[TimeframeBias],
    ) -> tuple[Direction, float, float]:
        """Combine timeframe biases and return consensus (direction, confidence, confluence_score).

        Applies weight normalization and confidence bonuses.
        """
        if not tf_biases:
            return Direction.NEUTRAL, 0.0, 0.0

        # Filter weights for timeframes that actually have data
        available_tfs = {b.timeframe for b in tf_biases}
        valid_weights = {tf: w for tf, w in self.raw_weights.items() if tf in available_tfs}
        
        # Normalize weights
        weight_sum = sum(valid_weights.values())
        if weight_sum > 0:
            normalized_weights = {tf: w / weight_sum for tf, w in valid_weights.items()}
        else:
            # Equal weighting if weights are missing/invalid
            normalized_weights = {tf: 1.0 / len(valid_weights) for tf in valid_weights}

        raw_score = 0.0
        agreeing_count = 0
        total_valid_tfs = 0

        # Create lookup map for biases
        bias_map = {b.timeframe: b for b in tf_biases}

        for tf in available_tfs:
            bias = bias_map[tf]
            weight = normalized_weights.get(tf, 0.0)

            # Map Direction to numeric vote
            vote = 0.0
            if bias.direction == Direction.LONG:
                vote = 1.0
            elif bias.direction == Direction.SHORT:
                vote = -1.0

            raw_score += vote * weight * bias.confidence
            total_valid_tfs += 1

        # Consensus direction
        if raw_score > 0.15:
            consensus_direction = Direction.LONG
        elif raw_score < -0.15:
            consensus_direction = Direction.SHORT
        else:
            consensus_direction = Direction.NEUTRAL

        confidence = abs(raw_score)

        # Confluence score = agreeing TFs / total TFs
        if consensus_direction != Direction.NEUTRAL:
            for tf in available_tfs:
                bias = bias_map[tf]
                if bias.direction == consensus_direction:
                    agreeing_count += 1
            confluence_score = agreeing_count / total_valid_tfs if total_valid_tfs > 0 else 0.0
        else:
            confluence_score = 0.0

        # Apply confidence bonuses (capped at 1.0)
        if consensus_direction != Direction.NEUTRAL:
            # 1. All 3+ major TFs agree
            if agreeing_count >= 3:
                confidence += 0.10

            # Find primary TF details
            primary_bias = bias_map.get(self.primary_tf)
            if primary_bias:
                # 2. Primary TF trending in signal direction
                if primary_bias.regime == MarketRegime.TRENDING and primary_bias.direction == consensus_direction:
                    confidence += 0.05

                # 3. Price at key S/R level
                # Check if distance to support or resistance is less than 0.2 * ATR
                close = primary_bias.indicators.get("close", 0.0)
                support = primary_bias.indicators.get("support", 0.0)
                resistance = primary_bias.indicators.get("resistance", 0.0)
                atr = primary_bias.indicators.get("atr", 0.0)

                if atr > 0:
                    dist_to_support = abs(close - support) if support > 0 else float("inf")
                    dist_to_resistance = abs(resistance - close) if resistance > 0 else float("inf")
                    if dist_to_support < 0.2 * atr or dist_to_resistance < 0.2 * atr:
                        confidence += 0.05

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        return consensus_direction, confidence, confluence_score
