"""
tests/test_cost_tracker.py — Tests for the cost tracking system
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cost_tracker import (
    init_tracker, track_call, calculate_cost,
    format_cost_summary, get_session, MODEL_PRICES,
)


class TestCostCalculation:
    def test_sonnet_pricing(self):
        """Sonnet pricing should calculate correctly"""
        cost = calculate_cost(1_000_000, 0, "claude-sonnet-4-6")
        assert abs(cost - 3.0) < 0.001  # $3 per million input tokens

    def test_output_token_cost(self):
        """Output tokens should cost more than input tokens"""
        input_cost = calculate_cost(1000, 0, "claude-sonnet-4-6")
        output_cost = calculate_cost(0, 1000, "claude-sonnet-4-6")
        assert output_cost > input_cost

    def test_zero_tokens(self):
        """Zero tokens should equal zero cost"""
        assert calculate_cost(0, 0, "claude-sonnet-4-6") == 0.0

    def test_default_model_fallback(self):
        """Unknown model should fall back to default pricing"""
        cost = calculate_cost(1000, 1000, "claude-unknown-model")
        assert cost > 0

    def test_all_models_have_both_prices(self):
        """Every model entry must have input and output prices"""
        for model, prices in MODEL_PRICES.items():
            assert "input" in prices, f"{model} is missing input price"
            assert "output" in prices, f"{model} is missing output price"
            assert prices["input"] >= 0
            assert prices["output"] >= 0

    def test_opus_most_expensive(self):
        """Opus should cost more than Sonnet"""
        opus_cost = calculate_cost(1000, 1000, "claude-opus-4-5")
        sonnet_cost = calculate_cost(1000, 1000, "claude-sonnet-4-6")
        assert opus_cost > sonnet_cost


class TestSessionTracking:
    def setup_method(self):
        """Start a fresh session before each test"""
        init_tracker("claude-sonnet-4-6")

    def test_track_single_call(self):
        """A single API call should be tracked correctly"""
        track_call(500, 200, "claude-sonnet-4-6")
        session = get_session()

        assert session.total_calls == 1
        assert session.total_input_tokens == 500
        assert session.total_output_tokens == 200

    def test_track_multiple_calls(self):
        """Multiple calls should accumulate correctly"""
        track_call(1000, 500, "claude-sonnet-4-6")
        track_call(2000, 800, "claude-sonnet-4-6")

        session = get_session()
        assert session.total_calls == 2
        assert session.total_input_tokens == 3000
        assert session.total_output_tokens == 1300

    def test_cost_accumulates(self):
        """Total cost should be greater than zero after a call"""
        track_call(100000, 50000, "claude-sonnet-4-6")
        session = get_session()
        assert session.total_cost_usd > 0

    def test_calls_log_maintained(self):
        """Each call should be logged individually"""
        track_call(100, 50, "claude-sonnet-4-6")
        track_call(200, 100, "claude-sonnet-4-6")
        session = get_session()
        assert len(session.calls_log) == 2
        assert session.calls_log[0]["call_num"] == 1
        assert session.calls_log[1]["call_num"] == 2

    def test_session_has_id(self):
        """Session must have a non-empty ID"""
        session = get_session()
        assert session.session_id
        assert len(session.session_id) > 0


class TestFormatSummary:
    def test_empty_session_message(self):
        """Should return a message when no calls have been made"""
        init_tracker("claude-sonnet-4-6")
        summary = format_cost_summary()
        assert "No API calls" in summary or "0" in summary

    def test_summary_shows_totals(self):
        """Summary must include all key information"""
        init_tracker("claude-sonnet-4-6")
        track_call(1000, 500, "claude-sonnet-4-6")
        summary = format_cost_summary()

        assert "1" in summary        # total calls
        assert "1,000" in summary    # input tokens (formatted)
        assert "500" in summary      # output tokens
        assert "$" in summary        # cost in USD

    def test_summary_shows_model(self):
        """Summary must include the model name"""
        init_tracker("claude-sonnet-4-6")
        track_call(100, 50, "claude-sonnet-4-6")
        summary = format_cost_summary()
        assert "claude-sonnet-4-6" in summary


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
