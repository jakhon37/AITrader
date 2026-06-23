---
name: add-indicator
description: Use this skill when the user wants to add a new technical indicator, extend the indicator set, add a new TA signal component, or wire a new indicator into the confluence voting system in Division 1 (D01-CORE) (D04-TECHNICAL).
---

# add-indicator

Adds a new technical indicator to Division 1 (D01-CORE) (D04-TECHNICAL) (`src/technical/indicators.py`) and wires it into the `TechnicalEngine` voting system.

## Step 1 — Implement the indicator function

Open `src/technical/indicators.py`. Add a new function following this exact pattern:

```python
def compute_{indicator_name}(df: pd.DataFrame) -> dict[str, float]:
    """
    {Description of what it measures and what the values mean}
    
    Args:
        df: OHLCV DataFrame with canonical schema (timestamp index, open/high/low/close/volume columns)
    
    Returns:
        dict of indicator values. All values must be finite floats.
        Returns empty dict if insufficient data.
    """
    if len(df) < {minimum_bars_required}:
        return {}
    
    try:
        # --- computation here ---
        # Use TA-Lib (import talib) or pandas_ta (import pandas_ta as ta)
        # Example with TA-Lib:
        # result = talib.RSI(df['close'].values, timeperiod=14)
        # value = float(result[-1])
        
        # Guard against NaN
        if not np.isfinite(value):
            return {}
        
        return {
            "{indicator_name}_{param}": value,
            # add more sub-values if the indicator produces multiple outputs
        }
    except Exception:
        return {}   # never crash — return empty on any error
```

**Naming convention:** `{indicator_name}_{parameter}` — e.g. `rsi_14`, `ema_200`, `macd_hist`, `bb_upper`, `atr_14`.

## Step 2 — Add to the indicator runner

In `src/technical/indicators.py`, find the `compute_all_indicators(df)` function and add your new function to the list:

```python
def compute_all_indicators(df: pd.DataFrame) -> dict[str, float]:
    results = {}
    
    for compute_fn in [
        compute_rsi,
        compute_macd,
        compute_ema,
        compute_adx,
        compute_bollinger,
        compute_atr,
        compute_{indicator_name},   # ← add here
    ]:
        results.update(compute_fn(df))
    
    return results
```

## Step 3 — Add a vote in TechnicalEngine

Open `src/technical/engine.py`. In the `_vote()` method, add a vote block for your indicator:

```python
def _vote(self, indicators: dict) -> tuple[Direction, float]:
    votes = []
    
    # ... existing votes ...
    
    # {Indicator name} vote
    {value} = indicators.get("{indicator_name}_{param}")
    if {value} is not None and np.isfinite({value}):
        if {value} > {bullish_threshold}:
            votes.append(("{indicator_name}", +1, {weight}))
        elif {value} < {bearish_threshold}:
            votes.append(("{indicator_name}", -1, {weight}))
        else:
            votes.append(("{indicator_name}",  0, {neutral_weight}))
    
    # ... rest of voting logic ...
```

**Weight guidance:**
- `1.2` — high-reliability trend indicator (EMA vs price, ADX direction)
- `1.0` — standard momentum indicator (RSI, Stochastic)
- `0.8` — secondary confirmation (CCI, OBV)
- `0.5` — weak signal, confirmation only (volume ratio, round number proximity)

## Step 4 — Write the unit test

Create or extend `tests/unit/test_technical_indicators.py`:

```python
def test_{indicator_name}_bullish():
    """Test with data that should produce a bullish reading."""
    df = make_trending_up_ohlcv(bars=50)   # use existing test fixture
    result = compute_{indicator_name}(df)
    assert "{indicator_name}_{param}" in result
    assert result["{indicator_name}_{param}"] > {bullish_threshold}

def test_{indicator_name}_insufficient_data():
    """Indicator must return empty dict, not raise, with too few bars."""
    df = make_ohlcv(bars=2)
    result = compute_{indicator_name}(df)
    assert result == {}

def test_{indicator_name}_nan_safe():
    """Indicator must handle NaN in input without crashing."""
    df = make_ohlcv_with_nans(bars=100)
    result = compute_{indicator_name}(df)   # must not raise
    for v in result.values():
        assert np.isfinite(v) or result == {}
```

## Step 5 — Verify vote wiring

Run the TechnicalEngine unit test to confirm the new vote participates in direction computation:

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_technical.py -v
```

## Step 6 — Document in DIVISION_3.md

Add the indicator to the **Indicator set** section of `DIVISION_3.md` under the appropriate category (Trend / Momentum / Volatility / Volume / Support-Resistance).

## Common mistakes to avoid

- **Never** return `float('nan')` or `np.nan` in the result dict — always guard with `np.isfinite()` and return empty dict instead
- **Never** modify `contracts.py` or any Division 1 (D01-CORE) file — indicators are internal to Division 1 (D01-CORE) (D04-TECHNICAL)
- **Never** add broker, bus, or data-fetch logic inside an indicator function — pure computation only
- The `indicators` dict key names in `TimeframeSignal.indicators` are part of the model feature vector — once named, don't rename them without retraining models (Division 8)
