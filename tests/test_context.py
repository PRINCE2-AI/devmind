"""
tests/test_context.py — Tests for the context / system prompt builder
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from context import build_system_prompt, get_basic_context, get_claude_md


class TestBasicContext:
    def test_returns_dict(self):
        """Should return a dict"""
        ctx = get_basic_context()
        assert isinstance(ctx, dict)

    def test_has_required_keys(self):
        """Must contain date, cwd, and os keys"""
        ctx = get_basic_context()
        assert "date" in ctx
        assert "cwd" in ctx
        assert "os" in ctx

    def test_cwd_is_valid_path(self):
        """cwd must be a valid existing path"""
        ctx = get_basic_context()
        assert Path(ctx["cwd"]).exists()


class TestBuildSystemPrompt:
    def test_returns_string(self):
        """Should return a string"""
        prompt = build_system_prompt()
        assert isinstance(prompt, str)

    def test_contains_identity(self):
        """DevMind identity must be present"""
        prompt = build_system_prompt()
        assert "DevMind" in prompt

    def test_contains_all_tools(self):
        """All 6 tools must be mentioned in the prompt"""
        prompt = build_system_prompt()
        assert "bash_tool" in prompt
        assert "file_read_tool" in prompt
        assert "file_write_tool" in prompt
        assert "file_edit_tool" in prompt
        assert "grep_tool" in prompt
        assert "list_files_tool" in prompt

    def test_contains_date(self):
        """Date must be included"""
        prompt = build_system_prompt()
        assert "date" in prompt.lower()

    def test_contains_instructions(self):
        """Working methodology must be present"""
        prompt = build_system_prompt()
        assert "Understand" in prompt or "understand" in prompt


class TestClaudeMd:
    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        """Should return None when CLAUDE.md does not exist"""
        monkeypatch.chdir(tmp_path)
        result = get_claude_md()
        assert result is None

    def test_reads_claude_md(self, tmp_path, monkeypatch):
        """Should return content when CLAUDE.md exists"""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("Test instructions here")
        result = get_claude_md()
        assert result is not None
        assert "Test instructions here" in result

    def test_empty_claude_md_returns_none(self, tmp_path, monkeypatch):
        """Should return None for a blank CLAUDE.md"""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("   ")
        result = get_claude_md()
        assert result is None


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
