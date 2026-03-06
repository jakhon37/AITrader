#!/bin/bash
# Stop all Docker containers for AITrader

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Detect docker compose command
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo "Error: docker-compose not found"
    exit 1
fi

echo -e "${YELLOW}🛑 Stopping AITrader Docker services...${NC}"
echo ""

# Stop and remove containers
$COMPOSE_CMD down

echo ""
echo -e "${GREEN}✅ All Docker services stopped${NC}"
echo ""
echo -e "${YELLOW}💡 To remove volumes (data, logs): $COMPOSE_CMD down -v${NC}"
echo ""
