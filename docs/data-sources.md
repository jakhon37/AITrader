# Data sources

## Forex

- **CSV:** Place files under `data/forex_raw/` or `data/raw/`. Expected columns: date/datetime, open, high, low, close, [volume]. Use `data.loaders.load_ohlcv_csv` to load.
- **Brokers:** OANDA, FXCM — use broker API; credentials via env.

## Gold

- **Spot / futures:** Same OHLCV CSV format. Suggested paths: `data/gold_raw/`. Document source and version in `data_version` in config.

## Download real data for testing

```bash
pip install -e ".[data]"
python scripts/download_sample_data.py
```

Fetches EUR/USD, GBP/USD, USD/JPY, and GLD (gold) from Yahoo Finance into `data/raw/`. Integration test `test_real_data_if_available` will then run on these files.

## Generate realistic fixture (no network)

```bash
python tests/fixtures/generate_realistic_fixture.py
```

Creates `tests/fixtures/eurusd_500_days.csv` (500 trading days) for CI and local testing.

## Alternative data (optional)

- **VIX, DXY, economic calendar:** Use `data/alternative_data/` and a dedicated loader when added.
