"""FastAPI router for config read/update operations on instruments.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
import yaml
from fastapi import APIRouter, Body, HTTPException

from src.core.contracts import Instrument

router = APIRouter(prefix="/config", tags=["config"])


def _get_instruments_path() -> Path:
    """Return path to config/instruments.yaml."""
    config_dir = Path(os.getenv("CONFIG_DIR", "config"))
    return config_dir / "instruments.yaml"


@router.get("/{instrument}")
async def get_instrument_config(instrument: str) -> Dict[str, Any]:
    """Retrieve configuration for a specific instrument from instruments.yaml."""
    try:
        inst = Instrument(instrument.upper())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    path = _get_instruments_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="instruments.yaml configuration file not found.")

    try:
        with open(path, "r") as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read instruments config: {e}")

    # Case-insensitive matching
    for k, block in config_data.items():
        if k.upper() == inst.value:
            return block

    raise HTTPException(status_code=404, detail=f"Instrument '{instrument}' not found in instruments.yaml")


@router.put("/{instrument}")
async def update_instrument_config(
    instrument: str, payload: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Update configuration values for an instrument in instruments.yaml."""
    try:
        inst = Instrument(instrument.upper())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    path = _get_instruments_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="instruments.yaml configuration file not found.")

    try:
        with open(path, "r") as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read instruments config: {e}")

    inst_key = None
    for k in config_data:
        if k.upper() == inst.value:
            inst_key = k
            break

    if not inst_key:
        raise HTTPException(status_code=404, detail=f"Instrument '{instrument}' not found in instruments.yaml")

    # Update settings
    config_data[inst_key].update(payload)

    try:
        with open(path, "w") as f:
            yaml.safe_dump(config_data, f, default_flow_style=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write configuration: {e}")

    return {"status": "success", "config": config_data[inst_key]}
