# Universal Trading Configuration

## Overview

Centralized configuration system to avoid repeating settings across scripts.

## Quick Start

### 1. Edit Your Config Once

```bash
# Edit config/dev.yaml
vim config/dev.yaml
```

```yaml
env: dev

data:
  symbols:
    - BTC_USD      # Primary symbol (used as default)
    - EUR_USD
    - GBP_USD
  timeframe: "1m"  # All scripts use this by default
  lookback_days: 365
  data_dir: data

model:
  model_type: "lstm_transformer"  # lstm_transformer or garch_gru
  batch_size: 256                 # Optimized for your GPU
  epochs: 50                      # Default training epochs
  confidence_threshold: 0.55

risk:
  max_position_pct: 0.02
  max_drawdown_pct: 0.15
  daily_loss_limit_pct: 0.05

execution:
  broker: mock
  slippage_pips: 0.5
```

### 2. Run Scripts Without Arguments

```bash
# Train - uses config defaults
python scripts/train_intraday.py

# Paper trade - uses config defaults
./scripts/start_paper.sh

# Backtest - uses config defaults  
python scripts/run_backtest.py

# All scripts automatically use:
# - Symbol: btcusd (from BTC_USD)
# - Timeframe: 1m
# - Model: lstm_transformer
# - Batch size: 256
# - Epochs: 50
```

### 3. Override When Needed

```bash
# Config says btcusd/1m, but test eurusd/1d
python scripts/train_intraday.py --symbol eurusd --timeframe 1d --epochs 100

# Config says lstm_transformer, but use garch_gru
./scripts/start_paper.sh --model garch_gru

# Override with different config file
python scripts/train_intraday.py --config config/prod.yaml
```

## Environment-Specific Configs

```bash
# Development (default)
ENV=dev python scripts/train_intraday.py
# → Loads config/dev.yaml

# Production
ENV=prod python scripts/train_intraday.py  
# → Loads config/prod.yaml

# Staging
ENV=staging python scripts/train_intraday.py
# → Loads config/staging.yaml
```

## Benefits

### Before (Repetitive ❌)
```bash
python scripts/train_intraday.py --symbol btcusd --timeframe 1m --batch-size 256 --epochs 50
python scripts/run_paper.py --symbol btcusd --timeframe 1m --model lstm_transformer
python scripts/run_backtest.py --symbol btcusd --timeframe 1m
streamlit run dashboards/feature_explorer.py  # Then select btcusd, 1m manually
```

### After (Simple ✅)
```bash
# One-time config edit
vim config/dev.yaml  # Set btcusd, 1m, lstm_transformer, batch_size 256

# Then just run
python scripts/train_intraday.py
./scripts/start_paper.sh
python scripts/run_backtest.py
streamlit run dashboards/feature_explorer.py  # Auto-defaults to btcusd, 1m
```

## Config Priority

1. **Command-line arguments** (highest priority)
2. **Config file** (specified with --config)
3. **Environment config** (config/dev.yaml, config/prod.yaml)
4. **Code defaults** (lowest priority, fallback only)

## Symbol Format

Config uses `SYMBOL_PAIR` format (uppercase with underscore):
```yaml
symbols:
  - BTC_USD   # Becomes "btcusd" in scripts
  - EUR_USD   # Becomes "eurusd" in scripts
  - GBP_USD   # Becomes "gbpusd" in scripts
```

Scripts automatically normalize to lowercase without underscores.

## Updating Other Scripts

To add config support to any script:

```python
from config import load_config

# Load config
cfg = load_config()

# Use config values as defaults
default_symbol = cfg.get_primary_symbol()      # "btcusd"
default_timeframe = cfg.data.timeframe         # "1m"
default_model = cfg.model.model_type           # "lstm_transformer"
default_batch_size = cfg.model.batch_size      # 256
default_epochs = cfg.model.epochs              # 50

# Use in argparse
parser.add_argument("--symbol", default=default_symbol)
parser.add_argument("--timeframe", default=default_timeframe)
```

## Pro Tips

1. **Different trading strategies**: Create multiple configs
   ```bash
   config/btc_scalping.yaml   # 1m, small epochs
   config/forex_swing.yaml    # 1h, large epochs
   ```

2. **Quick switching**:
   ```bash
   # BTC 1-minute scalping
   python scripts/train_intraday.py --config config/btc_scalping.yaml
   
   # EUR/USD daily swing
   python scripts/train_all.py --config config/forex_swing.yaml
   ```

3. **Environment variables**:
   ```bash
   export ENV=prod
   export CONFIG_DIR=/path/to/configs
   python scripts/run_paper.py  # Uses prod config
   ```

## Next Steps

All scripts now support unified config:
- ✅ `scripts/train_intraday.py` - Updated
- ⏳ `scripts/train_all.py` - TODO
- ⏳ `scripts/run_paper.py` - TODO  
- ⏳ `scripts/run_backtest.py` - TODO
- ⏳ `dashboards/feature_explorer.py` - TODO

You can update remaining scripts using the same pattern shown above.
