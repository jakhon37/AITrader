# Data sources

## Forex

- **CSV:** Place files under `data/forex_raw/`. Expected columns: date/datetime, open, high, low, close, [volume]. Use `data.loaders.load_ohlcv_csv` to load.
- **Brokers:** OANDA, FXCM — use broker API; credentials via env.

## Gold

- **Spot / futures:** Same OHLCV CSV format. Suggested paths: `data/gold_raw/`. Document source and version in `data_version` in config.

## Alternative data (optional)

- **VIX, DXY, economic calendar:** Use `data/alternative_data/` and a dedicated loader when added.
