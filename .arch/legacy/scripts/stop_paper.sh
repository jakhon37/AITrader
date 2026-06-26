#!/bin/bash
# ARCHIVED — duplicate of stop_webui.sh. Use ./scripts/stop_webui.sh instead.
#
# Moved to .arch/legacy/scripts/ on 2026-06-26.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
exec "$PROJECT_DIR/scripts/stop_webui.sh"