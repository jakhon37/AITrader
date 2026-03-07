#!/bin/bash
# Check GPU availability in Docker

echo "🎮 Checking GPU availability..."
echo ""

# Check if nvidia-smi is available on host
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ nvidia-smi not found on host"
    echo "   GPU support not available"
    exit 1
fi

# Check if NVIDIA driver is working
if ! nvidia-smi &> /dev/null; then
    echo "❌ NVIDIA driver not working"
    echo "   Run: nvidia-smi"
    exit 1
fi

echo "✅ NVIDIA driver detected on host"
echo ""

# Show GPU info
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | while IFS=',' read -r name driver memory; do
    echo "   GPU: $name"
    echo "   Driver: $driver"
    echo "   Memory: $memory"
done

echo ""

# Check Docker GPU support
echo "🐳 Testing Docker GPU access..."
if docker run --rm --runtime=nvidia --gpus all ubuntu:22.04 nvidia-smi &> /dev/null; then
    echo "✅ Docker can access GPU"
    echo ""
    echo "GPU-enabled commands:"
    echo "  ./docker/docker_dev_train.sh --gpu       # Force GPU training"
    echo "  ./docker/docker_dev_shell.sh             # Shell with GPU access"
else
    echo "❌ Docker cannot access GPU"
    echo ""
    echo "To fix:"
    echo "  1. Install nvidia-docker2:"
    echo "     sudo apt-get install -y nvidia-docker2"
    echo "     sudo systemctl restart docker"
    echo ""
    echo "  2. Or install NVIDIA Container Toolkit:"
    echo "     distribution=\$(. /etc/os-release;echo \$ID\$VERSION_ID)"
    echo "     curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -"
    echo "     curl -s -L https://nvidia.github.io/nvidia-docker/\$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list"
    echo "     sudo apt-get update && sudo apt-get install -y nvidia-docker2"
    echo "     sudo systemctl restart docker"
fi
