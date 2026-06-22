#!/bin/bash
# Run paper trading in Docker with local code mounted
# This starts paper trading using the Docker environment

set -e

# Get the absolute path to the project directory (parent of docker/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# Stop any existing paper trading containers (docker-compose or dev)
echo "🧹 Stopping any existing paper trading containers..."
docker stop aitrader-paper aitrader-dev-paper 2>/dev/null || true
echo ""

# Load defaults from config if available
if [ -f "$PROJECT_DIR/config/dev.yaml" ]; then
    CONFIG_SYMBOL=$(grep -A 1 "symbols:" "$PROJECT_DIR/config/dev.yaml" | grep -v "symbols:" | head -1 | sed 's/.*- //;s/_//g' | tr '[:upper:]' '[:lower:]' | xargs)
    CONFIG_TIMEFRAME=$(grep "timeframe:" "$PROJECT_DIR/config/dev.yaml" | sed 's/.*timeframe: "\(.*\)".*/\1/')
    CONFIG_MODEL=$(grep "model_type:" "$PROJECT_DIR/config/dev.yaml" | sed 's/.*model_type: "\(.*\)".*/\1/')
fi

# Default values (use config if available)
CAPITAL="${CAPITAL:-100000}"
SYMBOLS="${SYMBOLS:-${CONFIG_SYMBOL:-btcusd}}"
INTERVAL="${INTERVAL:-3600}"
TIMEFRAME="${TIMEFRAME:-${CONFIG_TIMEFRAME:-1d}}"
MODEL="${MODEL:-${CONFIG_MODEL:-lstm_transformer}}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --capital)
            CAPITAL="$2"
            shift 2
            ;;
        --symbols)
            SYMBOLS="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --timeframe)
            TIMEFRAME="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --no-live)
            NO_LIVE="--no-live"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--capital N] [--symbols 'sym1 sym2'] [--interval N] [--timeframe TF] [--model MODEL] [--no-live]"
            exit 1
            ;;
    esac
done

echo "📈 Starting paper trading in Docker..."
echo "📁 Project directory: $PROJECT_DIR"
echo "💰 Capital: \$$CAPITAL"
echo "📊 Symbols: $SYMBOLS"
echo "🤖 Model: $MODEL"
echo "⏱️  Interval: ${INTERVAL}s"
echo "📅 Timeframe: $TIMEFRAME"
echo ""

ENV_FILE_ARG=""
if [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE_ARG="--env-file $PROJECT_DIR/.env"
fi

# Run paper trading with local code mounted
docker run -it --rm \
    --name aitrader-dev-paper \
    $ENV_FILE_ARG \
    -v "$PROJECT_DIR/src:/app/src:ro" \
    -v "$PROJECT_DIR/scripts:/app/scripts:ro" \
    -v "$PROJECT_DIR/config:/app/config:ro" \
    -v "$PROJECT_DIR/data:/app/data:rw" \
    -v "$PROJECT_DIR/models:/app/models:ro" \
    -v "$PROJECT_DIR/logs:/app/logs:rw" \
    -e PYTHONPATH=/app/src \
    -e CONFIG_DIR=/app/config \
    -e PYTHONUNBUFFERED=1 \
    -w /app \
    aitrader-dev:latest \
    python scripts/run_paper.py \
        --capital "$CAPITAL" \
        --model "$MODEL" \
        --symbols "$SYMBOLS" \
        --interval "$INTERVAL" \
        --timeframe "$TIMEFRAME" \
        $NO_LIVE

echo ""
echo "📊 Paper trading session ended"
