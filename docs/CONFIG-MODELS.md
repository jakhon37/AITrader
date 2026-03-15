# Model Configuration Guide

The new models are fully integrated with the config system. You can switch between models and adjust their hyperparameters in `config/dev.yaml`.

## Quick Model Switch

Edit `config/dev.yaml` and change the `model_type`:

```yaml
model:
  model_type: "lightgbm"  # Change this line
```

Available options:
- `lightgbm` - Fast gradient boosting (recommended for quick wins)
- `xgboost` - Robust gradient boosting with GPU support
- `enhanced_transformer` - State-of-art transformer (best accuracy)
- `lstm_transformer` - Current default hybrid model
- `garch_gru` - Volatility specialist

## Training With Config

All training scripts now use config automatically:

```bash
# Train with whatever model_type is set in config/dev.yaml
python scripts/train_model.py --symbol gold

# Override model type from command line
python scripts/train_model.py --symbol gold --model-type lightgbm

# Override other parameters
python scripts/train_model.py --symbol btcusd --timeframe 1m --epochs 100
```

## Model-Specific Parameters

### LightGBM / XGBoost (Tree-based)
```yaml
model:
  model_type: "lightgbm"
  
  # Tree-based parameters (both models)
  n_estimators: 500           # Number of trees (50-5000)
  max_depth: 7                # Tree depth (3-15)
  tree_learning_rate: 0.01    # Learning rate (0.001-0.5)
  subsample: 0.8              # Row sampling (0.5-1.0)
  colsample_bytree: 0.8       # Column sampling (0.5-1.0)
  reg_alpha: 0.1              # L1 regularization
  reg_lambda: 0.1             # L2 regularization
```

**Tuning tips:**
- **Faster training**: Reduce `n_estimators` to 200
- **Better accuracy**: Increase to 1000, reduce `tree_learning_rate` to 0.005
- **Less overfitting**: Reduce `max_depth` to 5, increase regularization

### Enhanced Transformer
```yaml
model:
  model_type: "enhanced_transformer"
  
  # Transformer-specific
  d_model: 256                # Model dimension (64-1024)
  nhead: 8                    # Attention heads (2-16, must divide d_model)
  num_transformer_layers: 4   # Depth (1-8)
  dim_feedforward: 1024       # FFN dimension (256-4096)
  
  # Common neural net params
  epochs: 50
  batch_size: 256
  seq_length: 50              # Use longer sequences (20-100)
  dropout: 0.2
  learning_rate: 0.0001       # Lower LR for transformers
```

**Tuning tips:**
- **More capacity**: Increase `d_model` to 512, `num_transformer_layers` to 6
- **Faster training**: Reduce `d_model` to 128, `num_transformer_layers` to 2
- **Better patterns**: Increase `seq_length` to 100 (looks back further)

### LSTM-Transformer / GARCH-GRU
```yaml
model:
  model_type: "lstm_transformer"
  
  # LSTM/GRU-specific
  hidden_size: 128            # Hidden dimension (32-512)
  num_layers: 2               # Number of layers (1-5)
  seq_length: 20              # Lookback window (5-50)
  
  # Training params
  epochs: 50
  batch_size: 256
  dropout: 0.2
  learning_rate: 0.001
```

**Tuning tips:**
- **More capacity**: Increase `hidden_size` to 256, `num_layers` to 3
- **Faster training**: Reduce `hidden_size` to 64, `num_layers` to 1
- **Better memory**: Increase `seq_length` to 50

## Preset Configurations

### Quick Win (Fast Training, Good Accuracy)
```yaml
model:
  model_type: "lightgbm"
  n_estimators: 500
  tree_learning_rate: 0.01
  max_depth: 7
```
**Training time**: 2-5 minutes  
**Expected accuracy**: 54-58%

### Maximum Accuracy (Slow, Best Results)
```yaml
model:
  model_type: "enhanced_transformer"
  d_model: 512
  nhead: 8
  num_transformer_layers: 6
  epochs: 100
  seq_length: 100
  batch_size: 128
```
**Training time**: 30-60 minutes  
**Expected accuracy**: 56-60%

### Balanced Production
```yaml
model:
  model_type: "xgboost"
  n_estimators: 1000
  tree_learning_rate: 0.005
  max_depth: 7
```
**Training time**: 5-10 minutes  
**Expected accuracy**: 54-58%

### GPU-Optimized Neural Net
```yaml
model:
  model_type: "lstm_transformer"
  hidden_size: 256
  num_layers: 3
  batch_size: 512      # Larger for RTX 4080
  epochs: 100
  seq_length: 50
```
**Training time**: 15-25 minutes  
**Expected accuracy**: 53-56%

## Complete Config Example

Here's a complete `config/dev.yaml` optimized for LightGBM:

```yaml
env: dev

data:
  symbols:
    - GOLD
    - BTC_USD
    - EUR_USD
    - GBP_USD
    - USD_JPY
  lookback_days: 365
  data_dir: data
  data_version: null
  timeframe: "1m"

model:
  checkpoint_dir: checkpoints
  ensemble_weights: {}
  confidence_threshold: 0.055
  
  # Use LightGBM for fast, accurate predictions
  model_type: "lightgbm"
  
  # Tree parameters (used by lightgbm/xgboost)
  n_estimators: 500
  max_depth: 7
  tree_learning_rate: 0.01
  subsample: 0.8
  colsample_bytree: 0.8
  reg_alpha: 0.1
  reg_lambda: 0.1
  
  # Neural net parameters (ignored when using tree models)
  epochs: 50
  batch_size: 256
  hidden_size: 128
  num_layers: 2
  dropout: 0.2
  learning_rate: 0.001
  seq_length: 20
  
  # Enhanced transformer (ignored when not using)
  d_model: 256
  nhead: 8
  num_transformer_layers: 4
  dim_feedforward: 1024

risk:
  max_position_pct: 0.102
  max_drawdown_pct: 0.215
  daily_loss_limit_pct: 0.20
  max_signals_per_day: 500

execution:
  broker: mock
  slippage_pips: 0.5
  rate_limit_per_min: 30
```

## Training Examples

### Train with config defaults
```bash
python scripts/train_model.py
```

### Train specific model and symbol
```bash
# LightGBM on GOLD
python scripts/train_model.py --model-type lightgbm --symbol gold

# XGBoost on BTCUSD intraday
python scripts/train_model.py --model-type xgboost --symbol btcusd --timeframe 1m

# Enhanced Transformer with custom epochs
python scripts/train_model.py --model-type enhanced_transformer --epochs 100
```

### Compare all models
```bash
# Compare on GOLD
python scripts/compare_models.py --symbol gold --epochs 30

# Quick comparison (tree models only)
python scripts/compare_models.py --models lightgbm xgboost
```

## Model Selection Strategy

### For Development/Testing
1. Start with **LightGBM** (fastest iteration)
2. Tune hyperparameters
3. Validate on test set

### For Production
1. Compare **LightGBM**, **XGBoost**, and **Enhanced Transformer**
2. Pick winner based on Sharpe ratio (not just accuracy)
3. **Ensemble** top 2-3 models for best results

### For Research
1. Use **Enhanced Transformer** with long sequences (100+)
2. Experiment with different architectures
3. Add custom features

## Troubleshooting

### "Model type X not available"
Install missing dependencies:
```bash
pip install lightgbm xgboost
```

### Config validation error
Check that all parameters are within valid ranges (see `src/config.py` for limits)

### Out of memory (GPU)
Reduce `batch_size` or `d_model`:
```yaml
model:
  batch_size: 128  # Was 256
  d_model: 128     # Was 256
```

### Slow training
Switch to tree-based model or reduce model size:
```yaml
model:
  model_type: "lightgbm"  # Much faster
```

## Advanced: Ensemble Configuration

To use multiple models in ensemble, set weights:

```yaml
model:
  ensemble_weights:
    lightgbm: 0.4
    xgboost: 0.4
    enhanced_transformer: 0.2
```

(Note: Ensemble support coming soon in inference pipeline)

## Next Steps

1. **Edit** `config/dev.yaml` and set your preferred `model_type`
2. **Train**: `python scripts/train_model.py --symbol gold`
3. **Compare**: `python scripts/compare_models.py --models lightgbm xgboost enhanced_transformer`
4. **Choose winner** based on metrics
5. **Update config** with winner and retrain for production
