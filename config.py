"""
config.py — DevMind's Centralized Configuration
All settings in one place — no hardcoded values scattered across files.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ModelConfig:
    """LLM model settings."""
    name: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    streaming: bool = True


@dataclass(frozen=True)
class RetryConfig:
    """Retry logic settings."""
    max_retries: int = 3
    base_delay: float = 2.0  # seconds
    retryable_codes: tuple[str, ...] = (
        "529", "overloaded", "rate_limit",
        "timeout", "connection", "502", "503",
    )


@dataclass(frozen=True)
class ToolConfig:
    """Tool execution settings."""
    bash_timeout: int = 30  # seconds
    file_read_max_lines: int = 200
    grep_max_results: int = 20
    blocked_commands: tuple[str, ...] = (
        "rm -rf /", "rm -rf /*", "mkfs", "dd if=",
        ":(){", "fork bomb", "chmod -R 777 /",
        "wget http", "curl http",
    )
    # Only these text extensions are searched by grep
    text_extensions: frozenset[str] = frozenset({
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
        ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
        ".html", ".css", ".scss", ".less", ".xml", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".conf", ".env", ".sh", ".bash", ".zsh",
        ".md", ".txt", ".rst", ".csv", ".sql", ".r", ".R", ".lua",
        ".dockerfile", ".makefile", ".gitignore", ".editorconfig",
    })
    skip_dirs: frozenset[str] = frozenset({
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".mypy_cache", ".pytest_cache", "dist", "build", ".tox",
    })


@dataclass(frozen=True)
class HistoryConfig:
    """Conversation history settings."""
    max_messages: int = 20
    summary_threshold: int = 16  # Summarize after this many messages


@dataclass(frozen=True)
class AppConfig:
    """Master application configuration."""
    model: ModelConfig = field(default_factory=ModelConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    tool: ToolConfig = field(default_factory=ToolConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    debug: bool = field(default_factory=lambda: os.getenv("DEVMIND_DEBUG", "").lower() == "true")


# Global config instance — import and use across all modules
config = AppConfig()
