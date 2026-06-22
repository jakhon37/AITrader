"""Signal ID generation.

Always use new_signal_id() — never inline str(uuid.uuid4()) in calling code.
"""

from __future__ import annotations

import uuid


def new_signal_id() -> str:
    """Return a new UUID4 string for use as a signal_id."""
    return str(uuid.uuid4())
