from __future__ import annotations

import os

DEFAULT_TIMEOUT = 1800


def resolve_timeout(explicit: int | None = None) -> int | None:
    """Resolve effective subprocess timeout in seconds.

    Precedence: explicit arg > ULTRA_PLAN_TIMEOUT env > DEFAULT_TIMEOUT.
    A value of 0 or negative disables the timeout (returns None).
    """
    if explicit is not None:
        return explicit if explicit > 0 else None
    raw = os.environ.get("ULTRA_PLAN_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_TIMEOUT
    try:
        value = int(raw)
    except ValueError as e:
        raise RuntimeError(f"ULTRA_PLAN_TIMEOUT must be an integer, got {raw!r}") from e
    return value if value > 0 else None
