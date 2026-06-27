#!/usr/bin/env python3
"""Paper trading soak status — Docker Web UI stack + API health."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "http://localhost:8000"
UI_URL = "http://localhost:5173"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _fetch_json(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _docker_status() -> list[dict[str, str]]:
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--filter", "name=aitrader", "--format", "{{.Names}}|{{.Status}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    rows: list[dict[str, str]] = []
    for line in out.strip().splitlines():
        if "|" not in line:
            continue
        name, status = line.split("|", 1)
        rows.append({"name": name, "status": status})
    return rows


def _audit_summary() -> dict[str, int]:
    audit = PROJECT_ROOT / "logs" / "audit.jsonl"
    counts: dict[str, int] = {}
    if not audit.exists():
        return counts
    with open(audit) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = row.get("event_type", "unknown")
            counts[et] = counts.get(et, 0) + 1
    return counts


def _parquet_summary() -> tuple[int, float]:
    raw = PROJECT_ROOT / "data" / "raw"
    if not raw.is_dir():
        return 0, 0.0
    files = list(raw.rglob("*.parquet"))
    size_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
    return len(files), size_mb


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"AITrader Paper Soak Status — {now}")
    print(f"Project: {PROJECT_ROOT}")
    print()

    containers = _docker_status()
    if containers:
        print("Docker containers:")
        for c in containers:
            print(f"  {c['name']}: {c['status']}")
    else:
        print("Docker: no aitrader containers running")
        print("  Start: ./scripts/start_webui.sh")
    print()

    pipeline = _fetch_json("/api/health/pipeline")
    ops = _fetch_json("/api/health/ops")
    soak = _fetch_json("/api/health/soak")
    portfolio = _fetch_json("/api/portfolio/state")

    if pipeline:
        comps = pipeline.get("components", {})
        running = sum(1 for c in comps.values() if c.get("running"))
        print(f"Pipeline: {running}/{len(comps)} components running")
        print(f"  Replay active: {pipeline.get('replay_active')}")
        print(f"  Live spine paused: {pipeline.get('live_signal_pipeline_paused')}")
    else:
        print(f"Pipeline: API unreachable ({API_BASE})")

    if ops:
        print(f"Ops health: {ops.get('status', 'unknown')}")
        for probe in ("data_freshness", "signal_flow", "execution", "model_registry"):
            block = ops.get(probe, {})
            if block:
                print(f"  {probe}: {block.get('status')} — {block.get('message', '')}")

    if soak:
        print()
        print("Paper soak (Tier 4):")
        print(f"  Status:    {soak.get('status')}")
        print(f"  Progress:  {soak.get('message', '')}")
        if soak.get("started_at"):
            print(f"  Started:   {soak.get('started_at')}")
            print(f"  Elapsed:   {soak.get('elapsed_days', 0):.2f} days ({soak.get('elapsed_hours', 0):.1f} h)")
            print(f"  Remaining: {soak.get('remaining_days', 0):.2f} days")
            print(f"  Target:    {soak.get('target_days', 14)} days")
    print()

    if portfolio:
        print("Portfolio (paper):")
        print(f"  Balance:  ${portfolio.get('balance', 0):,.2f}")
        print(f"  Equity:   ${portfolio.get('equity', 0):,.2f}")
        print(f"  Drawdown: {portfolio.get('drawdown_pct', 0):.2f}%")
        print(f"  Open positions: {len(portfolio.get('open_positions', []))}")
        print(f"  Realized PnL today: ${portfolio.get('realized_pnl_today', 0):,.2f}")
    print()

    audit = _audit_summary()
    if audit:
        print("Audit log (logs/audit.jsonl):")
        for key in sorted(audit):
            print(f"  {key}: {audit[key]}")
    else:
        print("Audit log: no events yet (logs/audit.jsonl)")
    print()

    n_parquet, size_mb = _parquet_summary()
    print(f"Data store: {n_parquet} parquet files ({size_mb:.1f} MB in data/raw/)")
    print()
    print(f"Web UI: {UI_URL}")
    print(f"API:    {API_BASE}")
    return 0 if pipeline else 1


if __name__ == "__main__":
    sys.exit(main())