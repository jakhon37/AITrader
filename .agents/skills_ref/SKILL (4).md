---
name: promote-model
description: Use this skill when promoting a model from dev to staging or staging to prod, checking which model is currently in production, listing all registered models, demoting a model, or deciding whether a model is ready for live trading.
---

# promote-model

Manages model lifecycle in the registry: dev → staging → prod. Only one prod model per instrument at a time. Auto-promotion to staging is allowed; prod promotion is always manual.

## List all registered models

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/list_models.py

# With filter
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/list_models.py --instrument EURUSD
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/list_models.py --status staging
```

Output format:
```
MODEL_ID                              | INSTRUMENT | TRAINER   | STATUS  | SHARPE | ACCURACY | TRAINED AT
xgboost_EURUSD_20240115_1430         | EURUSD     | XGBoost   | staging | 0.72   | 54.3%    | 2024-01-15 14:30
lstm_EURUSD_20240110_0900            | EURUSD     | LSTM      | dev     | 0.61   | 53.1%    | 2024-01-10 09:00
xgboost_XAUUSD_20240112_1100         | XAUUSD     | XGBoost   | dev     | 0.48   | 51.8%    | 2024-01-12 11:00
```

## Check current prod model

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/list_models.py --status prod
```

Or in Python:
```python
from training.registry import ModelRegistry
from config import AppConfig
from signals.contracts import Instrument

config = AppConfig.from_env()
registry = ModelRegistry(config)
model, metadata = registry.get_prod_model(Instrument.EURUSD)
print(metadata)
```

## Promote staging → prod (manual, your decision)

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/promote_model.py \
  --model-id xgboost_EURUSD_20240115_1430 \
  --to prod
```

This will:
1. Validate the model file exists at the expected path
2. Demote the current prod model to `staging` (if one exists)
3. Set the new model status to `prod`
4. Write the updated registry JSON
5. Print confirmation

The live system picks up the new prod model on its next signal evaluation cycle (no restart required).

## Promote dev → staging (manual override of auto-promotion)

Auto-promotion from dev to staging happens automatically during training if Sharpe > 0.5 AND accuracy > 52%. To manually promote a dev model that didn't meet the threshold:

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/promote_model.py \
  --model-id lstm_EURUSD_20240110_0900 \
  --to staging \
  --force   # bypasses threshold check
```

Use `--force` only if you have a good reason (e.g. the model performs well on an instrument where the thresholds are calibrated for another instrument).

## Demote a model

```bash
# Demote prod to staging
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/promote_model.py \
  --model-id xgboost_EURUSD_20240115_1430 \
  --to staging

# Demote to dev
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/promote_model.py \
  --model-id xgboost_EURUSD_20240115_1430 \
  --to dev
```

## Is this model ready for prod? — decision checklist

Go through all of these before running the promote command:

**Training metrics (from training report)**
- [ ] CPCV Sharpe > 0.8 (> 0.5 is staging threshold, aim higher for prod)
- [ ] CPCV accuracy > 54% (> 52% is staging threshold)
- [ ] Max drawdown across CPCV folds < 20%
- [ ] Performance is consistent across folds (std dev of Sharpe < 0.3)
- [ ] Trained on at least 2 years of data
- [ ] Out-of-sample test period not used in training

**Paper trading validation (required before prod)**
- [ ] Model has been in staging for at least 2 weeks
- [ ] Paper trading Sharpe (annualized) > 0.7
- [ ] Paper trading win rate > 48%
- [ ] Paper trading max drawdown < 15%
- [ ] No circuit breaker trips in paper trading
- [ ] Paper performance is within ±30% of backtest performance (not overfit)

**System checks**
- [ ] Model loads without error: `python scripts/list_models.py --validate --model-id {id}`
- [ ] Decision engine picks up new model: check `/health` after promotion
- [ ] Feature columns in model metadata match current Division 3 indicator output

## Model registry file structure

```
data/models/
├── registry.json                    ← master registry (all models + statuses)
├── xgboost_EURUSD_20240115_1430.pkl ← model file
├── xgboost_EURUSD_20240115_1430.json ← metadata (Sharpe, accuracy, feature_columns, status)
├── lstm_EURUSD_20240110_0900.pt
├── lstm_EURUSD_20240110_0900.json
└── reports/
    ├── xgboost_EURUSD_20240115_1430_report.md
    └── lstm_EURUSD_20240110_0900_report.md
```

## Rollback

If a newly promoted prod model is performing poorly in live trading:

```bash
# 1. Immediately demote the bad model
python scripts/promote_model.py --model-id bad_model_id --to staging

# 2. Promote the previous prod model back
python scripts/promote_model.py --model-id previous_good_model_id --to prod

# 3. Check decision engine switched models
curl http://localhost:8000/health | jq '.metrics'
```

If no previous prod model exists (first promotion), the system automatically falls back to the rule-based fusion mode in Division 5 — no crash, no trades until a model is promoted again.
