"""
tools.py — DevMind's Tools (The Agent's Hands)

Security features:
  - Path traversal + symlink-escape protection (security.py)
  - Dangerous command blocking on bash (security.py)
  - Binary file filtering on grep
  - Null-byte and length validation on all text inputs
  - Configurable via config.py

Observability:
  - Every tool invocation is timed and recorded in metrics.py
  - Failures are counted separately so we can compute per-tool error rates
"""

from __future__ import annotations

import functools
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from config import config
from logger import get_logger
from metrics import record_tool
from security import validate_command, validate_path, validate_string
from plugins import collect_plugin_tools

log = get_logger("tools")


def _validate_path(filepath: str):
    """Backward-compatible wrapper for the old (is_valid, error, path) signature."""
    return validate_path(filepath)


def _timed(tool_name: str):
    """Decorator that times a tool invocation and records it in metrics."""
    def deco(fn: Callable[..., str]) -> Callable[..., str]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> str:
            start = time.monotonic()
            success = True
            try:
                result = fn(*args, **kwargs)
                low = (result or "").lower()
                if any(low.startswith(prefix) for prefix in (
                    "error", "security:", "timeout", "permission denied",
                )):
                    success = False
                return result
            except Exception as e:
                success = False
                log.error(f"{tool_name} crashed: {e}")
                return f"Error in {tool_name}: {e}"
            finally:
                record_tool(tool_name, time.monotonic() - start, success)
        return wrapper
    return deco


# ============================================================
# TOOL 1: BashTool
# ============================================================
@tool
def bash_tool(command: str) -> str:
    """
    Run a command in the terminal.
    Use when: running code, git commands, listing files.
    Example: bash_tool("python --version")
    """
    return _bash_impl(command)


@_timed("bash_tool")
def _bash_impl(command: str) -> str:
    ok, err = validate_command(command)
    if not ok:
        return err

    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=config.tool.bash_timeout,
            cwd=os.getcwd(),
        )
        output = result.stdout.strip()
        error = result.stderr.strip()

        log.debug(f"bash_tool: '{command[:50]}' -> exit {result.returncode}")

        if result.returncode != 0 and error:
            return f"Error (code {result.returncode}):\n{error}"
        return output if output else "(Command ran with no output)"

    except subprocess.TimeoutExpired:
        log.warning(f"Command timed out: {command[:80]}")
        return f"Timeout! Command took longer than {config.tool.bash_timeout} seconds."
    except Exception as e:
        log.error(f"bash_tool error: {e}")
        return f"Error running command: {e}"


# ============================================================
# TOOL 2: FileReadTool
# ============================================================
@tool
def file_read_tool(filepath: str) -> str:
    """
    Read the contents of any file.
    Use when: viewing code, reading a README, checking a config file.
    Example: file_read_tool("main.py")
    """
    return _file_read_impl(filepath)


@_timed("file_read_tool")
def _file_read_impl(filepath: str) -> str:
    ok, err = validate_string(filepath, name="filepath")
    if not ok:
        return f"Error: {err}"

    is_valid, error, path = validate_path(filepath)
    if not is_valid:
        return error

    try:
        if not path.exists():
            return f"File not found: {filepath}"
        if not path.is_file():
            return f"This is a directory, not a file: {filepath}"

        size = path.stat().st_size
        max_bytes = config.tool.file_read_max_bytes
        if size > max_bytes:
            return (
                f"File is too large to read: {size} bytes "
                f"(max {max_bytes}). Use grep_tool or read a slice."
            )

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        max_lines = config.tool.file_read_max_lines
        if len(lines) > max_lines:
            content = "".join(lines[:max_lines])
            log.debug(f"File truncated: {filepath} ({len(lines)} lines -> {max_lines})")
            return f"{content}\n\n... (file is large, showing first {max_lines} lines)"

        return "".join(lines) if lines else "(File is empty)"

    except PermissionError:
        return f"Permission denied: {filepath}"
    except Exception as e:
        log.error(f"file_read_tool error: {e}")
        return f"Error reading file: {e}"


# ============================================================
# TOOL 3: FileWriteTool
# ============================================================
@tool
def file_write_tool(filepath: str, content: str) -> str:
    """
    Write content to a file (create new or fully overwrite).
    Use this for new files only. To edit an existing file use file_edit_tool.
    Example: file_write_tool("hello.py", "print('Hello World')")
    """
    return _file_write_impl(filepath, content)


@_timed("file_write_tool")
def _file_write_impl(filepath: str, content: str) -> str:
    ok, err = validate_string(filepath, name="filepath")
    if not ok:
        return f"Error: {err}"
    ok, err = validate_string(
        content,
        name="content",
        max_length=config.tool.file_write_max_bytes,
        allow_empty=True,
    )
    if not ok:
        return f"Error: {err}"

    is_valid, error, path = validate_path(filepath)
    if not is_valid:
        return error

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        lines = len(content.splitlines())
        log.info(f"File written: {filepath} ({lines} lines)")
        return f"File written: {filepath} ({lines} lines)"

    except PermissionError:
        return f"Permission denied: {filepath}"
    except Exception as e:
        log.error(f"file_write_tool error: {e}")
        return f"Error writing file: {e}"


# ============================================================
# TOOL 4: FileEditTool
# ============================================================
@tool
def file_edit_tool(filepath: str, old_text: str, new_text: str) -> str:
    """
    Find a specific piece of text in a file and replace it.
    The rest of the file is not touched — only that section changes.
    Use when: fixing a bug, updating a function.
    Example: file_edit_tool("main.py", "print('hello')", "print('Hello World')")

    Rules:
    - old_text must exist exactly in the file (copy-paste it)
    - old_text must appear only once (must be unique)
    - Returns an error if old_text is not found
    """
    return _file_edit_impl(filepath, old_text, new_text)


@_timed("file_edit_tool")
def _file_edit_impl(filepath: str, old_text: str, new_text: str) -> str:
    ok, err = validate_string(filepath, name="filepath")
    if not ok:
        return f"Error: {err}"
    ok, err = validate_string(old_text, name="old_text", allow_empty=False)
    if not ok:
        return f"Error: {err}"
    ok, err = validate_string(new_text, name="new_text", allow_empty=True)
    if not ok:
        return f"Error: {err}"

    is_valid, error, path = validate_path(filepath)
    if not is_valid:
        return error

    if old_text == new_text:
        return "old_text and new_text are identical — nothing to change."

    try:
        if not path.exists():
            return f"File not found: {filepath}"

        original = path.read_text(encoding="utf-8")

        count = original.count(old_text)
        if count == 0:
            lines_preview = "\n".join(original.splitlines()[:10])
            return (
                f"old_text not found in file: '{old_text[:50]}...'\n"
                f"First 10 lines of file:\n{lines_preview}"
            )

        if count > 1:
            return (
                f"old_text found {count} times — ambiguous!\n"
                f"Provide more specific old_text so only one location matches."
            )

        updated = original.replace(old_text, new_text, 1)
        path.write_text(updated, encoding="utf-8")

        old_lines = len(old_text.splitlines())
        new_lines = len(new_text.splitlines())
        diff = new_lines - old_lines
        diff_str = f"+{diff}" if diff >= 0 else str(diff)

        log.info(f"File edited: {filepath} ({old_lines} -> {new_lines} lines)")
        return (
            f"File edited: {filepath}\n"
            f"Replaced {old_lines} lines -> {new_lines} lines ({diff_str} lines)"
        )

    except PermissionError:
        return f"Permission denied: {filepath}"
    except Exception as e:
        log.error(f"file_edit_tool error: {e}")
        return f"Error editing file: {e}"


# ============================================================
# TOOL 5: GrepTool
# ============================================================
@tool
def grep_tool(pattern: str, directory: str = ".") -> str:
    """
    Search for a word or pattern across the entire codebase.
    Use when: finding a function, locating where a variable is used.
    Example: grep_tool("def main", ".") or grep_tool("import os")
    """
    return _grep_impl(pattern, directory)


@_timed("grep_tool")
def _grep_impl(pattern: str, directory: str = ".") -> str:
    if not pattern or not pattern.strip():
        return "Pattern is empty! Please provide a search pattern."

    try:
        results = []
        search_dir = Path(directory)

        if not search_dir.exists():
            return f"Directory not found: {directory}"

        max_results = config.tool.grep_max_results
        max_files = config.tool.grep_max_files
        files_scanned = 0

        for file_path in search_dir.rglob("*"):
            if files_scanned >= max_files:
                break
            if len(results) >= max_results:
                break

            if any(skip in file_path.parts for skip in config.tool.skip_dirs):
                continue
            if not file_path.is_file():
                continue

            suffix = file_path.suffix.lower()
            if suffix and suffix not in config.tool.text_extensions:
                continue

            files_scanned += 1
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if pattern.lower() in line.lower():
                            rel_path = file_path.relative_to(search_dir)
                            results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                            if len(results) >= max_results:
                                break
            except Exception:
                continue

        if not results:
            return f"'{pattern}' not found anywhere."

        output = "\n".join(results)
        if len(results) == max_results:
            output += f"\n\n(There may be more results — showing first {max_results})"

        log.debug(f"grep_tool: '{pattern}' -> {len(results)} results")
        return output

    except Exception as e:
        log.error(f"grep_tool error: {e}")
        return f"Search error: {e}"


# ============================================================
# TOOL 6: ListFilesTool
# ============================================================
@tool
def list_files_tool(directory: str = ".") -> str:
    """
    List the files in a directory.
    Use when: understanding project structure.
    Example: list_files_tool(".") or list_files_tool("src")
    """
    return _list_files_impl(directory)


@_timed("list_files_tool")
def _list_files_impl(directory: str = ".") -> str:
    try:
        path = Path(directory)
        if not path.exists():
            return f"Directory not found: {directory}"
        if not path.is_dir():
            return f"This is a file, not a directory: {directory}"

        items = []

        for item in sorted(path.iterdir()):
            if item.name in config.tool.skip_dirs or item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"[DIR]  {item.name}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size // (1024 * 1024)}MB"
                items.append(f"[FILE] {item.name} ({size_str})")

        if not items:
            return f"Directory is empty: {directory}"

        return f"{directory} — {len(items)} items:\n" + "\n".join(items)

    except Exception as e:
        log.error(f"list_files_tool error: {e}")
        return f"Error listing directory: {e}"


# ============================================================
# All registered tools (core + plugins)
# ============================================================
_CORE_TOOLS = [
    bash_tool,
    file_read_tool,
    file_write_tool,
    file_edit_tool,
    grep_tool,
    list_files_tool,
]


def _load_plugin_tools():
    if not config.plugins.enabled:
        return []
    try:
        return collect_plugin_tools(config.plugins.plugins_dir)
    except Exception as e:
        log.error(f"Plugin loader failed: {e}")
        return []


ALL_TOOLS = _CORE_TOOLS + _load_plugin_tools()
TOOL_NAMES = [t.name for t in ALL_TOOLS]


if __name__ == "__main__":
    print("Available tools:")
    for t in ALL_TOOLS:
        print(f"  - {t.name}: {t.description[:60]}...")
