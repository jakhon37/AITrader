#!/bin/bash
# ARCHIVED — duplicate of start_webui.sh. Use ./scripts/start_webui.sh instead.
#
# Paper trading is integrated into the Web UI backend; this script only forwarded
# to start_webui.sh. Moved to .arch/legacy/scripts/ on 2026-06-26.
#
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
exec "$PROJECT_DIR/scripts/start_webui.sh"