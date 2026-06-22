# D03 — FUNDAMENTAL

## 1. Purpose & boundaries
Turns raw news and macro data from D02 into `FundamentalSignal` objects: sentiment
scoring, event classification, signal decay, and periodic narrative synthesis. This is
the agentic loop — continuous monitoring, event-triggered analysis. **Does not fetch
raw news** (D02 does that) and **does not decide trades** (D05 does). This division is
currently 0% built — greenfield.

## 2. Dependencies
D01, D02.

## 3. Emits / exposes
Bus topic: `signals.fundamental.{instrument}` — `FundamentalSignal` per CONTRACTS.md.

No direct read API — D03 is purely a bus producer. Anything that wants fundamental
context (D05, D07, D08, D09) subscribes to the bus topic, never imports D03 directly.

## 4. Internal module structure
```
src/fundamental/
  sentiment/
    finbert_scorer.py      # local FinBERT inference — runs inline on every article, ~20ms
  classifier/
    event_classifier.py     # maps article -> EventType taxonomy
  decay.py                  # computes valid_until per signal type/event
  synthesis/
    openrouter_client.py    # async narrative synthesis, best-effort, with template fallback
  agent_loop.py              # subscribes to data.news.raw.*, data.calendar.event.*,
                               # orchestrates scorer -> classifier -> decay -> publish
```

## 5. Existing code to migrate
None. Build new.

## 6. Testing strategy
**Coverage target: 50%**.
- Golden-set tests: known articles with expected sentiment ranges (not exact values —
  FinBERT output drifts slightly across versions, so assert direction + rough magnitude)
- Decay math: unit tests on `valid_until` calculation per `EventType` (a CPI miss should
  decay faster than a structural geopolitical risk signal)
- OpenRouter fallback: simulate timeout/error, assert the signal still publishes with
  `narrative=None` and trade-blocking never occurs

## 7. Implementation phases (internal)
1. FinBERT inline scorer wired to `data.news.raw.*` — Phase 3, week 1
2. Event classifier + decay logic — Phase 3, week 1–2
3. OpenRouter synthesis with timeout + template fallback — Phase 3, week 2–3
4. Backfill: wire historical replay support for D08 once this division is stable

## 8. Known risks & gotchas
- **FinBERT model size** — first-run download and memory footprint; plan for a model
  cache directory, not a re-download on every process start.
- **Financial sentiment ≠ general sentiment** — "stocks fall" is neutral-to-positive
  framing in some contexts; rely on FinBERT's financial-domain training rather than a
  general sentiment model, and don't second-guess it with custom keyword rules that
  will silently rot.
- **OpenRouter must never block trading.** Per the decision made earlier: FinBERT runs
  inline per-article, OpenRouter runs async on a ~5–15 min cycle for narrative only. If
  OpenRouter is down, the `FundamentalSignal` still publishes with `narrative=None` —
  D05 must not wait on it.
- **Continuous polling rate limits** — both FinBERT (compute) and OpenRouter (API quota)
  need backpressure if news volume spikes during high-impact events.
