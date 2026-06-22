# D07 — NOTIFIER

## 1. Purpose & boundaries
Telegram bot integration: alert routing, rate limiting, message aggregation, and inbound
commands. **No analysis, no trading logic** — this division is purely a bus subscriber
plus an outbound/inbound channel. It is the reference implementation of the
observer/subscriber pattern: signal producers (D02/D03/D04/D05/D06) are completely
unmodified and unaware this division exists.

## 2. Dependencies
D01 only. Subscribes to bus topics from D02 (calendar events), D03 (fundamental
signals), D04 (technical signals), D05 (trade signals), D06 (fills) — **all via the bus,
never via direct import.** This is the hard rule from MASTER.md; it's what makes adding
Discord or email later a zero-touch change to every other division.

## 3. Emits / exposes
No outbound bus topics in v1. Inbound Telegram commands (`/status`, `/signals`, `/halt`,
`/portfolio`) are translated into either direct read calls (status/portfolio — read-only,
safe) or, for `/halt`, a published `notifier.command.halt` event that D06 subscribes to.
`/halt` is the only inbound command with a write effect — treat it with the same review
bar as anything else touching D06.

## 4. Internal module structure
```
src/notifier/
  telegram_bot.py       # bot lifecycle, auth (only responds to configured chat ID)
  rate_limiter.py          # caps at Telegram's 20 msg/min per-chat limit
  aggregator.py              # batches multiple signals within a window into one message
  formatters.py                # signal -> readable message text, sentiment-colored where relevant
  commands.py                    # /status, /signals, /halt, /portfolio handlers
```

## 5. Existing code to migrate
None. Build new.

## 6. Testing strategy
**Coverage target: 50%**.
- Rate limiter: confirm hard cap at 20 messages/minute to the same chat is never exceeded
  even under a burst of 50 signals in one second
- Aggregator: signals arriving within the aggregation window collapse into one message;
  signals outside the window do not
- Command parsing: malformed or unauthorized (wrong chat ID) commands are rejected without
  crashing the bot process
- `/halt` integration test: confirm it reaches D06 and is logged with full audit trail

## 7. Implementation phases (internal)
1. Outbound alerts + rate limiter — Phase 3, week 1
2. Message aggregation — Phase 3, week 1–2
3. Inbound commands (`/status`, `/signals`, `/halt`, `/portfolio`) — Phase 3, week 2–3

## 8. Known risks & gotchas
- **Telegram API downtime must never block trading.** All sends are fire-and-forget from
  the trading loop's perspective — if Telegram is unreachable, log it and move on, never
  let a failed send propagate back into D05 or D06.
- **Command auth** — only ever respond to the configured chat ID; this is a remote control
  surface into a live trading system and needs to be locked down from day one, not
  retrofitted later.
- **Message formatting limits** — Telegram caps messages at 4096 characters; the
  aggregator needs to split or truncate gracefully rather than fail silently on overflow.
- **Filter configuration** — decide per-signal-type and per-confidence-threshold filters
  early (you don't want every 15m technical update, just high-confidence and final
  decisions); make this configurable rather than hardcoded so it can be tuned without a deploy.
