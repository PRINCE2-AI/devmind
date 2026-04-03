"""
tools.py — DevMind's Tools (The Agent's Hands)
Inspired by Claude Code's tools.ts.
Each tool performs one specific job — reading files, running commands, etc.

Security features:
  - Path traversal protection on all file tools
  - Dangerous command blocking on bash
  - Binary file filtering on grep
  - Configurable via config.py
"""

import subprocess
import os
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from config import config
from logger import log


# ============================================================
# Helper: Path validation — prevent path traversal attacks
# ============================================================
def _validate_path(filepath: str) -> tuple[bool, str, Optional[Path]]:
    """
    Validate a file path to prevent path traversal attacks.

    Returns:
        (is_valid, error_message, resolved_path)
    """
    try:
        path = Path(filepath).resolve()
        cwd = Path(os.getcwd()).resolve()

        # Ensure the path stays within the current working directory
        if not str(path).startswith(str(cwd)):
            log.warning(f"Path traversal attempt blocked: {filepath}")
            return False, "Security: Only files within the current working directory can be accessed.", None

        return True, "", path

    except Exception as e:
        return False, f"Invalid path: {str(e)}", None


# ============================================================
# TOOL 1: BashTool — Run terminal commands
# ============================================================
@tool
def bash_tool(command: str) -> str:
    """
    Run a command in the terminal.
    Use when: running code, git commands, listing files.
    Example: bash_tool("python --version")
    """
    cmd_lower = command.lower().strip()

    if not cmd_lower:
        return "No command provided. Please enter a command to run."

    # Block dangerous commands
    if any(blocked in cmd_lower for blocked in config.tool.blocked_commands):
        log.warning(f"Blocked dangerous command: {command[:80]}")
        return "This command has been blocked for security reasons."

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

        log.debug(f"bash_tool: '{command[:50]}' → exit {result.returncode}")

        if result.returncode != 0 and error:
            return f"Error (code {result.returncode}):\n{error}"
        return output if output else "(Command ran with no output)"

    except subprocess.TimeoutExpired:
        log.warning(f"Command timed out: {command[:80]}")
        return f"Timeout! Command took longer than {config.tool.bash_timeout} seconds."
    except Exception as e:
        log.error(f"bash_tool error: {e}")
        return f"Error running command: {str(e)}"


# ============================================================
# TOOL 2: FileReadTool — Read a file
# ============================================================
@tool
def file_read_tool(filepath: str) -> str:
    """
    Read the contents of any file.
    Use when: viewing code, reading a README, checking a config file.
    Example: file_read_tool("main.py")
    """
    is_valid, error, path = _validate_path(filepath)
    if not is_valid:
        return error

    try:
        if not path.exists():
            return f"File not found: {filepath}"
        if not path.is_file():
            return f"This is a directory, not a file: {filepath}"

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        max_lines = config.tool.file_read_max_lines
        if len(lines) > max_lines:
            content = "".join(lines[:max_lines])
            log.debug(f"File truncated: {filepath} ({len(lines)} lines → {max_lines})")
            return f"{content}\n\n... (file is large, showing first {max_lines} lines)"

        return "".join(lines) if lines else "(File is empty)"

    except PermissionError:
        return f"Permission denied: {filepath}"
    except Exception as e:
        log.error(f"file_read_tool error: {e}")
        return f"Error reading file: {str(e)}"


# ============================================================
# TOOL 3: FileWriteTool — Create or overwrite a file
# ============================================================
@tool
def file_write_tool(filepath: str, content: str) -> str:
    """
    Write content to a file (create new or fully overwrite).
    Use this for new files only. To edit an existing file use file_edit_tool.
    Example: file_write_tool("hello.py", "print('Hello World')")
    """
    is_valid, error, path = _validate_path(filepath)
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
        return f"Error writing file: {str(e)}"


# ============================================================
# TOOL 4: FileEditTool — Find and replace specific text
# Python version of Claude Code's str_replace_based_edit_tool
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
    is_valid, error, path = _validate_path(filepath)
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

        log.info(f"File edited: {filepath} ({old_lines} → {new_lines} lines)")
        return (
            f"File edited: {filepath}\n"
            f"Replaced {old_lines} lines → {new_lines} lines ({diff_str} lines)"
        )

    except PermissionError:
        return f"Permission denied: {filepath}"
    except Exception as e:
        log.error(f"file_edit_tool error: {e}")
        return f"Error editing file: {str(e)}"


# ============================================================
# TOOL 5: GrepTool — Search the codebase
# ============================================================
@tool
def grep_tool(pattern: str, directory: str = ".") -> str:
    """
    Search for a word or pattern across the entire codebase.
    Use when: finding a function, locating where a variable is used.
    Example: grep_tool("def main", ".") or grep_tool("import os")
    """
    if not pattern.strip():
        return "Pattern is empty! Please provide a search pattern."

    try:
        results: list[str] = []
        search_dir = Path(directory)

        if not search_dir.exists():
            return f"Directory not found: {directory}"

        max_results = config.tool.grep_max_results

        for file_path in search_dir.rglob("*"):
            if len(results) >= max_results:
                break

            if any(skip in file_path.parts for skip in config.tool.skip_dirs):
                continue
            if not file_path.is_file():
                continue

            # Skip binary files — only search known text extensions
            suffix = file_path.suffix.lower()
            if suffix and suffix not in config.tool.text_extensions:
                continue
            # Files with no extension (e.g. Makefile, Dockerfile) are allowed

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

        log.debug(f"grep_tool: '{pattern}' → {len(results)} results")
        return output

    except Exception as e:
        log.error(f"grep_tool error: {e}")
        return f"Search error: {str(e)}"


# ============================================================
# TOOL 6: ListFilesTool — List files in a directory
# ============================================================
@tool
def list_files_tool(directory: str = ".") -> str:
    """
    List the files in a directory.
    Use when: understanding project structure.
    Example: list_files_tool(".") or list_files_tool("src")
    """
    try:
        path = Path(directory)
        if not path.exists():
            return f"Directory not found: {directory}"
        if not path.is_dir():
            return f"This is a file, not a directory: {directory}"

        items: list[str] = []

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
        return f"Error listing directory: {str(e)}"


# ============================================================
# All registered tools
# ============================================================
ALL_TOOLS = [
    bash_tool,
    file_read_tool,
    file_write_tool,
    file_edit_tool,
    grep_tool,
    list_files_tool,
]

TOOL_NAMES: list[str] = [t.name for t in ALL_TOOLS]


if __name__ == "__main__":
    print("Available tools:")
    for t in ALL_TOOLS:
        print(f"  - {t.name}: {t.description[:60]}...")
