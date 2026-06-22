"""D11-OPS — Data integrity probes for validating Parquet partitions."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.logging import get_logger
from src.data.store import DataStore
from src.ops.session_helper import expected_bar_count

_log = get_logger("D11-OPS")


class DataProbe:
    """Probe to verify completeness and integrity of historical data partitions."""

    def __init__(self, store: DataStore, gap_threshold_pct: float = 0.05) -> None:
        self.store = store
        self.gap_threshold_pct = gap_threshold_pct

    def verify_stored_integrity(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        month_key: str,  # Format: "YYYY-MM"
    ) -> dict[str, any]:
        """Check a single month's Parquet partition for row count and health.

        Returns a status dictionary with health state (ok, degraded, or missing).
        """
        try:
            year, month = map(int, month_key.split("-"))
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid month format: '{month_key}'. Expected YYYY-MM.",
            }

        # Locate partition path
        partition_path = self.store._base / "raw" / instrument.value / timeframe.value / f"{month_key}.parquet"

        if not partition_path.exists():
            return {
                "status": "missing",
                "instrument": instrument.value,
                "timeframe": timeframe.value,
                "month": month_key,
                "actual_bars": 0,
                "expected_bars": 0,
                "gap_pct": 1.0,
                "message": "Parquet file does not exist",
            }

        try:
            # Read Parquet row count
            df = pd.read_parquet(partition_path)
            actual_bars = len(df)
        except Exception as e:
            _log.error("data_probe_corrupted_file", path=str(partition_path), error=str(e))
            return {
                "status": "corrupted",
                "instrument": instrument.value,
                "timeframe": timeframe.value,
                "month": month_key,
                "actual_bars": 0,
                "expected_bars": 0,
                "gap_pct": 1.0,
                "message": f"Corrupted Parquet file: {e}",
            }

        # Calculate expected open market bars
        expected_bars = expected_bar_count(timeframe, year, month)

        if expected_bars <= 0:
            return {
                "status": "ok",
                "instrument": instrument.value,
                "timeframe": timeframe.value,
                "month": month_key,
                "actual_bars": actual_bars,
                "expected_bars": 0,
                "gap_pct": 0.0,
                "message": f"Expected bar count could not be computed (Timeframe: {timeframe.value})",
            }

        gap_pct = max(0.0, 1.0 - (actual_bars / expected_bars))
        status = "ok"
        message = "Data partition matches expected counts"

        # Check gap threshold
        if gap_pct > self.gap_threshold_pct:
            status = "degraded"
            message = (
                f"Degraded partition: {actual_bars}/{expected_bars} bars "
                f"({gap_pct:.1%} gap exceeds threshold of {self.gap_threshold_pct:.1%})"
            )

        return {
            "status": status,
            "instrument": instrument.value,
            "timeframe": timeframe.value,
            "month": month_key,
            "actual_bars": actual_bars,
            "expected_bars": expected_bars,
            "gap_pct": gap_pct,
            "message": message,
        }
