# Archived launcher scripts

Superseded aliases moved from `scripts/` during launcher consolidation.

| Script | Was | Use instead |
|--------|-----|-------------|
| `start_paper.sh` | Thin wrapper → `start_webui.sh` | `./scripts/start_webui.sh` |
| `stop_paper.sh` | Thin wrapper → `stop_webui.sh` | `./scripts/stop_webui.sh` |

Paper trading runs inside the Web UI backend (`ExecutionEngine` in FastAPI lifespan).
There is no separate paper-trading process.

Do not use these scripts. Kept for reference only.