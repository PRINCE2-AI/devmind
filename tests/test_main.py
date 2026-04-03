"""
tests/test_main.py — Tests for the REPL and UI functions
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import smart_truncate_history, show_banner, show_help


class TestSmartTruncateHistory:
    def test_short_history_unchanged(self):
        """Short history should not be modified"""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = smart_truncate_history(history, max_messages=20, summary_threshold=16)
        assert result == history

    def test_long_history_truncated(self):
        """Long history should be truncated"""
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})

        result = smart_truncate_history(history, max_messages=20, summary_threshold=16)
        assert len(result) <= 22  # max_messages + summary pair

    def test_summary_at_start(self):
        """Truncated history should start with a summary"""
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})

        result = smart_truncate_history(history, max_messages=20, summary_threshold=16)
        assert "summary" in result[0]["content"].lower()

    def test_recent_messages_preserved(self):
        """Most recent messages must be preserved exactly"""
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})

        result = smart_truncate_history(history, max_messages=20, summary_threshold=16)
        last = result[-1]
        assert "Answer 29" in last["content"]

    def test_threshold_boundary(self):
        """History exactly at threshold should not be truncated"""
        history = []
        for i in range(8):
            history.append({"role": "user", "content": f"Q{i}"})
            history.append({"role": "assistant", "content": f"A{i}"})

        # 16 messages, threshold 16 — should not truncate
        result = smart_truncate_history(history, max_messages=20, summary_threshold=16)
        assert len(result) == 16


class TestUIFunctions:
    def test_show_banner_no_error(self):
        """Banner should display without raising an error"""
        try:
            show_banner()
        except Exception as e:
            assert False, f"show_banner() raised an exception: {e}"

    def test_show_help_no_error(self):
        """Help panel should display without raising an error"""
        try:
            show_help()
        except Exception as e:
            assert False, f"show_help() raised an exception: {e}"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
