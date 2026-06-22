# D05 — DECISION

## Purpose
Signal fusion engine. Subscribes to FundamentalSignal and TechnicalSignal,
validates signal freshness, combines them into a TradeSignal, applies position
sizing, and publishes the result. Manages active signal state per instrument.

Does NOT: fetch data, run indicators, execute orders, notify external services,
or train models. Reads two signal types and emits one.

---

## Dependencies
- D01-CORE: contracts, bus, clock, config, logging
- D03-FUNDAMENTAL: via bus subscription only (no direct import)
- D04-TECHNICAL: via bus subscription only (no direct import)
- D09-TRAINER: **artifact-only dependency.** Reads `data/models/registry.json`
  (ModelArtifact, per CONTRACTS.md) directly off disk to select the active prod model
  for fusion v2. D05 never imports D09 code and has no runtime/process dependency on it —
  D09 runs offline and writes the registry file; D05 only ever reads it. This is the
  one division dependency in D05 that isn't a bus subscription, because the registry
  is file-based by design (see CONTRACTS.md's Model Registry Artifact section).

---

## Emits
| Channel | Type | When |
|---|---|---|
| BusChannel.TRADE_SIGNAL | TradeSignal | After each fusion cycle; also NEUTRAL to cancel a prior signal |

---

## Internal Module Structure

```
src/decision/
  __init__.py
  engine.py      <- subscribes to F+T signals; orchestrates fusion pipeline
  state.py       <- per-instrument signal state: last valid F signal, last valid T signal
  expiry.py      <- checks valid_until vs VirtualClock.now(); linear confidence decay
  fusion.py      <- weighted combiner v1; model-based fusion v2 (after D09)
  sizer.py       <- position size suggestion: ATR + equity + risk%
  narrator.py    <- builds narrative string; uses FundamentalSignal.narrative or template
```

### engine.py
Two subscriptions:
- BusChannel.FUNDAMENTAL_SIGNAL -> updates state.fundamental[instrument]
- BusChannel.TECHNICAL_SIGNAL -> updates state.technical[instrument]; triggers fusion
- BusChannel.PORTFOLIO_UPDATE -> cached locally for sizer.py equity reference

Fusion triggered by TechnicalSignal (the more frequent). FundamentalSignal updates
state but doesn't trigger fusion alone — picked up on the next TechnicalSignal.

On each TechnicalSignal:
1. Load state for instrument: (f_signal, t_signal)
2. expiry.check(f_signal) -> if expired treat as None
3. fusion.combine(f_signal, t_signal, config) -> FusionOutput
4. If now NEUTRAL and prior was directional: emit NEUTRAL TradeSignal (cancellation)
5. sizer.compute(fusion, config, portfolio_cache) -> suggested_size
6. narrator.build(fusion, f_signal, t_signal) -> narrative
7. Build and publish TradeSignal

### expiry.py
```python
def is_valid(signal, clock) -> bool:
    return clock.now() < signal.valid_until

def effective_confidence(signal: FundamentalSignal, clock) -> float:
    # linear decay: 0% confidence at valid_until, 100% at timestamp
    total = (signal.valid_until - signal.timestamp).total_seconds()
    remaining = (signal.valid_until - clock.now()).total_seconds()
    return signal.confidence * max(0.0, remaining / total)
```

### fusion.py — Version 1 (weighted combiner)

```python
def combine(f, t, config, clock) -> FusionOutput:
    t_score = t.confidence * direction_sign(t.direction)

    if f is not None and is_valid(f, clock):
        f_conf = effective_confidence(f, clock)
        f_score = f_conf * direction_sign(f.direction)
        raw = config.fundamental_weight * f_score + config.technical_weight * t_score
    else:
        raw = t_score  # full weight to technical when no valid fundamental

    direction = LONG if raw > 0.15 else SHORT if raw < -0.15 else NEUTRAL
    confidence = min(abs(raw), 1.0)
    return FusionOutput(direction=direction, confidence=confidence, ...)
```

Version 2 (after D09 trains model): same interface, loads model from registry,
runs inference. Weighted combiner remains available via config flag:
decision.fusion_mode: "weighted" | "model"

Staged rollout: model runs in shadow mode (logs predictions, doesn't publish)
for 2 weeks before becoming primary.

### sizer.py
Fixed fractional risk:
```
risk_per_trade = equity * risk_pct_per_trade  (default 1%)
stop_distance  = abs(entry_price - suggested_sl)
pip_value      = instrument_config.pip_size * lot_size
size_lots      = risk_per_trade / (stop_distance / pip_value)
size_lots      = min(size_lots, instrument_config.max_position_lots)
```
D06 may override after its own risk checks. suggested_size is a recommendation.

### narrator.py
Builds narrative under 280 chars for Telegram compatibility.
1. If f_signal.narrative is set -> use it as the fundamental part
2. Else if f_signal exists -> template: "Fundamental: {direction} bias from {event_type}"
3. Technical part: top-2 confirming indicators from per_timeframe
4. Combined sentence with instrument name and direction

---

## Existing Code to Migrate
No existing decision/fusion code. Entirely new.
src/models/ensemble.py: review for logic to inform fusion.py v2.
src/models/meta_labeler.py: candidate for the v2 model in fusion.py.

---

## Testing Strategy
Coverage target: 70%.

Unit:
- expiry.py: valid signal -> True; just-expired -> False; linear decay math
- fusion.py: both LONG -> LONG high confidence; F=LONG T=SHORT -> low confidence;
  F=None -> full weight to T; F expired -> treated as None; NEUTRAL threshold boundary
- sizer.py: known equity + risk_pct + stop -> expected lots; max_lots cap
- narrator.py: with/without fundamental; assert length < 280

Integration:
- Bus round-trip: mock F+T signals published -> TradeSignal received
- Signal cancellation: prior LONG -> NEUTRAL TechnicalSignal -> NEUTRAL TradeSignal emitted

---

## Implementation Phases

### Phase 4a (MASTER Phase 4)
1. Write state.py, expiry.py
2. Write fusion.py — weighted combiner
3. Write sizer.py, narrator.py
4. Write engine.py — subscribe to both channels + PORTFOLIO_UPDATE
5. Integration tests
6. Milestone: TradeSignal emitted from mock F+T inputs

### Phase 4b
7. Wire into full paper trading loop with D06
8. Log fusion_mode, weights used, F signal availability per trade
9. Tune NEUTRAL threshold if signals are too noisy or sparse

### Phase 6 (model fusion, after D09)
10. Add model inference path in fusion.py
11. Add decision.fusion_mode config flag
12. Shadow mode rollout: 2 weeks observation before going live

---

## Known Risks

**No FundamentalSignal most of the time.** Most TechnicalSignal events arrive with f=None.
The combiner must handle this gracefully. Don't penalize confidence for missing fundamental.

**Signal timing mismatch.** F and T signals are produced on different cadences.
State store holds last valid F until expiry. This is correct behavior — don't "fix" it.
Document clearly in code so future devs don't break it trying to synchronize them.

**Confidence inflation.** If F and T both agree with high confidence, fused confidence
near 1.0 routinely makes STRONG threshold meaningless. Add D11 histogram check:
if > 30% of fused values exceed 0.8 over one month, weights need tuning.

**Portfolio state for sizer.** Engine subscribes to PORTFOLIO_UPDATE and caches last state.
If portfolio cache is None (startup), use a default equity from config as fallback.
Never block signal emission waiting for portfolio state.
