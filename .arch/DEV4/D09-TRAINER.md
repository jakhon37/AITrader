# D09 — TRAINER

## 1. Purpose & boundaries
Offline model training and validation pipeline. Evaluates model candidate performance using
CPCV backtests before registering models.
**Does not run live** and **does not generate runtime signals**. Decoupled from live loop.
Outputs models to the registry store.

## 2. Dependencies
D01 (contracts, config), D02 (data storage reads), D03 (fundamental features in Phase 3),
D04 (technical features), D08 (runs engine/CPCV for model validation).

## 3. Emits / exposes
Does not publish to the signal bus.
Writes promoted model binaries and metadata JSONs directly to the model registry folder (`data/models/`).

## 4. Internal module structure
```
src/trainer/
  __init__.py
  pipeline.py      # handles data loading, feature engineering, and model training loops
  evaluator.py     # executes CPCV validation tests on trained models using D08 engine
  registry.py      # writes model weights and metadata JSON to data/models/ registry (D02)
  train_all.py     # automation script to train GARCH-GRU, LSTM, Transformer, and ensembles
```

## 5. Existing code to migrate
- `scripts/train_model.py`, `scripts/train_all.py` → migrate logic into `src/trainer/` package.

## 6. Testing strategy
**Coverage target: 50%** (default gate).
- Training loop validation: verify GARCH-GRU and LSTM models fit and converge on mock datasets.
- Registry schema contract: verify that model artifacts written by D09 match the `ModelArtifact` Pydantic schema from `CONTRACTS.md`.

## 7. Implementation phases (internal)
1. Ingestion and pipeline training structures — Phase 6, week 1
2. CPCV validation evaluator integration — Phase 6, week 1-2
3. Model registry writing automation — Phase 6, week 2

## 8. Known risks & gotchas
- **Decoupled Model Loading:** To ensure runtime safety, training and execution must never share memory or imports. The model checkpoint file and its metadata JSON must be the sole interface contract.
- **CPCV Leakage:** Ensure data splits used in CPCV purging are identical to the model training configurations to prevent training leaks.
