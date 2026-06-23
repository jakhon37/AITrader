---
name: new-signal-type
description: Use this skill when adding a new signal type to the platform, extending the signal contracts, adding a new field to an existing signal model, or creating a new event type that needs to flow through the signal bus.
---

# new-signal-type

Safely adds a new signal type or extends an existing signal model in Division 4 (`src/signals/contracts.py`). This is the highest-impact change in the codebase — every division depends on these contracts.

## Impact assessment (do this first)

Before touching `contracts.py`, answer:

1. **Is this truly a new signal type, or a new field on an existing type?**
   - New field on existing type → Section A below
   - New signal type entirely → Section B below

2. **Which divisions will consume the new type/field?**
   - List them — each needs handler updates

3. **Does Division 8 (model training) use this as a feature?**
   - If yes: adding a field to `TechnicalSignal` changes the feature vector → all trained models are invalid → retrain required

4. **Does Division 7 (notifications) format this type?**
   - If yes: add a formatter in `src/notifications/formatters.py`

5. **Does Division 10 (UI) display this?**
   - If yes: update TypeScript types in `frontend/src/types/signals.ts`

---

## Section A — Adding a field to an existing signal

### Step 1 — Add to contracts.py with a default value

**Always add new fields with defaults.** This keeps existing code that constructs the model from breaking.

```python
# src/signals/contracts.py

class TechnicalSignal(BaseModel):
    # ... existing fields ...
    
    # NEW FIELD — always provide default so existing construction still works
    new_field: float = 0.0
    # or for optional:
    new_field: str | None = None
```

### Step 2 — Populate the field in the producer

Find where the signal is constructed (e.g. `src/features/engine.py` for `TechnicalSignal`) and populate the new field.

### Step 3 — Update Division 7 formatter if signal is displayed

```python
# src/notifications/formatters.py
def format_technical(signal: TechnicalSignal) -> str:
    # ... existing lines ...
    # Add the new field to the message
    f"New metric: `{signal.new_field:.2f}`\n"
```

### Step 4 — Update TypeScript types

```typescript
// frontend/src/types/signals.ts
interface TechnicalSignal {
  // ... existing fields ...
  new_field: number;   // add with matching type
}
```

### Step 5 — Update tests

Add assertions for the new field in the signal producer's tests. Ensure existing tests still pass (they should if you used a default).

---

## Section B — Adding a completely new signal type

### Step 1 — Define the model in contracts.py

```python
# src/signals/contracts.py

class MyNewSignal(BaseModel):
    signal_id:   str
    timestamp:   datetime
    instrument:  Instrument          # always include instrument
    # ... your fields ...
    
    # Every signal needs confidence if it drives decisions
    confidence:  float = Field(ge=0.0, le=1.0)
```

**Required fields for any signal:** `signal_id`, `timestamp`. Strongly recommended: `instrument`, `confidence`.

### Step 2 — Export from contracts module

```python
# src/signals/__init__.py — add to exports
from signals.contracts import MyNewSignal
```

### Step 3 — Add signal_id prefix to utils.py

```python
# src/signals/utils.py
SIGNAL_PREFIXES = {
    "fundamental": "FA",
    "technical":   "TA",
    "trade":       "DE",
    "system":      "SY",
    "my_new":      "MN",    # ← add yours
}
```

### Step 4 — Update the bus type union

```python
# src/signals/bus.py

# Update the type alias
SignalType = FundamentalSignal | TechnicalSignal | TradeSignal | SystemEvent | MyNewSignal
```

### Step 5 — Wire the producer

In the division that creates this signal, publish via:
```python
await self.bus.publish(MyNewSignal(
    signal_id=make_signal_id("MN", instrument.value, self.clock.now()),
    timestamp=self.clock.now(),
    instrument=instrument,
    ...
))
```

### Step 6 — Add formatter in Division 7

```python
# src/notifications/formatters.py
def format_my_new(signal: MyNewSignal) -> str:
    return (
        f"🔔 *New Signal* — {signal.instrument.value}\n"
        f"..."
    )
```

And add subscription in `NotificationService.__init__()`:
```python
bus.subscribe(MyNewSignal, self.on_my_new)
```

### Step 7 — Add TypeScript type in Division 10

```typescript
// frontend/src/types/signals.ts
interface MyNewSignal {
  signal_id: string;
  timestamp: string;
  instrument: string;
  confidence: number;
  // ...
}

// Add to the union type
type AnySignal = FundamentalSignal | TechnicalSignal | TradeSignal | SystemEvent | MyNewSignal;
```

And update the WebSocket message handler in `frontend/src/hooks/useLiveSignals.ts` to handle `"MyNewSignal"` type.

### Step 8 — Write tests

```python
# tests/unit/test_contracts.py

def test_my_new_signal_valid():
    sig = MyNewSignal(
        signal_id="MN_EURUSD_123_abcd",
        timestamp=datetime.utcnow(),
        instrument=Instrument.EURUSD,
        confidence=0.75,
        # ...
    )
    assert sig.confidence == 0.75

def test_my_new_signal_confidence_bounds():
    with pytest.raises(ValidationError):
        MyNewSignal(..., confidence=1.5)   # > 1.0 must fail
```

---

## What NOT to do

- **Never remove a field** from an existing signal — it breaks all consumers. Mark as deprecated with `None` default first.
- **Never rename a field** — same reason. Add the new name alongside the old one, migrate, then remove old in a later commit.
- **Never add a required field without a default** to an existing signal — it breaks all existing construction sites.
- **Never define signal models outside `contracts.py`** — the one-file rule keeps the contract auditable.
