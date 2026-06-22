# D01 — CORE

## 1. Purpose & boundaries
Shared foundation every other division imports from: signal bus, virtual clock,
config loading, instrument config, structured logging setup, and the schema definitions
documented in `CONTRACTS.md`. CORE contains **no business logic** — no analysis, no
trading rules, no data fetching. If a function makes a trading decision or touches a
broker, it does not belong here.

## 2. Dependencies
None. This is the one division every other division can depend on.

## 3. Emits / exposes
- The `Bus` protocol and its two implementations (`InProcessBus`, `RedisBus`)
- `VirtualClock` (full implementation, not just an interface — handles both live and replay clock modes)
- All Pydantic schemas from `CONTRACTS.md`
- `AppConfig`, `InstrumentConfig` loaders
- Structured logging setup (JSON formatter, `signal_id` correlation support)

CORE exposes Python imports, not bus topics — nothing is published here.

## 4. Internal module structure
```
src/core/
  __init__.py
  contracts.py        # all Pydantic models from CONTRACTS.md
  bus.py              # Bus protocol, InProcessBus (asyncio.Queue), RedisBus (Redis pub/sub)
  clock.py            # VirtualClock — live mode + replay control methods (UTC timezone aware)
  config.py           # AppConfig loading config/dev.yaml etc. (refactor of src/config.py)
  instrument_config.py# InstrumentConfig mapping config/instruments.yaml
  logging.py          # structlog/JSON setup, signal_id correlation helper
  ids.py              # uuid4 helper for signal_id generation
  exceptions.py       # base exceptions hierarchy for the platform
```

## 5. Existing code to migrate
- `src/config.py` → `src/core/config.py`. Keep the existing Pydantic validation
  approach (`AppConfig.from_env()` / `load_config()`), extend with `bus_backend` and
  `execution.mode` fields per MASTER.md's cross-cutting concerns.

## 6. Testing strategy
**Coverage target: 80%** (critical path — every division depends on this being correct).
- Bus: publish/subscribe ordering, multiple subscribers per topic, error isolation
- Clock: replay mode clock setting and advancing. Double-check that datetime.utcnow() or now() is not used outside clock.py.
- Config: loading and validating AppConfig and InstrumentConfig schemas; invalid configurations must fail-fast on load.

## 7. Implementation phases (internal)
1. virtual clock and basic memory bus implementation — Phase 1, week 1
2. config loading and logging migrations — Phase 1, week 1-2
3. RedisBus interface completion — Phase 7

## 8. Known risks & gotchas
- **Timezone Normalization:** All inputs must be parsed to timezone-aware UTC timestamps at the system boundary. Failing to enforce this inside `clock.py` or `contracts.py` will raise comparison errors.
- **NTP Sync in Live Mode:** LiveClock relies on the system time. Host system clock drift will cause execution errors or delayed fills if trading servers are desynchronized.
