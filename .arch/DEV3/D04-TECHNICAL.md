# D04 — TECHNICAL

## 1. Purpose & boundaries
Runs indicators per timeframe on OHLCV data from D02, combines them into a multi-timeframe
confluence score, and classifies market regime. Emits typed `TechnicalSignal` objects.
**Does not fetch raw price data** (D02 does) and **does not fuse with fundamental signals**
(D05 does). This is the strongest existing pillar — mostly refactor, not greenfield.

## 2. Dependencies
D01, D02.

## 3. Emits / exposes
Bus topic: `signals.technical.{instrument}` — `TechnicalSignal` per CONTRACTS.md,
published on each active timeframe's candle close (subscribes to `data.bar.*`).

No direct read API — pure bus producer, same pattern as D03.

## 4. Internal module structure
```
src/technical/
  indicators.py        # refactor of technical_indicators.py — per-timeframe indicator calc
  regime_detector.py     # refactor of existing regime_detector.py
  order_flow.py           # refactor of order_flow_signals.py
  causal_validator.py      # refactor of existing causal_validator.py — feature leakage checks
  confluence.py             # NEW — weights per-TF signals into one TechnicalSignal,
                              # weighting scheme keyed by regime + timeframe importance
  engine.py                   # subscribes to data.bar.*, orchestrates the above, publishes
```

## 5. Existing code to migrate
- `src/features/technical_indicators.py` → `src/technical/indicators.py`
- `src/features/regime_detector.py` → `src/technical/regime_detector.py`
- `src/features/order_flow_signals.py` → `src/technical/order_flow.py`
- `src/features/causal_validator.py` → `src/technical/causal_validator.py`
- `src/features/feature_engine.py` — logic absorbed into `engine.py` + `confluence.py`

All four existing files keep their core logic; the change is output type (typed
`TechnicalSignal` instead of raw DataFrames) and the bus-publish wiring.

## 6. Testing strategy
**Coverage target: 50%** (consider raising to 80% given this feeds D05 and D06 directly
— flag for review once Phase 2 starts).
- Regression tests against known indicator values on fixed input series (e.g., RSI of a
  known 14-period series should match a hand-calculated value)
- Confluence weighting: unit tests with synthetic per-TF inputs, assert expected combined
  score and that timeframe-importance weighting behaves as configured
- Causal validator: confirm no future-bar leakage, especially under VirtualClock replay mode

## 7. Implementation phases (internal)
1. Refactor existing indicators to typed signal output, wire to `data.bar.*` — Phase 2, week 1
2. Confluence layer — Phase 2, week 1–2
3. Regime-weighted indicator selection — Phase 2, week 2–3

## 8. Known risks & gotchas
- **Lookahead bias in replay** — every indicator calculation must respect `VirtualClock`;
  this is the single most damaging bug class for a backtested strategy and the existing
  `causal_validator.py` should be the enforcement point, not an afterthought.
- **TA-Lib install friction** — confirm it's already handled in the Docker dev image; if
  not, document the native dependency install step explicitly, it's a common onboarding blocker.
- **Confluence weighting overfit risk** — a weighting scheme tuned on recent regime data
  will look great in backtest and fail live. Validate weighting choices against D08's
  walk-forward, not a single backtest window.
