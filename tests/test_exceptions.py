"""
tests/test_exceptions.py — Tests for the custom exception hierarchy
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from exceptions import (
    DevMindError, ConfigError, ToolError,
    AgentError, RetryExhaustedError, SecurityError,
)


class TestExceptionHierarchy:
    def test_config_error_is_devmind_error(self):
        """ConfigError must be a subclass of DevMindError"""
        assert issubclass(ConfigError, DevMindError)

    def test_tool_error_is_devmind_error(self):
        """ToolError must be a subclass of DevMindError"""
        assert issubclass(ToolError, DevMindError)

    def test_agent_error_is_devmind_error(self):
        """AgentError must be a subclass of DevMindError"""
        assert issubclass(AgentError, DevMindError)

    def test_retry_exhausted_is_agent_error(self):
        """RetryExhaustedError must be a subclass of AgentError"""
        assert issubclass(RetryExhaustedError, AgentError)

    def test_security_error_is_tool_error(self):
        """SecurityError must be a subclass of ToolError"""
        assert issubclass(SecurityError, ToolError)


class TestToolError:
    def test_tool_name_in_message(self):
        """Tool name must appear in the error message"""
        err = ToolError("bash_tool", "Command failed")
        assert "bash_tool" in str(err)
        assert "Command failed" in str(err)


class TestRetryExhaustedError:
    def test_attempts_stored(self):
        """Attempt count must be stored on the error"""
        original = ValueError("API error")
        err = RetryExhaustedError(3, original)
        assert err.attempts == 3
        assert err.last_error is original

    def test_message_contains_info(self):
        """Error message must contain attempt count and last error"""
        err = RetryExhaustedError(3, ValueError("timeout"))
        assert "3" in str(err)
        assert "timeout" in str(err)


class TestSecurityError:
    def test_security_prefix(self):
        """Security errors must have a SECURITY prefix"""
        err = SecurityError("bash_tool", "Blocked command")
        assert "SECURITY" in str(err)


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
