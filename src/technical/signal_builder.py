"""Technical signal builder for AITrader.

Assembles the final TechnicalSignal contract from confluence outputs,
computing ATR-based entry, stop loss, and take profit targets.
"""

from __future__ import annotations

from datetime import datetime
from src.core.contracts import (
    Instrument,
    Timeframe,
    Direction,
    SignalStrength,
    MarketRegime,
    TimeframeBias,
    TechnicalSignal,
)
from src.core.ids import new_signal_id
from src.technical.loader import timeframe_to_timedelta


def get_signal_strength(confidence: float) -> SignalStrength:
    """Map a confidence float [0, 1] to a SignalStrength enum."""
    if confidence < 0.4:
        return SignalStrength.WEAK
    elif confidence <= 0.7:
        return SignalStrength.MODERATE
    else:
        return SignalStrength.STRONG


class TechnicalSignalBuilder:
    """Assembles TechnicalSignal contracts and calculates entry/SL/TP limits."""

    def __init__(self, primary_tf: Timeframe) -> None:
        self.primary_tf = primary_tf

    def build(
        self,
        instrument: Instrument,
        timestamp: datetime,
        direction: Direction,
        confidence: float,
        confluence_score: float,
        per_timeframe: list[TimeframeBias],
        primary_indicators: dict[str, float],
        primary_regime: MarketRegime,
    ) -> TechnicalSignal:
        """Assemble the complete TechnicalSignal object.

        Calculates ATR-based levels for LONG/SHORT directions.
        """
        # valid_until is set to the next primary timeframe candle close
        delta = timeframe_to_timedelta(self.primary_tf)
        valid_until = timestamp + delta

        # Calculate entry/SL/TP targets
        entry_price = None
        stop_loss = None
        take_profit = None

        if direction != Direction.NEUTRAL:
            close = primary_indicators.get("close", 0.0)
            atr = primary_indicators.get("atr", 0.0)

            if close > 0 and atr > 0:
                entry_price = close
                if direction == Direction.LONG:
                    stop_loss = close - 1.5 * atr
                    take_profit = close + 2.5 * atr
                else:  # SHORT
                    stop_loss = close + 1.5 * atr
                    take_profit = close - 2.5 * atr

        strength = get_signal_strength(confidence)

        return TechnicalSignal(
            signal_id=new_signal_id(),
            instrument=instrument,
            timestamp=timestamp,
            valid_until=valid_until,
            direction=direction,
            confidence=confidence,
            strength=strength,
            regime=primary_regime,
            confluence_score=confluence_score,
            per_timeframe=per_timeframe,
            primary_tf=self.primary_tf,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
