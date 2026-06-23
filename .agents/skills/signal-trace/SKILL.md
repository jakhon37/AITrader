---
name: signal-trace
description: Use this skill when debugging why a trade did or did not happen, tracing a signal_id through the audit log, understanding the lifecycle of a specific signal, investigating a missed trade, or diagnosing why a signal was rejected or suppressed.
---

# signal-trace

Traces any signal by its `signal_id` through the full system: from creation through bus delivery, decision engine evaluation, and final execution or rejection. All evidence is in the structured logs and audit log.

## Signal ID format

```
{PREFIX}_{INSTRUMENT}_{TIMESTAMP_MS}_{SHORT_UUID}

Examples:
FA_EURUSD_1705276800000_a3f2    ← FundamentalSignal
TA_XAUUSD_1705276812000_b7c1    ← TechnicalSignal
DE_EURUSD_1705276815000_d4e9    ← TradeSignal (Decision Engine)
MANUAL_EURUSD_1705276820000_f2a1 ← Manual replay trade
```

Prefix key: `FA` = Fundamental, `TA` = Technical, `DE` = Decision/Trade, `SY` = System, `MN` = Manual

## Step 1 — Find the signal in the logs

Logs are NDJSON (one JSON object per line). Use `grep` or `jq`:

```bash
# Find any log line containing a signal_id
grep "FA_EURUSD_1705276800000_a3f2" data/logs/platform.log

# Pretty print all events for a signal
grep "FA_EURUSD_1705276800000_a3f2" data/logs/platform.log | jq '.'

# Find all signals for an instrument in a time window
jq 'select(.instrument == "EURUSD" and .timestamp >= "2024-01-15T10:00:00")' data/logs/platform.log

# Find all REJECTED trade signals
jq 'select(.message == "SIGNAL_REJECTED_RISK" or .message == "SIGNAL_REJECTED_CONFIDENCE")' data/logs/platform.log
```

## Step 2 — Check the audit log (for trade signals)

The audit log (`data/audit/audit.log`) records every TradeSignal the execution engine received, regardless of outcome:

```bash
# Find a specific TradeSignal in audit
grep "DE_EURUSD_1705276815000_d4e9" data/audit/audit.log | jq '.'

# Find all rejected orders
jq 'select(.event == "ORDER_REJECTED")' data/audit/audit.log

# Find all fills for an instrument today
jq 'select(.event == "ORDER_FILLED" and .instrument == "EURUSD")' data/audit/audit.log

# List all events for a position
jq 'select(.position_id == "pos_abc123")' data/audit/audit.log
```

## Step 3 — Trace the full signal lifecycle

A complete trace for a trade that was expected but didn't happen:

```bash
SIGNAL_TIME="2024-01-15T10:30:00"
INSTRUMENT="EURUSD"

echo "=== 1. Fundamental signals around the time ==="
jq --arg t "$SIGNAL_TIME" --arg i "$INSTRUMENT" \
  'select(.type == "FundamentalSignal" and .instrument == $i and .timestamp >= $t)' \
  data/logs/platform.log | head -5

echo "=== 2. Technical signals ==="
jq --arg t "$SIGNAL_TIME" --arg i "$INSTRUMENT" \
  'select(.type == "TechnicalSignal" and .instrument == $i and .timestamp >= $t)' \
  data/logs/platform.log | head -5

echo "=== 3. Decision engine evaluation ==="
jq --arg t "$SIGNAL_TIME" --arg i "$INSTRUMENT" \
  'select(.division == "decision" and .instrument == $i and .timestamp >= $t)' \
  data/logs/platform.log

echo "=== 4. Audit log — any trade signals ==="
jq --arg t "$SIGNAL_TIME" --arg i "$INSTRUMENT" \
  'select(.instrument == $i and .timestamp >= $t)' \
  data/audit/audit.log
```

## Common rejection reasons and fixes

| Rejection message | Cause | Fix |
|---|---|---|
| `Direction is NEUTRAL` | Fused direction is neither bullish nor bearish | Check if FA and TA are in disagreement (disagreement penalty applied) |
| `Confidence X.XX below threshold 0.65` | Fused confidence too low | Check individual signal confidences; confluence score may be low |
| `In news blackout period` | Division 2 (D02-DATA) declared blackout | Expected — major news event is imminent |
| `Minimum time between trades not elapsed` | Cooldown (1h) not passed since last trade | Normal risk management |
| `Daily trade limit reached` | 5 trades/day/instrument cap hit | Normal risk management — review config if limit is too low |
| `Already have open position in instrument` | Execution engine blocks duplicate positions | Close existing position first |
| `Signal state not ready` | Only one of FA/TA has fired, not both | Check if the other pillar is running and healthy |
| `Signal is stale` | One signal is > 4 hours old | Check if news fetcher or OHLCV scheduler is still running |

## Diagnosing a missed trade — checklist

Run through in order:

```bash
# 1. Is the system running? (check heartbeats)
curl http://localhost:8000/health | jq '.divisions'

# 2. Did FA signal fire?
jq 'select(.type == "FundamentalSignal" and .instrument == "EURUSD")' data/logs/platform.log | tail -3

# 3. Did TA signal fire?
jq 'select(.type == "TechnicalSignal" and .instrument == "EURUSD")' data/logs/platform.log | tail -3

# 4. Was there a blackout?
jq 'select(.message == "NEWS_BLACKOUT_START" and .metadata.instrument == "EURUSD")' data/logs/platform.log | tail -3

# 5. Did the decision engine evaluate?
jq 'select(.division == "decision" and .message | test("EURUSD"))' data/logs/platform.log | tail -5

# 6. Did a TradeSignal reach the execution engine?
jq 'select(.division == "execution")' data/audit/audit.log | tail -5

# 7. What was the rejection reason?
jq 'select(.event == "SIGNAL_REJECTED" and .instrument == "EURUSD")' data/audit/audit.log | tail -3
```

## Tracing in replay mode

In replay mode, the same logs are written but prefixed with `[REPLAY]` in the `metadata.mode` field:

```bash
jq 'select(.metadata.mode == "replay")' data/logs/platform.log | tail -20
```

## Programmatic trace (Python)

```python
# Quick script to trace all events for a signal_id
import json

signal_id = "DE_EURUSD_1705276815000_d4e9"

for log_file in ["data/logs/platform.log", "data/audit/audit.log"]:
    with open(log_file) as f:
        for line in f:
            try:
                record = json.loads(line)
                if signal_id in json.dumps(record):
                    print(f"[{record.get('level', '?')}] {record.get('division', '?')}: {record.get('message', '?')}")
                    print(f"  {record}")
            except json.JSONDecodeError:
                pass
```
