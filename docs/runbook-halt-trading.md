# Runbook: Halt trading

## When to use

- Circuit breaker triggered.
- Suspected bug or misconfiguration.
- Exchange/broker outage or maintenance.
- Manual decision to stop risk.

## Steps

1. **Disable auto-trading** — Use the configured mechanism; ensure no new orders.
2. **Verify no new orders** — Check logs and broker dashboard.
3. **Close or hold positions** — Decide per strategy; document.
4. **Preserve state and logs** — Keep audit log for investigation.
5. **Investigate** — Review circuit breaker reason, recent signals.
6. **Resume only after sign-off** — Re-enable trading only after explicit approval.
