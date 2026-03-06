# Main Implementation Plan — AI Trading Platform (Forex & Gold)

**Version:** 1.0  
**Based on:** Forex-Gold-AI-Trading-Plan-2025 + PROJECT-GUIDE-IMPROVEMENTS  
**Timeline:** Phase 0 (1 week) + 12 weeks core + ongoing hardening

---

## 1. Overview

### 1.1 Objectives

- Build an **industrial-standard** algorithmic trading platform for Forex (EUR/USD, GBP/USD, USD/JPY) and Gold (spot & futures).
- Deliver in **phases**: bootstrap → data → features → models → backtest → execution → paper → live.
- Meet **industrial bar**: tests, CI/CD, config, secrets, observability, audit trail, runbooks.

### 1.2 Principles

- **No production code without tests:** Unit tests for logic; integration tests for pipelines and execution.
- **Config and secrets separate:** All config in versioned YAML; all secrets in vault/env, never in repo.
- **Reproducibility:** Every run (train, backtest, paper) logs git commit, config, data version, model version.
- **Fail fast:** Config validation and dependency checks at startup.

### 1.3 Success Criteria (from strategy guide)

| Metric            | Target        |
|-------------------|---------------|
| Directional accuracy | 65–75%     |
| Sharpe ratio      | 1.2–2.0+      |
| Win rate          | 48–55%        |
| Max drawdown      | 8–15%         |
| CPCV 5th %ile Sharpe | > 0.3 (robustness) |

---

## 2. Repository & Folder Structure

```
trading-platform/
├── .github/workflows/       # CI/CD
├── config/                  # dev.yaml, staging.yaml, prod.yaml
├── src/
│   ├── data/                # Tier 1: Data
│   ├── features/            # Tier 2: Features
│   ├── models/              # Tier 3: Models
│   ├── backtest/            # CPCV, walk-forward, runner
│   ├── execution/           # Tier 4/5: Execution & risk
│   ├── api/                 # Optional: REST/gRPC
│   └── config.py            # Load & validate config
├── tests/unit/, integration/, e2e/, fixtures/
├── scripts/                 # train_all, run_backtest, run_paper, retrain_monthly
├── docs/                    # ADRs, runbooks
├── docker/, k8s/
├── pyproject.toml
└── README.md
```

---

## 3. Phase 0: Project Bootstrap (Week 0)

**Goal:** Repo, tooling, CI, and config foundation.

### Tasks

| # | Task | Deliverable |
|---|------|-------------|
| 0.1 | Create repo with folder structure | Repo with all dirs and `__init__.py` |
| 0.2 | Add `pyproject.toml`: deps, ruff, mypy, pytest, pytest-cov | pyproject.toml + lockfile |
| 0.3 | Add config schema (Pydantic): data, models, risk, execution | `src/config.py` |
| 0.4 | Add `config/dev.yaml`, `staging.yaml`, `prod.yaml` | 3 config files |
| 0.5 | Add `.env.example` and `.gitignore` | .env.example, .gitignore |
| 0.6 | CI: lint, typecheck, test, coverage ≥ 50% | `.github/workflows/ci.yml` |
| 0.7 | Pre-commit: ruff, mypy, pytest | `.pre-commit-config.yaml` |
| 0.8 | README: how to run tests, backtest, paper | README.md |
| 0.9 | First ADRs: CPCV, config schema | docs/ADR-*.md |

### Acceptance Criteria

- [ ] `pytest` runs and passes.
- [ ] `ruff check .` and `mypy src` pass.
- [ ] Config load fails fast if required env var missing.
- [ ] No secrets in repo or config files.

---

## 4. Phase 1: Data Infrastructure (Weeks 1–2)

**Goal:** Ingest, validate, and serve historical data with point-in-time guarantee.

### Week 1

| # | Task | Deliverable |
|---|------|-------------|
| 1.1 | Implement data loaders (CSV) | `src/data/loaders/` |
| 1.2 | Define raw data schema (OHLCV) and validation | `src/data/validation.py` + tests |
| 1.3 | Implement point-in-time access helper | `src/data/point_in_time.py` + tests |
| 1.4 | Download or generate 5+ years EUR/USD | `data/` or fixture |
| 1.5 | Integration test: load → validate → point-in-time slice | `tests/integration/test_data_pipeline.py` |

### Week 2

| # | Task | Deliverable |
|---|------|-------------|
| 2.1 | Add gold spot/futures data path (or placeholder) | config + docs |
| 2.2 | Optional: alternative data loader | `src/data/loaders/alternative.py` |
| 2.3 | Data versioning: document how to tag data | docs/data-versioning.md |
| 2.4 | Run integration test in CI | CI green |

### Acceptance Criteria

- [ ] Unit tests for validation and point-in-time logic.
- [ ] Integration test runs in CI; no data leakage.
- [ ] At least one symbol with 5+ years data available for backtest.

---

## 5. Phase 2: Feature Engineering (Weeks 3–4)

**Goal:** Reusable, tested feature pipeline.

### Week 3

| # | Task | Deliverable |
|---|------|-------------|
| 3.1 | Technical indicators (returns, volatility, EMA, ATR, RSI, MACD) | `src/features/technical_indicators.py` |
| 3.2 | GARCH-related inputs | In technical or separate module |
| 3.3 | Feature engine: config-driven | `src/features/feature_engine.py` |
| 3.4 | Regime detector (HMM) | `src/features/regime_detector.py` |

### Week 4

| # | Task | Deliverable |
|---|------|-------------|
| 4.1 | Causal validator (Granger) | `src/features/causal_validator.py` |
| 4.2 | Order flow signals (or stub) | `src/features/order_flow_signals.py` |
| 4.3 | Integration test: data → feature_engine → no leakage | `tests/integration/test_feature_pipeline.py` |

### Acceptance Criteria

- [ ] All feature modules have unit tests.
- [ ] Feature pipeline integration test passes in CI.

---

## 6. Phase 3: Model Development (Weeks 5–7)

**Goal:** At least 2–3 models + ensemble; all with tests and checkpointing.

### Week 5

| # | Task | Deliverable |
|---|------|-------------|
| 5.1 | GARCH-GRU model | `src/models/garch_gru.py` + tests |
| 5.2 | LSTM-Transformer hybrid | `src/models/lstm_transformer.py` + tests |
| 5.3 | Training script | `scripts/train_all.py` |
| 5.4 | Model registry (version, config, metrics) | scripts + config |

### Week 6

| # | Task | Deliverable |
|---|------|-------------|
| 6.1 | Multimodal stub (or skip) | `src/models/multimodal.py` |
| 6.2 | Foundation model (TTM/Chronos) stub | `src/models/foundation_model.py` |
| 6.3 | Normalizing flow stub | `src/models/normalizing_flow.py` |
| 6.4 | Ensemble: weighted vote | `src/models/ensemble.py` + tests |

### Week 7

| # | Task | Deliverable |
|---|------|-------------|
| 7.1 | Meta-labeler | `src/models/meta_labeler.py` + tests |
| 7.2 | End-to-end: load checkpoints → ensemble → meta-label → signal | Script |
| 7.3 | Integration test: model I/O | `tests/integration/test_models.py` |

### Acceptance Criteria

- [ ] At least 2 models with train/predict and tests.
- [ ] Ensemble + meta-labeler wired; integration test passes.

---

## 7. Phase 4: Backtesting & Evaluation (Week 8)

**Goal:** CPCV + walk-forward; pass/fail robustness; deterministic e2e test.

### Tasks

| # | Task | Deliverable |
|---|------|-------------|
| 8.1 | CPCV runner | `src/backtest/cpcv.py` + tests |
| 8.2 | Walk-forward runner (30+ windows) | `src/backtest/walk_forward.py` + tests |
| 8.3 | Backtest runner | `scripts/run_backtest.py` |
| 8.4 | Robustness gate: CPCV 5th %ile Sharpe > 0.3 | In runner or CI |
| 8.5 | E2E test: fixed data → backtest → assert metrics in band | `tests/e2e/test_backtest_deterministic.py` |

### Acceptance Criteria

- [ ] CPCV and walk-forward tests pass.
- [ ] Single full backtest produces report.
- [ ] E2E deterministic test in CI.

---

## 8. Phase 5: Execution & Risk (Weeks 9–10)

**Goal:** Execution engine, risk manager, circuit breakers, audit log.

### Week 9

| # | Task | Deliverable |
|---|------|-------------|
| 9.1 | Risk manager: position size, max drawdown, daily loss limit | `src/execution/risk_manager.py` |
| 9.2 | Circuit breaker | `src/execution/circuit_breaker.py` |
| 9.3 | Position manager | `src/execution/position_manager.py` |
| 9.4 | Execution engine + broker adapter (mock + one real) | `src/execution/engine.py` |

### Week 10

| # | Task | Deliverable |
|---|------|-------------|
| 10.1 | Audit log: every signal, order, fill, cancel | `src/execution/audit_log.py` |
| 10.2 | Persist "trading halted" state | Config or state file |
| 10.3 | Integration test: mock broker, risk, circuit breaker | `tests/integration/test_execution_mock.py` |
| 10.4 | Runbooks: halt trading, deploy | docs/runbook-*.md |

### Acceptance Criteria

- [ ] Risk and circuit breaker unit tests pass.
- [ ] Execution integration test with mock broker passes.
- [ ] Audit log written for every trade-related action.

---

## 9. Phase 6: Paper Trading & Go-Live (Weeks 11–12)

**Goal:** 4–6 weeks paper trading, then go-live checklist and small-size live.

### Week 11

| # | Task | Deliverable |
|---|------|-------------|
| 11.1 | Paper trading script | `scripts/run_paper.py` |
| 11.2 | Sim broker | `src/execution/brokers/sim.py` |
| 11.3 | Daily report: PnL, drawdown, win rate, signal count | reporting module |
| 11.4 | Start paper trading (4–6 weeks) | Dashboard or logs |

### Week 12

| # | Task | Deliverable |
|---|------|-------------|
| 12.1 | Go-live checklist | `docs/go-live-checklist.md` |
| 12.2 | Deploy to staging/prod | CD or manual deploy |
| 12.3 | Enable live with small account ($5K–10K), 1 micro lot | Operations |
| 12.4 | Monitor 1+ hour daily | Runbook + audit |

### Acceptance Criteria

- [ ] Paper trading runs end-to-end for at least 1 week.
- [ ] Go-live checklist completed.
- [ ] Live trading uses separate config and secrets.

---

## 10. Phase 7: Production Hardening (Ongoing)

**Goal:** Observability, retraining, DR, compliance.

- **Observability:** Structured logging, metrics, alerts with runbooks, optional tracing.
- **Retraining:** Monthly retrain script; promotion rule (e.g. CPCV 5th %ile ≥ 0.3).
- **DR & Compliance:** Backups, audit trail retention (5–7 years), secret rotation.

---

## 11. Implementation Checklist (Master)

### Phase 0 — Bootstrap
- [ ] Repo structure created
- [ ] pyproject.toml + lockfile
- [ ] Config schema + dev/staging/prod YAML
- [ ] .env.example and .gitignore
- [ ] CI (lint, typecheck, test, coverage)
- [ ] Pre-commit
- [ ] README and 2 ADRs

### Phase 1 — Data
- [ ] Loaders + validation + point-in-time
- [ ] 5+ years data for ≥1 symbol
- [ ] Data pipeline integration test in CI

### Phase 2 — Features
- [ ] Technical indicators + feature_engine
- [ ] Regime detector + causal validator
- [ ] Feature pipeline integration test

### Phase 3 — Models
- [ ] ≥2 models + ensemble + meta-labeler
- [ ] Train script + checkpoint/registry
- [ ] Model integration test

### Phase 4 — Backtest
- [ ] CPCV + walk-forward
- [ ] Backtest runner + robustness gate
- [ ] E2E deterministic test

### Phase 5 — Execution
- [ ] Risk manager + circuit breaker + position manager
- [ ] Execution engine + broker adapter(s)
- [ ] Audit log + halt persistence
- [ ] Execution integration test + runbooks

### Phase 6 — Paper & Live
- [ ] Paper trading 4–6 weeks
- [ ] Go-live checklist and deploy
- [ ] Live with small size + monitoring

### Phase 7 — Hardening
- [ ] Logging + metrics + alerts + runbooks
- [ ] Retrain procedure + promotion rule
- [ ] Backup + audit retention + secret rotation

---

## 12. Document References

- **Strategy & architecture:** `Forex-Gold-AI-Trading-Plan-2025`
- **Improvements (testing, CI, config, security, etc.):** `PROJECT-GUIDE-IMPROVEMENTS.md`
- **This plan:** `MAIN-IMPLEMENTATION-PLAN.md`

---

**End of Main Implementation Plan.**
