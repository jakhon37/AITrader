# D11 — OPS

## 1. Purpose & boundaries
System health, not trading performance: per-division health checks, signal bus latency
metrics, data freshness alerts, model drift monitoring, and structured log aggregation.
Answers "is the platform healthy" independent of "is the platform making money." **Never
intervenes in trading logic directly** — D06's circuit breaker handles trading-safety
halts on its own; OPS observes and alerts, it doesn't act on the trading path. The one
exception: OPS can publish system alerts that D07 forwards, distinctly formatted from
trade alerts so they're never confused for one another.

## 2. Dependencies
Read-only health endpoints from every other division (explicit exception to the
no-cross-import rule, since this division exists purely to observe). D01 for the
structured logging schema it aggregates against.

## 3. Emits / exposes
Bus topic: `ops.alert.{division}` — consumed by D07 for forwarding, formatted distinctly
from `signals.trade.*` and other trading alerts so a system failure notification is never
mistaken for a trade notification.

Direct API: health dashboard data (division status, bus latency, data freshness,
drift metrics) — could be surfaced in D10 as an admin panel if useful later, not required for v1.

## 4. Internal module structure
```
src/ops/
  health_checks.py       # per-division liveness/readiness checks
  metrics.py                # bus latency, message throughput, queue depth
  log_aggregator.py            # queries structured logs by signal_id, division, time range
  drift_monitor.py                # compares live model performance against staging baseline
```

## 5. Existing code to migrate
None. Build new.

## 6. Testing strategy
**Coverage target: 50%**.
- Health check failure simulation: kill/stub a division's health endpoint, confirm OPS
  detects and alerts within the expected window
- Drift monitor thresholds: feed synthetic performance degradation, confirm the alert
  fires at the configured threshold and not before

## 7. Implementation phases (internal)
1. Health checks + log aggregation — Phase 7, week 1
2. Bus latency and data freshness metrics — Phase 7, week 1–2
3. Model drift monitoring — Phase 7, week 2

## 8. Known risks & gotchas
- **Alert fatigue** — too many low-signal system alerts trains you to ignore them, which
  defeats the purpose. Tune thresholds deliberately and prefer aggregated/digest alerts
  over one-message-per-event for non-critical issues.
- **Distinguishing real failure from expected quiet periods** — markets close on
  weekends and holidays; a naive "no data in N minutes" check will false-positive every
  Friday night. Build market-hours awareness into the freshness checks from the start,
  not as a later patch.
- **This division is the last one built (Phase 7)**, which means the first six phases
  run without it. Keep manual log-checking habits during that window rather than assuming
  silence means health.
