#!/bin/bash
# Train models in Docker with local code mounted
# This runs the training script using the Docker environment

set -e

# Get the absolute path to the project directory (parent of docker/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# Stop any existing training containers
echo "🧹 Stopping any existing training containers..."
docker stop aitrader-dev-train 2>/dev/null || true
echo ""

# Default values
EPOCHS="${EPOCHS:-10}"
USE_GPU="${USE_GPU:-auto}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --epochs)
            EPOCHS="$2"
            shift 2
            ;;
        --gpu)
            USE_GPU="yes"
            shift
            ;;
        --no-gpu)
            USE_GPU="no"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--epochs N] [--gpu] [--no-gpu]"
            exit 1
            ;;
    esac
done

# Detect GPU availability
GPU_FLAGS=""
if [ "$USE_GPU" = "auto" ]; then
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        USE_GPU="yes"
    else
        USE_GPU="no"
    fi
fi

if [ "$USE_GPU" = "yes" ]; then
    GPU_FLAGS="--runtime=nvidia --gpus all"
    GPU_STATUS="🎮 GPU enabled (NVIDIA)"
else
    GPU_STATUS="💻 CPU only"
fi

echo "🤖 Training models in Docker..."
echo "📁 Project directory: $PROJECT_DIR"
echo "🔄 Epochs: $EPOCHS"
echo "$GPU_STATUS"
echo ""

# Run training with local code mounted
ENV_FILE_ARG=""
if [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE_ARG="--env-file $PROJECT_DIR/.env"
fi

docker run -it --rm $GPU_FLAGS \
    --name aitrader-dev-train \
    $ENV_FILE_ARG \
    -v "$PROJECT_DIR/src:/app/src:ro" \
    -v "$PROJECT_DIR/scripts:/app/scripts:ro" \
    -v "$PROJECT_DIR/config:/app/config:ro" \
    -v "$PROJECT_DIR/data:/app/data:ro" \
    -v "$PROJECT_DIR/models:/app/models:rw" \
    -e PYTHONPATH=/app/src \
    -e CONFIG_DIR=/app/config \
    -e PYTHONUNBUFFERED=1 \
    -w /app \
    aitrader-dev:latest \
    python scripts/train_all.py --epochs "$EPOCHS"

echo ""
echo "✅ Training completed!"
echo "📁 Models saved to: $PROJECT_DIR/models/"
