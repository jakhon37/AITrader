# Docker Development Environment

This directory contains scripts in `docker/` folder for running the AITrader platform in Docker with local code mounted. This approach allows you to:

- Use a consistent Docker environment (Python 3.12, all dependencies)
- Edit code locally and see changes immediately (no rebuild needed)
- Test in an isolated environment separate from your conda/system Python
- **Auto-stop previous containers** to avoid conflicts

## Quick Start

### 1. Build the Docker Image

```bash
./docker/docker_dev_build.sh
```

This creates the `aitrader-dev:latest` image with all dependencies (~2-3 GB).

### 2. Available Commands

#### Interactive Shell
```bash
./docker/docker_dev_shell.sh
```
Opens an interactive bash shell in the Docker container with all your local code mounted. Perfect for exploring and running commands.

#### Run Tests
```bash
./docker/docker_dev_test.sh                    # Run all tests
./docker/docker_dev_test.sh tests/unit/        # Run specific test directory
./docker/docker_dev_test.sh -k test_name       # Run specific test
./docker/docker_dev_test.sh --cov=src          # With coverage
```

#### Paper Trading
```bash
./docker/docker_dev_paper.sh                                           # Default: $100k, EURUSD, 1h interval
./docker/docker_dev_paper.sh --capital 50000 --symbols "eurusd gbpusd" # Custom settings
./docker/docker_dev_paper.sh --timeframe 5m --interval 300             # 5-minute scalping
./docker/docker_dev_paper.sh --no-live                                 # Use historical data only
```

#### Train Models
```bash
./docker/docker_dev_train.sh                  # Train with default epochs (10)
./docker/docker_dev_train.sh --epochs 50      # Train with 50 epochs
./docker/docker_dev_train.sh --gpu            # Force GPU training
./docker/docker_dev_train.sh --no-gpu         # Force CPU training
```

#### Check GPU Support
```bash
./docker/docker_dev_gpu_check.sh
```
Shows GPU availability and Docker GPU access status.

#### Start Dashboards
```bash
./docker/docker_dev_dashboards.sh
```
Starts both Streamlit dashboards in background:
- Paper Monitor: http://localhost:8501
- Feature Explorer: http://localhost:8502

#### Check Status
```bash
./docker/docker_dev_status.sh
```
Shows running containers and image info.

#### Stop All Containers
```bash
./docker/docker_dev_stop.sh
```
Stops all running AITrader containers.

## How It Works

All scripts mount your local code directories into the Docker container:

- `src/` → `/app/src` (your source code)
- `tests/` → `/app/tests` (your tests)
- `scripts/` → `/app/scripts` (scripts)
- `config/` → `/app/config` (configuration)
- `data/` → `/app/data` (data files)
- `models/` → `/app/models` (trained models)
- `logs/` → `/app/logs` (logs)

**This means:**
- ✅ You edit files locally with your favorite editor
- ✅ Changes are immediately available in the container
- ✅ No need to rebuild the image after code changes
- ✅ Logs, models, and data persist on your local filesystem
- ✅ **Auto-stops previous containers** to avoid port conflicts
- ✅ **GPU support** - Automatically uses NVIDIA GPU if available

## When to Rebuild

You only need to rebuild (`./docker/docker_dev_build.sh`) when:
- Adding new Python dependencies to `pyproject.toml`
- Changing system dependencies in the `Dockerfile`
- First time setup

## Example Workflow

```bash
# 1. Build image (first time only)
./docker/docker_dev_build.sh

# 2. Run tests to verify everything works
./docker/docker_dev_test.sh

# 3. Train models if needed
./docker/docker_dev_train.sh --epochs 10

# 4. Start paper trading
./docker/docker_dev_paper.sh --capital 100000

# 5. In another terminal, start dashboards
./docker/docker_dev_dashboards.sh

# 6. Check what's running
./docker/docker_dev_status.sh

# 7. When done, stop everything
./docker/docker_dev_stop.sh
```

## Troubleshooting

### GPU Support

Check GPU availability:
```bash
./docker/docker_dev_gpu_check.sh
```

If GPU is not accessible in Docker:
1. Install NVIDIA Container Toolkit:
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

2. Test GPU access:
```bash
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

### Image not found
```bash
./docker/docker_dev_build.sh
```

### Port already in use
```bash
# Stop all containers (auto-stops old ones)
./docker/docker_dev_stop.sh

# Or stop specific container
docker stop aitrader-monitor
```

### Permission issues
On Linux, Docker runs as root. If you get permission errors with mounted files:
```bash
# Make sure your user owns the directories
sudo chown -R $USER:$USER data/ logs/ models/
```

### View container logs
```bash
docker logs aitrader-monitor      # Dashboard logs
docker logs aitrader-explorer     # Feature explorer logs
docker logs -f aitrader-dev-paper # Follow paper trading logs
```

## Comparison: Docker vs Conda

| Feature | Docker Dev Scripts | Conda Base |
|---------|-------------------|------------|
| Environment | Python 3.12 (isolated) | Python 3.12.4 (base) |
| Dependencies | All in Docker image | Install with pip |
| Isolation | Complete isolation | Shares system Python |
| Reproducibility | 100% reproducible | Depends on system |
| Portability | Works anywhere Docker runs | Linux-specific |
| Setup Time | Build once (~5 min) | Install deps (~2 min) |
| Code Editing | Local files mounted | Direct access |
| GPU Support | Auto-detected NVIDIA GPU | Manual CUDA setup |

**Recommendation:** Use Docker for production-like testing and GPU training, conda for quick development iterations.

## Advanced Usage

### Run Custom Commands
```bash
./docker/docker_dev_shell.sh
# Then inside container:
python scripts/generate_plots.py
python scripts/run_backtest.py
pytest tests/integration/ -v
```

### Access Python REPL
```bash
./docker/docker_dev_shell.sh
# Then:
python
>>> from src.models.lstm_transformer import LSTMTransformer
>>> # Interactive exploration
```

### Debug with IPython
Add to requirements and rebuild:
```bash
pip install ipython
./docker/docker_dev_build.sh
```

Then use in shell:
```bash
./docker/docker_dev_shell.sh
ipython
```
