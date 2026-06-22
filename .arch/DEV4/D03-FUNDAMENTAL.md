# D03 — FUNDAMENTAL

## 1. Purpose & boundaries
Extracts sentiment signals and categorizes macro news events from raw text ingested by D02.
Translates unstructured textual data into structured numerical indicators.
**Does not trade** (D05 fuses signals) and **does not fetch data** (D02 owns fetchers).

## 2. Dependencies
D01 (contracts, logging, clock), D02 (read raw news/calendar).

## 3. Emits / exposes
Bus topics:
- `signals.fundamental.{instrument}` — emits typed `FundamentalSignal` on news score or major event release.

## 4. Internal module structure
```
src/fundamental/
  __init__.py
  classifier.py    # event classifier (CPI, NFP, interest rates, geopolitics)
  sentiment.py     # sentiment analysis (FinBERT model scoring)
  decay.py         # signal decay logic (applies time-to-live decays based on event type)
  narrative.py     # async summarizer (OpenRouter synthesis for D05 display)
```

## 5. Existing code to migrate
None. This is a greenfield division.

## 6. Testing strategy
**Coverage target: 50%** (default gate).
- Sentiment scoring validation: verify mock articles score correctly (positive, negative, neutral sentiment bounds).
- Signal decay tests: verify that a CPI news event expires after its instrument's decay settings (e.g. 4 hours), while central bank releases persist longer (48 hours).
- Classification: verify correct event typing.

## 7. Implementation phases (internal)
1. FinBERT scoring and event classification — Phase 3, week 1-2
2. Signal decay implementation — Phase 3, week 2
3. Narrative summarizer integration — Phase 3, week 2-3

## 8. Known risks & gotchas
- **API and Model Latency:** LLM narrative generation via OpenRouter can take seconds. Sentiment scoring and text analysis must be executed asynchronously so they never block the core signal path.
- **News Volume Spikes:** Volatile market periods cause news feed floods. The sentiment worker must use a rate-limited queue to prevent memory exhaustion and model thread blocks.
