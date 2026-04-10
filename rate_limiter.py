"""
rate_limiter.py — Client-side rate limiting (token bucket)

A lightweight, thread-safe token bucket that smooths request bursts before
they reach the Anthropic API. Uses monotonic time for correctness under
clock changes, and exposes both a blocking `acquire()` and a non-blocking
`try_acquire()` so callers can decide how to react.

The default configuration comes from `config.rate_limit`, but an instance
can be constructed with any rate/burst for tests or custom agents.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from config import config
from exceptions import RateLimitError
from logger import get_logger

log = get_logger("rate_limiter")


@dataclass
class TokenBucket:
    """
    Classic token bucket.

    Args:
        rate_per_sec: Sustained refill rate in tokens per second.
        capacity: Maximum burst size the bucket can hold.
    """
    rate_per_sec: float
    capacity: float

    def __post_init__(self) -> None:
        if self.rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._tokens: float = float(self.capacity)
        self._last: float = time.monotonic()
        self._lock = threading.Lock()

    # --------------------------------------------------------
    # Internal refill
    # --------------------------------------------------------
    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.rate_per_sec,
            )
            self._last = now

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------
    @property
    def tokens(self) -> float:
        """Current (refilled) token count — useful for tests & telemetry."""
        with self._lock:
            self._refill_locked()
            return self._tokens

    def try_acquire(self, cost: float = 1.0) -> tuple[bool, float]:
        """
        Attempt to acquire `cost` tokens without blocking.

        Returns:
            (acquired, wait_seconds)
            - acquired=True and wait_seconds=0 on success
            - acquired=False and wait_seconds>0 if not enough tokens
        """
        with self._lock:
            self._refill_locked()
            if self._tokens >= cost:
                self._tokens -= cost
                return True, 0.0
            deficit = cost - self._tokens
            wait = deficit / self.rate_per_sec
            return False, wait

    def acquire(self, cost: float = 1.0, timeout: float | None = None) -> bool:
        """
        Block until `cost` tokens are available or `timeout` is reached.

        Returns:
            True on success, False if timed out.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            ok, wait = self.try_acquire(cost)
            if ok:
                return True
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait = min(wait, remaining)
            log.debug(f"Rate limit: waiting {wait:.2f}s for {cost} token(s)")
            time.sleep(max(wait, 0.01))


# ============================================================
# Global limiter — configured from config.rate_limit
# ============================================================
_global_limiter: TokenBucket | None = None
_global_lock = threading.Lock()


def get_limiter() -> TokenBucket | None:
    """
    Return the global rate limiter, or None if disabled in config.
    Lazily constructed on first use.
    """
    global _global_limiter
    if not config.rate_limit.enabled:
        return None
    with _global_lock:
        if _global_limiter is None:
            rpm = max(1, config.rate_limit.requests_per_minute)
            burst = max(1, config.rate_limit.burst)
            _global_limiter = TokenBucket(
                rate_per_sec=rpm / 60.0,
                capacity=float(burst),
            )
            log.debug(
                f"Global rate limiter: {rpm} req/min, burst={burst}"
            )
        return _global_limiter


def reset_limiter() -> None:
    """Clear the cached global limiter (used by tests)."""
    global _global_limiter
    with _global_lock:
        _global_limiter = None


def acquire_or_raise(cost: float = 1.0) -> None:
    """
    Block on the global limiter. If the wait would exceed a reasonable
    ceiling (2x burst window), raise RateLimitError instead of hanging.
    """
    limiter = get_limiter()
    if limiter is None:
        return

    # Ceiling: at most enough time to refill 2x the burst
    max_wait = (limiter.capacity * 2) / limiter.rate_per_sec
    ok = limiter.acquire(cost=cost, timeout=max_wait)
    if not ok:
        raise RateLimitError(max_wait)


if __name__ == "__main__":
    # Quick smoke test
    bucket = TokenBucket(rate_per_sec=2.0, capacity=3.0)
    for i in range(5):
        ok, wait = bucket.try_acquire()
        print(f"#{i} ok={ok} wait={wait:.2f} tokens={bucket.tokens:.2f}")
        time.sleep(0.2)
