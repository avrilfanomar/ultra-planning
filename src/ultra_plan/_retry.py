from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

from ._logging import get_logger

T = TypeVar("T")

log = get_logger(__name__)


def retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    is_retryable: Callable[[BaseException], bool],
    sleep: Callable[[float], None] | None = None,
    rand: Callable[[float, float], float] | None = None,
) -> T:
    """Invoke `fn()` with exponential-backoff retries on retryable failures.

    The exception is considered retryable when `is_retryable(exc)` returns True.
    Non-retryable exceptions propagate immediately. After `max_attempts` total
    tries, the last exception is re-raised.

    Delay sequence (with jitter): base_delay, 2*base_delay, 4*base_delay, ...
    capped at `max_delay`. Actual sleep is `random.uniform(0, delay)` to spread
    contention.
    """
    # Resolve defaults lazily so test fixtures patching time.sleep / random.uniform
    # at module level take effect (defaults bound at def-time would not).
    _sleep = sleep if sleep is not None else time.sleep
    _rand = rand if rand is not None else random.uniform

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 - explicit by design
            if not is_retryable(exc) or attempt == max_attempts:
                raise
            last_exc = exc
            delay_cap = min(base_delay * (2 ** (attempt - 1)), max_delay)
            wait = _rand(0, delay_cap)
            log.warning(
                "retry %d/%d after %.2fs: %s",
                attempt,
                max_attempts,
                wait,
                exc,
            )
            _sleep(wait)
    # Unreachable: the loop either returns or re-raises.
    assert last_exc is not None
    raise last_exc
