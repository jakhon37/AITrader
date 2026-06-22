#!/bin/bash
# Start an interactive shell in Docker with the entire project mounted

set -e

# Get project root (parent of docker/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

CONTAINER_NAME="aitrader-dev-shell"
IMAGE_NAME="aitrader-dev:latest"

# Detect NVIDIA GPU
GPU_FLAGS=""
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    GPU_FLAGS="--runtime=nvidia --gpus all"
    GPU_STATUS="🎮 GPU enabled"
else
    GPU_STATUS="💻 CPU only"
fi

# Optional .env support
ENV_FILE_ARG=""
if [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE_ARG="--env-file $PROJECT_DIR/.env"
fi

echo "======================================"
echo "🐳 Docker Interactive Development Shell"
echo "======================================"
echo "📁 Project directory: $PROJECT_DIR"
echo "📦 Docker image: $IMAGE_NAME"
echo "$GPU_STATUS"
echo ""

# Remove exited container if it somehow exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then

    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "✅ Container already running"
        echo "🔗 Attaching shell..."
        exec docker exec -it "$CONTAINER_NAME" /bin/bash
    else
        echo "⚡ Starting existing container..."
        docker start "$CONTAINER_NAME" >/dev/null
        echo "🔗 Attaching shell..."
        exec docker exec -it "$CONTAINER_NAME" /bin/bash
    fi

else

    echo "🚀 Creating new development container..."
    echo ""

    exec docker run -it \
        --name "$CONTAINER_NAME" \
        $GPU_FLAGS \
        $ENV_FILE_ARG \
        -v "$PROJECT_DIR:/app:rw" \
        -w /app \
        -e PYTHONPATH=/app/src:/app \
        -e CONFIG_DIR=/app/config \
        -e PYTHONUNBUFFERED=1 \
        "$IMAGE_NAME" \
        /bin/bash
fi

# python scripts/backfill_historical.py --instruments EURUSD --timeframes 1m --start 2016-01-01 --end 2026-01-01
# python scripts/backfill_historical.py --instruments XAUUSD --timeframes 1m --start 2016-01-01 --end 2026-01-01