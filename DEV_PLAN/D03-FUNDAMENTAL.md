# D03 — FUNDAMENTAL

**Status (2026-06-25)**: Core components implemented but **not wired**. Major architecture revision in progress.

> This document now contains both the original implementation description and the **revised development plan**. The revised sections (starting with "Design Decisions & Revised Plan") are the active guide.

See also:
- [STATUS_AND_ROADMAP.md](STATUS_AND_ROADMAP.md) — Tier 3 priorities
- [MASTER.md](MASTER.md) — overall phases
- `src/fundamental/` and `src/data/sources/` for current code

## Purpose
Fundamental analysis pillar. Monitors news continuously, scores sentiment via FinBERT (or pluggable alternatives),
classifies economic events, applies signal decay, emits FundamentalSignal objects.
Maintains macro regime view (risk-on/off, dollar strength bias).

Does NOT: fetch raw data (D02), combine with technical signals (D05), execute trades,
or run inference for trade decisions. Produces one signal type only.

---

## Dependencies
- D01-CORE: contracts, bus, clock, config, logging
- D02-DATA: subscribes to BusChannel.ECONOMIC_EVENT; queries DataStore.get_news()

---

## Emits
| Channel | Type | When |
|---|---|---|
| BusChannel.FUNDAMENTAL_SIGNAL | FundamentalSignal | After scoring meaningful news or on economic event release |

The contract and emission semantics remain unchanged. Only the internal quality, efficiency, and hardware adaptability of signal generation are being improved.

---

## Internal Module Structure (Current + Planned)

```
src/fundamental/
  __init__.py
  agent.py              <- coordinator / orchestrator (revised for pluggable backends + historical mode)
  sentiment.py          <- pluggable scorer (finbert | mock | openrouter) + cache
  classifier.py         <- event type + direction/strength (rule-based + future LLM option)
  decay.py              <- unchanged (config-driven)
  synthesizer.py        <- OpenRouter narrative + structured enrichment (revised prompts)
  macro_regime.py       <- improved (better features, optional persistence)
  filter.py             <- enhanced (source credibility, better dedup)
  models.py             <- internal models
  cache.py (new)        <- sentiment score cache (optional)
```

**Key change**: `SentimentScorer` becomes the extension point for hardware adaptation. `FundamentalAgent` gains `process_historical(...)` for replay.

### agent.py — two trigger paths (to be improved in revision)

**Current (pre-revision):**
Path 1 — Periodic news poll (every 10 minutes):
1. DataStore.get_news(since=last_poll_time)
2. filter.is_relevant() -> sentiment.score() -> classifier.classify()
3. Aggregate candidates per instrument (5-min window)
4. synthesizer.get_narrative() async fire-and-forget
5. decay.compute() -> valid_until
6. Publish FundamentalSignal

Path 2 — Economic event trigger (immediate):
- Subscribe to BusChannel.ECONOMIC_EVENT
- On event with actual != None: force-score immediately
- Emit FundamentalSignal within 30 seconds of release

**Target (revised):**
- Hybrid triggers (event-driven for calendar + smarter news window + optional bus notification from D02).
- Pluggable sentiment inside the pipeline.
- Explicit `aggregate_and_publish` with better clustering and macro context.
- Separate `process_batch_historical(articles, events)` for replay.

### sentiment.py (Revised)
- Primary: FinBERT when available and configured.
- Pluggable backends controlled by config.
- Built-in caching of scores.
- Automatic graceful degradation (load failure → mock).
- On low-resource machines: prefer "openrouter" (structured) or "mock".
- ThreadPoolExecutor still used for any CPU-heavy local model.

### classifier.py
Stage 1 — Instrument relevance: keyword/regex map per instrument.
Stage 2 — Event type: rule-based taxonomy:
- "rate decision", "hike", "cut" -> CENTRAL_BANK
- "CPI", "NFP", "GDP", "payroll" -> ECONOMIC_DATA
- "war", "sanction", "tariff" -> GEOPOLITICAL
- "risk-off", "flight to safety" -> MARKET_RISK
- default -> TECHNICAL_CONF

### decay.py
```python
def compute_valid_until(event_type, instrument, config, clock) -> datetime:
    hours = config.signal_decay[event_type]
    return clock.now() + timedelta(hours=hours)
```

### synthesizer.py (and LLM usage)
- Narrative generation (existing).
- Planned: Structured enrichment calls (e.g. impact analysis, event classification refinement) using cheap/free OpenRouter models.
- Always best-effort + budget protected + strong template fallback.
- Used for both live and (cached) replay enrichment.

### filter.py
- Language: English only (FinBERT is English-only)
- Recency: articles older than 2 hours ignored for real-time signals
- Duplicate: SHA-256 of (headline + source) -> skip if seen in last 6 hours
- Source quality: configurable allowlist of trusted sources
- Relevance: must contain instrument keyword or macro keyword
Prevents a single news event from generating 50 identical signals.

---

## Environment Variables Required
```
OPENROUTER_API_KEY       # optional; signals still work without narrative
OPENROUTER_DAILY_BUDGET  # USD float; synthesis disabled when exceeded
```

---

## Testing Strategy
Coverage target: 60%.

Unit:
- sentiment.py: fixture texts with known direction -> correct score sign
- classifier.py: fixture headlines -> correct FundamentalEventType + instruments
- decay.py: each event type -> correct valid_until offset with ReplayClock
- filter.py: duplicate detection, recency cutoff, language filter
- synthesizer.py: mock OpenRouter HTTP; timeout -> narrative=None; success path

Integration:
- Full pipeline: fixture articles -> agent -> FundamentalSignal on bus
- Economic event trigger: mock EconomicEvent -> signal within 30s

Performance: FinBERT batch scoring 100 articles under 5 seconds on CPU.

---

## Original (Superseded) Implementation Phases

> **Note**: The phases below describe how the initial implementation was built. The revised plan above (2026-06) is now the active development guide.

### Phase 3a (MASTER Phase 3)
1. scripts/setup_finbert.py — download and cache FinBERT model
2. Write sentiment.py with thread pool wrapper
3. Write classifier.py, filter.py, decay.py
4. Write agent.py — Path 1 only
5. Milestone: agent polls D02, produces FundamentalSignal on bus

### Phase 3b
6. Write macro_regime.py
7. Subscribe to ECONOMIC_EVENT (Path 2)
8. Write synthesizer.py (mock first, real API second)
9. Integration tests

---

## Current Implementation Status (as of 2026-06-25)

**Implemented (but dormant):**
- Full `FundamentalAgent` with poll loop + `ECONOMIC_EVENT` handler.
- `SentimentScorer` (FinBERT with lazy load, ThreadPoolExecutor, automatic mock fallback).
- `NewsFilter`, `EventClassifier`, `decay`, `MacroRegimeDetector`, `NarrativeSynthesizer` (OpenRouter).
- Supporting D02 components: `NewsFetcher`, `CalendarFetcher`, `DataStore` news/calendar tables.
- Unit tests with mocks.
- `FundamentalSignal` contract and bus channel.

**Not wired:**
- No `NewsFetcher`, `CalendarFetcher`, or `FundamentalAgent` started in `src/api/main.py`.
- Modern replay (`src/backtest/replay/strategy/`) only uses Technical + MockDecision.
- No sentiment backend configuration.
- Ingestion services not running → agent has no real data.

**Limitations of v1 design:**
- Pure polling for news (reactive for calendar only).
- No score caching.
- Weak aggregation and calendar correlation.
- Crude keyword classifier.
- FinBERT assumed as only high-quality path (problematic on low-RAM CPU hardware).
- LLM usage limited to narrative (no structured extraction).

---

## Design Decisions & Revised Plan (June 2026)

### 1. Hardware Reality & Pluggable Sentiment
The primary development machine is a 2020 Intel MacBook Pro (16GB RAM). FinBERT (~440MB on disk, 700-950MB RAM when loaded) runs on CPU only and is slow. Full stack easily causes pressure.

**Strategy:**
- **Implement full FinBERT support** (keep existing code + improve it).
- Make sentiment **pluggable** at the `SentimentScorer` level:
  - `"finbert"`: Local model (best quality, zero ongoing cost, fast on GPU/CUDA or Apple Silicon).
  - `"mock"`: Rule-based fallback (fast, deterministic for dev/tests/replay).
  - `"openrouter"`: Cheap LLM call (structured output for sentiment score + direction) — primary path on weak hardware.
- On current Mac dev: default to `mock` or `openrouter`.
- On GPU servers / stronger machines: use `"finbert"`.
- Narrative synthesis continues to use OpenRouter (best-effort, always available).

This keeps the system powerful when hardware allows, while remaining practical on limited machines.

**Recommended default for dev** (in `config/dev.yaml`): `sentiment_backend: "mock"` (or `"openrouter"` if you want real scores without heavy local models).

### 2. No Heavy Agent Frameworks (CrewAI, LangChain, etc.)
**Decision: Do not adopt CrewAI or similar.**

Reasons:
- Conflicts with platform principles (explicit contracts, bus, `VirtualClock`, replay determinism, auditability).
- Multiple LLM calls per news item would burn free OpenRouter tier.
- Added complexity, nondeterminism, and dependencies are unnecessary for this use case.
- Current explicit pipeline (filter → score → classify → aggregate → enrich) is more controllable and cheaper.

Instead: Keep `FundamentalAgent` as a thin, explicit coordinator. Use direct `httpx` + structured prompts for LLM steps when needed. Add a very lightweight internal "enrichment step" if multi-hop reasoning is required later.

### 3. Optimized Flow Architecture
**High-level revised flow:**

```
D02 (Ingestion - background)
  NewsFetcher (multi-source + dedup)  → DataStore (news.db)
  CalendarFetcher                     → publish ECONOMIC_EVENT (pre + post)

D03 (Processing)
  FundamentalAgent (orchestrator)
    ├─ Subscribes ECONOMIC_EVENT (immediate, high priority)
    ├─ Hybrid news trigger (improved poll + optional lightweight bus event from fetcher)
    └─ Processing pipeline (per batch or event):
        1. Filter (cheap, early reject + dedup)
        2. Sentiment (pluggable: cache hit → finbert / mock / openrouter)
        3. Classify + instrument linking + calendar correlation
        4. Time-windowed / event-driven aggregation (debounce + weighting)
        5. MacroRegime update
        6. LLM enrichment (structured + narrative, budget + timeout)
        7. Decay + valid_until (from instruments.yaml)
    → Publish high-quality FundamentalSignal
```

Key improvements:
- Sentiment caching by `article_id`.
- Stronger aggregation (recency + source credibility + calendar linkage).
- Debouncing per instrument.
- Deterministic historical processing path for replay.
- Structured LLM output where valuable.

### 4. Replay & Determinism Requirements
- Agent must support explicit batch/historical processing mode.
- LLM calls must be skippable or cached during replay.
- Use `ReplayClock` everywhere.

---

## Revised Implementation Phases

### Phase 3.1 — Foundation & Config (immediate)
1. Add `fundamental.sentiment_backend` (and related) to config schema + `dev.yaml`.
2. Extend `SentimentScorer` to support `"openrouter"` mode (structured JSON for score/direction).
3. Add simple in-memory (or SQLite) sentiment cache keyed by article_id.
4. Run `scripts/setup_finbert.py` (for machines that want it).
5. Milestone: Can switch backends via config and see different behavior.

### Phase 3.2 — Wiring Live Path
1. Start `NewsFetcher` + `CalendarFetcher` in `src/api/main.py` lifespan.
2. Instantiate revised `FundamentalAgent(config, bus, store, sentiment_backend=...)`.
3. Handle graceful shutdown.
4. Ensure `FUNDAMENTAL_SIGNAL` reaches:
   - DecisionEngine
   - WS bridge / API state
   - UI (Fusion panel, signals)
5. Milestone: Real (or mocked) fundamental signals visible in live Web UI.

### Phase 3.3 — Replay Integration & Quality
1. Add historical processing support to `FundamentalAgent` (or a dedicated replay processor).
2. Wire into `src/backtest/replay/strategy/loop.py` (and manual if needed).
3. Improve:
   - Aggregation logic
   - Economic event → sentiment mapping
   - MacroRegimeDetector
   - Filter (source credibility weights)
4. Add correlation between news articles and recent calendar events.
5. Milestone: Replay sessions produce `FundamentalSignal`s that influence `TradeSignal`.

### Phase 3.4 — D07 + Full Tier 3
- Wire `NotifierService` (consumes `FUNDAMENTAL_SIGNAL` + `TRADE_SIGNAL`).
- Basic accuracy logging hooks (for future D11).
- End-to-end integration test for live + replay.

---

## Environment Variables & Config

Sentiment backend is configured via the main app config (loaded from `config/*.yaml` through `src/core/config.py` or `AppConfig`).

```yaml
# Example (to be added to dev.yaml / schema)
fundamental:
  sentiment_backend: "mock"          # "finbert" | "mock" | "openrouter"
  poll_interval_seconds: 600
  aggregation_window_minutes: 15
  min_confidence_to_emit: 0.25
  enable_structured_llm: true
```

**Environment variables**
```
OPENROUTER_API_KEY
OPENROUTER_DAILY_BUDGET
NEWSAPI_KEY               # optional but strongly recommended
```

The `SentimentScorer` and `FundamentalAgent` accept the backend as a constructor parameter (DI-friendly).

---

## Updated Known Risks & Mitigations (Revised)

- **Hardware variance**: Use pluggable backends + clear docs. Current Mac defaults to mock/OpenRouter.
- **FinBERT memory/CPU**: Lazy load + auto-fallback. Document 16GB Intel limits.
- **OpenRouter cost & rate limits**: Budget guard + caching + cheap free-tier models. Structured calls only when high value.
- **Accuracy of early signals**: Rule-based + FinBERT first. Track outcomes later (D11). Start conservative (high confidence threshold).
- **Replay look-ahead / determinism**: Strict use of `clock.now()`. Disable or cache LLM during replay.
- **Data starvation**: Explicitly start fetchers in main lifespan. Add health checks.
- **No CrewAI**: Explicit pipeline kept for controllability and cost.

---

## Testing Strategy (Updated)

- Unit: All existing + new backends for scorer.
- Integration: Live spine test now includes FUNDAMENTAL_SIGNAL.
- Replay: Historical articles + events → correct signals on isolated bus.
- Performance: Benchmark FinBERT vs OpenRouter vs mock (different hardware profiles).
- Hardware matrix: Document expected behavior on "low-RAM CPU" vs "GPU".

---

## Next Actions (from STATUS_AND_ROADMAP Tier 3)

See [STATUS_AND_ROADMAP.md](STATUS_AND_ROADMAP.md) for the current priority order.

Primary owner for this phase: Wire + replan D03, then D07 notifier.

This revised plan supersedes the original "Phase 3a / 3b" bullets in the original document. The original implementation phases are retained below for historical reference.

