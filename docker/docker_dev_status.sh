#!/bin/bash
# Check status of AITrader Docker containers

echo "📊 AITrader Docker Container Status"
echo "===================================="
echo ""

# Check for running containers
CONTAINERS=$(docker ps --filter "name=aitrader-" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true)

if [ -z "$CONTAINERS" ] || [ "$CONTAINERS" = "NAMES	STATUS	PORTS" ]; then
    echo "ℹ️  No running AITrader containers"
else
    echo "$CONTAINERS"
fi

echo ""
echo "===================================="

# Check if image exists
if docker images aitrader-dev:latest --format '{{.Repository}}:{{.Tag}}' | grep -q aitrader-dev; then
    SIZE=$(docker images aitrader-dev:latest --format '{{.Size}}')
    echo "✅ Docker image: aitrader-dev:latest ($SIZE)"
else
    echo "⚠️  Docker image not built yet. Run: ./docker/docker_dev_build.sh"
fi

echo ""

# Check GPU availability
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    echo "🎮 GPU: $GPU_NAME"
    echo "   Run: ./docker/docker_dev_gpu_check.sh for details"
else
    echo "💻 GPU: Not available (CPU only)"
fi
