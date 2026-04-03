"""
exceptions.py — DevMind's Custom Exception Hierarchy
Each error type has its own class — easier to debug and handle.
"""


class DevMindError(Exception):
    """Base exception for all DevMind errors."""
    pass


class ConfigError(DevMindError):
    """Configuration errors — missing API key, invalid settings."""
    pass


class ToolError(DevMindError):
    """Tool execution errors — file not found, command failed."""

    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        super().__init__(f"[{tool_name}] {message}")


class AgentError(DevMindError):
    """Errors during agent / LLM interaction."""
    pass


class RetryExhaustedError(AgentError):
    """All retry attempts failed."""

    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"DevMind failed after {attempts} attempt(s). "
            f"Last error: {last_error}"
        )


class SecurityError(ToolError):
    """Security violation — blocked command, path traversal attempt."""

    def __init__(self, tool_name: str, message: str):
        super().__init__(tool_name, f"SECURITY: {message}")


class FileNotFoundError_(ToolError):
    """Requested file does not exist."""

    def __init__(self, filepath: str):
        super().__init__("file", f"File not found: {filepath}")
        self.filepath = filepath
