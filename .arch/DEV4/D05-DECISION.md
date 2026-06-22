# D05 — DECISION

## 1. Purpose & boundaries
Fuses technical and fundamental inputs to generate trade signals. Generates the human-readable
trading narrative explainers.
**Does not execute orders** (D06 owns order paths) and **does not evaluate indicators directly**.
Decides what to trade, which direction, and at what size.

## 2. Dependencies
D01 (contracts, bus, config), D02 (models registry store for loaded models).
Subscribes to `signals.technical.*` and `signals.fundamental.*` via the bus.

## 3. Emits / exposes
Bus topics:
- `signals.trade.{instrument}` — emits typed `TradeSignal` when combination threshold is met.

## 4. Internal module structure
```
src/decision/
  __init__.py
  combiner.py      # signal fusion (fuses D03 fundamental + D04 technical biases)
  model_loader.py  # loads and reloads model checkpoints written by D09 (decoupled artifact handoff)
  inference.py     # runs active model inference (LSTM, GARCH, or XGBoost) to produce direction
  narrator.py      # aggregates signal context for narrative summarizer
```

## 5. Existing code to migrate
- `src/models/model_factory.py` — integrate model loading and factory logic inside decision runtime.

## 6. Testing strategy
**Coverage target: 50%** (default gate).
- Fusion correctness: verify weighted combiner matches expected directions for known input scores.
- Artifact loader: test that loader picks up newly written checkpoints from the models folder without runtime interruption.
- Narrative compilation: ensure narrative context aggregates signals correctly.

## 7. Implementation phases (internal)
1. Signal combiner implementation — Phase 4, week 1
2. Factory loading and prediction integration — Phase 4, week 1-2
3. Decoupled artifact loading logic — Phase 6 (staging)

## 8. Known risks & gotchas
- **Decoupled Model Handoff Reliability:** `model_loader.py` must load models from `data/models/` safely. If a new checkpoint file is corrupted, the system must log an error and fall back to the last active model without crashing the execution loop.
- **Threshold Tuning:** Directional biases can conflict. Ensure signal expiration rules (`valid_until`) prevent decisions on outdated fundamental inputs.
