#!/bin/bash
# Start Streamlit dashboards in Docker with local code mounted
# This launches both paper monitor and feature explorer

set -e

# Get the absolute path to the project directory (parent of docker/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

echo "📊 Starting Streamlit dashboards in Docker..."
echo "📁 Project directory: $PROJECT_DIR"
echo ""

# Stop any existing dashboard containers (docker-compose or dev)
echo "🧹 Stopping any existing dashboard containers..."
docker stop aitrader-monitor aitrader-explorer 2>/dev/null || true
sleep 2
echo ""

ENV_FILE_ARG=""
if [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE_ARG="--env-file $PROJECT_DIR/.env"
fi

# Start paper monitor dashboard
echo "🚀 Starting Paper Monitor on port 8501..."
docker run -d --rm \
    --name aitrader-monitor \
    -p 8501:8501 \
    $ENV_FILE_ARG \
    -v "$PROJECT_DIR/dashboards:/app/dashboards:ro" \
    -v "$PROJECT_DIR/logs:/app/logs:ro" \
    -v "$PROJECT_DIR/data:/app/data:ro" \
    -e PYTHONUNBUFFERED=1 \
    -e STREAMLIT_SERVER_HEADLESS=true \
    -w /app \
    aitrader-dev:latest \
    streamlit run dashboards/paper_monitor.py --server.port 8501 --server.headless true

# Start feature explorer dashboard
echo "🚀 Starting Feature Explorer on port 8502..."
docker run -d --rm \
    --name aitrader-explorer \
    -p 8502:8502 \
    $ENV_FILE_ARG \
    -v "$PROJECT_DIR/dashboards:/app/dashboards:ro" \
    -v "$PROJECT_DIR/data:/app/data:ro" \
    -e PYTHONUNBUFFERED=1 \
    -e STREAMLIT_SERVER_HEADLESS=true \
    -w /app \
    aitrader-dev:latest \
    streamlit run dashboards/feature_explorer.py --server.port 8502 --server.headless true

echo ""
echo "✅ Dashboards started successfully!"
echo ""
echo "📊 Access dashboards at:"
echo "   Paper Monitor:     http://localhost:8501"
echo "   Feature Explorer:  http://localhost:8502"
echo ""
echo "🛑 To stop dashboards, run:"
echo "   docker stop aitrader-monitor aitrader-explorer"
