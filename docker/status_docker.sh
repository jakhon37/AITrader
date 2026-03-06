#!/bin/bash
# Check status of AITrader Docker services

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🐳 AITrader Docker Status${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if docker-compose is running
if ! $COMPOSE_CMD ps | grep -q "Up"; then
    echo -e "${RED}❌ No services running${NC}"
    echo ""
    echo -e "${YELLOW}Start services with: ./docker/start_docker.sh${NC}"
    echo ""
    exit 0
fi

# Show running containers
echo -e "${GREEN}Running Services:${NC}"
$COMPOSE_CMD ps
echo ""

# Show resource usage
echo -e "${BLUE}Resource Usage:${NC}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" $($COMPOSE_CMD ps -q)
echo ""

# Show recent logs
echo -e "${BLUE}Recent Activity:${NC}"
echo -e "${YELLOW}Paper Trading:${NC}"
$COMPOSE_CMD logs --tail=3 paper-trading 2>/dev/null | grep -v "Attaching" || echo "  No logs"

echo ""
echo -e "${YELLOW}Monitor Dashboard:${NC}"
$COMPOSE_CMD logs --tail=3 monitor-dashboard 2>/dev/null | grep -v "Attaching" || echo "  No logs"

echo ""
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}💡 Commands:${NC}"
echo "   Full logs:    $COMPOSE_CMD logs -f"
echo "   Stop all:     ./docker/stop_docker.sh"
echo "   Restart:      $COMPOSE_CMD restart"
echo "   Rebuild:      ./docker/start_docker.sh --build"
echo ""
