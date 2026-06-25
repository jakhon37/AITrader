# D07 — NOTIFIER

## Purpose
External notification routing. Subscribes to bus channels and forwards high-value
events to Telegram. Handles inbound Telegram commands as a remote control interface.
Extensible to Discord, email, and webhooks without modifying any other division.

Does NOT: produce signals, execute trades, or modify system state directly.
All state changes from inbound commands go through the bus or appropriate division API.

---

## Dependencies
- D01-CORE: contracts, bus, clock, config, logging only

D07 never imports from D03, D04, D05, or D06 directly.

---

## Emits
Nothing onto the signal bus. Side effects only (HTTP calls to Telegram API).

---

## Internal Module Structure

```
src/notifier/
  __init__.py
  service.py      <- main entry; subscribes to bus; routes to formatters + sender
  telegram.py     <- Telegram Bot API client; rate limiter; inbound polling
  formatters.py   <- per-event-type message formatters; Telegram HTML format
  aggregator.py   <- batches high-frequency signals; prevents message flooding
  commands.py     <- inbound command handler
  router.py       <- maps BusChannel events to send decision (filter logic)
```

### telegram.py
Uses python-telegram-bot or direct httpx calls.

Outbound rate limiter: token bucket, 20 tokens max, refill 1/3s.
Queue overflow (50 items max): oldest messages dropped; D11 records telegram_overflow metric.
Error handling: network errors retry 3x exponential; 429 respects retry_after header.
Inbound: long-polling /getUpdates every 2 seconds; offset tracked by library.

### formatters.py
All messages use Telegram HTML formatting. Signal alerts under 280 chars.

TradeSignal format:
```
[LONG/SHORT emoji] LONG XAUUSD — STRONG (87%)
[chart emoji] Technical: RSI oversold 1H+4H, trending regime
[news emoji] Fundamental: Bearish USD post CPI miss
[bolt emoji] Entry: 2341.50 | SL: 2318.00 | TP: 2379.00
[clock emoji] Valid until: 16:00 UTC
```

OrderEvent (fill): instrument, side, size, fill price, SL/TP, signal_id (last 8 chars).
SystemHealth (DEGRADED/DOWN): division name, message, timestamp.

### aggregator.py
Per-instrument batching window: 60 seconds for TechnicalSignal (not enabled by default).
TradeSignals: NEVER batched; always sent immediately.
FundamentalSignals: at most 1 per instrument per 5 minutes.
SystemHealth: at most 1 DEGRADED alert per division per 10 minutes.

### commands.py
All commands are read-only or confirmed-action. No direct state mutation.

| Command | Response |
|---|---|
| /status | All division health, execution mode, open positions count |
| /portfolio | Balance, equity, open positions, today P&L |
| /signals [N or instrument] | Last N trade signals; default 5 |
| /fundamental [instrument] | Last fundamental signal |
| /halt | Confirmation prompt -> on CONFIRM: publishes halt event to bus |
| /resume | Confirmation prompt -> on CONFIRM: publishes resume event |
| /help | Lists available commands |

Security: verifies update.message.from_user.id in ALLOWED_TELEGRAM_USER_IDS.
Silently ignores commands from unknown IDs.
/halt and /resume require reply "CONFIRM" within 30 seconds.

### router.py
Per-channel filters configured in YAML:
```yaml
notifier:
  telegram:
    trade_signal:
      enabled: true
      min_confidence: 0.5
      directions: [long, short]
    fundamental_signal:
      enabled: true
      min_strength: strong
    technical_signal:
      enabled: false     # too noisy; opt-in only
    order_event:
      enabled: true
      event_types: [filled, rejected]
    system_health:
      enabled: true
      min_status: degraded
    quiet_hours:
      start: "22:00"     # UTC
      end: "06:00"
      override_for: [system_health, order_event]
```

---

## Environment Variables Required
```
TELEGRAM_BOT_TOKEN           # BotFather token; never log this
TELEGRAM_CHAT_ID             # comma-separated list supported for multiple chats; treat as secret
ALLOWED_TELEGRAM_USER_IDS    # comma-separated Telegram user IDs
```

---

## Testing Strategy
Coverage target: 60%.

Unit:
- formatters.py: each event type -> valid HTML string; length < 4096; no KeyError on optional fields
- aggregator.py: 3 TechnicalSignals in 60s -> 1 batched; TradeSignal -> immediate
- router.py: each filter condition; quiet hours edge cases
- commands.py: known user -> correct response; unknown user -> ignored; /halt without CONFIRM -> rejected
- telegram.py: mock HTTP; 21st message in 1 min -> queued; 429 -> respects retry_after

Integration:
- Bus -> Telegram pipeline: mock TradeSignal published -> send called once with correct text
- Flood test: 30 events in 1 second -> rate limiter queues correctly

---

## Implementation Phases

### Phase 3b (MASTER Phase 3, parallel with D03)
1. Write telegram.py — send only + rate limiter
2. Write formatters.py — all event types
3. Write router.py — filter logic + YAML config
4. Write aggregator.py
5. Write service.py — subscribe to TRADE_SIGNAL and ORDER_EVENT first
6. Milestone: Telegram message received when mock TradeSignal published

### Phase 3c
7. Write commands.py — read-only commands first
8. Add /halt and /resume with confirmation
9. Subscribe to FUNDAMENTAL_SIGNAL and SYSTEM_HEALTH
10. Integration tests

### Future
11. discord.py alongside telegram.py; add to router
12. email.py — weekly performance digest
13. webhook.py — generic POST for external integrations

---

## Known Risks

**Token in logs.** Add log filter in logging.py that redacts TELEGRAM_BOT_TOKEN pattern.
Never log TELEGRAM_CHAT_ID either. Treat both as secrets.

**Rate limiter queue overflow.** If queue of 50 fills, oldest messages are dropped.
This is acceptable — Telegram is informational, not critical. Audit log in D06 is truth.
Document this clearly.

**Command injection via /halt.** A compromised account can halt trading. This is intentional.
Ensure RESUME also requires CONFIRM so accidental resume doesn't happen.
All command events logged to audit.

**Long-polling reliability.** Use python-telegram-bot ApplicationBuilder which handles
offset tracking. Do not implement raw polling from scratch — offset tracking bugs
cause duplicate or missing updates.
