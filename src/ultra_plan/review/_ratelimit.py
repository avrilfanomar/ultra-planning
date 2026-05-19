from __future__ import annotations

import threading
import time


class TokenBucket:
    """Thread-safe token-bucket rate limiter keyed by client IP.

    Capacity is `capacity` tokens; refill rate is `refill_per_sec`. Each
    `check(ip)` consumes one token; returns True when allowed, False when the
    bucket is empty (deny / 429).

    Defaults: 30 req capacity, refilled at 0.5/s (i.e. 30 req per minute steady
    state with bursts up to 30).
    """

    def __init__(self, capacity: int = 30, refill_per_sec: float = 0.5) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_sec <= 0:
            raise ValueError("refill_per_sec must be positive")
        self._capacity = float(capacity)
        self._refill = float(refill_per_sec)
        self._lock = threading.Lock()
        # {ip: (tokens_remaining, last_refill_monotonic)}
        self._state: dict[str, tuple[float, float]] = {}

    def check(self, ip: str, *, now: float | None = None) -> bool:
        ts = now if now is not None else time.monotonic()
        with self._lock:
            tokens, last = self._state.get(ip, (self._capacity, ts))
            elapsed = max(0.0, ts - last)
            tokens = min(self._capacity, tokens + elapsed * self._refill)
            if tokens >= 1.0:
                tokens -= 1.0
                self._state[ip] = (tokens, ts)
                return True
            self._state[ip] = (tokens, ts)
            return False
