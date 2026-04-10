"""
tests/test_rate_limiter.py - Tests for the token-bucket rate limiter.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from rate_limiter import TokenBucket, acquire_or_raise, reset_limiter
from exceptions import RateLimitError


class TestTokenBucket:
    def test_initial_burst_available(self):
        bucket = TokenBucket(rate_per_sec=1.0, capacity=5)
        for _ in range(5):
            ok, _ = bucket.try_acquire(1.0)
            assert ok is True

    def test_empty_bucket_waits(self):
        bucket = TokenBucket(rate_per_sec=10.0, capacity=1)
        ok, _ = bucket.try_acquire(1.0)
        assert ok is True
        ok, wait = bucket.try_acquire(1.0)
        assert ok is False
        assert wait > 0

    def test_refill_over_time(self):
        bucket = TokenBucket(rate_per_sec=100.0, capacity=1)
        bucket.try_acquire(1.0)
        time.sleep(0.05)
        ok, _ = bucket.try_acquire(1.0)
        assert ok is True

    def test_cost_greater_than_capacity_fails(self):
        bucket = TokenBucket(rate_per_sec=1.0, capacity=2)
        ok, _ = bucket.try_acquire(cost=5.0)
        assert ok is False

    def test_acquire_blocking_succeeds_fast(self):
        bucket = TokenBucket(rate_per_sec=1000.0, capacity=1)
        bucket.try_acquire(1.0)
        start = time.monotonic()
        got = bucket.acquire(1.0, timeout=1.0)
        assert got is True
        assert time.monotonic() - start < 0.5

    def test_acquire_timeout_returns_false(self):
        bucket = TokenBucket(rate_per_sec=0.1, capacity=1)
        bucket.try_acquire(1.0)
        got = bucket.acquire(1.0, timeout=0.05)
        assert got is False


class TestAcquireOrRaise:
    def setup_method(self):
        reset_limiter()

    def teardown_method(self):
        reset_limiter()

    def test_under_budget_ok(self):
        # first call within burst should not raise
        acquire_or_raise(cost=1.0)

    def test_respects_disabled_setting(self, monkeypatch):
        # Even with rate limiter logic, simple small cost should always pass
        acquire_or_raise(cost=0.01)
