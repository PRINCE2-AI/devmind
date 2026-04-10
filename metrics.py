"""
metrics.py — DevMind's Performance Metrics

Tracks observability data the cost tracker doesn't cover:
  - Request latencies (p50 / p95 / p99)
  - Success / failure counts
  - Retry counts
  - Tool invocation counts and error rates
  - Session uptime

Metrics are in-memory by default and persisted to
~/.devmind/metrics/session_<id>.json on exit if enabled in config.
"""

from __future__ import annotations

import atexit
import json
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import config
from logger import get_logger

log = get_logger("metrics")


# ============================================================
# Dataclasses
# ============================================================
@dataclass
class LatencySeries:
    """Rolling latency samples with percentile calculations."""
    samples: list[float] = field(default_factory=list)
    max_samples: int = 500  # keep memory bounded

    def record(self, value: float) -> None:
        self.samples.append(value)
        if len(self.samples) > self.max_samples:
            # Drop oldest 10% in one shot (avoids O(n) per append)
            drop = max(1, self.max_samples // 10)
            del self.samples[:drop]

    def percentile(self, p: float) -> float:
        if not self.samples:
            return 0.0
        ordered = sorted(self.samples)
        idx = min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1))))
        return round(ordered[idx], 4)

    @property
    def p50(self) -> float: return self.percentile(50)
    @property
    def p95(self) -> float: return self.percentile(95)
    @property
    def p99(self) -> float: return self.percentile(99)

    @property
    def mean(self) -> float:
        return round(sum(self.samples) / len(self.samples), 4) if self.samples else 0.0

    @property
    def count(self) -> int:
        return len(self.samples)


@dataclass
class ToolMetrics:
    """Per-tool invocation metrics."""
    invocations: int = 0
    errors: int = 0
    total_time_seconds: float = 0.0

    @property
    def error_rate(self) -> float:
        return round(self.errors / self.invocations, 4) if self.invocations else 0.0

    @property
    def avg_time_seconds(self) -> float:
        return round(self.total_time_seconds / self.invocations, 4) if self.invocations else 0.0


@dataclass
class MetricsSnapshot:
    """A serializable view of all current metrics."""
    session_id: str
    started_at: str
    uptime_seconds: float
    requests_total: int
    requests_succeeded: int
    requests_failed: int
    retries_total: int
    success_rate: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    latency_mean: float
    tools: dict[str, dict]


# ============================================================
# MetricsRegistry — the single source of truth
# ============================================================
class MetricsRegistry:
    """Thread-safe in-memory metrics store for the current session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.session_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._started: float = time.monotonic()
        self._started_wall: str = datetime.now().isoformat()

        self.requests_total: int = 0
        self.requests_succeeded: int = 0
        self.requests_failed: int = 0
        self.retries_total: int = 0
        self.latencies = LatencySeries()
        self.tools: dict[str, ToolMetrics] = {}

    # --------------------------------------------------------
    # Recording APIs
    # --------------------------------------------------------
    def record_request(self, duration: float, success: bool, retries: int = 0) -> None:
        with self._lock:
            self.requests_total += 1
            self.retries_total += retries
            if success:
                self.requests_succeeded += 1
            else:
                self.requests_failed += 1
            self.latencies.record(duration)

    def record_tool(self, name: str, duration: float, success: bool) -> None:
        with self._lock:
            tm = self.tools.setdefault(name, ToolMetrics())
            tm.invocations += 1
            tm.total_time_seconds += duration
            if not success:
                tm.errors += 1

    def record_retry(self, count: int = 1) -> None:
        with self._lock:
            self.retries_total += count

    # --------------------------------------------------------
    # Reading APIs
    # --------------------------------------------------------
    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            total = self.requests_total
            return MetricsSnapshot(
                session_id=self.session_id,
                started_at=self._started_wall,
                uptime_seconds=round(time.monotonic() - self._started, 2),
                requests_total=total,
                requests_succeeded=self.requests_succeeded,
                requests_failed=self.requests_failed,
                retries_total=self.retries_total,
                success_rate=round(self.requests_succeeded / total, 4) if total else 0.0,
                latency_p50=self.latencies.p50,
                latency_p95=self.latencies.p95,
                latency_p99=self.latencies.p99,
                latency_mean=self.latencies.mean,
                tools={name: asdict(m) | {
                    "error_rate": m.error_rate,
                    "avg_time_seconds": m.avg_time_seconds,
                } for name, m in self.tools.items()},
            )

    def format_summary(self) -> str:
        """Pretty-printed human summary."""
        s = self.snapshot()
        if s.requests_total == 0:
            return "No requests recorded yet."

        lines = [
            "",
            "=" * 46,
            "  DevMind Performance Metrics",
            "=" * 46,
            f"  Session         : {s.session_id}",
            f"  Uptime          : {s.uptime_seconds:.1f}s",
            f"  Requests        : {s.requests_total} "
            f"({s.requests_succeeded} ok, {s.requests_failed} fail)",
            f"  Success rate    : {s.success_rate * 100:.1f}%",
            f"  Retries         : {s.retries_total}",
            f"  Latency p50/p95 : {s.latency_p50:.2f}s / {s.latency_p95:.2f}s",
            f"  Latency p99/avg : {s.latency_p99:.2f}s / {s.latency_mean:.2f}s",
        ]
        if s.tools:
            lines.append("  Tools:")
            for name, m in sorted(s.tools.items()):
                lines.append(
                    f"    - {name}: {m['invocations']} calls, "
                    f"{m['error_rate'] * 100:.1f}% errors, "
                    f"avg {m['avg_time_seconds']:.3f}s"
                )
        lines.append("=" * 46)
        return "\n".join(lines)

    # --------------------------------------------------------
    # Persistence
    # --------------------------------------------------------
    def persist(self) -> Optional[Path]:
        """Write a JSON snapshot to disk. Returns the file path or None."""
        if self.requests_total == 0:
            return None
        try:
            metrics_dir = Path.home() / ".devmind" / "metrics"
            metrics_dir.mkdir(parents=True, exist_ok=True)
            path = metrics_dir / f"session_{self.session_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.snapshot()), f, indent=2)
            log.info(f"Metrics saved: {path}")
            return path
        except Exception as e:
            log.warning(f"Failed to persist metrics: {e}")
            return None


# ============================================================
# Global registry + helpers
# ============================================================
_registry: MetricsRegistry | None = None
_reg_lock = threading.Lock()


def get_registry() -> MetricsRegistry:
    """Return the global metrics registry, creating it on first use."""
    global _registry
    with _reg_lock:
        if _registry is None:
            _registry = MetricsRegistry()
            if config.metrics.persist_on_exit:
                atexit.register(lambda: _registry and _registry.persist())
        return _registry


def reset_registry() -> None:
    """Reset the global registry (mostly for tests)."""
    global _registry
    with _reg_lock:
        _registry = None


# Convenience wrappers — safe no-ops when metrics are disabled
def record_request(duration: float, success: bool, retries: int = 0) -> None:
    if not config.metrics.enabled:
        return
    get_registry().record_request(duration, success, retries)


def record_tool(name: str, duration: float, success: bool) -> None:
    if not config.metrics.enabled:
        return
    get_registry().record_tool(name, duration, success)


def format_metrics_summary() -> str:
    if not config.metrics.enabled:
        return "Metrics collection is disabled."
    return get_registry().format_summary()


if __name__ == "__main__":
    reg = get_registry()
    reg.record_request(0.23, True, 0)
    reg.record_request(1.12, True, 1)
    reg.record_request(0.87, False, 2)
    reg.record_tool("bash_tool", 0.05, True)
    reg.record_tool("bash_tool", 0.09, False)
    reg.record_tool("file_read_tool", 0.01, True)
    print(reg.format_summary())
