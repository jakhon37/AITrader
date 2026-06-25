"""Unit tests for D05 model registry lookup."""

from __future__ import annotations

import json
from pathlib import Path

from src.decision.registry import resolve_active_model_version


def test_resolve_active_model_version_none_when_missing(tmp_path: Path) -> None:
    assert resolve_active_model_version("lstm_transformer", tmp_path / "missing.json") is None


def test_resolve_active_model_version_finds_prod(tmp_path: Path) -> None:
    registry = tmp_path / "index.json"
    meta_dir = tmp_path / "metadata"
    meta_dir.mkdir()
    meta_file = meta_dir / "lstm_transformer_v1.json"
    meta_file.write_text(json.dumps({"status": "prod"}))
    registry.write_text(
        json.dumps(
            {
                "versions": {"lstm_transformer:v1": "metadata/lstm_transformer_v1.json"},
            }
        )
    )
    assert resolve_active_model_version("lstm_transformer", registry) == "v1"