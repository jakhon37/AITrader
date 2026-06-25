#!/bin/bash
# Docker launcher for AITrader
# Builds and starts all services in Docker containers

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🐳 AITrader Docker Launcher${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Detect docker compose command (v1 or v2)
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo -e "${RED}❌ docker-compose is not available${NC}"
    echo "Please install docker-compose plugin: https://docs.docker.com/compose/install/"
    exit 1
fi

echo -e "${GREEN}✅ Docker is installed (using: $COMPOSE_CMD)${NC}"
echo ""

# Parse arguments
BUILD_FLAG=""
DETACH_FLAG="-d"

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD_FLAG="--build"
            shift
            ;;
        --foreground)
            DETACH_FLAG=""
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--build] [--foreground]"
            echo "  --build      Rebuild Docker images"
            echo "  --foreground Run in foreground (see logs)"
            exit 1
            ;;
    esac
done

# Create necessary directories
mkdir -p logs data models config

# Build or pull images
if [ -n "$BUILD_FLAG" ]; then
    echo -e "${YELLOW}🔨 Building Docker images...${NC}"
    $COMPOSE_CMD build
    echo -e "${GREEN}✅ Images built${NC}"
    echo ""
fi

# Start services
echo -e "${YELLOW}🚀 Starting AITrader services...${NC}"
echo ""

if [ -n "$DETACH_FLAG" ]; then
    $COMPOSE_CMD up $DETACH_FLAG
    
    # Wait for services to start
    echo -e "${YELLOW}⏳ Waiting for services to initialize...${NC}"
    sleep 5
    
    # Check if containers are running
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ AITrader running in Docker!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}🌐 Web UI:${NC}"
    echo "   • Trading Terminal: http://localhost:5173"
    echo "   • API Docs:         http://localhost:8000/docs"
    echo ""
    echo -e "${BLUE}🐳 Docker Commands:${NC}"
    echo "   • Status:  $COMPOSE_CMD ps"
    echo "   • Logs:    $COMPOSE_CMD logs -f"
    echo "   • Stop:    ./docker/stop_docker.sh"
    echo "   • Restart: $COMPOSE_CMD restart"
    echo ""
    echo -e "${BLUE}📝 Individual Service Logs:${NC}"
    echo "   • Backend:  $COMPOSE_CMD logs -f webui-backend"
    echo "   • Frontend: $COMPOSE_CMD logs -f webui-frontend"
    echo ""
    echo -e "${YELLOW}💡 Tip: Logs are also saved to ./logs/ directory${NC}"
    echo ""
else
    # Run in foreground
    echo -e "${YELLOW}Running in foreground. Press Ctrl+C to stop.${NC}"
    echo ""
    $COMPOSE_CMD up
fi
