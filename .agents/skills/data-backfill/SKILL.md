---
name: data-backfill
description: Use this skill when downloading historical OHLCV price data, backfilling missing data, fetching data for a new instrument or timeframe, running the sample data downloader, or verifying the data store is populated before backtesting or training.
---

# data-backfill

Downloads and stores historical OHLCV data for all configured instruments and timeframes. Required before running backtests, training models, or replay sessions.

## Quick start — download everything

```bash
# Download all instruments × all timeframes (from config)
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/download_sample_data.py

# Download with explicit date range
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/download_sample_data.py \
  --start 2020-01-01 \
  --end 2024-12-31

# Download a single instrument
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/download_sample_data.py \
  --instrument EURUSD \
  --timeframes 1h,4h,1d

# Download multiple instruments
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/download_sample_data.py \
  --instruments EURUSD,XAUUSD,GBPUSD,USDJPY \
  --timeframes 15m,1h,4h,1d
```

## yfinance ticker mapping

The project uses yfinance as the primary data source. Instrument names map to yfinance tickers:

| Instrument | yfinance ticker |
|---|---|
| EURUSD | EURUSD=X |
| GBPUSD | GBPUSD=X |
| USDJPY | USDJPY=X |
| XAUUSD | GC=F  (Gold futures) or GLD (ETF) |

## Timeframe mapping

| Config timeframe | yfinance interval | Max history |
|---|---|---|
| 1m | 1m | 7 days only |
| 5m | 5m | 60 days only |
| 15m | 15m | 60 days only |
| 30m | 30m | 60 days only |
| 1h | 1h | 730 days |
| 4h | Not native — resample from 1h | unlimited |
| 1d | 1d | unlimited |
| 1w | 1wk | unlimited |
| 1mo | 1mo | unlimited |

**Important:** yfinance does not provide a native 4h interval. The downloader resamples 1h data into 4h automatically using OHLCV resample logic (open=first, high=max, low=min, close=last, volume=sum).

## Data storage location

```
data/
└── raw/
    ├── EURUSD/
    │   ├── 1h/
    │   │   ├── 2022.parquet
    │   │   ├── 2023.parquet
    │   │   └── 2024.parquet
    │   ├── 4h/
    │   └── 1d/
    ├── XAUUSD/
    ├── GBPUSD/
    └── USDJPY/
```

Each Parquet file is partitioned by year. Files are append-safe — running the downloader twice for the same period deduplicates by timestamp.

## Verify data is present and valid

```bash
# Check what's in the store
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/project_overview.py

# Run the validate-data skill for full integrity check
# (see validate-data skill)
```

## Manual fetch using the DataGateway (in code)

```python
import asyncio
from config import AppConfig
from signals.clock import LiveClock
from signals.bus import init_bus
from data.gateway import DataGateway
from data.store.ohlcv_store import OHLCVStore
from signals.contracts import Instrument, Timeframe

async def fetch_manual():
    config = AppConfig.from_env()
    clock = LiveClock()
    bus = init_bus()
    store = OHLCVStore(config)
    gateway = DataGateway(store=store, clock=clock, bus=bus)
    
    df = await gateway.get_ohlcv(
        instrument=Instrument.EURUSD,
        timeframe=Timeframe.H1,
        bars=1000,
    )
    print(f"Fetched {len(df)} bars")
    print(df.tail())

asyncio.run(fetch_manual())
```

## Minimum data requirements

| Use case | Minimum bars | Recommended |
|---|---|---|
| Indicator computation | 50 bars | 200 bars |
| Regime detection (ADX) | 28 bars | 100 bars |
| LSTM training | 5,000 bars | 20,000+ bars |
| XGBoost training | 1,000 bars | 10,000+ bars |
| CPCV (6 folds) | 2,000 bars | 8,000+ bars |
| Replay session | 100 bars | any range |

For a complete 2-year training dataset on 1h: approximately 17,520 bars per instrument. Run:
```bash
python scripts/download_sample_data.py --start 2022-01-01 --end 2024-01-01 --timeframes 1h,4h,1d
```

## Forex market hours note

Forex trades Sunday 22:00 UTC to Friday 22:00 UTC. Saturday bars are absent — this is normal, not a gap. The data validator (`validate-data` skill) is aware of weekend gaps and will not flag them as errors.
