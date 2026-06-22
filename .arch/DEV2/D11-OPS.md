# D11 — OPS

## Purpose
Observability, health monitoring, and operational tooling. Aggregates structured logs
from all divisions, tracks system-level metrics (bus latency, data freshness, model
inference time), runs health probes against each division, and alerts on failures.
Tells you whether the platform is healthy independent of whether trades are profitable.

Does NOT: produce trading signals, execute orders, or modify system behavior.
Read-only access. Passive monitoring only.

---

## Dependencies
- D01-CORE: contracts (SystemHealthEvent), bus (subscribe to BusChannel.SYSTEM_HEALTH), logging
- All other divisions: read-only health HTTP endpoints exposed by each division
- D02-DATA: read access to logs/ directory for log aggregation

---

## Emits
Nothing onto the signal bus. Alerts are sent via D07-NOTIFIER (via bus subscription
in D07 — D11 publishes SystemHealthEvent; D07 picks it up and sends Telegram).

Wait — correction: D11 publishes SystemHealthEvent onto BusChannel.SYSTEM_HEALTH.
D07 already subscribes to this channel. D11 does NOT call D07 directly.

---

## Internal Module Structure

```
src/ops/
  __init__.py
  monitor.py        <- main loop; runs all health probes on schedule; aggregates metrics
  probes/
    __init__.py
    bus_probe.py    <- measures bus queue depth and publish latency
    data_probe.py   <- checks data freshness: last bar age per instrument/TF
    signal_probe.py <- checks signal flow: last F/T/Trade signal timestamps
    model_probe.py  <- checks D09 model registry: prod model age, recent performance
    exec_probe.py   <- checks D06: daily P&L, drawdown, circuit breaker state
    system_probe.py <- CPU, memory, disk usage; audit log disk size
  metrics.py        <- in-memory metric store; rolling windows; histogram support
  log_aggregator.py <- tails all logs/audit_{date}.jsonl files; indexes by signal_id
  api.py            <- lightweight HTTP server (FastAPI or Flask) for D10 health route
  alerts.py         <- threshold checks; publishes SystemHealthEvent to bus on breach
```

### monitor.py
Runs all probes on a configurable schedule:
- Every 30 seconds: bus_probe, data_probe, signal_probe
- Every 5 minutes: exec_probe, model_probe, system_probe
- Every hour: log_aggregator scan

On each probe run: collect metrics -> alerts.check_thresholds() ->
if breach: publish SystemHealthEvent(DEGRADED or DOWN) to bus.

### Probe Details

**bus_probe.py:**
Measures publish-to-receive latency by publishing a synthetic "ping" event
and measuring time until a subscriber receives it.
Metrics: p50/p95/p99 latency; queue depth per channel.
Alert: p99 latency > 500ms -> DEGRADED; > 2000ms -> DOWN.

**data_probe.py:**
Checks age of last received OHLCVBar for each active (instrument, timeframe) pair.
Expected freshness: within 2 candle periods (e.g., H1 bar should arrive every 60 min;
alert if last bar is > 90 minutes old during market hours).
Session hours awareness: don't alert on stale data when the market is closed.
Alert: bar more than 2x candle period old during session -> DEGRADED.

**signal_probe.py:**
Checks timestamp of last TechnicalSignal per instrument per primary TF.
Checks timestamp of last FundamentalSignal per instrument.
Alert if technical signals stop flowing during an active trading session.
Does NOT alert on missing fundamental signals (they're event-driven, not periodic).

**model_probe.py:**
Reads model registry. Checks:
- Is there a prod model? (DEGRADED if none after Phase 6)
- When was prod model trained? Alert if > 60 days old.
- Shadow model metrics (if staging model running): Sharpe vs prod.
- Consecutive loss count (triggers rollback threshold monitoring).

**exec_probe.py:**
Reads D06 audit log (not live bus — uses log_aggregator for historical reads).
Checks: daily P&L vs daily loss limit (% used); drawdown; circuit breaker state.
Alert: drawdown > 10% -> DEGRADED; > 15% -> DOWN (already handled by circuit breaker,
but D11 provides an independent check).

**system_probe.py:**
CPU usage > 90% for 5 min -> DEGRADED.
Memory > 85% -> DEGRADED.
Disk usage for data/ and logs/ > 80% -> DEGRADED.
Audit log file size > 1GB per day -> DEGRADED.

### metrics.py
In-memory rolling metric store. Retains last 24 hours at 30-second resolution.
Supports: counter, gauge, histogram (percentile calculation).
Exposed via D11 API endpoint for D10-WEBUI health panel.

```python
class MetricsStore:
    def record(self, name: str, value: float, labels: dict = {}) -> None: ...
    def gauge(self, name: str, labels: dict = {}) -> float | None: ...
    def histogram_pct(self, name: str, pct: float, labels: dict = {}) -> float | None: ...
```

No external metrics infrastructure needed for v1 (no Prometheus/Grafana dependency).
Plan to add Prometheus exporter in a future iteration if needed.

### log_aggregator.py
Tails logs/audit_{date}.jsonl files. Builds an in-memory index keyed by signal_id.
Enables queries like: "show me all log lines related to signal abc-123"
(from news fetch -> FundamentalSignal -> TradeSignal -> order fill).

```python
class LogAggregator:
    def tail(self, path: str) -> None: ...    # background task
    def query_signal(self, signal_id: str) -> list[dict]: ...
    def recent_errors(self, division: str, last_n_minutes: int) -> list[dict]: ...
```

### api.py
Lightweight FastAPI app (can share the D10 FastAPI process or run standalone).
Endpoints:
- GET /ops/health -> summary of all division health statuses
- GET /ops/metrics -> current metric snapshot
- GET /ops/signal/{signal_id} -> full log trace for a signal_id
- GET /ops/alerts -> last 50 alerts with timestamps

D10-WEBUI calls GET /ops/health via its routes/health.py proxy.

### alerts.py
Threshold configuration in ops.yaml:

```yaml
ops:
  alerts:
    bus_latency_p99_ms: 500      # DEGRADED threshold
    data_freshness_multiplier: 2 # candle periods before alert
    daily_drawdown_pct: 10       # DEGRADED
    memory_pct: 85
    disk_pct: 80
    audit_log_gb_per_day: 1.0
  alert_cooldown_minutes: 10     # same division+status won't re-alert within this window
```

---

## Environment Variables Required
None beyond D01 standard config. D11 is purely internal monitoring.

---

## Testing Strategy
Coverage target: 55%.

Unit:
- metrics.py: record + gauge + histogram_pct; rolling window eviction
- alerts.py: threshold breach -> SystemHealthEvent published; cooldown dedup
- data_probe.py: mock last bar timestamp; within/outside session hours; alert conditions
- log_aggregator.py: fixture audit log -> query_signal returns all matching lines

Integration:
- Full probe cycle: run monitor.py for 60 seconds against running paper trading session;
  verify all probes return OK status
- Alert flow: set data freshness threshold to 1 second; verify SystemHealthEvent appears
  on bus within probe interval; verify D07 receives it (in integration test with D07)

---

## Implementation Phases

### Phase 7 (MASTER Phase 7)
1. Write metrics.py
2. Write probes/ — bus_probe, data_probe, system_probe first (simplest)
3. Write monitor.py — scheduling + probe runner
4. Write alerts.py — threshold checks + SystemHealthEvent publishing
5. Write api.py — health + metrics endpoints
6. Wire D10 health route to call /ops/health
7. Milestone: division health visible in D10 browser UI

### Phase 7b
8. Write log_aggregator.py — signal_id trace query
9. Write signal_probe.py, exec_probe.py, model_probe.py
10. Add signal trace endpoint to D10 UI (click on a signal -> see full lifecycle log)
11. Milestone: any division failure triggers Telegram alert via D07

### Phase 7c (RedisBus swap)
12. Swap InProcessBus to RedisBus (one config line change: core.bus_backend: redis)
13. Run full integration test suite against RedisBus
14. Add bus_probe Redis-specific metrics (connection pool depth, subscriber count)
15. Milestone: multi-process deployment works; D08/D09 run in separate processes

---

## Known Risks

**D11 must not be a bottleneck.** All probe operations must be non-blocking and have
timeouts. A slow health probe must not delay the monitor loop. Use asyncio.wait_for()
with a 5-second timeout on every probe call.

**Log aggregator memory.** If audit logs are large (1GB+/day at high frequency),
the in-memory index could consume significant RAM. Index only the signal_id and log
file offset, not the full log content. Fetch content on demand.

**Alert fatigue.** If alert thresholds are too sensitive, Telegram fills with noise
and real alerts get ignored. Start with conservative thresholds; tighten over time.
Alert cooldown (10 minutes per division+status) is essential from day one.

**Self-monitoring paradox.** D11 monitors the bus, but D11 publishes alerts to the bus.
If the bus itself is DOWN, D11 cannot publish the alert. Mitigation: D11 has a secondary
alert path that writes directly to a file (logs/ops_alerts.jsonl) even when bus is unavailable.
D07 can optionally poll this file if bus alerts are not received for N minutes.

**Probe security.** D11 reads D06 audit logs directly (file system access).
This is acceptable in single-machine deployment. In distributed deployment (Phase 7+),
D06 would need to expose a read-only HTTP endpoint for audit log access instead.
Plan for this transition in the Phase 7 distributed design.
