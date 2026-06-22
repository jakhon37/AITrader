# D09 — TRAINER

## Purpose
Offline model training pipeline. Pulls historical data, generates feature sets
from D04's indicator engine, trains models (LSTM, XGBoost, ensemble), evaluates
with CPCV from D08, manages the model registry with promotion and rollback.

Does NOT: run during live trading; subscribe to any live bus channel; train online
(all training is batch offline). Never runs in the same process as the live loop.

---

## Dependencies
- D01-CORE: contracts, config, logging (no bus — offline, not event-driven)
- D02-DATA: DataStore.get_ohlcv(), get_news() (historical reads)
- D03-FUNDAMENTAL: imports sentiment scoring directly for feature generation
  (historical FundamentalSignal reconstruction over the training window — see features.py.
  Not a bus subscription; D09 calls D03's scorer/classifier as a library against historical
  news pulled from D02, since there's no live bus to subscribe to offline)
- D04-TECHNICAL: imports indicator engine directly for feature generation
- D08-BACKTEST: imports CPCV and walk-forward engines for model evaluation

**Downstream:** D09 has no dependency on D05, and no division depends on D09 at runtime.
D09 writes ModelArtifact records to `data/models/registry.json` (see CONTRACTS.md);
D05 reads that file directly. This is an artifact handoff, not a code or process
dependency — D09 never imports D05 and is never imported by it.

---

## Emits
Nothing onto any bus. Outputs are model checkpoint files written to data/models/.
On promotion, writes a `ModelArtifact` record (per CONTRACTS.md) to
`data/models/registry.json` — this is the sole interface D05 reads from.

---

## Internal Module Structure

```
src/trainer/
  __init__.py
  pipeline.py       <- main training pipeline; orchestrates all stages; CLI entry
  features.py       <- feature engineering: combines D04 indicators + D03 sentiment scores
  datasets.py       <- TimeSeriesDataset builder; train/val/test splits; CPCV folds
  models/
    lstm.py         <- LSTM + optional Transformer head (refactored from src/models/lstm_transformer.py)
    xgboost_model.py <- XGBoost classifier/regressor wrapper
    garch_gru.py    <- refactored from src/models/garch_gru.py
    ensemble.py     <- ensemble combiner (refactored from src/models/ensemble.py)
    base.py         <- BaseModel protocol: fit(), predict(), save(), load()
  registry.py       <- model registry: track checkpoints, metadata, promote dev->staging->prod
  evaluator.py      <- CPCV evaluation wrapper; performance metrics; rollback trigger logic
  rollback.py       <- detects underperforming prod model; promotes previous checkpoint
```

### pipeline.py
CLI: python -m src.trainer.pipeline --instrument EURUSD --model lstm --start 2020-01-01

Stages:
1. Load historical OHLCV + news from D02 DataStore for date range
2. features.build() -> feature DataFrame (indicators + sentiment + macro + target labels)
3. datasets.build() -> CPCV folds (using D08 cpcv.py)
4. For each fold: model.fit(train), model.predict(val) -> fold metrics
5. evaluator.aggregate_cpcv_metrics() -> overall performance
6. If performance > baseline threshold: registry.promote(model, "dev")
7. Generate evaluation report
8. Optional: run walk-forward validation before staging promotion

Training runs are logged with a run ID. All artifacts (checkpoints, metrics, feature
importances) stored under data/models/{run_id}/.

### features.py
Feature vector per bar:
- Technical indicators from D04 indicator engine (all active indicators for all TFs)
  Flattened: rsi_1h, rsi_4h, macd_hist_1h, adx_1d, etc.
- Confluence score from D04 (per TF and overall)
- MarketRegime encoding (one-hot: trending/ranging/volatile/unknown per TF)
- Fundamental sentiment_score (last valid FundamentalSignal for instrument, or 0.0)
- Time features: hour of day, day of week, days to next high-impact event
- Target label: forward return sign over N bars (configurable N; default primary TF × 5)

Label construction must be purged (no overlap between train and val in CPCV).
Use embargo period = 2 × ATR lookback to prevent leakage.

### registry.py
Refactored from src/models/model_registry.py (existing).
Model lifecycle: dev -> staging -> prod.

```
data/models/
  registry.json           <- master index of all model versions + metadata
  {run_id}/
    checkpoint.pt         <- PyTorch state dict (or .json for XGBoost)
    metadata.json         <- run config, metrics, feature list, training date, instrument
    feature_importance.json
```

Promotion rules:
- dev -> staging: CPCV Sharpe > 0.5 AND max drawdown < 20%
- staging -> prod: 2 weeks live shadow evaluation (logs but doesn't trade) + Sharpe > 0.6

Rollback procedure (handled by rollback.py):
- Trigger: 5 consecutive live losses OR daily drawdown > 15% attributed to model signals
- Action: atomically swap prod -> previous checkpoint; alert D07 Telegram; log to D11
- Rollback is automatic but generates an alert requiring human acknowledgment before re-promotion

### evaluator.py
Wraps D08's CPCV and walk-forward engines.
Additional metrics beyond standard CPCV:
- Direction accuracy (% of correct long/short calls)
- Confidence calibration (do high-confidence signals actually perform better?)
- Sharpe ratio, Sortino ratio, Calmar ratio
- Max drawdown, average drawdown duration
- Per-instrument breakdown

Compares new model against the current prod model on the same holdout period.
Only promotes if new model is strictly better on at least 3 of 5 metrics.

### rollback.py
Monitors live model performance (reads from D06 audit log, not live bus).
Checks every hour during trading sessions.
Triggers rollback if threshold breached (see registry.py).
Runs as a separate cron process, not in the live trading loop.

---

## Existing Code to Migrate

| Existing | Action |
|---|---|
| src/models/model_registry.py | Move to src/trainer/registry.py; add rollback + staging shadow |
| src/models/model_factory.py | Absorb into pipeline.py; factory pattern replaced by explicit model classes |
| src/models/lstm_transformer.py | Move to src/trainer/models/lstm.py; ensure BaseModel protocol |
| src/models/enhanced_transformer.py | Move to src/trainer/models/; evaluate if worth keeping vs lstm.py |
| src/models/garch_gru.py | Move to src/trainer/models/garch_gru.py |
| src/models/meta_labeler.py | Evaluate as the v2 fusion model in D05; keep in trainer |
| src/models/ensemble.py | Move to src/trainer/models/ensemble.py |

---

## Environment Variables Required
```
# No live API keys needed; purely offline
# GPU training uses CUDA_VISIBLE_DEVICES if available
```

---

## Testing Strategy
Coverage target: 55% (offline pipeline; harder to unit test deeply).

Unit:
- features.py: known OHLCV + indicators -> feature vector has correct shape and no NaN
- registry.py: promote dev->staging; rollback; version ordering
- evaluator.py: mock CPCV results -> correct metric aggregation; promotion threshold logic
- rollback.py: mock audit log with 5 consecutive losses -> rollback triggered

Integration:
- Full pipeline: fixture 2-year EUR/USD data -> model trains -> metrics generated -> dev promotion
- Staging shadow mode: model runs in shadow for N bars; metrics logged; no TradeSignals emitted
- Rollback integration: prod model underperforms -> previous checkpoint promoted -> alert fired

---

## Implementation Phases

### Phase 6 (MASTER Phase 6)
1. Migrate model files to src/trainer/models/; ensure BaseModel protocol
2. Migrate registry.py; add staging shadow + rollback logic
3. Write features.py — combined F+T feature vector
4. Write datasets.py — CPCV fold builder with embargo
5. Write evaluator.py — wrap D08 CPCV; additional metrics
6. Write pipeline.py — end-to-end CLI
7. Milestone: LSTM trains on EUR/USD fixture; promotes to dev registry

### Phase 6b
8. Write rollback.py — hourly monitor as cron process
9. Staging shadow rollout for trained model in D05
10. Write ensemble.py — combine LSTM + XGBoost predictions
11. Milestone: model in staging, evaluated vs weighted combiner baseline

---

## Known Risks

**Look-ahead in feature engineering.** Sentiment scores and macro data must be
lagged by at least 1 bar before use as features. Using today's CPI to predict
today's price is trivial look-ahead. features.py must enforce:
all fundamental features are lagged by the release-to-bar delay.

**Overfitting to CPCV.** CPCV reduces overfitting but doesn't eliminate it.
Always evaluate on a true holdout (last 6 months never touched during training).
The holdout period must be set before training starts and never changed.

**Training time on CPU.** LSTM on 5 years of 1h data can take hours on CPU.
Plan for GPU-accelerated training (CUDA; RTX 4080 on aoi-linux is available per background).
Add --device flag to pipeline.py. Log training time to metadata.json.

**Feature importance drift.** The features that matter most in 2022 may not in 2024.
Run feature importance analysis on each training run. If top-5 features change
significantly between runs, flag it in D11 as a regime-change signal.

**Rollback storm.** If the market enters a regime where no model performs well,
rollback.py could trigger repeatedly and cycle through all checkpoints.
Add rollback cooldown: minimum 24 hours between rollbacks. After 3 rollbacks in 72h,
halt model-based trading and fall back to the weighted combiner (D05 fusion_mode: weighted).
