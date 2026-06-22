# CONTRACTS.md — Shared Schema & Interface Reference

Every division MD links here instead of redefining types. If you're about to add a field
to a signal, change it here first and bump the schema version — don't drift a local copy.

All schemas are written as Pydantic-style models for clarity. This is a design reference,
not the implementation — D01-CORE owns the actual `src/core/contracts.py` module.

---

## Versioning policy

Every top-level schema carries a `schema_version: int` field, starting at `1`.
Breaking changes (removing a field, changing a type, changing meaning) bump the version
and require a migration note in this file's changelog section at the bottom.
Additive, optional fields do not require a version bump.

---

## Enums

```python
class Instrument(str, Enum):
    EURUSD = "EURUSD"
    GBPUSD = "GBPUSD"
    USDJPY = "USDJPY"
    XAUUSD = "XAUUSD"

class Timeframe(str, Enum):
    M1 = "1m"; M5 = "5m"; M15 = "15m"; M30 = "30m"
    H1 = "1h"; H4 = "4h"; D1 = "1d"; W1 = "1w"

class Direction(str, Enum):
    LONG = "long"; SHORT = "short"; NEUTRAL = "neutral"

class Regime(str, Enum):
    TRENDING = "trending"; RANGING = "ranging"; VOLATILE = "volatile"

class EventType(str, Enum):
    CENTRAL_BANK_DECISION = "central_bank_decision"
    ECONOMIC_DATA_RELEASE = "economic_data_release"
    GEOPOLITICAL_RISK = "geopolitical_risk"
    TECHNICAL_BREAKOUT = "technical_breakout"
    EARNINGS = "earnings"
    OTHER = "other"

class ExecutionMode(str, Enum):
    PAPER = "paper"; LIVE = "live"

class OrderSide(str, Enum):
    BUY = "buy"; SELL = "sell"

class OrderStatus(str, Enum):
    PENDING = "pending"; FILLED = "filled"; REJECTED = "rejected"; CANCELLED = "cancelled"
```

---

## Market data

```python
class MarketBar(BaseModel):
    schema_version: int = 1
    instrument: Instrument
    timeframe: Timeframe
    timestamp: datetime          # bar close time, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_replay: bool = False      # True when sourced from D08 replay, never live
```

## News & calendar

```python
class NewsArticle(BaseModel):
    schema_version: int = 1
    article_id: str
    source: str                  # "reuters", "bloomberg_rss", etc.
    published_at: datetime
    headline: str
    body: str | None
    instruments_mentioned: list[Instrument]

class EconomicEvent(BaseModel):
    schema_version: int = 1
    event_id: str
    name: str                    # "US Non-Farm Payrolls"
    instruments_affected: list[Instrument]
    scheduled_at: datetime
    importance: Literal["low", "medium", "high"]
    actual: float | None = None
    forecast: float | None = None
    previous: float | None = None
```

## Signals

```python
class FundamentalSignal(BaseModel):
    schema_version: int = 1
    signal_id: str                # uuid4; correlation key for logging
    instrument: Instrument
    generated_at: datetime
    valid_until: datetime         # decay cutoff — D05 must check this before using the signal
    sentiment: float               # -1.0 to +1.0
    confidence: float              # 0.0 to 1.0
    event_type: EventType
    source_article_ids: list[str]
    narrative: str | None = None   # OpenRouter synthesis; None if not yet generated or timed out

class TechnicalSignal(BaseModel):
    schema_version: int = 1
    signal_id: str
    instrument: Instrument
    generated_at: datetime
    timeframe_bias: dict[Timeframe, float]   # per-TF score, -1.0 to +1.0
    confluence_score: float                   # combined across active timeframes, -1.0 to +1.0
    confidence: float
    regime: Regime

class TradeSignal(BaseModel):
    schema_version: int = 1
    signal_id: str
    instrument: Instrument
    generated_at: datetime
    direction: Direction
    size_hint: float                # suggested position size, 0.0–1.0 of max
    confidence: float
    fundamental_signal_id: str | None
    technical_signal_id: str | None
    explanation: str | None = None  # human-readable "why" — best-effort, never blocks execution
```

## Execution & portfolio

```python
class Order(BaseModel):
    schema_version: int = 1
    order_id: str
    trade_signal_id: str
    instrument: Instrument
    side: OrderSide
    size: float
    status: OrderStatus
    requested_at: datetime
    filled_at: datetime | None
    fill_price: float | None
    slippage: float | None

class PortfolioState(BaseModel):
    schema_version: int = 1
    as_of: datetime
    mode: ExecutionMode
    equity: float
    open_positions: list[Order]
    daily_pnl: float
    max_drawdown_pct: float
```

## Model registry artifact (the D09 → D05 contract)

```python
class ModelArtifact(BaseModel):
    schema_version: int = 1
    model_id: str
    model_type: str              # "lstm_transformer", "xgboost", etc.
    trained_at: datetime
    promotion_stage: Literal["dev", "staging", "prod"]
    cpcv_score: float
    feature_set_version: str     # must match D04/D03 feature pipeline version
    artifact_path: str           # path under data/models/
    previous_prod_model_id: str | None  # for rollback
```

## Instrument config

```python
class InstrumentConfig(BaseModel):
    instrument: Instrument
    pip_size: float
    lot_size: float
    session_hours_utc: tuple[str, str]
    active_timeframes: list[Timeframe]
    fundamental_weight: float    # 0.0–1.0, technical_weight = 1 - this
    max_position_size: float
```

---

## Bus protocol

```python
class Bus(Protocol):
    async def publish(self, topic: str, payload: BaseModel) -> None: ...
    async def subscribe(self, topic: str, handler: Callable[[BaseModel], Awaitable[None]]) -> None: ...
```

Two implementations live in D01: `InProcessBus` (asyncio.Queue) and `RedisBus` (pub/sub).
Selected via `core.bus_backend` config (`memory` | `redis`). Every division depends only
on this protocol, never on a concrete implementation.

### Topic naming convention

```
data.bar.{instrument}.{timeframe}
data.news.raw.{instrument}
data.calendar.event.{instrument}
signals.fundamental.{instrument}
signals.technical.{instrument}
signals.trade.{instrument}
execution.fill.{instrument}
ops.alert.{division}
```

---

## VirtualClock interface

```python
class VirtualClock(Protocol):
    def now(self) -> datetime: ...
    # control methods — only D08-BACKTEST calls these
    def set_replay_time(self, t: datetime) -> None: ...
    def advance(self, delta: timedelta) -> None: ...
    def reset_to_live(self) -> None: ...
```

In live mode, `now()` returns real UTC time. In replay mode, it returns the current
replay position, advanced only by D08. Every other division calls `now()` and nothing else.

---

## Changelog

- v1 (Phase 0): initial schema set, locked before any implementation begins.
