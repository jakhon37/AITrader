# D07 — NOTIFIER

## 1. Purpose & boundaries
Pushes system notifications, alerts, and scorecard updates to developers. Receives commands
from Telegram to query system status.
**Does not generate signals** and **does not execute trades**. **Strictly isolated:** does not import
the codebases of `D03`, `D04`, `D05`, or `D06`. All updates are received via the `D01` signal bus.

## 2. Dependencies
D01 (contracts, bus, config, logging).
Pure bus subscription: subscribes to `signals.trade.*`, `execution.fill.*`, `signals.fundamental.*`, `signals.technical.*`, and `system.health.*` topics on the bus.

## 3. Emits / exposes
Exposes Telegram bot commands for status queries.
Nothing published back onto the signal bus.

## 4. Internal module structure
```
src/notifier/
  __init__.py
  telegram_bot.py # bot handler (listens to commands / sends notifications)
  aggregator.py   # message batching (prevents spamming during high volatility)
  formatter.py    # builds pretty markdown notifications and emojis
```

## 5. Existing code to migrate
None. This is a greenfield division.

## 6. Testing strategy
**Coverage target: 50%** (default gate).
- Integration: mock Telegram API client and verify messages format correctly.
- Aggregator: verify message grouping behaves as expected (batches rapid events).
- Architecture check: assert that running the notifier imports zero logic from execution/analysis packages.

## 7. Implementation phases (internal)
1. Telegram bot notification skeleton — Phase 3, week 1
2. Message formatter and aggregator — Phase 3, week 2
3. Inbound commands integration — Phase 3, week 2-3

## 8. Known risks & gotchas
- **Monorepo Separation Violations:** Telegram bots are prone to importing analysis modules directly to run diagnostic commands. To preserve architecture integrity, diagnostic commands must query `D02` data files or query status via the backend REST APIs, keeping dependency graphs strictly clean.
- **Telegram API Outages:** Slow responses from Telegram must never block signal processing. Implement outbound notifications on an isolated background worker queue.
