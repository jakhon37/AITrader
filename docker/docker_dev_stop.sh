#!/bin/bash
# Stop all running AITrader Docker containers

set -e

echo "🛑 Stopping all AITrader Docker containers..."
echo ""

# Find and stop all aitrader containers
CONTAINERS=$(docker ps --filter "name=aitrader-" --format '{{.Names}}' 2>/dev/null || true)

if [ -z "$CONTAINERS" ]; then
    echo "ℹ️  No running AITrader containers found"
else
    echo "Found containers:"
    echo "$CONTAINERS"
    echo ""
    docker stop $CONTAINERS
    echo ""
    echo "✅ All AITrader containers stopped"
fi
