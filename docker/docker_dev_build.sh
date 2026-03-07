#!/bin/bash
# Build Docker image for development
# This creates the aitrader-dev image with all dependencies

set -e

# Get project root directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

echo "🐳 Building AITrader Docker development image..."
echo "📁 Project directory: $PROJECT_DIR"
echo ""

# Build the image from project root
cd "$PROJECT_DIR"
docker build -t aitrader-dev:latest -f Dockerfile .

echo "✅ Docker image 'aitrader-dev:latest' built successfully!"
echo ""
echo "Next steps:"
echo "  - Run tests: ./docker/docker_dev_test.sh"
echo "  - Start shell: ./docker/docker_dev_shell.sh"
echo "  - Run paper trading: ./docker/docker_dev_paper.sh"
