# Trading Platform — Project Guide Improvements

**Purpose:** Gaps and recommendations to bring **Forex-Gold-AI-Trading-Plan-2025** up to **industrial-standard** project quality.  
**Audience:** New trading platform build; use this alongside the main plan.

---

## 1. Project & Repository Structure

**Current state:** Plan shows `data/`, `features/`, `models/` and script names but not a full repo layout.

**Improvements:**

- **Define a clear monorepo (or multi-repo) layout**, for example:

```
trading-platform/
├── .github/
│   └── workflows/          # CI/CD
├── config/
│   ├── dev.yaml
│   ├── staging.yaml
│   └── prod.yaml
├── src/
│   ├── data/               # Ingestion, validation, storage
│   ├── features/           # Feature engineering
│   ├── models/             # Model definitions & training
│   ├── execution/          # Execution engine, risk, broker adapters
│   ├── backtest/           # CPCV, walk-forward, backtrader glue
│   └── api/                # Optional: REST/gRPC for signals/control
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/                # Paper-trading / sim runs
├── scripts/                # One-off, migrations, retrain
├── docs/                   # ADRs, runbooks, API docs
├── docker/
├── k8s/                    # K8s manifests
├── pyproject.toml          # Single source of truth for deps & tooling
└── README.md
```

- **Add:** `.env.example` (no secrets), `.gitignore` for data/checkpoints/secrets, and a short **README** with: how to run tests, backtest, and paper/live.

---

## 2. Testing Strategy

**Current state:** No explicit testing strategy; only "evaluation" (CPCV, walk-forward) is described.

**Improvements:**

- **Unit tests:** Feature calculators, risk/position sizing, parsers and validators.
- **Integration tests:** Data pipeline (no leakage), model I/O, execution path with mock broker.
- **E2E / simulation:** Deterministic backtest run; optional short paper-trading run in CI.
- **Add to guide:** Minimum coverage target (e.g. 80% for `src/`). Where test data lives (`tests/fixtures/`).

---

## 3. CI/CD

**Current state:** Not covered.

**Improvements:**

- **CI (every PR / push):** Lint (ruff, mypy), format check, unit + integration tests, build Docker image(s). No secrets in logs.
- **CD:** Separate pipelines for dev → staging → prod. Staging: deploy and run short backtest/paper. Prod: deploy from tagged release; manual approval.
- **Add to guide:** One-page "CI/CD" section; broker keys only in vault (e.g. GitHub Secrets), never in repo.

---

## 4. Configuration & Environment

**Current state:** Broker API key example in K8s only; no env-specific or validated config.

**Improvements:**

- **Single config schema** (e.g. Pydantic): data, models, risk, execution. Validation at startup.
- **Environment-specific files:** `config/dev.yaml`, `config/prod.yaml`; secrets never in config.
- **Add to guide:** "Configuration" subsection: schema, env split, "no secrets in config files".

---

## 5. Security & Secrets

**Current state:** K8s `secretKeyRef` for broker key is mentioned; no broader security policy.

**Improvements:**

- **Secrets:** All in vault or cloud secret manager; inject at runtime. No secrets in code, config repo, or CI logs.
- **Least privilege:** Broker API keys with minimal scope; service accounts with minimal permissions.
- **Audit:** Log all trade-related actions (signal, order, fill, cancel) with timestamp, symbol, size, outcome.
- **Add to guide:** Short "Security & secrets" section.

---

## 6. Observability & Operations

**Current state:** Prometheus/Grafana mentioned; no logging/tracing or runbooks.

**Improvements:**

- **Structured logging (JSON):** Correlation ID, log level, component. No PII/secrets.
- **Tracing:** Trace ID across data → features → models → execution.
- **Metrics:** P&L, drawdown, latency, circuit_breaker_triggered, order_rejected.
- **Alerting:** Each alert must have a **runbook**: what it means, how to verify, what to do.
- **Add to guide:** "Observability" subsection.

---

## 7. Documentation

**Current state:** Plan is the main doc; no API, runbooks, or ADRs.

**Improvements:**

- **README:** One-page: what the system does, how to run tests, backtest, paper/live.
- **Architecture Decision Records (ADRs):** Short docs for major choices (e.g. "Why CPCV", "Why ensemble").
- **Runbooks:** Operational (deploy, rollback, halt trading, handle outage).
- **API docs:** OpenAPI spec if REST/gRPC exists.
- **Add to guide:** "Documentation" section.

---

## 8. Dependency & Build Hygiene

**Current state:** Loose `pip install` list; no lockfile or vulnerability process.

**Improvements:**

- **Single declaration:** Use `pyproject.toml`; no duplicate dependency lists.
- **Lockfile:** Use `uv lock` or `pip-tools`; CI and production install from lockfile.
- **Vulnerability scanning:** CI or weekly job (e.g. `pip-audit`, Dependabot).
- **Add to guide:** "Dependencies" subsection.

---

## 9. Data & Model Versioning

**Current state:** Paths like `checkpoints/` and `data/`; no explicit versioning.

**Improvements:**

- **Data:** Versioned datasets (e.g. DVC or paths with dates/version tags). Document which data version a run used.
- **Models:** Model registry (e.g. MLflow): version, training config, metrics. Promotion rule (e.g. CPCV 5th %ile > 0.3).
- **Reproducibility:** Every run logs: git commit, config, data version, model version.
- **Add to guide:** "Data and model versioning" section.

---

## 10. Disaster Recovery & High Availability

**Current state:** Not covered.

**Improvements:**

- **Backups:** Config, critical state, audit logs; restore tested periodically.
- **Failover:** Define how data/execution fail over; avoid double execution.
- **Circuit breakers:** Persist "trading halted" state so restart does not auto-resume.
- **Add to guide:** Short "DR & HA" section.

---

## 11. Compliance & Audit Trail

**Current state:** Risk warnings and "comply with local regulations"; no concrete audit requirements.

**Improvements:**

- **Trade audit trail:** Immutable log of signal, order sent, fills, cancels, manual overrides. Retention aligned with regulation.
- **Model and strategy:** Log which model/strategy version was used for each signal.
- **Add to guide:** "Compliance" subsection.

---

## 12. Paper Trading & Go-Live

**Current state:** "2+ weeks" paper trading then go live.

**Improvements:**

- **Paper trading:** Extend to **4–6 weeks**; span different regimes if possible.
- **Go-live:** Phased: 1 symbol, minimal size; add symbols/size after stable period. Checklist: config, circuit breakers, audit log, runbooks.
- **Add to guide:** "Paper trading criteria" and "Go-live checklist".

---

## 13. Code Quality & Consistency

**Current state:** Pseudocode only; no standards for real codebase.

**Improvements:**

- **Linting and formatting:** Ruff (or equivalent); run in CI.
- **Type hints:** Use for all public functions; mypy in CI.
- **Pre-commit:** Run lint and format on commit.
- **Add to guide:** "Code quality" subsection.

---

## Summary Checklist

| Area | In current guide? | Improvement |
|------|-------------------|------------|
| Repo structure | Partial | Full layout, README, .env.example |
| Testing | No | Unit, integration, e2e, coverage |
| CI/CD | No | CI (lint, test, build), CD (staging/prod) |
| Config | No | Schema, env-specific, validation |
| Security & secrets | Minimal | Vault, least privilege, audit log |
| Observability | Partial | Logging, tracing, alert runbooks |
| Documentation | Plan only | README, ADRs, runbooks |
| Dependencies | Loose | pyproject, lockfile, vuln scan |
| Data/model versioning | No | Versioning, registry, promotion |
| DR/HA | No | Backups, halt persistence, failover |
| Compliance | Brief | Audit trail, retention, lineage |
| Paper / go-live | Brief | 4–6 weeks paper, checklist |
| Code quality | No | Lint, types, pre-commit |

---

**Next step:** Add these as new sections to **Forex-Gold-AI-Trading-Plan-2025** (or a separate "Operations & standards" doc) and implement them from Week 1.
