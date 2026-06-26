"""MT4 Scalping XAUUSD M15 template parameters."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.contracts import Timeframe


@dataclass(frozen=True)
class FLBandParams:
    half_length: int
    atr_period: int
    atr_multiplier: float


# From Saclping XAUUSD M15.tpl
FL1_PARAMS = FLBandParams(half_length=61, atr_period=110, atr_multiplier=1.8)

FL2_MULTIPLIERS: tuple[float, ...] = (
    2.2,
    2.6,
    3.0,
    3.4,
    3.8,
    4.2,
    4.6,
    5.0,
)

FL2_BASE = FLBandParams(half_length=63, atr_period=110, atr_multiplier=2.2)

HULL_PERIOD = 20
HULL_DIVISOR = 2.2

# Signal_Bars_v8
SIGNAL_BARS_MACD = (8, 21, 8)
SIGNAL_BARS_RSI = 8
SIGNAL_BARS_CCI = 13
SIGNAL_BARS_STOCH = (12, 3, 6)
SIGNAL_BARS_MA = (5, 7)

# FerruFx_Multi_info THV
TREND_STRONG_LEVEL = 75.0

# JokerFilter
JOKER_SMOOTH_PERIOD = 5

# i-Sessions (broker/server clock — configurable; defaults from MT4 template)
ASIA_SESSION = ("00:00", "08:45")
EU_SESSION = ("10:00", "18:00")
US_SESSION = ("15:00", "23:00")

# Multi-TF weights for M15 gold scalping (aligned with MT4 panel TFs)
SCALPING_TF_WEIGHTS: dict[Timeframe, float] = {
    Timeframe.M5: 0.15,
    Timeframe.M15: 0.25,
    Timeframe.M30: 0.15,
    Timeframe.H1: 0.20,
    Timeframe.H4: 0.15,
    Timeframe.D1: 0.10,
}

SCALPING_ACTIVE_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.M30,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
)


@dataclass(frozen=True)
class ScalpingScoreWeights:
    trend_panel: float = 0.35
    signal_bars: float = 0.25
    structure: float = 0.20
    fl_bands: float = 0.10
    joker: float = 0.10


DEFAULT_SCORE_WEIGHTS = ScalpingScoreWeights()

# Risk: use wide-band ATR from FL system for gold scalping
RISK_ATR_PERIOD = 110
STOP_ATR_MULT = 1.5
TARGET_ATR_MULT = 2.5

ENTRY_CONFIDENCE_BOOST = 0.15
ENTRY_DIRECTION_THRESHOLD = 0.12