#!/usr/bin/env python3
"""Project Overview & Health Check.

A lightweight, robust script to quickly inspect the repository state,
active configurations, data assets, model registry, and development tools
without loading heavy external dependencies or running slow processes.
Can be executed in a new session on host or inside Docker.
"""

from __future__ import annotations

import os
import sys
import json
import platform
import subprocess
from pathlib import Path

# Color utilities for terminal formatting
COLOR_GREEN = "\033[92m"
COLOR_BLUE = "\033[94m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

def print_section(title: str) -> None:
    print(f"\n{COLOR_BOLD}{COLOR_BLUE}=== {title} ==={COLOR_RESET}")

def print_status(label: str, status: bool, detail: str = "") -> None:
    symbol = f"{COLOR_GREEN}✓{COLOR_RESET}" if status else f"{COLOR_RED}✗{COLOR_RESET}"
    detail_str = f" ({detail})" if detail else ""
    print(f"  {symbol} {label}{detail_str}")

def main() -> None:
    print(f"{COLOR_BOLD}{COLOR_GREEN}🔍 AITrader Project Overview & Status Report{COLOR_RESET}")
    project_root = Path(__file__).resolve().parent.parent
    
    # 1. System & Environment
    print_section("System & Environment")
    print(f"  Project Root:  {project_root}")
    print(f"  OS / Platform: {platform.system()} {platform.release()}")
    print(f"  Python Path:   {sys.executable}")
    print(f"  Python Ver:    {platform.python_version()}")
    
    # Environment Variables
    env_vars = ["ENV", "CONFIG_DIR", "PYTHONPATH"]
    for var in env_vars:
        val = os.environ.get(var)
        print(f"  Env {var}:" + (f" {COLOR_GREEN}{val}{COLOR_RESET}" if val else f" {COLOR_YELLOW}Not Set{COLOR_RESET}"))

    # 2. Workspace Directories Check
    print_section("Core Directories")
    dirs = ["src", "config", "tests", "data", "models", "scripts", "docs", "dashboards"]
    for d in dirs:
        path = project_root / d
        exists = path.is_dir()
        print_status(f"{d}/", exists, f"exists" if exists else "missing")

    # 3. Active Configuration Check
    print_section("Configuration")
    env = os.environ.get("ENV", "dev")
    config_dir_env = os.environ.get("CONFIG_DIR")
    config_dir = Path(config_dir_env) if config_dir_env else project_root / "config"
    config_file = config_dir / f"{env}.yaml"
    
    config_loaded = False
    config_data = {}
    
    # Try reading configuration directly via PyYAML if available
    try:
        import yaml
        if config_file.exists():
            with open(config_file) as f:
                config_data = yaml.safe_load(f) or {}
            config_loaded = True
            print_status(f"Configuration file found: config/{env}.yaml", True)
        else:
            print_status(f"Configuration file config/{env}.yaml does not exist", False)
    except ImportError:
        print_status("PyYAML library not available in host Python environment", False)
        # Attempt basic line parser as fallback
        if config_file.exists():
            try:
                with open(config_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and ':' in line:
                            k, v = line.split(':', 1)
                            config_data[k.strip()] = v.strip()
                config_loaded = True
                print_status(f"Configuration parsed fallback: config/{env}.yaml", True)
            except Exception:
                pass

    if config_loaded:
        # Display selected parsed values
        data_sec = config_data.get("data", {})
        model_sec = config_data.get("model", {})
        risk_sec = config_data.get("risk", {})
        exec_sec = config_data.get("execution", {})
        
        symbols = data_sec.get("symbols", []) if isinstance(data_sec, dict) else []
        timeframe = data_sec.get("timeframe", "N/A") if isinstance(data_sec, dict) else "N/A"
        model_type = model_sec.get("model_type", "N/A") if isinstance(model_sec, dict) else "N/A"
        broker = exec_sec.get("broker", "N/A") if isinstance(exec_sec, dict) else "N/A"
        max_pos = risk_sec.get("max_position_pct", "N/A") if isinstance(risk_sec, dict) else "N/A"
        
        print(f"    - Target Symbols:  {symbols}")
        print(f"    - Timeframe:       {timeframe}")
        print(f"    - Selected Model:  {COLOR_BOLD}{model_type}{COLOR_RESET}")
        print(f"    - Active Broker:   {broker}")
        print(f"    - Max Position %:  {max_pos}")
        
    # Attempt high-level validation check via Pydantic AppConfig
    sys.path.insert(0, str(project_root / "src"))
    try:
        # Set config dir env temporarily for loader testing
        os.environ["CONFIG_DIR"] = str(config_dir)
        from core.config import AppConfig
        app_config = AppConfig.from_env()
        print_status("Pydantic Config Schema Validation: PASS", True)
    except Exception as e:
        print_status("Pydantic Config Schema Validation: FAIL/SKIP", False, str(e))

    # 4. Data Assets Status
    print_section("Data Assets")
    raw_data_dir = project_root / "data" / "raw"
    fixtures_dir = project_root / "tests" / "fixtures"
    
    raw_parquet = (
        list(raw_data_dir.rglob("*.parquet")) if raw_data_dir.is_dir() else []
    )
    raw_csv = list(raw_data_dir.glob("*.csv")) if raw_data_dir.is_dir() else []
    fixture_files = list(fixtures_dir.glob("*.csv")) if fixtures_dir.is_dir() else []

    raw_size_mb = sum(f.stat().st_size for f in raw_parquet) / (1024 * 1024)
    print(
        f"  Raw OHLCV (data/raw/): {len(raw_parquet)} parquet files"
        f" ({raw_size_mb:.1f} MB)"
    )
    if raw_csv:
        print(f"  Legacy CSV in data/raw/: {len(raw_csv)} found")
        for f in raw_csv:
            size_kb = f.stat().st_size / 1024
            print(f"    - {f.name} ({size_kb:.1f} KB)")
        
    print(f"  Test Fixtures (tests/fixtures/): {len(fixture_files)} found")
    for f in fixture_files:
        size_kb = f.stat().st_size / 1024
        print(f"    - {f.name} ({size_kb:.1f} KB)")

    # 5. Model Registry Status
    print_section("Model Registry")
    registry_index = project_root / "models" / "registry" / "index.json"
    if registry_index.exists():
        try:
            with open(registry_index) as f:
                idx = json.load(f)
            models = idx.get("models", {})
            versions_dict = idx.get("versions", {})
            print_status(f"Registry Index Loaded: models/registry/index.json", True)
            print(f"    - Registered Models: {list(models.keys())}")
            for m, vers in models.items():
                print(f"      * {m}: {len(vers)} versions (Latest: {vers[-1] if vers else 'None'})")
            print(f"    - Total Versions Tracked: {len(versions_dict)}")
        except Exception as e:
            print_status("Error parsing models/registry/index.json", False, str(e))
    else:
        print_status("Model Registry index.json not found", False, "No models registered yet")

    # 6. Tooling & Development Checks
    print_section("Tooling Check (Host)")
    tools = ["ruff", "mypy", "pytest", "docker"]
    for t in tools:
        try:
            res = subprocess.run(["which", t], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            installed = res.returncode == 0
            detail = res.stdout.strip() if installed else "not in PATH"
            print_status(t, installed, detail)
        except Exception:
            print_status(t, False, "unknown error")

    # 7. Cheat Sheet / Common Commands
    print_section("Quick Development Cheat Sheet")
    print(f"  {COLOR_BOLD}Docker Dev Environment:{COLOR_RESET}")
    print("    - Build dev image:     ./docker/docker_dev_build.sh")
    print("    - Run tests in Docker:  ./docker/docker_dev_test.sh")
    print("    - Interactive shell:   ./docker/docker_dev_shell.sh")
    print("    - Start dashboards:    ./docker/docker_dev_dashboards.sh")
    print("")
    print(f"  {COLOR_BOLD}Local Dev Environment:{COLOR_RESET}")
    print("    - Install dependencies: pip install -e \".[dev,live_data,dashboard]\"")
    print("    - Download real data:  python scripts/download_sample_data.py")
    print("    - Run test suite:      PYTHONPATH=src CONFIG_DIR=config pytest tests -v")
    print("    - Lint check:          ruff check src tests scripts")
    print("    - Type check:          mypy src")
    print("    - Run Backtest:        python scripts/run_backtest.py")
    print("    - Start Web UI + paper:  ./scripts/start_webui.sh")

if __name__ == "__main__":
    main()
