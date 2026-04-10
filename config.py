"""
config.py — DevMind's Centralized Configuration
All settings in one place — no hardcoded values scattered across files.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ModelConfig:
    """LLM model settings."""
    name: str = field(default_factory=lambda: os.getenv("DEVMIND_MODEL", "claude-sonnet-4-6"))
    max_tokens: int = field(default_factory=lambda: _env_int("DEVMIND_MAX_TOKENS", 4096))
    streaming: bool = True


@dataclass(frozen=True)
class RetryConfig:
    """Retry logic settings with exponential backoff + jitter."""
    max_retries: int = field(default_factory=lambda: _env_int("DEVMIND_MAX_RETRIES", 4))
    base_delay: float = field(default_factory=lambda: _env_float("DEVMIND_RETRY_BASE_DELAY", 1.0))
    max_delay: float = field(default_factory=lambda: _env_float("DEVMIND_RETRY_MAX_DELAY", 30.0))
    backoff_factor: float = 2.0
    jitter: float = 0.25
    retryable_codes: tuple = (
        "529", "overloaded", "rate_limit",
        "timeout", "connection", "502", "503", "504",
        "ECONNRESET", "Temporary failure",
    )


@dataclass(frozen=True)
class RateLimitConfig:
    """Client-side rate limiting (token bucket)."""
    enabled: bool = field(default_factory=lambda: _env_bool("DEVMIND_RATE_LIMIT", True))
    requests_per_minute: int = field(default_factory=lambda: _env_int("DEVMIND_RPM", 50))
    burst: int = field(default_factory=lambda: _env_int("DEVMIND_BURST", 10))


@dataclass(frozen=True)
class ToolConfig:
    """Tool execution settings."""
    bash_timeout: int = field(default_factory=lambda: _env_int("DEVMIND_BASH_TIMEOUT", 30))
    file_read_max_lines: int = 200
    file_write_max_bytes: int = 5 * 1024 * 1024
    file_read_max_bytes: int = 2 * 1024 * 1024
    grep_max_results: int = 20
    grep_max_files: int = 5000
    blocked_commands: tuple = (
        "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf ~/",
        "mkfs", "dd if=", "dd of=/dev/",
        ":(){", "fork bomb", "chmod -R 777 /",
        "wget ", "curl ",
        "shutdown", "reboot", "halt", "poweroff",
        "> /dev/sda", "mv / ",
    )
    text_extensions: frozenset = frozenset({
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
        ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
        ".html", ".css", ".scss", ".less", ".xml", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".conf", ".env", ".sh", ".bash", ".zsh",
        ".md", ".txt", ".rst", ".csv", ".sql", ".r", ".R", ".lua",
        ".dockerfile", ".makefile", ".gitignore", ".editorconfig",
    })
    skip_dirs: frozenset = frozenset({
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".mypy_cache", ".pytest_cache", "dist", "build", ".tox",
    })


@dataclass(frozen=True)
class HistoryConfig:
    """Conversation history settings."""
    max_messages: int = 20
    summary_threshold: int = 16


@dataclass(frozen=True)
class PersistenceConfig:
    """Conversation save/load settings."""
    enabled: bool = field(default_factory=lambda: _env_bool("DEVMIND_PERSIST", True))
    sessions_dir: str = field(
        default_factory=lambda: os.getenv(
            "DEVMIND_SESSIONS_DIR",
            str(os.path.expanduser("~/.devmind/sessions")),
        )
    )
    autosave_every: int = field(default_factory=lambda: _env_int("DEVMIND_AUTOSAVE", 5))


@dataclass(frozen=True)
class MetricsConfig:
    """Performance metrics tracking."""
    enabled: bool = field(default_factory=lambda: _env_bool("DEVMIND_METRICS", True))
    persist_on_exit: bool = True


@dataclass(frozen=True)
class PluginConfig:
    """Plugin/extension system settings."""
    enabled: bool = field(default_factory=lambda: _env_bool("DEVMIND_PLUGINS", True))
    plugins_dir: str = field(
        default_factory=lambda: os.getenv(
            "DEVMIND_PLUGINS_DIR",
            str(os.path.expanduser("~/.devmind/plugins")),
        )
    )


@dataclass(frozen=True)
class AppConfig:
    """Master application configuration."""
    model: ModelConfig = field(default_factory=ModelConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    tool: ToolConfig = field(default_factory=ToolConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    plugins: PluginConfig = field(default_factory=PluginConfig)
    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    debug: bool = field(default_factory=lambda: _env_bool("DEVMIND_DEBUG", False))


config = AppConfig()
