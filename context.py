"""
context.py — DevMind's Context Builder
Inspired by Claude Code's context.ts.
Tells Claude: "Here is where you are working and what is happening."

Responsibilities:
  - Build the system prompt (git + CLAUDE.md + date + tools)
  - Retrieve Git repository information
  - Load project-specific instructions (CLAUDE.md)
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import log


# ============================================================
# Git Information
# (Inspired by context.ts: getGitStatus)
# ============================================================
def _run_git(args: list[str]) -> str:
    """Run a git command and return stdout, or empty string on error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception as e:
        log.debug(f"Git command failed: git {' '.join(args)} → {e}")
        return ""


def get_git_status() -> Optional[str]:
    """
    Return a summary of the current git repository state.
    (Inspired by context.ts: getGitStatus)

    Returns:
        Git info string if inside a git repo, otherwise None.
    """
    is_git = _run_git(["rev-parse", "--is-inside-work-tree"])
    if is_git != "true":
        return None

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    status = _run_git(["status", "--short"])
    recent_commits = _run_git(["log", "--oneline", "-n", "5"])
    user_name = _run_git(["config", "user.name"])

    # Truncate if status is very long
    if len(status) > 1000:
        status = status[:1000] + "\n... (too many changes, truncated)"

    parts = [
        "=== Git Status ===",
        f"Branch: {branch or 'unknown'}",
    ]
    if user_name:
        parts.append(f"Git User: {user_name}")
    parts.append(f"Changes:\n{status or '(no changes — clean)'}")
    parts.append(f"Recent Commits:\n{recent_commits or '(no commits yet)'}")

    return "\n".join(parts)


# ============================================================
# CLAUDE.md — Project-specific instructions
# (Inspired by context.ts: getClaudeMds pattern)
# ============================================================
def get_claude_md() -> Optional[str]:
    """
    Read CLAUDE.md if it exists.
    This file contains project-specific instructions for Claude.

    Returns:
        CLAUDE.md content if the file exists, otherwise None.
    """
    claude_md_path = Path(os.getcwd()) / "CLAUDE.md"
    if claude_md_path.exists():
        try:
            content = claude_md_path.read_text(encoding="utf-8")
            if content.strip():
                log.debug("CLAUDE.md found and loaded")
                return f"=== Project Instructions (CLAUDE.md) ===\n{content}"
        except Exception as e:
            log.warning(f"Failed to read CLAUDE.md: {e}")
    return None


# ============================================================
# Basic Context — date, cwd, OS
# ============================================================
def get_basic_context() -> dict[str, str]:
    """
    Return basic environment information.

    Returns:
        Dict with date, cwd, and os keys.
    """
    return {
        "date": datetime.now().strftime("%A, %d %B %Y, %I:%M %p"),
        "cwd": os.getcwd(),
        "os": os.name,
    }


# ============================================================
# MAIN FUNCTION: Build the full system prompt
# (Inspired by context.ts: getSystemContext + getUserContext)
# ============================================================
def build_system_prompt() -> str:
    """
    Build the complete system prompt for Claude.
    Injects: git status + CLAUDE.md + date + tool list + instructions.

    Returns:
        Complete system prompt string.
    """
    ctx = get_basic_context()
    git_info = get_git_status()
    claude_md = get_claude_md()

    prompt_parts = [
        "You are DevMind — an autonomous coding assistant.",
        "You do real work using tools: reading files, running code, finding bugs.",
        "",
        f"Today's date: {ctx['date']}",
        f"Working directory: {ctx['cwd']}",
        "",
        "=== Available Tools ===",
        "- bash_tool: Run terminal commands (git, python, etc.)",
        "- file_read_tool: Read file contents",
        "- file_write_tool: Create new files or fully overwrite existing ones",
        "- file_edit_tool: Find and replace specific text in an existing file (bug fixes, code updates)",
        "- grep_tool: Search for patterns across the codebase",
        "- list_files_tool: List files in a directory",
        "",
        "=== How to Work ===",
        "1. Understand what the user wants",
        "2. Plan — decide which tool(s) to use",
        "3. Use the tool and examine the result",
        "4. Use more tools if needed",
        "5. Give a clear and helpful answer",
        "",
        "Always: gather information with tools first, then respond. Never guess.",
    ]

    if git_info:
        prompt_parts.append("")
        prompt_parts.append(git_info)

    if claude_md:
        prompt_parts.append("")
        prompt_parts.append(claude_md)

    log.debug(f"System prompt built: {len(prompt_parts)} parts")
    return "\n".join(prompt_parts)


if __name__ == "__main__":
    print("=== System Prompt Preview ===")
    print(build_system_prompt())
