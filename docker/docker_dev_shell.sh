#!/bin/bash
# Start an interactive shell in Docker with local code mounted
# This allows you to develop and test using the Docker environment

set -e

# Get the absolute path to the project directory (parent of docker/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# Stop any existing dev shell containers
echo "🧹 Stopping any existing dev shell containers..."
docker stop aitrader-dev-shell 2>/dev/null || true

# Detect GPU availability
GPU_FLAGS=""
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    GPU_FLAGS="--runtime=nvidia --gpus all"
    GPU_STATUS="🎮 GPU enabled"
else
    GPU_STATUS="💻 CPU only"
fi

echo "🐳 Starting interactive Docker shell with local code mounted..."
echo "📁 Project directory: $PROJECT_DIR"
echo "$GPU_STATUS"
echo ""

# Run interactive shell with local code mounted
docker run -it --rm $GPU_FLAGS \
    --name aitrader-dev-shell \
    -v "$PROJECT_DIR/src:/app/src:rw" \
    -v "$PROJECT_DIR/tests:/app/tests:rw" \
    -v "$PROJECT_DIR/scripts:/app/scripts:rw" \
    -v "$PROJECT_DIR/dashboards:/app/dashboards:rw" \
    -v "$PROJECT_DIR/config:/app/config:ro" \
    -v "$PROJECT_DIR/data:/app/data:rw" \
    -v "$PROJECT_DIR/models:/app/models:rw" \
    -v "$PROJECT_DIR/logs:/app/logs:rw" \
    -v "$PROJECT_DIR/reports:/app/reports:rw" \
    -e PYTHONPATH=/app/src \
    -e CONFIG_DIR=/app/config \
    -e PYTHONUNBUFFERED=1 \
    -w /app \
    aitrader-dev:latest \
    /bin/bash

echo "👋 Exited Docker shell"
