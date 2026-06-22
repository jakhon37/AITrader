# D11 — OPS

## 1. Purpose & boundaries
Observability, health monitoring, metrics, and alerting for the entire platform. Aggregates logs, monitors system performance, tracks model drift, and manages alarms.
**Read-only observer status.** Does not perform business logic, execute trades, or route signals. Zero divisions depend on OPS (no division imports from D11).

## 2. Dependencies
All divisions (observes health checks, latency, and log feeds). This is a declared exception to the import rule since it is read-only.

## 3. Emits / exposes
- Prometheus/Grafana metric endpoints.
- Outbound slack/pager alerts for degraded health.

## 4. Internal module structure
```
src/ops/
  __init__.py
  monitor.py    # health checks aggregator (queries health.py routes)
  metrics.py    # platform execution metrics (latency, data freshness)
  alerts.py     # routes alarms to Telegram/Slack
  drift.py      # tracks model prediction drift over time
```

## 5. Existing code to migrate
None. Greenfield division.

## 6. Testing strategy
**Coverage target: 50%**.
- Health check aggregator: test mock division failures trigger alerts correctly.
- Metric calculation: test that latency calculations are correct.

## 7. Implementation phases (internal)
1. Prometheus metric endpoint setup — Phase 7, week 1
2. Health check daemon — Phase 7, week 1-2
3. Model drift alarm triggers — Phase 7, week 2

## 8. Known risks & gotchas
- **OPS Alert Spams:** High market volatility can trigger transient latency warnings. Alert routing must use rate limiters to batch alarms and prevent notification fatigue.
