#!/bin/bash
# Paper trading entrypoint — delegates to the canonical Web UI stack.
#
# ExecutionEngine (SimBroker) runs inside the FastAPI backend lifespan.
# This script exists for backward compatibility with legacy start_paper.sh usage.
#
# Usage:
#   ./scripts/start_paper.sh
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/start_webui.sh"