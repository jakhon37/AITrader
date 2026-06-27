"""User-facing display preferences (chart timezone for Telegram + UI)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/preferences", tags=["preferences"])


class ChartTimezoneBody(BaseModel):
    timezone: str = Field(
        ...,
        description="IANA timezone (e.g. Asia/Seoul, Europe/London) or UTC",
        json_schema_extra={"example": "Asia/Seoul"},
    )


@router.get("/chart-timezone")
async def get_chart_timezone(request: Request) -> dict[str, str]:
    prefs = getattr(request.app.state, "display_prefs", None)
    if prefs is None:
        raise HTTPException(status_code=500, detail="Display preferences not initialized.")
    return {"timezone": prefs.get_chart_timezone()}


@router.put("/chart-timezone")
async def set_chart_timezone(
    request: Request,
    body: ChartTimezoneBody,
) -> dict[str, Any]:
    prefs = getattr(request.app.state, "display_prefs", None)
    if prefs is None:
        raise HTTPException(status_code=500, detail="Display preferences not initialized.")
    saved = prefs.set_chart_timezone(body.timezone)
    return {"status": "ok", "timezone": saved}