"""Unit tests for paper soak tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.ops.paper_soak import build_soak_report, load_soak_state, record_soak_start


def test_record_soak_start_is_idempotent(tmp_path: Path) -> None:
    first = record_soak_start(data_dir=tmp_path)
    second = record_soak_start(data_dir=tmp_path)
    assert first["started_at"] == second["started_at"]
    assert load_soak_state(tmp_path)["target_days"] == 14


def test_build_soak_report_not_started(tmp_path: Path) -> None:
    report = build_soak_report(data_dir=tmp_path, pipeline_running=False)
    assert report["status"] == "not_started"
    assert report["complete"] is False


def test_build_soak_report_in_progress(tmp_path: Path) -> None:
    path = tmp_path / "state" / "paper_soak.json"
    path.parent.mkdir(parents=True)
    started = datetime.now(timezone.utc) - timedelta(days=3)
    path.write_text(
        '{"started_at": "%s", "target_days": 14, "mode": "paper"}' % started.isoformat()
    )
    report = build_soak_report(data_dir=tmp_path, pipeline_running=True, ops_status="ok")
    assert report["status"] == "in_progress"
    assert 2.9 < report["elapsed_days"] < 3.1
    assert report["ops_status"] == "ok"


def test_model_probe_ok_in_dev_mode(tmp_path: Path) -> None:
    import json

    from src.ops.probes.model_probe import ModelRegistryProbe

    registry = tmp_path / "index.json"
    meta_dir = tmp_path / "metadata"
    meta_dir.mkdir()
    meta_file = meta_dir / "lstm_transformer_v1.json"
    meta_file.write_text(json.dumps({"status": "dev"}))
    registry.write_text(
        json.dumps({"versions": {"lstm_transformer:v1": "metadata/lstm_transformer_v1.json"}})
    )
    dev_result = ModelRegistryProbe(registry_path=registry, require_prod=False).check(
        "lstm_transformer"
    )
    prod_result = ModelRegistryProbe(registry_path=registry, require_prod=True).check(
        "lstm_transformer"
    )
    assert dev_result["status"] == "ok"
    assert prod_result["status"] == "degraded"