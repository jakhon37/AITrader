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
- `VirtualClock` (full implementation, not just an interface — see MASTER.md note)
- All Pydantic schemas from `CONTRACTS.md`
- `AppConfig`, `InstrumentConfig` loaders
- Structured logging setup (JSON formatter, `signal_id` correlation support)

CORE exposes Python imports, not bus topics — nothing is published here.

## 4. Internal module structure
```
src/core/
  bus.py              # Bus protocol, InProcessBus, RedisBus
  clock.py            # VirtualClock — live mode + replay control methods
  contracts.py        # all Pydantic models from CONTRACTS.md
  config.py           # AppConfig, env/CONFIG_DIR loading (refactor of src/config.py)
  instrument_config.py
  logging.py          # structlog/JSON setup, signal_id correlation helper
```

## 5. Existing code to migrate
- `src/config.py` → `src/core/config.py`. Keep the existing Pydantic validation
  approach (`AppConfig.from_env()` / `load_config()`), extend with `bus_backend` and
  `execution.mode` fields per MASTER.md's cross-cutting concerns.

## 6. Testing strategy
**Coverage target: 80%** (critical path — every division depends on this being correct).
- Bus: publish/subscribe ordering, multiple subscribers per topic, error isolation
  (one subscriber's exception doesn't break others)
- Clock: live mode returns real time; replay mode holds steady until `advance()`;
  `reset_to_live()` correctly switches back; thread-safety if bus runs subscribers
  concurrently
- Config: missing `CONFIG_DIR`, missing `ENV`, malformed YAML all raise clear errors
  (no silent defaults on critical fields)

## 7. Implementation phases (internal)
1. Lock contracts (Phase 0, no code — paper review against every division's emit/consume list)
2. `InProcessBus` + `VirtualClock` (live mode) + config loader — Phase 1
3. `RedisBus` — Phase 7, behind the same `Bus` protocol, swapped via config only

## 8. Known risks & gotchas
- **Bus ordering guarantees**: InProcessBus via asyncio.Queue is FIFO per-topic but
  has no cross-topic ordering guarantee — don't assume signal arrival order across topics.
- **Clock thread-safety**: if the bus ever runs subscriber callbacks on separate threads
  (not just asyncio tasks), the clock needs a lock. Default asyncio single-threaded
  event loop avoids this in v1; flag if that assumption changes.
- **Schema drift**: any field change to a `CONTRACTS.md` model without a version bump
  silently breaks every consumer. Treat contract changes as the highest-review-bar
  changes in the whole codebase.
