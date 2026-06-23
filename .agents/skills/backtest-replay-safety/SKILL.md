---
name: backtest-replay-safety
description: Guidelines and safety rules for working with ReplayClock, historical backtests, data feeds, and avoiding lookahead leakages in AITrader.
---

# Backtest & Replay Safety Guidelines

This skill enforces best practices when working with historical data streams, virtual time, and backtesting systems in the AITrader repository.

## 🕒 1. Virtual Time Enforcement (No System Time)
* **Rule**: You must NEVER use `datetime.now()` or `datetime.utcnow()` directly in code files outside of `src/core/clock.py`.
* **Action**: Always import and use the active clock system:
  ```python
  from src.core.clock import now
  current_time = now()
  ```
* In backtests and replay mode, the clock is controlled via `ReplayClock`. Using system time will cause trade signals to use future/wrong dates.

## 🚫 2. Lookahead Bias Prevention (Data Leaks)
* When loading historical bars for indicator calculations, you must filter out any candle that has not fully closed at the current virtual clock timestamp.
* **Calculation**: A candle closes at `open_time + timeframe_duration`.
* If a bar's close time is after `clock.now()`, the strategy must not see it. Ensure this boundary check is present:
  ```python
  df = df[df.index + timeframe_delta <= clock.now()]
  ```

## 📊 3. Resampling Rules
* All raw data is stored at the 1-minute (`1m`) resolution fetched from Dukascopy.
* Higher timeframes (`5m`, `15m`, `1h`, `4h`, `1d`) must be resampled chronologically using right-labeled, right-closed bins to ensure candles are labeled with their end/close time.

## 💸 4. Slippage and Execution Modeling
* The simulated paper broker (`SimBroker`) must account for slippage and spread commissions to prevent unrealistic performance results.
* Ensure backtests and replays configure commissions in their execution engine setup.
