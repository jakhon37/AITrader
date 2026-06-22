# D01 — CORE

## Purpose
Shared foundation that every other division imports from.
Owns: all contract types, the signal bus implementations, VirtualClock,
config loading, structured logging, and shared utilities.

Does NOT: fetch data, produce signals, execute orders, or run any business logic.
If a module in D01 contains domain logic, it belongs in another division.

---

## Dependencies
None. D01 has zero imports from any other division.
All other divisions depend on D01. It is the only universal dependency.

---

## Emits / Exposes
Does not publish to the bus.
Exposes the Bus protocol and both implementations for injection at startup.
Exposes VirtualClock and both clock implementations.
Exposes all contract types from src.core.contracts.

---

## Internal Module Structure

```
src/core/
  __init__.py
  contracts.py   <- all Pydantic models and enums from CONTRACTS.md
  bus.py         <- Bus protocol + InProcessBus + RedisBus
  clock.py       <- VirtualClock protocol + LiveClock + ReplayClock
  config.py      <- AppConfig, InstrumentConfig (replaces top-level src/config.py)
  ids.py         <- new_signal_id() helper
  logging.py     <- get_logger(division_name) factory; JSON output
  exceptions.py  <- base exception hierarchy
```

### bus.py
InProcessBus: asyncio.Queue per channel. Single-process only. Zero external dependencies.
RedisBus: Redis pub/sub. JSON serialization. Requires redis-py[asyncio].
Both implement the Bus protocol. All divisions receive a Bus instance via DI.

```python
def create_bus(backend: str) -> Bus:
    # backend: "memory" | "redis"
```

### clock.py
LiveClock.now() returns datetime.now(tz=timezone.utc).
ReplayClock implements ControllableClock; control methods called only by D08.
ReplayClock is thread-safe (threading.Lock covers both read and write paths).

All code uses:
```python
from src.core.clock import now
ts = now()
```
Never import the clock instance directly.

### config.py
Replaces and absorbs src/config.py (existing). Retains all Pydantic validation.
Adds:
- InstrumentConfig: typed model for per-instrument YAML block
- CoreConfig.bus_backend: "memory" | "redis"
- CoreConfig.execution_mode: ExecutionMode
- load_instruments() -> dict[Instrument, InstrumentConfig]

### logging.py
get_logger(division: str) returns logger pre-bound with {"division": division}.
Every log record automatically includes division + timestamp.
Signal-scoped: log.bind(signal_id=..., instrument=...).
Output: JSON lines to stdout.

### exceptions.py hierarchy
```
AITraderError
  DataError          # D02: fetch failures, schema violations
  SignalError        # D03, D04, D05: signal production failures
  ExecutionError     # D06: order rejection, broker errors
    RiskViolation    # risk manager hard stops
  BusError           # D01: publish/subscribe failures
  ConfigError        # missing config, bad values
  ReplayError        # D08: replay control errors
```

---

## Existing Code to Migrate

| Existing file | Action |
|---|---|
| src/config.py | Move to src/core/config.py; extend with InstrumentConfig, bus/clock config |
| datetime.utcnow() calls | Replace all with from src.core.clock import now |

---

## Testing Strategy
Coverage target: 80%.

Unit tests:
- InProcessBus: publish -> subscriber receives; multi-subscriber; channel isolation
- RedisBus: same tests with Redis test container
- LiveClock: returns UTC within 1 second
- ReplayClock: set/advance/reset; thread safety under concurrent reads + one writer
- contracts.py: round-trip serialize/deserialize every model; validation error cases
- config.py: AppConfig loads from each ENV; InstrumentConfig validates all fields

Integration tests:
- Bus backend swap: same test suite runs against both bus implementations
- Full clock lifecycle: live -> replay -> reset to live

---

## Implementation Phases

### Phase 1a
1. Create src/core/; move src/config.py -> src/core/config.py
2. Write contracts.py — all types from CONTRACTS.md
3. Write ids.py, exceptions.py, logging.py
4. Write clock.py — LiveClock only
5. Write bus.py — InProcessBus only
6. Update all existing imports to use src.core.*
7. Run existing test suite — zero behavior changes

### Phase 1b (when D08 starts)
8. Add ReplayClock to clock.py
9. Add ControllableClock control interface + tests

### Phase 7 (multi-process)
10. Add RedisBus to bus.py
11. Redis integration tests

---

## Known Risks

**Circular imports.** Enforce: all cross-division imports go through D01 contracts only.
Use mypy --no-implicit-reexport to catch leakage.

**ReplayClock thread safety.** threading.Lock must cover the read path too, not just write.
Test explicitly with concurrent readers + one writer.

**Pydantic v2 migration.** Existing code may use v1 syntax (parse_obj, __fields__).
Audit src/ before writing contracts.py. V2 migration is a prerequisite for Phase 1a.
