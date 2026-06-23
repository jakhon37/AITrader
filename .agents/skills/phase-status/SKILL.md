---
name: phase-status
description: Use this skill when the user asks what to work on next, what the current development phase is, which divisions are complete, what is blocking progress, how to get unstuck, or wants a project health summary.
---

# phase-status

Shows the current state of the platform build, what's complete, what's in progress, and what to work on next.

## Quick project overview

```bash
# Built-in overview script (existing in project)
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python3 scripts/project_overview.py
```

## Read division statuses

Each division MD file has a status line at the top. Check all at once:

```bash
# Show status of all divisions
grep -h "^Status:" \
  MASTER.md \
  DIVISION_1.md DIVISION_2.md DIVISION_3.md DIVISION_4.md \
  DIVISION_5.md DIVISION_6.md DIVISION_7.md DIVISION_8.md \
  DIVISION_9.md DIVISION_10.md DIVISION_11.md \
  2>/dev/null | nl
```

## Development sequence and gates

The mandatory build order (from MASTER.md):

```
Step 1:  Division 1 (D01-CORE)   ← MUST be first. Blocks everything.
Step 2:  Division 1   ← Blocks Division 2 (D02-DATA), 3, 8
Step 3a: Division 1 (D01-CORE) (D04-TECHNICAL)   ← Can parallel with 3b
Step 3b: Division 2 (D02-DATA)   ← Can parallel with 3a
Step 4:  Division 5   ← Needs signals from Div 2 and 3
Step 5:  Division 6   ← Blocks full replay in Div 9
--- After step 5, these are parallel ---
Step 6a: Division 7 (D07-NOTIFIER)   ← Can start after Div 4
Step 6b: Division 8   ← Can start after Div 1, 3
Step 6c: Division 9   ← Full after Div 6
Step 6d: Division 10  ← Backend after Div 4; full after Div 6
Step 6e: Division 11  ← Can start after Div 4
```

## Phase-by-phase milestones

### Milestone 1 — "Signal pipeline works"
All of Div 4 + Div 1 + Div 3 complete. You can:
- Generate `TechnicalSignal` from live price data
- See signals on the bus

Minimum viable test:
```bash
PYTHONPATH=src python -c "
import asyncio
from signals.bus import init_bus
from signals.clock import LiveClock
from config import AppConfig
# ... instantiate data gateway + technical engine
# publish an OHLCV_UPDATED event
# assert TechnicalSignal appears on bus
print('Signal pipeline: OK')
"
```

### Milestone 2 — "Full analysis pipeline works"
Div 2 complete. Both FA + TA signals fire. Decision engine (Div 5, v1 rule-based) produces `TradeSignal`. Telegram bot (Div 7) delivers it to your phone.

This is the first point where you can **watch the system think** about real markets in paper trading mode.

### Milestone 3 — "Paper trading works"
Div 6 complete. Full loop: signal → decision → order → position → SL/TP → close → audit log. Run paper trading for 2 weeks minimum before touching live.

### Milestone 4 — "Replay works"
Div 9 complete. Can replay historical periods. Can practice manual trading. Can validate signals visually.

### Milestone 5 — "Web UI replaces Streamlit"
Div 10 complete. Decommission `dashboards/`. Everything visible in the browser.

### Milestone 6 — "ML model in production"
Div 8 complete + model trained + promoted to prod. Decision engine now uses LSTM or XGBoost instead of rule-based fusion.

### Milestone 7 — "Live broker connected"
Div 6 live broker stub filled in. Go-live checklist passed. Real money trading.

## What to work on right now — decision tree

```
Is Division 1 (D01-CORE) COMPLETE?
  No → Work on Division 1 (D01-CORE). Nothing else can proceed.
  Yes → Continue...

Is Division 1 COMPLETE?
  No → Work on Division 1.
  Yes → Continue...

Are Divisions 2 AND 3 both COMPLETE?
  No → Work on whichever is not complete (can parallel)
  Yes → Continue...

Is Division 5 COMPLETE?
  No → Work on Division 5.
  Yes → Continue...

Is Division 6 COMPLETE?
  No → Work on Division 6.
  Yes → Everything else is parallel. Pick by priority:
    - Division 9 (replay) — highest learning value
    - Division 10 (web UI) — most visible improvement
    - Division 7 (D07-NOTIFIER) (Telegram) — simplest, highest daily value
    - Division 8 (ML training) — runs offline, can do anytime
    - Division 11 (monitoring) — do before going live
```

## Blocked? Common causes

| Symptom | Likely cause | Fix |
|---|---|---|
| Can't import from `signals.contracts` | Division 1 (D01-CORE) not installed | `pip install -e ".[dev]"` from project root |
| `CONFIG_DIR` errors | Missing env var | `export CONFIG_DIR=$(pwd)/config` |
| `BusNotInitializedError` | `init_bus()` not called before `get_bus()` | Call `init_bus()` at application startup in `main.py` |
| Data gateway returns 0 bars | No data downloaded | Run `data-backfill` skill |
| Tests fail with import errors | `PYTHONPATH` not set | `export PYTHONPATH=src` |
| mypy errors on torch/xgboost/arch | Missing stubs — expected | Add `# type: ignore` or use `--ignore-missing-imports` |
| FinBERT slow on CPU | Normal — 200-500ms per article | Expected; run in thread with `asyncio.to_thread()` |

## Update a division status

When a division passes its definition of done:

```bash
# Edit the division file's status line
sed -i 's/^Status: PLANNED/Status: COMPLETE/' DIVISION_4.md
sed -i 's/^Status: IN_PROGRESS/Status: COMPLETE/' DIVISION_4.md

# Or for blocked:
sed -i 's/^Status: PLANNED/Status: BLOCKED_BY: Division 1 (D01-CORE)/' DIVISION_5.md
```
