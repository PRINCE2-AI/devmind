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

from config import config
from logger import get_logger

log = get_logger("security")


# ============================================================
# Path validation
# ============================================================
def validate_path(
    filepath: str,
    *,
    base_dir: Path | None = None,
    must_exist: bool = False,
    allow_symlinks: bool = False,
) -> tuple[bool, str, Path | None]:
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
                (
                    "Security: Only files within the current working directory "
                    "can be accessed."
                ),
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
_SHELL_OPERATORS = re.compile(r"&&|\|\||[;|\n]")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {
    "builtin",
    "command",
    "env",
    "exec",
    "nice",
    "nohup",
    "setsid",
    "stdbuf",
    "time",
    "timeout",
    "xargs",
}
_WRAPPER_VALUE_OPTIONS = {
    "env": {"-u", "--unset", "-C", "--chdir"},
    "exec": {"-a"},
    "nice": {"-n", "--adjustment"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "time": {"-f", "--format", "-o", "--output"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {
        "-a",
        "--arg-file",
        "-d",
        "--delimiter",
        "-E",
        "--eof",
        "-I",
        "--replace",
        "-L",
        "--max-lines",
        "-n",
        "--max-args",
        "-P",
        "--max-procs",
        "-s",
        "--max-chars",
    },
}
_PRIVILEGE_TOOLS = {"sudo", "su", "doas", "pkexec"}
_SHELLS = {"bash", "sh", "zsh", "ksh", "fish", "dash", "powershell", "pwsh", "cmd"}
_INLINE_CODE = {
    "py": {"-c"},
    "python": {"-c"},
    "python3": {"-c"},
    "node": {"-e", "--eval"},
    "perl": {"-e"},
    "ruby": {"-e"},
    "php": {"-r"},
}


def _segments(command: str) -> list[str]:
    return [
        segment.strip()
        for segment in _SHELL_OPERATORS.split(command)
        if segment.strip()
    ]


def _split_env_string(value: str) -> list[str]:
    try:
        return shlex.split(value, posix=True)
    except ValueError:
        return value.split()


def _executable(tokens: list[str]) -> tuple[str, list[str]]:
    while tokens:
        if _ENV_ASSIGNMENT.match(tokens[0]):
            tokens = tokens[1:]
            continue
        head = Path(tokens[0]).name.lower()
        if head not in _WRAPPERS:
            break
        tokens = tokens[1:]

        while tokens and tokens[0].startswith("-"):
            option = tokens[0]
            tokens = tokens[1:]
            if option == "--":
                break
            if head == "env" and (
                option in {"-S", "--split-string"}
                or option.startswith("--split-string=")
                or (option.startswith("-S") and len(option) > 2)
            ):
                if option.startswith("--split-string="):
                    value = option.split("=", 1)[1]
                elif option.startswith("-S") and len(option) > 2:
                    value = option[2:]
                elif tokens:
                    value = tokens[0]
                    tokens = tokens[1:]
                else:
                    break
                tokens = _split_env_string(value) + tokens
                continue
            if option in _WRAPPER_VALUE_OPTIONS.get(head, set()) and tokens:
                tokens = tokens[1:]

        if head == "timeout" and tokens and not tokens[0].startswith("-"):
            tokens = tokens[1:]

    if not tokens:
        return "", []
    return Path(tokens[0]).name.lower(), tokens[1:]


def _shell_has_command_flag(arguments: list[str]) -> bool:
    for argument in arguments:
        lowered = argument.lower()
        if lowered in {"-c", "/c", "/k"}:
            return True
        if (
            lowered.startswith("-")
            and not lowered.startswith("--")
            and "c" in lowered[1:]
        ):
            return True
    return False


def _has_inline_flag(arguments: list[str], flags: set[str]) -> bool:
    short_flags = {
        flag[1:] for flag in flags if flag.startswith("-") and not flag.startswith("--")
    }
    for argument in arguments:
        lowered = argument.lower()
        if not lowered.startswith("-"):
            break
        if lowered in flags:
            return True
        if lowered.startswith("-") and not lowered.startswith("--"):
            if any(flag in lowered[1:] for flag in short_flags):
                return True
    return False


def validate_command(command: str) -> tuple[bool, str]:
    """
    Best-effort shell guardrail for the bash tool.

    This is a denylist over parsed shell segments, not an OS sandbox: a
    determined caller can still run arbitrary code through an allowed
    interpreter. The agent-level approval flow is the real boundary.

    Rules:
      - Must be a non-empty string
      - Null bytes rejected
      - Command substitution (backticks, `$()`) rejected
      - Blocked substrings from config.tool.blocked_commands rejected
      - Privilege escalation (sudo/su/doas/pkexec) rejected anywhere,
        including via env wrappers and absolute paths
      - Nested shell `-c` and inline interpreter code (`python -c`, `node -e`)
        rejected
      - base64 decode piped into a shell rejected
      - Length capped (10 KB)

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
    if _SUSPICIOUS_CHAR_RUNS.search(stripped):
        log.warning(f"Command substitution blocked: {stripped[:80]}")
        return False, "Command substitution (backticks or $()) is blocked."

    lower = stripped.lower()

    for blocked in config.tool.blocked_commands:
        if blocked.strip() and blocked.lower() in lower:
            log.warning(f"Blocked command pattern '{blocked}': {stripped[:80]}")
            return (
                False,
                (
                    "This command has been blocked for security reasons "
                    f"({blocked.strip()})."
                ),
            )

    if re.search(r"\bbase64\b[^|]*(?:-d|--decode)[^|]*\|\s*(?:ba|z|k)?sh\b", lower):
        return False, "Decoding base64 into a shell is blocked."

    for segment in _segments(stripped):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = segment.split()
        executable, arguments = _executable(tokens)
        if not executable:
            continue
        if executable in _PRIVILEGE_TOOLS:
            log.warning(f"Privilege escalation blocked: {stripped[:80]}")
            return False, "Privilege escalation commands (sudo/su/doas) are blocked."
        if executable == "eval":
            return False, "Shell eval is blocked."
        if executable in _SHELLS and _shell_has_command_flag(arguments):
            return False, "Nested shell execution (-c) is blocked."
        inline_flags = _INLINE_CODE.get(executable, set())
        if inline_flags and _has_inline_flag(arguments, inline_flags):
            return False, (
                f"Inline code execution via {executable} is blocked; "
                "write a script file instead."
            )

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
