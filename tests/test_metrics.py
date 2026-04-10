"""
tests/test_metrics.py - Tests for the metrics registry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metrics import (
    LatencySeries, MetricsRegistry, reset_registry, get_registry,
    record_request, record_tool, format_metrics_summary,
)


class TestLatencySeries:
    def test_empty_percentile_zero(self):
        s = LatencySeries()
        assert s.percentile(50) == 0.0

    def test_single_sample(self):
        s = LatencySeries()
        s.record(1.0)
        assert s.percentile(50) == 1.0
        assert s.percentile(99) == 1.0

    def test_percentile_ordering(self):
        s = LatencySeries()
        for v in range(1, 101):
            s.record(float(v))
        p50 = s.percentile(50)
        p95 = s.percentile(95)
        assert p50 < p95
        assert 49 <= p50 <= 51
        assert 94 <= p95 <= 96

    def test_bounded_samples(self):
        s = LatencySeries(max_samples=10)
        for v in range(50):
            s.record(float(v))
        # Should only retain last 10
        assert len(s.samples) <= 10


class TestMetricsRegistry:
    def test_record_request_success(self):
        reg = MetricsRegistry()
        reg.record_request(duration=0.5, success=True, retries=0)
        snap = reg.snapshot()
        assert snap.requests_total == 1
        assert snap.requests_succeeded == 1
        assert snap.requests_failed == 0

    def test_record_request_failure(self):
        reg = MetricsRegistry()
        reg.record_request(duration=0.5, success=False, retries=2)
        snap = reg.snapshot()
        assert snap.requests_failed == 1
        assert snap.retries_total == 2

    def test_record_tool(self):
        reg = MetricsRegistry()
        reg.record_tool("bash_tool", 0.1, True)
        reg.record_tool("bash_tool", 0.2, False)
        snap = reg.snapshot()
        assert "bash_tool" in snap.tools
        assert snap.tools["bash_tool"]["invocations"] == 2
        assert snap.tools["bash_tool"]["errors"] == 1

    def test_format_summary_contains_text(self):
        reg = MetricsRegistry()
        reg.record_request(0.1, True)
        reg.record_tool("grep_tool", 0.05, True)
        out = reg.format_summary()
        assert isinstance(out, str)
        assert len(out) > 0


class TestGlobalHelpers:
    def setup_method(self):
        reset_registry()

    def teardown_method(self):
        reset_registry()

    def test_record_request_global(self):
        record_request(duration=0.1, success=True)
        snap = get_registry().snapshot()
        assert snap.requests_total == 1

    def test_record_tool_global(self):
        record_tool("file_read_tool", 0.05, True)
        snap = get_registry().snapshot()
        assert "file_read_tool" in snap.tools

    def test_format_metrics_summary(self):
        record_request(0.1, True)
        out = format_metrics_summary()
        assert isinstance(out, str)
