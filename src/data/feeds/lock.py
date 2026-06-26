"""D02-DATA — Dukascopy access coordination (lock + dedicated executor)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

# Serialize network calls to Dukascopy; live polls skip when already held.
DUKASCOPY_LOCK = threading.Lock()

# All Dukascopy HTTP work runs here so the default asyncio pool stays free for API/ops.
DUKASCOPY_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="dukascopy",
)


def dukascopy_lock_held() -> bool:
    """True when another thread is inside a Dukascopy fetch."""
    acquired = DUKASCOPY_LOCK.acquire(blocking=False)
    if acquired:
        DUKASCOPY_LOCK.release()
        return False
    return True