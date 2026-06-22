# D04 — TECHNICAL

## Purpose
Technical analysis pillar. On each candle close, loads multi-timeframe OHLCV data,
runs indicators, detects regime, computes cross-TF confluence, emits TechnicalSignal.

Does NOT: fetch data (D02), combine with fundamental signals (D05), execute trades,
or train models. Produces one signal type per primary-TF candle close per instrument.

---

## Dependencies
- D01-CORE: contracts, bus, clock, config, logging
- D02-DATA: subscribes to BusChannel.OHLCV_BAR; queries DataStore.get_ohlcv()

---

## Emits
| Channel | Type | When |
|---|---|---|
| BusChannel.TECHNICAL_SIGNAL | TechnicalSignal | On each primary-TF candle close per instrument |

---

## Internal Module Structure

```
src/technical/
  __init__.py
  engine.py          <- subscribes to OHLCVBar; orchestrates full pipeline
  loader.py          <- fetches multi-TF data from D02; returns MultiTFDataset
  indicators.py      <- refactored from src/features/technical_indicators.py
  regime.py          <- refactored from src/features/regime_detector.py
  confluence.py      <- NEW: cross-TF combiner; produces direction + confidence
  signal_builder.py  <- assembles TechnicalSignal; computes entry/SL/TP
  order_flow.py      <- refactored from order_flow_signals.py (optional, feature-flagged)
  causal.py          <- refactored from causal_validator.py
```

### engine.py
Subscribes to BusChannel.OHLCV_BAR. Triggers on primary-TF close only.
Lower TFs update internal state but don't trigger a new TechnicalSignal.

Pipeline on primary-TF close:
1. loader.load(instrument, active_timeframes) -> MultiTFDataset
2. indicators.compute(dataset) -> per-TF indicator dict
3. regime.detect(dataset) -> per-TF MarketRegime
4. confluence.combine(per_tf_results) -> direction, confidence, confluence_score
5. causal.filter(indicators) -> drop spurious features
6. signal_builder.build(...) -> TechnicalSignal
7. Publish signal onto bus

### indicators.py
Returns dict[Timeframe, dict[str, float]]. Computed via pandas_ta or ta-lib.

Standard set (all configurable):
- Trend: EMA 20/50/200, ADX(14)
- Momentum: RSI(14), Stochastic(14,3), MACD(12,26,9)
- Volatility: ATR(14), Bollinger Bands(20,2)
- Volume: OBV, VWAP (intraday only)
- Structure: swing high/low (last 3 pivots), distance from S/R

### regime.py
Per-TF classification:
- Trending: ADX > 25 AND price above/below EMA200
- Ranging: ADX < 20 AND price within Bollinger Bands
- Volatile: ATR > 1.5x 20-period ATR average
- Unknown: fallback

### confluence.py
Key new module. Timeframe weight defaults (configurable per instrument + regime):

Position trading (primary=4H/1D):  1d=0.35, 4h=0.30, 1h=0.20, 15m=0.15
Intraday (primary=1H):             4h=0.40, 1h=0.35, 15m=0.20, 5m=0.05
Scalping (primary=5M/15M):         1h=0.35, 15m=0.30, 5m=0.25, 1m=0.10

Algorithm:
1. Each TF votes LONG=+1, SHORT=-1, NEUTRAL=0, weighted by TF_weight * TF_confidence
2. Sum weighted votes -> raw_score in [-1, +1]
3. direction: LONG if raw > 0.15, SHORT if raw < -0.15, else NEUTRAL
4. confidence = abs(raw_score)
5. confluence_score = agreeing TFs / total TFs

Bonuses (capped at 1.0):
- All 3+ major TFs agree: +0.10 to confidence
- Primary TF trending in signal direction: +0.05
- Price at key S/R level: +0.05

### signal_builder.py
Computes entry/SL/TP via ATR-based method:
- stop_loss = entry +/- 1.5 * ATR(14) on primary TF
- take_profit = entry +/- 2.5 * ATR(14)  (1:1.67 R:R minimum)
- valid_until = next primary TF candle close

---

## Existing Code to Migrate

| Existing | New location | Action |
|---|---|---|
| src/features/technical_indicators.py | src/technical/indicators.py | Refactor: return dict[str,float]; remove side effects |
| src/features/regime_detector.py | src/technical/regime.py | Make pure function; accept indicators dict |
| src/features/order_flow_signals.py | src/technical/order_flow.py | Feature-flagged; default off |
| src/features/causal_validator.py | src/technical/causal.py | Keep as filter; add D11 metric |
| src/features/feature_engine.py | Absorbed into engine.py | Delete after migration |

---

## Testing Strategy
Coverage target: 65%.

Unit:
- indicators.py: fixture OHLCV -> all indicators return valid floats (no NaN on full series)
- regime.py: known ADX/ATR values -> correct regime
- confluence.py: all TFs agree -> high confidence; split -> NEUTRAL; weight normalization
- signal_builder.py: mock sub-module outputs -> valid TechnicalSignal with correct valid_until

Integration:
- engine.py: mock OHLCVBar events -> TechnicalSignal emitted on bus
- End-to-end with EUR/USD 2023 fixture: signal directions are not uniformly random

Performance: full pipeline 4 instruments x 5 TFs under 200ms (real-time budget).

---

## Implementation Phases

### Phase 2a (MASTER Phase 2)
1. Create src/technical/ structure
2. Migrate indicators.py; add tests
3. Migrate regime.py; make pure; add tests
4. Write loader.py — MultiTFDataset builder
5. Write confluence.py — full algorithm + tests
6. Write signal_builder.py — TechnicalSignal assembly
7. Write engine.py — subscribe to OHLCV_BAR; orchestrate
8. Milestone: TechnicalSignal emitted from fixture data

### Phase 2b
9. Migrate order_flow.py and causal.py
10. Wire causal filter into engine
11. Integration tests + performance test

---

## Known Risks

**Indicator NaN on short history.** EMA200 needs 200 bars minimum. Always check for NaN;
emit NEUTRAL with confidence=0.0 rather than pass NaN downstream.

**Multi-TF timing alignment.** Always fetch last CLOSED bar per TF, not current open bar.
Use DataStore.get_ohlcv(closed_only=True). Failing this introduces look-ahead bias.

**Confluence weight config drift.** Log the weight configuration in every TechnicalSignal
for retrospective analysis. Weights must not change mid-session silently.

**order_flow.py.** Requires tick/bid-ask data not available from yfinance.
Feature flag technical.order_flow.enabled: false by default.

**causal_validator.** Add D11 metric: "% indicators dropped by causal filter per session."
If > 50% are dropped, the data or validator config is wrong.
