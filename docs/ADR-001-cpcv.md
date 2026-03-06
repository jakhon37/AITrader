# ADR-001: Use Combinatorial Purged Cross-Validation (CPCV) for Backtesting

## Status

Accepted.

## Context

Standard backtesting (single train/test split or simple walk-forward) often yields overfitted or lucky results. Time series have temporal dependence, so random splits cause leakage. We need a robust evaluation that produces a **distribution** of outcomes, not a single Sharpe ratio.

## Decision

We use **Combinatorial Purged Cross-Validation (CPCV)** as the primary evaluation method for strategy and model selection.

## Consequences

- More realistic performance estimates and fewer false positives.
- Implementation depends on `mlfinlab` or a custom CPCV implementation.
- Backtest runs take longer than a single split.
