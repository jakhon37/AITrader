# Runbook: Deploy

## Pre-deploy

- [ ] Tests and lint pass in CI.
- [ ] Config for target env reviewed; no secrets in repo.
- [ ] Approval for production deploy (if prod).

## Deploy steps

1. **Build** — Build Docker image from the tagged commit.
2. **Deploy to staging first** — Run short backtest or paper run to verify.
3. **Deploy to prod** — Ensure secrets are injected from vault/env.
4. **Smoke check** — Verify service health.
5. **Monitor** — Watch P&L, drawdown, error rates.

## Rollback

If issues: halt trading, revert to previous image, restart with previous config.
