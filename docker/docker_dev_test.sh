#!/bin/bash
# Run tests in Docker with local code mounted.
# Mounts src/, tests/, config/, data/, and pyproject.toml as read-only volumes.
# Use: ./docker/docker_dev_test.sh [pytest args]
# Example: ./docker/docker_dev_test.sh tests/unit/test_core.py -v

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# Detect GPU (optional for tests)
GPU_FLAGS=""
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    GPU_FLAGS="--runtime=nvidia --gpus all"
fi

echo "🧪 Running tests in Docker (Python 3.12)..."
echo "📁 Project: $PROJECT_DIR"
echo ""

# Default pytest args: run all tests with verbose + short tracebacks
PYTEST_ARGS="${@:---tb=short -q}"

ENV_FILE_ARG=""
if [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE_ARG="--env-file $PROJECT_DIR/.env"
fi

docker run --rm $GPU_FLAGS \
    --name aitrader-dev-test \
    $ENV_FILE_ARG \
    -v "$PROJECT_DIR/src:/app/src:ro" \
    -v "$PROJECT_DIR/tests:/app/tests:ro" \
    -v "$PROJECT_DIR/config:/app/config:ro" \
    -v "$PROJECT_DIR/data:/app/data:ro" \
    -v "$PROJECT_DIR/models:/app/models:ro" \
    -v "$PROJECT_DIR/pyproject.toml:/app/pyproject.toml:ro" \
    -e PYTHONPATH=/app/src:/app \
    -e CONFIG_DIR=/app/config \
    -e PYTHONUNBUFFERED=1 \
    -w /app \
    aitrader-dev:latest \
    pytest $PYTEST_ARGS

echo ""
echo "✅ Tests completed!"
