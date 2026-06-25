#!/bin/bash
# Deprecated: Streamlit dashboards replaced by D10 Web UI.
# This script now starts the Docker Web UI stack.
set -e
echo "ℹ️  Streamlit dashboards are retired. Starting D10 Web UI instead..."
"$(dirname "${BASH_SOURCE[0]}")/docker_dev_webui.sh"