"""D02-DATA — global lock so refresh, gap-fill, and live poll don't hammer Dukascopy."""

from __future__ import annotations

import threading

DUKASCOPY_LOCK = threading.Lock()