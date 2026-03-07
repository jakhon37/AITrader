#!/bin/bash
# Run tests in Docker with local code mounted
# This allows you to test changes without rebuilding the image

set -e

# Get the absolute path to the project directory (parent of docker/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# Detect GPU availability (optional for tests)
GPU_FLAGS=""
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    GPU_FLAGS="--runtime=nvidia --gpus all"
fi

echo "🧪 Running tests in Docker..."
echo "📁 Project directory: $PROJECT_DIR"
echo ""

# Parse arguments for pytest
PYTEST_ARGS="${@:---tb=short -v}"

# Run tests with local code mounted (with GPU if available)
docker run --rm $GPU_FLAGS \
    --name aitrader-dev-test \
    -v "$PROJECT_DIR/src:/app/src:ro" \
    -v "$PROJECT_DIR/tests:/app/tests:ro" \
    -v "$PROJECT_DIR/config:/app/config:ro" \
    -v "$PROJECT_DIR/data:/app/data:ro" \
    -v "$PROJECT_DIR/models:/app/models:ro" \
    -e PYTHONPATH=/app/src \
    -e CONFIG_DIR=/app/config \
    -e PYTHONUNBUFFERED=1 \
    -w /app \
    aitrader-dev:latest \
    pytest tests $PYTEST_ARGS

echo ""
echo "✅ Tests completed!"
