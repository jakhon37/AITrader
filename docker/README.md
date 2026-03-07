# 🐳 Docker Deployment Guide

Run AITrader in Docker containers for easy deployment and isolation.

---

## � Two Modes Available

### 🔧 Development Mode (Local Code Mounted)
Use **docker_dev_*.sh** scripts for development with local code mounted:
- Edit code locally, changes appear instantly in Docker
- No rebuild needed after code changes
- Perfect for testing and development

**Quick Start:**
```bash
./docker/docker_dev_build.sh      # Build once
./docker/docker_dev_test.sh       # Run tests
./docker/docker_dev_shell.sh      # Interactive shell
./docker/docker_dev_paper.sh      # Paper trading
```

**See [DOCKER-DEV-GUIDE.md](DOCKER-DEV-GUIDE.md) for complete development guide.**

---

### 🚀 Production Mode (docker-compose)
Use **start_docker.sh/stop_docker.sh** for production deployment:
- Multi-service orchestration
- Background services with auto-restart
- Production-ready configuration

---

## 🚀 Production Quick Start

```bash
# Build and start all services
./docker/start_docker.sh --build

# Check status
./docker/status_docker.sh

# Stop all services
./docker/stop_docker.sh
```

Open dashboards:
- **Paper Monitor**: http://localhost:8501
- **Feature Explorer**: http://localhost:8502

---

## 📋 Prerequisites

1. **Install Docker:**
   - Ubuntu/Debian: `sudo apt-get install docker.io`
   - Mac: Download Docker Desktop
   - Windows: Download Docker Desktop

2. **Install docker-compose:**
   ```bash
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

3. **Add user to docker group (Linux):**
   ```bash
   sudo usermod -aG docker $USER
   # Log out and back in for changes to take effect
   ```

---

## 🏗️ Architecture

**3 Docker Services:**

1. **paper-trading** - Main trading engine
   - Fetches live data
   - Generates signals
   - Executes trades
   - Logs to audit trail

2. **monitor-dashboard** - Real-time monitoring
   - Port: 8501
   - Shows portfolio, PnL, trades
   - Auto-refreshes every 5 seconds

3. **feature-explorer** - Data analysis
   - Port: 8502
   - Charts, features, correlations

**Volumes:**
- `./logs` - Trading and dashboard logs
- `./data` - Market data
- `./models` - Trained models
- `./config` - Configuration files

---

## 🎯 Usage

### Start Services

```bash
# First time (build images)
./docker/start_docker.sh --build

# Subsequent starts (use existing images)
./docker/start_docker.sh

# Run in foreground (see logs)
./docker/start_docker.sh --foreground
```

### Check Status

```bash
./docker/status_docker.sh
```

Shows:
- Running containers
- CPU and memory usage
- Recent activity

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f paper-trading
docker-compose logs -f monitor-dashboard
docker-compose logs -f feature-explorer
```

### Stop Services

```bash
# Stop all (keep data)
./docker/stop_docker.sh

# Stop and remove volumes (DELETES DATA!)
docker-compose down -v
```

---

## 🔧 Configuration

### Custom Capital and Symbols

Edit `docker-compose.yml`:

```yaml
paper-trading:
  command: python scripts/run_paper.py --capital 50000 --symbols "eurusd gbpusd" --interval 1800
```

### Different Ports

Edit `docker-compose.yml`:

```yaml
monitor-dashboard:
  ports:
    - "8503:8501"  # Change host port

feature-explorer:
  ports:
    - "8504:8502"  # Change host port
```

### Environment Variables

Add to service in `docker-compose.yml`:

```yaml
environment:
  - CAPITAL=100000
  - SYMBOLS=eurusd,gbpusd
  - INTERVAL=3600
```

---

## 🛠️ Advanced Usage

### Rebuild After Code Changes

```bash
./docker/start_docker.sh --build
```

### Access Container Shell

```bash
# Paper trading container
docker exec -it aitrader-paper /bin/bash

# Monitor dashboard
docker exec -it aitrader-monitor /bin/bash
```

### Restart Single Service

```bash
docker-compose restart paper-trading
docker-compose restart monitor-dashboard
```

### Scale Services (Multiple Instances)

```bash
# Run 3 instances of paper trading (different symbols)
docker-compose up --scale paper-trading=3 -d
```

### View Resource Usage

```bash
docker stats
```

---

## 📦 What's Included in Image

**Base:** Python 3.12-slim  
**Size:** ~1GB

**Installed:**
- AITrader source code
- All Python dependencies
- Trained models (if exist)
- Configuration files

**Not Included (Mounted as Volumes):**
- Logs (persisted on host)
- Data files (persisted on host)
- Model files (persisted on host)

---

## 🔍 Troubleshooting

### Port Already in Use

```bash
# Check what's using the port
sudo lsof -i :8501
sudo lsof -i :8502

# Kill the process or change ports in docker-compose.yml
```

### Container Keeps Restarting

```bash
# Check logs for errors
docker-compose logs paper-trading

# Common issues:
# - Model not found: Train model first
# - Data not found: Ensure data/ directory exists
# - Import errors: Rebuild with --build
```

### Out of Memory

```bash
# Increase Docker memory limit
# Docker Desktop: Preferences → Resources → Memory

# Or limit service memory in docker-compose.yml:
services:
  paper-trading:
    mem_limit: 2g
```

### Slow Build

```bash
# Use BuildKit for faster builds
DOCKER_BUILDKIT=1 docker-compose build

# Or set in ~/.bashrc:
export DOCKER_BUILDKIT=1
```

---

## 🔐 Production Deployment

### Security Best Practices

1. **Use secrets for API keys:**
   ```yaml
   services:
     paper-trading:
       secrets:
         - broker_api_key
   secrets:
     broker_api_key:
       file: ./secrets/broker_key.txt
   ```

2. **Run as non-root user:**
   ```dockerfile
   RUN useradd -m -u 1000 aitrader
   USER aitrader
   ```

3. **Limit resources:**
   ```yaml
   services:
     paper-trading:
       mem_limit: 2g
       cpus: 2.0
   ```

### Persistent Storage

```yaml
volumes:
  logs:
    driver: local
  data:
    driver: local
  models:
    driver: local
```

### Health Checks

```yaml
services:
  paper-trading:
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## 📊 Monitoring in Production

### Prometheus Metrics (Optional)

Add to `docker-compose.yml`:

```yaml
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

### Log Aggregation (Optional)

```bash
# Send logs to external service
docker-compose logs -f | your-log-service
```

---

## 🚢 Deployment Platforms

### Deploy to Cloud

**AWS:**
```bash
# EC2 with Docker
ssh user@ec2-instance
git clone <repo>
./docker/start_docker.sh --build
```

**DigitalOcean:**
```bash
# Docker Droplet
docker-compose up -d
```

**Google Cloud Run:**
```bash
# Deploy container
gcloud run deploy aitrader --source .
```

### Deploy to Kubernetes

See `k8s/` directory for Kubernetes manifests.

---

## 📝 Files

```
docker/
├── start_docker.sh      # Launch script
├── stop_docker.sh       # Stop script
├── status_docker.sh     # Status checker
└── README.md           # This file

Dockerfile               # Image definition
docker-compose.yml       # Service orchestration
.dockerignore           # Build exclusions
```

---

## ❓ FAQ

**Q: How big is the Docker image?**  
A: ~1GB (includes Python, deps, and code)

**Q: Can I run this on ARM (Apple Silicon)?**  
A: Yes, but build time may be longer. Use `--platform linux/amd64` if needed.

**Q: How do I update the code?**  
A: `git pull && ./docker/start_docker.sh --build`

**Q: Can I run multiple instances?**  
A: Yes, with different configs or use docker-compose scale.

**Q: Does Docker affect performance?**  
A: Minimal overhead (<5%), suitable for production.

**Q: How do I back up data?**  
A: Copy `./logs`, `./data`, `./models` directories.

---

## 🔗 Related

- **Local deployment**: `QUICKSTART-PAPER-TRADING.md`
- **Go-live checklist**: `docs/go-live-checklist.md`
- **Docker Compose docs**: https://docs.docker.com/compose/

---

**Ready to deploy with Docker?**

```bash
./docker/start_docker.sh --build
```

Then visit: http://localhost:8501 🚀
