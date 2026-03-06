# ADR-002: Pydantic config schema and env-specific YAML

## Status

Accepted.

## Context

We need a single, validated configuration for data, models, risk, and execution. Config must support dev/staging/prod and must **never** contain secrets.

## Decision

- **Schema:** Define config in code using **Pydantic** (`src/config.py`).
- **Files:** Env-specific YAML in `config/`: `dev.yaml`, `staging.yaml`, `prod.yaml`.
- **Secrets:** Not in config. Injected via environment variables or a secret manager.
- **Loading:** `AppConfig.from_yaml(path)` or `AppConfig.from_env(config_dir=...)`.

## Consequences

- One source of truth for structure; invalid config is caught at startup.
- Operators must set env vars or use a vault for production secrets.
