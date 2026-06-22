# D04 — TECHNICAL

## 1. Purpose & boundaries
Calculates mathematical and statistical features from raw OHLCV price bars. Identifies market
regimes and provides technical directional biases.
**Does not fetch price data** (D02 does) and **does not make trade decisions** (D05 does).

## 2. Dependencies
D01 (contracts, logging, clock), D02 (price feed).

## 3. Emits / exposes
Bus topics:
- `signals.technical.{instrument}` — emits typed `TechnicalSignal` on price bar updates.

Exposes direct feature extraction API for offline models (`FeatureEngine.extract`).

## 4. Internal module structure
```
src/features/
  __init__.py
  technical_indicators.py # EMA, RSI, MACD, ATR calculations
  order_flow_signals.py   # volume and spread-based features
  regime_detector.py      # market classification (ranging, trending, volatile)
  causal_validator.py     # validates feature correlation, filters leaking features
  feature_engine.py       # consolidates feature calculation, registers pipeline version
```

## 5. Existing code to migrate
- `src/features/*` — refactor existing indicators and estimators to inherit from the core `FeatureEngine` and publish `TechnicalSignal` structures.

## 6. Testing strategy
**Coverage target: 50%** (default gate).
- Vectorized vs iterative equivalence: verify indicator values match traditional calculators.
- Causal validation: run leakage tests to guarantee feature values use past bars only.
- Regime detector: verify mock prices classify correctly.

## 7. Implementation phases (internal)
1. FeatureEngine refactor and signal emission — Phase 2, week 1
2. Technical indicator integrations — Phase 2, week 1-2
3. Causal validation and regime detection updates — Phase 2, week 2-3

## 8. Known risks & gotchas
- **Temporal Leakage (Look-ahead bias):** Features must only evaluate historic close prices. Ensure indicators never query future indices.
- **CPCV Alignment:** Feature versions used during online inference must exactly match the pipeline version used in D09 training to prevent model representation drift.
