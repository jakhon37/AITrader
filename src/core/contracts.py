"""All shared Pydantic v2 contracts for AITrader.

Every division imports types from src.core.contracts.
NEVER define signal models locally in a division.

Rule: adding or renaming a field here is a BREAKING CHANGE.
Update consuming division MDs and run the full test suite before merging.

Version: v1.0  (Pydantic v2 — use model_validate, not parse_obj)
All datetime fields are UTC and timezone-aware (tzinfo=timezone.utc).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class Instrument(str, Enum):
    EURUSD = "EURUSD"
    GBPUSD = "GBPUSD"
    USDJPY = "USDJPY"
    XAUUSD = "XAUUSD"


class Timeframe(str, Enum):
    M1  = "1m"
    M5  = "5m"
    M15 = "15m"
    M30 = "30m"
    H1  = "1h"
    H4  = "4h"
    D1  = "1d"
    W1  = "1w"


class Direction(str, Enum):
    LONG    = "long"
    SHORT   = "short"
    NEUTRAL = "neutral"


class SignalStrength(str, Enum):
    WEAK     = "weak"      # confidence < 0.4
    MODERATE = "moderate"  # 0.4 – 0.7
    STRONG   = "strong"    # > 0.7


class OrderSide(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING         = "pending"
    FILLED          = "filled"
    PARTIALLY       = "partially_filled"
    CANCELLED       = "cancelled"
    REJECTED        = "rejected"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE  = "live"


class MarketRegime(str, Enum):
    TRENDING  = "trending"
    RANGING   = "ranging"
    VOLATILE  = "volatile"
    UNKNOWN   = "unknown"


class FundamentalEventType(str, Enum):
    CENTRAL_BANK   = "central_bank"    # rate decisions, speeches
    ECONOMIC_DATA  = "economic_data"   # CPI, NFP, GDP
    GEOPOLITICAL   = "geopolitical"
    MARKET_RISK    = "market_risk"     # risk-on / risk-off
    TECHNICAL_CONF = "technical_conf"  # news confirming a technical breakout


class BusChannel(str, Enum):
    OHLCV_BAR          = "ohlcv_bar"
    ECONOMIC_EVENT     = "economic_event"
    FUNDAMENTAL_SIGNAL = "fundamental_signal"
    TECHNICAL_SIGNAL   = "technical_signal"
    TRADE_SIGNAL       = "trade_signal"
    ORDER_EVENT        = "order_event"
    PORTFOLIO_UPDATE   = "portfolio_update"
    SYSTEM_HEALTH      = "system_health"


class HealthStatus(str, Enum):
    OK       = "ok"
    DEGRADED = "degraded"
    DOWN     = "down"


class PromotionStage(str, Enum):
    DEV     = "dev"
    STAGING = "staging"
    PROD    = "prod"


# ── Core Data Types ───────────────────────────────────────────────────────────

class OHLCVBar(BaseModel):
    """Published by D02-DATA on each confirmed candle close.

    BusChannel.OHLCV_BAR
    """

    signal_id:  str
    instrument: Instrument
    timeframe:  Timeframe
    timestamp:  datetime        # bar open time, UTC, timezone-aware
    open:       float
    high:       float
    low:        float
    close:      float
    volume:     float
    source:     str             # "yfinance" | "oanda" | "csv" | "replay"


class EconomicEvent(BaseModel):
    """Published by D02-DATA from the economic calendar.

    BusChannel.ECONOMIC_EVENT — published 60 min before, then again at release with actuals.
    D06 uses the pre-release event to activate the news_halt window.
    """

    signal_id:      str
    timestamp:      datetime            # scheduled release time, UTC
    name:           str                 # e.g. "US CPI YoY", "FOMC Rate Decision"
    impact:         Literal["low", "medium", "high"]
    affected_pairs: List[Instrument]
    actual:         Optional[float] = None
    forecast:       Optional[float] = None
    previous:       Optional[float] = None
    surprise_pct:   Optional[float] = None  # (actual - forecast) / |forecast|, set post-release


# ── Analytical Signal Types ───────────────────────────────────────────────────

class FundamentalSignal(BaseModel):
    """Emitted by D03-FUNDAMENTAL. BusChannel.FUNDAMENTAL_SIGNAL."""

    signal_id:        str
    instrument:       Instrument
    timestamp:        datetime      # when signal was produced, UTC
    valid_until:      datetime      # timestamp + decay_hours; D05 discards after this
    direction:        Direction
    confidence:       Annotated[float, Field(ge=0.0, le=1.0)]
    strength:         SignalStrength
    sentiment_score:  Annotated[float, Field(ge=-1.0, le=1.0)]  # FinBERT output
    event_type:       FundamentalEventType
    source_headline:  str           # first 200 chars of triggering headline
    source_url:       Optional[str]
    decay_hours:      float
    narrative:        Optional[str]  # OpenRouter synthesis; None if unavailable
    triggering_event: Optional[EconomicEvent]


class TimeframeBias(BaseModel):
    """Per-timeframe directional bias, used inside TechnicalSignal."""

    timeframe:  Timeframe
    direction:  Direction
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    regime:     MarketRegime
    indicators: Dict[str, float]    # e.g. {"rsi": 32.1, "macd_hist": -0.002}
    support:    Optional[float]
    resistance: Optional[float]


class TechnicalSignal(BaseModel):
    """Emitted by D04-TECHNICAL. BusChannel.TECHNICAL_SIGNAL."""

    signal_id:        str
    instrument:       Instrument
    timestamp:        datetime
    valid_until:      datetime          # next primary TF candle close
    direction:        Direction         # consensus across timeframes
    confidence:       Annotated[float, Field(ge=0.0, le=1.0)]
    strength:         SignalStrength
    regime:           MarketRegime
    confluence_score: Annotated[float, Field(ge=0.0, le=1.0)]  # degree of TF agreement
    per_timeframe:    List[TimeframeBias]
    primary_tf:       Timeframe
    entry_price:      Optional[float]
    stop_loss:        Optional[float]
    take_profit:      Optional[float]


# ── Decision / Trade Types ────────────────────────────────────────────────────

class SignalSource(BaseModel):
    """Carries the input signals that produced a TradeSignal."""

    fundamental: Optional[FundamentalSignal]
    technical:   Optional[TechnicalSignal]


class TradeSignal(BaseModel):
    """Emitted by D05-DECISION. BusChannel.TRADE_SIGNAL.

    D06-EXECUTION subscribes to this and places orders accordingly.
    """

    signal_id:          str
    instrument:         Instrument
    timestamp:          datetime
    valid_until:        datetime
    direction:          Direction
    confidence:         Annotated[float, Field(ge=0.0, le=1.0)]
    strength:           SignalStrength
    fundamental_weight: Annotated[float, Field(ge=0.0, le=1.0)]
    technical_weight:   Annotated[float, Field(ge=0.0, le=1.0)]
    suggested_side:     Optional[OrderSide]      # None when NEUTRAL
    suggested_entry:    Optional[float]
    suggested_sl:       Optional[float]
    suggested_tp:       Optional[float]
    suggested_size:     Optional[float]           # lots; D06 may override per risk rules
    narrative:          Optional[str]
    sources:            SignalSource
    model_version:      Optional[str]             # which D09 model produced this
    is_limit:           bool = False              # whether this is a limit entry order


# ── Execution Types ───────────────────────────────────────────────────────────

class Order(BaseModel):
    """An individual order (pending → filled / cancelled / rejected)."""

    order_id:       str
    signal_id:      str
    instrument:     Instrument
    side:           OrderSide
    size:           float
    order_type:     Literal["market", "limit", "stop"]
    limit_price:    Optional[float]
    stop_price:     Optional[float]
    sl:             Optional[float]
    tp:             Optional[float]
    status:         OrderStatus
    created_at:     datetime
    filled_at:      Optional[datetime]
    filled_price:   Optional[float]
    commission:     float = 0.0
    slippage:       float = 0.0
    execution_mode: ExecutionMode


class OrderEvent(BaseModel):
    """Published by D06-EXECUTION. BusChannel.ORDER_EVENT."""

    signal_id:  str
    event_type: Literal["created", "filled", "cancelled", "rejected"]
    order:      Order
    timestamp:  datetime


class PositionSummary(BaseModel):
    """Snapshot of a single open position, used inside PortfolioState."""

    instrument:     Instrument
    side:           OrderSide
    size:           float
    entry_price:    float
    current_price:  float
    unrealized_pnl: float
    open_since:     datetime
    leg_id:         Optional[str] = None
    sl:             Optional[float] = None
    tp:             Optional[float] = None


class PortfolioState(BaseModel):
    """Published by D06-EXECUTION. BusChannel.PORTFOLIO_UPDATE."""

    signal_id:          str
    timestamp:          datetime
    execution_mode:     ExecutionMode
    balance:            float
    equity:             float
    margin_used:        float
    free_margin:        float
    open_positions:     List[PositionSummary]
    realized_pnl_today: float
    drawdown_pct:       float


# ── System / Health Types ─────────────────────────────────────────────────────

class SystemHealthEvent(BaseModel):
    """Published by any division on health check. BusChannel.SYSTEM_HEALTH."""

    signal_id: str
    division:  str      # "D01-CORE" | "D02-DATA" | etc.
    status:    HealthStatus
    timestamp: datetime
    message:   Optional[str]
    metrics:   Dict[str, float]


# ── Model Registry Artifact ───────────────────────────────────────────────────

class ModelArtifact(BaseModel):
    """Written by D09-TRAINER to data/models/registry.json on every promotion.

    Read by D05-DECISION to select the active prod model.
    This is the ENTIRE contract between D09 and D05.
    D09 never runs live; D05 never imports D09.
    The registry file on disk is the only thing that passes between them.
    """

    model_id:               str              # uuid4, stable across promotions of same lineage
    run_id:                 str              # training run that produced this artifact
    instrument:             Instrument
    model_type:             str              # "lstm" | "xgboost" | "garch_gru" | "ensemble"
    promotion_stage:        PromotionStage
    trained_at:             datetime
    promoted_at:            Optional[datetime]
    cpcv_sharpe:            float
    cpcv_max_drawdown_pct:  float
    feature_set_version:    str              # must match D04/D03 feature pipeline version
    checkpoint_path:        str              # data/models/{run_id}/checkpoint.pt
    metadata_path:          str              # data/models/{run_id}/metadata.json
    previous_prod_model_id: Optional[str]   # for rollback
    rollback_count:         int = 0          # incremented each time this lineage is rolled back to
