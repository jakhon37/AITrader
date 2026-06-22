"""D06-EXECUTION — Live trading mode gate.

Restricts live trading sessions to production environments and requires explicit
two-factor shell environment confirmation.
"""

from __future__ import annotations

import os

from src.core.config import AppConfig
from src.core.contracts import ExecutionMode
from src.core.exceptions import ExecutionError


class ModeGate:
    """Hard gate controlling execution mode shifts (paper vs live)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def check(self) -> None:
        """Validate execution parameters.

        Raises:
            ExecutionError: If execution mode is live but confirmation env var is missing,
                            or if live trading is attempted in a non-production environment.
        """
        mode = self.config.core.execution_mode

        # Normalise to string/enum for checks
        mode_str = mode.value.lower() if hasattr(mode, "value") else str(mode).lower()

        if mode_str == "live":
            # 1. Require manual shell confirmation
            if os.getenv("LIVE_TRADING_CONFIRMED") != "YES":
                raise ExecutionError(
                    "Live mode requires LIVE_TRADING_CONFIRMED=YES in shell env. "
                    "Cannot be in .env — must be set explicitly in session."
                )

            # 2. Require environment target to be prod
            if self.config.env != "prod":
                raise ExecutionError("Live trading only allowed in prod environment.")
