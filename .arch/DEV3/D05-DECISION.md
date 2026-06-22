# D05 — DECISION

## 1. Purpose & boundaries
Fuses `FundamentalSignal` and `TechnicalSignal` into a `TradeSignal`: weighted combiner
in v1, trained-model combiner in v2 (once D09 promotes a model). Generates a best-effort
narrative explanation via OpenRouter. **Does not execute orders** (D06) and **does not
fetch or compute raw signals** (D03/D04 do that). Greenfield — informed by the existing
`meta_labeler.py` design but not a direct migration.

## 2. Dependencies
D01. Subscribes to D03 and D04 via the bus only. Reads the model registry store
(owned by D02, written by D09) directly — see MASTER.md's artifact-handoff note. No
runtime/process dependency on D09.

## 3. Emits / exposes
Bus topic: `signals.trade.{instrument}` — `TradeSignal` per CONTRACTS.md.

## 4. Internal module structure
```
src/decision/
  fusion/
    weighted_combiner.py   # v1 — configurable per-instrument fundamental/technical weight
    model_combiner.py        # v2 — wraps a promoted model from the registry, falls back
                                # to weighted_combiner.py if no prod model is available
  expiry.py                   # checks FundamentalSignal.valid_until before use; discards
                                 # or down-weights decayed signals
  narrative/
    openrouter_explainer.py    # async, best-effort, never blocks publish
  engine.py                     # subscribes to signals.fundamental.*, signals.technical.*,
                                  # holds latest-per-instrument state, triggers fusion on update
```

## 5. Existing code to migrate
None directly, but `src/models/meta_labeler.py` and `src/models/model_factory.py`
inform the `model_combiner.py` design — review them before writing v2, don't migrate
them as-is since they predate the typed signal contracts.

## 6. Testing strategy
**Coverage target: 50%**.
- Known F+T signal pairs → expected fused `TradeSignal` output (table-driven tests
  covering agreement, disagreement, and one-pillar-silent cases)
- Expiry/decay: a `FundamentalSignal` past `valid_until` must not influence the fusion
- Missing-signal fallback: if D03 hasn't published yet for an instrument (cold start or
  D03 outage), D05 must still produce a technical-only `TradeSignal` rather than stalling

## 7. Implementation phases (internal)
1. Weighted combiner v1 + expiry handling — Phase 4, week 1
2. OpenRouter narrative with fallback — Phase 4, week 1–2
3. Model-based combiner reading D09's registry artifacts — Phase 6, once a model reaches staging

## 8. Known risks & gotchas
- **Silent-pillar behavior must be defined, not improvised.** Decide explicitly: does a
  missing fundamental signal mean "treat as neutral" or "fall back to technical-only
  weighting"? Pick one and document it in this file once chosen — don't let it be an
  implicit accident of whatever the code happens to do.
- **Model hot-swap without restart** — `model_combiner.py` needs to detect a new prod
  artifact and reload without dropping in-flight fusion state.
- **Narrative latency must never gate execution.** If OpenRouter takes 10 seconds, the
  `TradeSignal` still publishes immediately with `explanation=None`; the narrative
  can arrive as a follow-up update if the architecture supports it, but trading doesn't wait.
