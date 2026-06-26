#!/bin/bash
# Paper trading status — Docker Web UI stack (replaces legacy PID-based checks).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"
PYTHONPATH=src CONFIG_DIR="$PROJECT_ROOT/config" python3 scripts/paper_soak_status.py