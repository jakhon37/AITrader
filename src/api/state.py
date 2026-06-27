"""Shared API module state — only non-signal globals (signals live in SQLite)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.decision.chart_markers import ChartMarkerStore

chart_marker_store: Optional["ChartMarkerStore"] = None