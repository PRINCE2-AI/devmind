"""
persistence.py — Conversation save/load

Stores a chat session (history + metadata) as a JSON file under
~/.devmind/sessions/ so users can pick up where they left off.

Each session file looks like:

    {
      "session_id": "20260410_093045",
      "created_at": "2026-04-10T09:30:45.123456",
      "updated_at": "2026-04-10T09:42:11.987654",
      "model": "claude-sonnet-4-6",
      "cwd": "/path/when/saved",
      "history": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
      ]
    }
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import config
from exceptions import PersistenceError, ValidationError
from logger import get_logger

log = get_logger("persistence")


# ============================================================
# Data model
# ============================================================
@dataclass
class ConversationSession:
    session_id: str
    created_at: str
    updated_at: str
    model: str
    cwd: str
    history: list[dict]  # [{"role": "user"|"assistant", "content": "..."}]
    metadata: dict = field(default_factory=dict)


# ============================================================
# Filename safety — only allow [A-Za-z0-9_-] in session names
# ============================================================
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValidationError("Session name must be a non-empty string.")
    name = name.strip()
    if not _NAME_RE.match(name):
        raise ValidationError(
            f"Invalid session name: '{name}'. "
            "Use only letters, digits, hyphens and underscores."
        )
    if len(name) > 128:
        raise ValidationError("Session name too long (max 128 chars).")
    return name


def _sessions_dir() -> Path:
    d = Path(config.persistence.sessions_dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_path(name: str) -> Path:
    name = _validate_name(name)
    # Ensure the resolved path is actually inside the sessions directory
    base = _sessions_dir().resolve()
    target = (base / f"{name}.json").resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise ValidationError("Session path escapes the sessions directory.")
    return target


# ============================================================
# History validation
# ============================================================
def _validate_history(history: list) -> list[dict]:
    if not isinstance(history, list):
        raise ValidationError("History must be a list.")
    cleaned: list[dict] = []
    for i, msg in enumerate(history):
        if not isinstance(msg, dict):
            raise ValidationError(f"History[{i}] must be a dict.")
        role = msg.get("role")
        content = msg.get("content")
        if role not in ("user", "assistant", "system"):
            raise ValidationError(f"History[{i}] has invalid role: {role!r}")
        if not isinstance(content, str):
            raise ValidationError(f"History[{i}] content must be a string.")
        cleaned.append({"role": role, "content": content})
    return cleaned


# ============================================================
# Save
# ============================================================
def save_session(
    name: str,
    history: list[dict],
    model: str,
    metadata: Optional[dict] = None,
) -> Path:
    """
    Save a conversation session to disk.

    Args:
        name: Session name (letters, digits, hyphen, underscore)
        history: List of {"role": ..., "content": ...} dicts
        model: Model name used for this session
        metadata: Optional extra metadata

    Returns:
        The saved file path.

    Raises:
        ValidationError: If inputs are malformed.
        PersistenceError: If writing fails.
    """
    if not config.persistence.enabled:
        raise PersistenceError("Persistence is disabled in config.")

    history = _validate_history(history)
    path = _session_path(name)
    now = datetime.now().isoformat()

    existing_created = now
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            existing_created = old.get("created_at", now)
        except Exception:
            pass

    session = ConversationSession(
        session_id=_validate_name(name),
        created_at=existing_created,
        updated_at=now,
        model=model,
        cwd=os.getcwd(),
        history=history,
        metadata=metadata or {},
    )

    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic on POSIX + Windows
        log.info(f"Saved session '{name}' ({len(history)} messages) → {path}")
        return path
    except PermissionError as e:
        raise PersistenceError(f"Permission denied saving session: {e}") from e
    except Exception as e:
        raise PersistenceError(f"Failed to save session: {e}") from e


# ============================================================
# Load
# ============================================================
def load_session(name: str) -> ConversationSession:
    """
    Load a previously saved session by name.

    Raises:
        ValidationError: If name is invalid or file is corrupt.
        PersistenceError: If file cannot be read.
    """
    path = _session_path(name)
    if not path.exists():
        raise PersistenceError(f"Session '{name}' not found.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValidationError(f"Session file is corrupt: {e}") from e
    except PermissionError as e:
        raise PersistenceError(f"Permission denied reading session: {e}") from e

    required = {"session_id", "created_at", "updated_at", "model", "cwd", "history"}
    missing = required - data.keys()
    if missing:
        raise ValidationError(f"Session file missing keys: {missing}")

    history = _validate_history(data["history"])

    log.info(f"Loaded session '{name}' ({len(history)} messages)")
    return ConversationSession(
        session_id=data["session_id"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        model=data["model"],
        cwd=data["cwd"],
        history=history,
        metadata=data.get("metadata") or {},
    )


# ============================================================
# List / delete
# ============================================================
def list_sessions() -> list[dict]:
    """
    Return a list of saved sessions with summary info.
    Each entry: {name, updated_at, messages, model}
    """
    d = _sessions_dir()
    out: list[dict] = []
    for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "name": f.stem,
                "updated_at": data.get("updated_at", ""),
                "messages": len(data.get("history", [])),
                "model": data.get("model", ""),
            })
        except Exception as e:
            log.debug(f"Skipping unreadable session file {f}: {e}")
    return out


def delete_session(name: str) -> bool:
    """Delete a session file. Returns True if it existed."""
    path = _session_path(name)
    if path.exists():
        path.unlink()
        log.info(f"Deleted session '{name}'")
        return True
    return False


if __name__ == "__main__":
    # Smoke test
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DEVMIND_SESSIONS_DIR"] = tmp
        # Reload config for the override to take effect
        import importlib, config as _cfg_mod
        importlib.reload(_cfg_mod)
        from config import config as reloaded
        print("Sessions dir:", reloaded.persistence.sessions_dir)
