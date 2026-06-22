# D09 — TRAINER

## 1. Purpose & boundaries
Offline model training pipeline: feature generation, training (LSTM/Transformer/GRU/
XGBoost), evaluation via D08's CPCV, registry promotion (dev → staging → prod), and
rollback. **Never runs in the live process** — different hardware profile (GPU server
or similar), different schedule (weekly retrain, not continuous), and must never be
triggerable by anything in the live trading path.

## 2. Dependencies
D01, D02 (historical data + registry write access), D04 (technical feature pipeline —
reused exactly, not reimplemented, to avoid train/serve skew), D03 (fundamental feature
pipeline — **wired in Phase 3**, same caveat as D08), D08 (CPCV evaluation before promotion).

## 3. Emits / exposes
No bus topics — D09 never touches the live bus. Writes `ModelArtifact` records (per
CONTRACTS.md) to D02's registry store at `data/models/`. This is the **only** interface
between D09 and the live system: D05 reads the registry directly, no runtime dependency
on D09 exists or should ever be introduced.

## 4. Internal module structure
```
src/trainer/
  feature_pipeline.py    # pulls historical data from D02, reuses D04's indicator code
                            # and D03's fundamental signal code directly (not reimplemented)
  train_lstm.py             # refactor/wrap of existing lstm_transformer.py training loop
  train_xgboost.py            # new — simpler baseline model, per the "don't over-engineer
                                 # the model" recommendation from the original assessment
  registry.py                   # refactor of existing model_registry.py
  promotion.py                     # NEW — staging performance thresholds, promotion logic
  rollback.py                        # NEW — keeps last N prod checkpoints, rollback trigger
```
Entry points: `scripts/train_model.py`, `scripts/train_all.py` (both already exist as
placeholders per the AGENTS.md scripts list).

## 5. Existing code to migrate
- `src/models/model_registry.py` → `src/trainer/registry.py`
- `src/models/model_factory.py` → informs `train_lstm.py` / `train_xgboost.py` structure
- `src/models/lstm_transformer.py`, `enhanced_transformer.py`, `garch_gru.py` → training
  logic wrapped by `train_lstm.py` and friends, not rewritten
- `src/models/meta_labeler.py`, `ensemble.py` → reviewed for reuse in later model versions

## 6. Testing strategy
**Coverage target: 50%**.
- Feature pipeline determinism: same historical window → identical feature output,
  critical for reproducible training runs
- Registry promotion/rollback state machine: dev→staging→prod transitions, and the
  rollback path, tested as explicit state transitions with invalid-transition rejection
- CPCV-gated promotion: a model failing the CPCV threshold must not reach staging,
  tested with a deliberately bad model

## 7. Implementation phases (internal)
1. Feature pipeline reusing D04 (and D03 once it exists) — Phase 6, week 1
2. Training scripts (LSTM baseline first, per "signals over models" guidance) — Phase 6, week 1–2
3. Registry promotion thresholds + rollback procedure — Phase 6, week 2

## 8. Known risks & gotchas
- **Train/serve feature skew is the most damaging failure mode here.** The feature
  pipeline must call D04's and D03's actual production code, not a reimplemented or
  simplified copy — otherwise a model trained on slightly different features than it
  sees live will silently underperform with no obvious cause.
- **GPU/process isolation** — confirm training never shares a process or even a host
  with the live trading loop; this was flagged early in planning and is easy to violate
  by accident if `scripts/train_model.py` is run carelessly in the same environment.
- **Stale model with no rollback trigger** — define explicit staging performance
  thresholds and an automatic rollback trigger (not just a manual procedure) before this
  division reaches prod; a silently underperforming production model is worse than no model.
