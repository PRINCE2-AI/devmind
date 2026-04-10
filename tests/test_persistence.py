"""
tests/test_persistence.py - Tests for session persistence.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import persistence
from persistence import (
    save_session, load_session, list_sessions, delete_session,
)
from exceptions import ValidationError, PersistenceError


@pytest.fixture
def isolated_sessions(tmp_path, monkeypatch):
    """Redirect sessions directory to a tmp path for each test."""
    monkeypatch.setattr(persistence, "_sessions_dir", lambda: tmp_path)
    yield tmp_path


class TestSaveLoad:
    def test_roundtrip(self, isolated_sessions):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        path = save_session("test1", history, "claude-sonnet-4-6")
        assert path.exists()

        loaded = load_session("test1")
        assert loaded.model == "claude-sonnet-4-6"
        assert len(loaded.history) == 2
        assert loaded.history[0]["content"] == "hello"

    def test_list_sessions(self, isolated_sessions):
        save_session("a", [{"role": "user", "content": "x"}], "claude-sonnet-4-6")
        save_session("b", [{"role": "user", "content": "y"}], "claude-sonnet-4-6")
        sessions = list_sessions()
        names = {s["name"] for s in sessions}
        assert "a" in names
        assert "b" in names

    def test_delete_session(self, isolated_sessions):
        save_session("doomed", [{"role": "user", "content": "x"}], "claude-sonnet-4-6")
        assert delete_session("doomed") is True
        with pytest.raises(PersistenceError):
            load_session("doomed")

    def test_load_missing_raises(self, isolated_sessions):
        with pytest.raises(PersistenceError):
            load_session("ghost")


class TestNameValidation:
    def test_reject_path_traversal(self, isolated_sessions):
        with pytest.raises((ValidationError, PersistenceError)):
            save_session("../evil", [{"role": "user", "content": "x"}], "m")

    def test_reject_slash(self, isolated_sessions):
        with pytest.raises((ValidationError, PersistenceError)):
            save_session("a/b", [{"role": "user", "content": "x"}], "m")

    def test_reject_empty(self, isolated_sessions):
        with pytest.raises((ValidationError, PersistenceError)):
            save_session("", [{"role": "user", "content": "x"}], "m")


class TestHistoryValidation:
    def test_reject_non_list(self, isolated_sessions):
        with pytest.raises((ValidationError, PersistenceError)):
            save_session("bad1", "not a list", "m")

    def test_reject_bad_entry(self, isolated_sessions):
        with pytest.raises((ValidationError, PersistenceError)):
            save_session("bad2", [{"no_role": True}], "m")
