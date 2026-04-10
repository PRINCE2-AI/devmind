"""
security.py — Hardened validation for user / tool inputs

Centralises the checks that keep DevMind safe:
  - Path traversal / symlink escape protection
  - Command sanitization for the bash tool
  - Generic input validators (length, type, encoding)

Every public helper returns `(ok: bool, message: str, value)` so callers
can surface the result to the user without raising inside the tool path.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Optional

from config import config
from logger import get_logger

log = get_logger("security")


# ============================================================
# Path validation
# ============================================================
def validate_path(
    filepath: str,
    *,
    base_dir: Optional[Path] = None,
    must_exist: bool = False,
    allow_symlinks: bool = False,
) -> tuple[bool, str, Optional[Path]]:
    """
    Validate a filesystem path.

    Rules:
      - Input must be a non-empty string
      - Null bytes are rejected
      - Resolved path must be inside `base_dir` (defaults to cwd)
      - Symlinks that escape the base_dir are rejected

    Returns:
        (is_valid, error_message, resolved_path)
    """
    if not isinstance(filepath, str) or not filepath.strip():
        return False, "Path must be a non-empty string.", None
    if "\x00" in filepath:
        log.warning("Null byte in path blocked")
        return False, "Invalid path (null byte).", None

    try:
        base = (base_dir or Path(os.getcwd())).resolve()

        # First, resolve without strict=True so missing files are allowed
        candidate = Path(filepath)
        if not candidate.is_absolute():
            candidate = base / candidate
        resolved = candidate.resolve()

        # Block traversal using relative_to
        try:
            resolved.relative_to(base)
        except ValueError:
            log.warning(f"Path traversal attempt blocked: {filepath!r}")
            return (
                False,
                "Security: Only files within the current working directory can be accessed.",
                None,
            )

        if must_exist and not resolved.exists():
            return False, f"File not found: {filepath}", None

        # Detect symlink escapes even when relative_to passes
        if not allow_symlinks and resolved.exists() and resolved.is_symlink():
            real = resolved.resolve(strict=True)
            try:
                real.relative_to(base)
            except ValueError:
                log.warning(f"Symlink escape blocked: {filepath!r} → {real}")
                return False, "Security: symlink points outside the workspace.", None

        return True, "", resolved

    except Exception as e:
        return False, f"Invalid path: {e}", None


# ============================================================
# Command validation
# ============================================================
_SUSPICIOUS_CHAR_RUNS = re.compile(r"`.+`|\$\([^)]+\)")


def validate_command(command: str) -> tuple[bool, str]:
    """
    Validate a shell command before running it.

    Rules:
      - Must be a non-empty string
      - Null bytes rejected
      - Must not contain any blocked substring from config.tool.blocked_commands
      - Tokens starting with `sudo` are blocked
      - Length is capped (10 KB) to avoid abuse

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(command, str):
        return False, "Command must be a string."
    stripped = command.strip()
    if not stripped:
        return False, "No command provided."
    if "\x00" in command:
        return False, "Invalid command (null byte)."
    if len(command) > 10_000:
        return False, "Command too long (max 10 KB)."

    lower = stripped.lower()

    for blocked in config.tool.blocked_commands:
        if blocked.strip() and blocked.lower() in lower:
            log.warning(f"Blocked command pattern '{blocked}': {stripped[:80]}")
            return False, f"This command has been blocked for security reasons ({blocked.strip()})."

    # Block sudo and su outright
    try:
        tokens = shlex.split(stripped, posix=True)
    except ValueError:
        # Unbalanced quotes etc. — allow bash itself to error out
        tokens = stripped.split()

    if tokens and tokens[0] in ("sudo", "su", "doas"):
        log.warning(f"Privilege escalation blocked: {stripped[:80]}")
        return False, "Privilege escalation commands (sudo/su/doas) are blocked."

    return True, ""


# ============================================================
# Generic string validator
# ============================================================
def validate_string(
    value,
    *,
    name: str = "value",
    max_length: int = 100_000,
    allow_empty: bool = False,
) -> tuple[bool, str]:
    """
    Basic string guardrails shared across tools.
    """
    if not isinstance(value, str):
        return False, f"{name} must be a string."
    if not allow_empty and not value.strip():
        return False, f"{name} must not be empty."
    if len(value) > max_length:
        return False, f"{name} too long (max {max_length} characters)."
    if "\x00" in value:
        return False, f"{name} contains a null byte."
    return True, ""


if __name__ == "__main__":
    print(validate_command("echo hi"))
    print(validate_command("sudo rm -rf /"))
    print(validate_command("curl https://evil"))
    print(validate_path("README.md"))
    print(validate_path("../../etc/passwd"))
