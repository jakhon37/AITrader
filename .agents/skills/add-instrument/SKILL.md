---
name: add-instrument
description: Use this skill when adding a new tradeable instrument (currency pair, commodity, index), extending the platform to support a new market, or configuring a new symbol in the system.
---

# add-instrument

Adds a new instrument (e.g. USDJPY, BTCUSD, USDCAD) across all divisions that need to know about it. This touches 4 places: contracts, config, data download, and impact map.

## Step 1 — Add to the Instrument enum (Division 1 (D01-CORE))

```python
# src/core/contracts.py

class Instrument(str, Enum):
    EURUSD = "EURUSD"
    GBPUSD = "GBPUSD"
    USDJPY = "USDJPY"
    XAUUSD = "XAUUSD"
    NEWPAIR = "NEWPAIR"   # ← add here
```

**This is the only place the instrument name is defined as an enum value.** Every other file uses `Instrument.NEWPAIR` — no string literals.

## Step 2 — Add to instruments.yaml (trading + activation)

```yaml
# config/instruments.yaml

NEWPAIR:
  enabled: true
  pip_size: 0.0001
  lot_size: 100000
  session_hours: {open: "22:00", close: "22:00"}
  active_timeframes: [15m, 1h, 4h, 1d]
  primary_timeframe: 1h
  fundamental_weight: 0.3
  technical_weight: 0.7
  max_position_lots: 1.0
  news_halt_minutes: 30
  signal_decay:
    central_bank: 48
    economic_data: 4
    geopolitical: 6
    market_risk: 2
    technical_conf: 1
```

Do **not** add a second instrument list to `dev.yaml`. Env YAML (`config/dev.yaml`) holds
pipeline cadence and model/risk settings only. `enabled: true` here drives D02 scheduler,
auto-refresh, and the chart UI (`GET /api/data/instruments`).

## Step 2b — Add Dukascopy feed mapping (if using live Dukascopy data)

```python
# src/data/feeds/dukascopy.py — _SYMBOL_MAP and _DIVISORS
```

**Finding the correct yfinance ticker:**
```python
import yfinance as yf
# Test it
ticker = yf.Ticker("NEWPAIR=X")
hist = ticker.history(period="5d", interval="1h")
print(hist.tail())   # should show OHLCV data
```

Common ticker patterns:
- Forex pairs: `EURUSD=X`, `USDCAD=X`, `AUDUSD=X`
- Gold: `GC=F` (futures) or `GLD` (ETF)
- Silver: `SI=F` (futures) or `SLV` (ETF)
- Oil: `CL=F` (WTI crude)
- Bitcoin: `BTC-USD`
- S&P 500: `^GSPC` or `SPY`

## Step 3 — Download historical data

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/download_sample_data.py \
  --instrument NEWPAIR \
  --timeframes 15m,1h,4h,1d \
  --start 2022-01-01 \
  --end 2024-12-31
```

Validate the download:
```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/project_overview.py --instrument NEWPAIR
```

## Step 4 — Add to fundamental impact map (Division 2 (D02-DATA))

```python
# src/core/config.py

# Which events affect this instrument and how strongly?
IMPACT_MAP = {
    "FEDFUNDS_DECISION": {
        "instruments": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "NEWPAIR"],
        "weights":     [1.0,      1.0,       1.0,      1.2,      0.8],    # ← add weight
        "decay_hours": 8,
        ...
    },
    # Add instrument-specific events if needed:
    "BOC_DECISION": {        # Bank of Canada — for USDCAD
        "instruments": ["USDCAD"],
        "weights":     [1.5],
        "decay_hours": 8,
        "blackout_minutes_before": 30,
        "blackout_minutes_after":  15,
    },
}
```

**Weight guidance by instrument type:**
- Major USD pairs (EURUSD, GBPUSD): weight 1.0 for USD events
- JPY pairs: weight 0.9 for USD events, 1.2 for BOJ events
- Gold (XAUUSD): weight 1.2 for USD events (inverse relationship)
- Commodities (oil, silver): weight 0.7 for USD events, higher for supply events
- Crypto: weight 0.3 for macro events (less correlated)

## Step 5 — Add confluence weight calibration if needed

The default `TF_WEIGHTS` in Division 1 (D01-CORE) (D04-TECHNICAL) are instrument-agnostic, which is fine for Forex. If the new instrument has different characteristics (e.g. crypto trades 24/7, oil has specific session patterns), you may need instrument-specific regime thresholds in `src/technical/regime.py`:

```python
# src/technical/regime.py — instrument-specific volatility thresholds
ATR_VOLATILE_THRESHOLD = {
    "EURUSD": 0.008,    # 0.8% ATR = volatile for EUR/USD
    "XAUUSD": 0.015,    # Gold moves more
    "BTCUSD": 0.05,     # Crypto moves a lot more
    "DEFAULT": 0.010,
}
```

## Step 6 — Update Telegram formatter (Division 7 (D07-NOTIFIER))

No code change needed — the formatters use `signal.instrument.value` which returns the string automatically. Just verify the Telegram messages look right for the new instrument after the first signal fires.

## Step 7 — Train a model for the new instrument (Division 8)

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/train_model.py \
  --instrument NEWPAIR \
  --start 2022-01-01 \
  --end 2024-01-01
```

The new instrument uses the same model architecture as existing instruments. Train separately — models are per-instrument in the registry.

## Step 8 — Run the violation checker

```bash
# Ensure no string literals snuck in
grep -rn '"NEWPAIR"\|'"'NEWPAIR'" src/ --include="*.py" \
  | grep -v "contracts.py\|test_\|config"
```

There should be **no string literals** for the instrument name outside of `contracts.py` and config files.

## Step 9 — Frontend (Division 10)

The trading terminal loads enabled instruments from `GET /api/data/instruments` automatically
when `enabled: true` is set in instruments.yaml. Replay pages may still need a local
update if they hardcode instrument lists.

## Removing an instrument

Never delete from the `Instrument` enum if there are existing positions, audit logs, or signals referencing it. Instead, add `DEPRECATED_NEWPAIR = "DEPRECATED_NEWPAIR"` and remove from the `config.yaml` instruments list — the system will stop generating signals for it but old data remains readable.
