# D03 — FUNDAMENTAL

## Purpose
Fundamental analysis pillar. Monitors news continuously, scores sentiment via FinBERT,
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

---

## Internal Module Structure

```
src/fundamental/
  __init__.py
  agent.py         <- main async loop; orchestrates all sub-modules
  sentiment.py     <- FinBERT wrapper; scores articles; runs in thread pool
  classifier.py    <- maps scored articles to FundamentalEventType + affected instruments
  decay.py         <- computes valid_until from event_type + instrument config
  synthesizer.py   <- async OpenRouter narrative call; best-effort, non-blocking
  macro_regime.py  <- dollar index bias, risk-on/off detector
  filter.py        <- dedup, relevance, source quality filter
  models.py        <- internal: ScoredArticle, RawSignalCandidate (not in contracts)
```

### agent.py — two trigger paths

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

### sentiment.py
FinBERT (ProsusAI/finbert, MIT license). Loaded once at startup (~400MB, cached in memory).
Input: headline + first 512 tokens of body.
Output: sentiment_score = positive_prob - negative_prob, range -1.0 to +1.0.
Runs in thread pool via loop.run_in_executor (never block the event loop).
Batch size 8 for GPU efficiency when CUDA available.

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

### synthesizer.py
OpenRouter call. Default model: mistralai/mistral-7b-instruct (free tier).
Upgrade option: anthropic/claude-3-haiku (faster, better financial reasoning).
Timeout: 8 seconds. On timeout/error: narrative=None (non-blocking).
Trade execution NEVER waits on this call.
Daily budget cap via OPENROUTER_DAILY_BUDGET env var; falls back to template if exceeded.

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

## Implementation Phases

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

## Known Risks

**FinBERT memory.** 400MB constant. Budget: FinBERT 400MB + LSTM 200MB + OS ~2GB minimum.
**OpenRouter cost.** ~18 calls/hour = ~432/day. Implement daily budget cap.
**FinBERT accuracy.** Track direction precision vs eventual price movement in D11.
If accuracy < 55% on high-confidence signals, revisit classifier rules.
**Async/FinBERT blocking.** ALWAYS use run_in_executor. Never call score() directly in a coroutine.
Add lint check or test to verify.
