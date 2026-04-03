"""
tests/test_config.py — Tests for the configuration system
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AppConfig, ModelConfig, RetryConfig, ToolConfig, HistoryConfig


class TestModelConfig:
    def test_default_model(self):
        """Default model should be claude-sonnet-4-6"""
        cfg = ModelConfig()
        assert cfg.name == "claude-sonnet-4-6"

    def test_default_max_tokens(self):
        """Default max tokens should be 4096"""
        cfg = ModelConfig()
        assert cfg.max_tokens == 4096

    def test_streaming_default_true(self):
        """Streaming should be enabled by default"""
        cfg = ModelConfig()
        assert cfg.streaming is True


class TestRetryConfig:
    def test_max_retries_default(self):
        """Default should be 3 retries"""
        cfg = RetryConfig()
        assert cfg.max_retries == 3

    def test_retryable_codes_present(self):
        """Important error codes must be present"""
        cfg = RetryConfig()
        assert "529" in cfg.retryable_codes
        assert "overloaded" in cfg.retryable_codes
        assert "rate_limit" in cfg.retryable_codes

    def test_no_duplicate_codes(self):
        """No duplicate error codes allowed"""
        cfg = RetryConfig()
        assert len(cfg.retryable_codes) == len(set(cfg.retryable_codes))


class TestToolConfig:
    def test_bash_timeout(self):
        """Bash timeout should be 30 seconds"""
        cfg = ToolConfig()
        assert cfg.bash_timeout == 30

    def test_blocked_commands_present(self):
        """Dangerous commands must be in the blocklist"""
        cfg = ToolConfig()
        assert any("rm -rf" in cmd for cmd in cfg.blocked_commands)

    def test_text_extensions_has_python(self):
        """Python files must be in text extensions"""
        cfg = ToolConfig()
        assert ".py" in cfg.text_extensions

    def test_skip_dirs_has_git(self):
        """.git must be in skip directories"""
        cfg = ToolConfig()
        assert ".git" in cfg.skip_dirs


class TestAppConfig:
    def test_app_config_has_all_sections(self):
        """AppConfig must contain all sub-configs"""
        cfg = AppConfig()
        assert isinstance(cfg.model, ModelConfig)
        assert isinstance(cfg.retry, RetryConfig)
        assert isinstance(cfg.tool, ToolConfig)
        assert isinstance(cfg.history, HistoryConfig)

    def test_frozen_config(self):
        """Config must be immutable (frozen dataclass)"""
        cfg = ModelConfig()
        try:
            cfg.name = "something-else"
            assert False, "Should have raised FrozenInstanceError"
        except Exception:
            pass  # Expected — frozen dataclass


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
