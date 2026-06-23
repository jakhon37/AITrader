"""File-retention and report limits cleanup logic for D08-BACKTEST."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_old_reports(reports_dir: Path, retention_days: int, retention_count: int) -> None:
    """Enforce report storage limits."""
    # Clean by age
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    
    # Read files in reports directory
    files = list(reports_dir.glob("*.*"))
    for f in files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff_date:
                f.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete old report {f.name}: {e}")

    # Re-list after age cleanup, and clean by total count
    files = []
    for ext in [".json", ".html"]:
        files.extend(list(reports_dir.glob(f"*{ext}")))
        
    # Sort by creation time (oldest first)
    files.sort(key=lambda x: x.stat().st_mtime)
    
    # We enforce retention_count per file type or total.
    # Let's enforce it per file type to make sure we don't delete matching HTML/JSON sets unequally.
    for ext in [".json", ".html"]:
        type_files = [f for f in files if f.suffix == ext]
        if len(type_files) > retention_count:
            to_delete = type_files[:len(type_files) - retention_count]
            for f in to_delete:
                try:
                    f.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete report {f.name} for limit: {e}")
