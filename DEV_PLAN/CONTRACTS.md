# AITrader — Contracts Reference

All shared Pydantic models, enums, and bus protocol definitions.
Every division imports types from src.core.contracts.
Never define signal models locally in a division.

Rule: if a field is added or renamed here, it is a breaking change.
Update the version comment, update consuming division MDs, run full test suite before merging.

---

## Enums

```python
class Instrument(str, Enum):
    EURUSD = "EURUSD"
    GBPUSD = "GBPUSD"
    USDJPY = "USDJPY"
    XAUUSD = "XAUUSD"

class Timeframe(str, Enum):
    M1="1m", M5="5m", M15="15m", M30="30m", H1="1h", H4="4h", D1="1d", W1="1w"

class Direction(str, Enum):
    LONG="long", SHORT="short", NEUTRAL="neutral"

class SignalStrength(str, Enum):
    WEAK="weak"        # confidence < 0.4
    MODERATE="moderate" # 0.4-0.7
    STRONG="strong"    # > 0.7

class OrderSide(str, Enum):
    BUY="buy", SELL="sell"

class OrderStatus(str, Enum):
    PENDING="pending", FILLED="filled", PARTIALLY="partially_filled"
    CANCELLED="cancelled", REJECTED="rejected"

class ExecutionMode(str, Enum):
    PAPER="paper", LIVE="live"

class MarketRegime(str, Enum):
    TRENDING="trending", RANGING="ranging", VOLATILE="volatile", UNKNOWN="unknown"

class FundamentalEventType(str, Enum):
    CENTRAL_BANK="central_bank"      # rate decisions, speeches
    ECONOMIC_DATA="economic_data"    # CPI, NFP, GDP
    GEOPOLITICAL="geopolitical"
    MARKET_RISK="market_risk"        # risk-on/risk-off
    TECHNICAL_CONF="technical_conf"  # news confirming technical breakout

class BusChannel(str, Enum):
    OHLCV_BAR          = "ohlcv_bar"
    ECONOMIC_EVENT     = "economic_event"
    FUNDAMENTAL_SIGNAL = "fundamental_signal"
    TECHNICAL_SIGNAL   = "technical_signal"
    TRADE_SIGNAL       = "trade_signal"
    ORDER_EVENT        = "order_event"
    PORTFOLIO_UPDATE   = "portfolio_update"
    SYSTEM_HEALTH      = "system_health"
```

---

## Core Data Types

### OHLCVBar
Published by D02-DATA on each confirmed candle close.

```python
class OHLCVBar(BaseModel):
    signal_id:  str        # uuid4
    instrument: Instrument
    timeframe:  Timeframe
    timestamp:  datetime   # bar open time, UTC, timezone-aware
    open: float; high: float; low: float; close: float; volume: float
    source: str            # "yfinance" | "oanda" | "csv" | "replay"
```

### EconomicEvent
Published by D02-DATA from the economic calendar.

```python
class EconomicEvent(BaseModel):
    signal_id:      str
    timestamp:      datetime            # scheduled release time, UTC
    name:           str                 # "US CPI YoY", "FOMC Rate Decision"
    impact:         Literal["low","medium","high"]
    affected_pairs: list[Instrument]
    actual:         float | None = None
    forecast:       float | None = None
    previous:       float | None = None
    surprise_pct:   float | None = None # (actual-forecast)/|forecast|, set post-release
```

---

## Analytical Signal Types

### FundamentalSignal
Emitted by D03 onto BusChannel.FUNDAMENTAL_SIGNAL.

```python
class FundamentalSignal(BaseModel):
    signal_id:       str
    instrument:      Instrument
    timestamp:       datetime     # when signal was produced, UTC
    valid_until:     datetime     # timestamp + decay_hours; D05 discards after this
    direction:       Direction
    confidence:      float        # 0.0 - 1.0
    strength:        SignalStrength
    sentiment_score: float        # FinBERT output, -1.0 to +1.0
    event_type:      FundamentalEventType
    source_headline: str          # first 200 chars of triggering headline
    source_url:      str | None
    decay_hours:     float
    narrative:       str | None   # OpenRouter synthesis; None if unavailable
    triggering_event: EconomicEvent | None
```

Decay hours by event type (configurable per instrument):
- CENTRAL_BANK: 48h | ECONOMIC_DATA: 4h (high), 2h (medium)
- GEOPOLITICAL: 6h | MARKET_RISK: 2h | TECHNICAL_CONF: 1h

### TechnicalSignal
Emitted by D04 onto BusChannel.TECHNICAL_SIGNAL.

```python
class TimeframeBias(BaseModel):
    timeframe:   Timeframe
    direction:   Direction
    confidence:  float
    regime:      MarketRegime
    indicators:  dict[str, float]   # e.g. {"rsi": 32.1, "macd_hist": -0.002}
    support:     float | None
    resistance:  float | None

class TechnicalSignal(BaseModel):
    signal_id:        str
    instrument:       Instrument
    timestamp:        datetime
    valid_until:      datetime       # next primary TF candle close
    direction:        Direction      # consensus across timeframes
    confidence:       float
    strength:         SignalStrength
    regime:           MarketRegime
    confluence_score: float          # 0.0-1.0, degree of TF agreement
    per_timeframe:    list[TimeframeBias]
    primary_tf:       Timeframe
    entry_price:      float | None
    stop_loss:        float | None
    take_profit:      float | None
```

---

## Decision / Trade Types

### TradeSignal
Emitted by D05 onto BusChannel.TRADE_SIGNAL.

```python
class SignalSource(BaseModel):
    fundamental: FundamentalSignal | None
    technical:   TechnicalSignal   | None

class TradeSignal(BaseModel):
    signal_id:          str
    instrument:         Instrument
    timestamp:          datetime
    valid_until:        datetime
    direction:          Direction
    confidence:         float
    strength:           SignalStrength
    fundamental_weight: float
    technical_weight:   float
    suggested_side:     OrderSide | None     # None if NEUTRAL
    suggested_entry:    float | None
    suggested_sl:       float | None
    suggested_tp:       float | None
    suggested_size:     float | None         # lots; D06 may override
    narrative:          str | None
    sources:            SignalSource
    model_version:      str | None           # which D09 model produced this
```

---

## Execution Types

### Order + OrderEvent

```python
class Order(BaseModel):
    order_id:       str
    signal_id:      str
    instrument:     Instrument
    side:           OrderSide
    size:           float
    order_type:     str          # "market" | "limit" | "stop"
    limit_price:    float | None
    stop_price:     float | None
    sl:             float | None
    tp:             float | None
    status:         OrderStatus
    created_at:     datetime
    filled_at:      datetime | None
    filled_price:   float | None
    commission:     float = 0.0
    slippage:       float = 0.0
    execution_mode: ExecutionMode

class OrderEvent(BaseModel):
    signal_id:  str
    event_type: str     # "created" | "filled" | "cancelled" | "rejected"
    order:      Order
    timestamp:  datetime
```

### PortfolioState

```python
class PositionSummary(BaseModel):
    instrument:     Instrument
    side:           OrderSide
    size:           float
    entry_price:    float
    current_price:  float
    unrealized_pnl: float
    open_since:     datetime

class PortfolioState(BaseModel):
    signal_id:          str
    timestamp:          datetime
    execution_mode:     ExecutionMode
    balance:            float
    equity:             float
    margin_used:        float
    free_margin:        float
    open_positions:     list[PositionSummary]
    realized_pnl_today: float
    drawdown_pct:       float
```

---

## System / Health Types

```python
class HealthStatus(str, Enum):
    OK="ok", DEGRADED="degraded", DOWN="down"

class SystemHealthEvent(BaseModel):
    signal_id: str
    division:  str       # "D01-CORE" | "D02-DATA" | etc.
    status:    HealthStatus
    timestamp: datetime
    message:   str | None
    metrics:   dict[str, float]
```

---

## Model Registry Artifact

Written by D09 to `data/models/registry.json` on every promotion event.
Read by D05's `fusion.py` (model fusion mode) to select the active prod model.
This is the **entire** contract between D09 and D05 — D09 never runs live and D05
never imports D09; the registry file on disk is the only thing that passes between them.

```python
class PromotionStage(str, Enum):
    DEV="dev", STAGING="staging", PROD="prod"

class ModelArtifact(BaseModel):
    model_id:               str          # uuid4, stable across promotions of the same lineage
    run_id:                 str          # training run that produced this artifact
    instrument:              Instrument
    model_type:               str         # "lstm" | "xgboost" | "garch_gru" | "ensemble"
    promotion_stage:           PromotionStage
    trained_at:                 datetime
    promoted_at:                  datetime | None
    cpcv_sharpe:                   float
    cpcv_max_drawdown_pct:           float
    feature_set_version:              str   # must match the D04/D03 feature pipeline version
                                              # that generated training features — see Version Notes
    checkpoint_path:                   str  # data/models/{run_id}/checkpoint.pt
    metadata_path:                      str # data/models/{run_id}/metadata.json
    previous_prod_model_id:              str | None  # for rollback
    rollback_count:                        int = 0    # incremented each time this lineage is rolled back to
```

D05 polls `registry.json` for the current `prod` artifact on a configurable interval
(default 5 minutes) and reloads inference weights only when `model_id` changes —
never mid-fusion-cycle.

---

## Bus Protocol

```python
class Bus(Protocol):
    async def publish(self, channel: BusChannel, payload: BaseModel) -> None: ...
    async def subscribe(self, channel: BusChannel,
                        handler: Callable[[BaseModel], Awaitable[None]]) -> None: ...
    async def unsubscribe(self, channel: BusChannel,
                          handler: Callable[[BaseModel], Awaitable[None]]) -> None: ...
```

Bus injected at startup from composition root (src/main.py).
Never instantiate InProcessBus or RedisBus directly outside src/core/bus.py.

```python
def create_bus(backend: str) -> Bus:
    # backend: "memory" | "redis"
```

---

## VirtualClock Protocol

```python
class ClockMode(str, Enum):
    LIVE="live", REPLAY="replay"

class VirtualClock(Protocol):
    def now(self) -> datetime: ...
    def mode(self) -> ClockMode: ...

# Only D08-BACKTEST calls these:
class ControllableClock(VirtualClock, Protocol):
    def set_replay_time(self, dt: datetime) -> None: ...
    def advance(self, delta: timedelta) -> None: ...
    def reset_to_live(self) -> None: ...
```

Usage everywhere:
```python
from src.core.clock import now
ts = now()   # always UTC, always VirtualClock
```

datetime.utcnow() and datetime.now() are BANNED outside src/core/clock.py.

---

## Signal ID

```python
# src/core/ids.py
def new_signal_id() -> str:
    return str(uuid.uuid4())
```

Use this helper everywhere. Never inline str(uuid.uuid4()).

---

## Instrument Config Block (config/instruments.yaml)

```yaml
EURUSD:
  pip_size: 0.0001
  lot_size: 100000
  session_hours: {open: "22:00", close: "22:00"}  # UTC Sun open / Fri close
  active_timeframes: [15m, 1h, 4h, 1d]
  primary_timeframe: 1h
  fundamental_weight: 0.3
  technical_weight: 0.7
  max_position_lots: 1.0
  news_halt_minutes: 30
  signal_decay:
    central_bank: 48
    economic_data: 4
    geopolitical: 6
    market_risk: 2
    technical_conf: 1
```

---

## Version Notes

- All models use Pydantic v2. Use model_validate, not parse_obj.
- All datetime fields are UTC and timezone-aware (tzinfo=timezone.utc).
- Price math uses decimal.Decimal internally; convert to float only at serialization.
