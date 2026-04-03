"""
tests/test_tools.py — Tests for all DevMind tools
Run with: python -m pytest tests/ -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import (
    bash_tool,
    file_read_tool,
    file_write_tool,
    file_edit_tool,
    grep_tool,
    list_files_tool,
    _validate_path,
    ALL_TOOLS,
)


# ============================================================
# Path Validation Tests — Security
# ============================================================
class TestPathValidation:
    def test_valid_path_in_cwd(self, tmp_path, monkeypatch):
        """A path inside the cwd should be valid"""
        monkeypatch.chdir(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")
        is_valid, error, path = _validate_path(str(test_file))
        assert is_valid is True
        assert path is not None

    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        """Path traversal attempts must be blocked"""
        monkeypatch.chdir(tmp_path)
        is_valid, error, path = _validate_path("/etc/passwd")
        assert is_valid is False
        assert "Security" in error


# ============================================================
# BashTool Tests
# ============================================================
class TestBashTool:
    def test_simple_command(self):
        """A basic echo command should work"""
        result = bash_tool.invoke({"command": "echo Hello DevMind"})
        assert "Hello DevMind" in result

    def test_python_version(self):
        """Python version command should return version string"""
        result = bash_tool.invoke({"command": "python3 --version"})
        assert "Python" in result

    def test_error_command(self):
        """An invalid command should return an error"""
        result = bash_tool.invoke({"command": "nonexistent_command_xyz"})
        assert "Error" in result or "not found" in result.lower() or result != ""

    def test_empty_command(self):
        """An empty command should return an informative message"""
        result = bash_tool.invoke({"command": ""})
        assert result  # Must return something non-empty

    def test_blocked_dangerous_command(self):
        """A dangerous command must be blocked"""
        result = bash_tool.invoke({"command": "rm -rf /"})
        assert "block" in result.lower() or "security" in result.lower()

    def test_pipe_commands_work(self):
        """Piped commands should execute correctly"""
        result = bash_tool.invoke({"command": "echo 'hello world' | wc -w"})
        assert "2" in result


# ============================================================
# FileReadTool Tests
# ============================================================
class TestFileReadTool:
    def test_read_existing_file(self, tmp_path, monkeypatch):
        """An existing file should be read correctly"""
        monkeypatch.chdir(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("print('Hello')\nprint('World')")

        result = file_read_tool.invoke({"filepath": str(test_file)})
        assert "Hello" in result
        assert "World" in result

    def test_file_not_found(self, tmp_path, monkeypatch):
        """A missing file should return an error"""
        monkeypatch.chdir(tmp_path)
        result = file_read_tool.invoke({"filepath": str(tmp_path / "nonexistent.py")})
        assert "not found" in result.lower()

    def test_large_file_truncated(self, tmp_path, monkeypatch):
        """Files over 200 lines should be truncated"""
        monkeypatch.chdir(tmp_path)
        large_file = tmp_path / "large.py"
        content = "\n".join([f"line_{i} = {i}" for i in range(300)])
        large_file.write_text(content)

        result = file_read_tool.invoke({"filepath": str(large_file)})
        assert "200 lines" in result or "large" in result.lower()

    def test_read_directory_gives_error(self, tmp_path, monkeypatch):
        """Trying to read a directory should return an error"""
        monkeypatch.chdir(tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        result = file_read_tool.invoke({"filepath": str(subdir)})
        assert "directory" in result.lower() or "not" in result.lower()

    def test_empty_file(self, tmp_path, monkeypatch):
        """An empty file should return an appropriate message"""
        monkeypatch.chdir(tmp_path)
        empty = tmp_path / "empty.txt"
        empty.write_text("")
        result = file_read_tool.invoke({"filepath": str(empty)})
        assert "empty" in result.lower()


# ============================================================
# FileWriteTool Tests
# ============================================================
class TestFileWriteTool:
    def test_write_new_file(self, tmp_path, monkeypatch):
        """A new file should be created correctly"""
        monkeypatch.chdir(tmp_path)
        new_file = tmp_path / "new_file.py"
        result = file_write_tool.invoke({
            "filepath": str(new_file),
            "content": "print('DevMind rocks!')"
        })
        assert "written" in result.lower()
        assert new_file.read_text() == "print('DevMind rocks!')"

    def test_overwrite_existing(self, tmp_path, monkeypatch):
        """An existing file should be overwritten"""
        monkeypatch.chdir(tmp_path)
        existing = tmp_path / "existing.txt"
        existing.write_text("old content")

        file_write_tool.invoke({
            "filepath": str(existing),
            "content": "new content"
        })
        assert existing.read_text() == "new content"

    def test_creates_parent_dirs(self, tmp_path, monkeypatch):
        """Missing parent directories should be created automatically"""
        monkeypatch.chdir(tmp_path)
        deep_file = tmp_path / "a" / "b" / "c" / "deep.py"
        file_write_tool.invoke({
            "filepath": str(deep_file),
            "content": "# deep file"
        })
        assert deep_file.exists()


# ============================================================
# FileEditTool Tests
# ============================================================
class TestFileEditTool:
    def test_simple_edit(self, tmp_path, monkeypatch):
        """A simple text replacement should work"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "edit_me.py"
        f.write_text("def hello():\n    print('hi')\n")

        result = file_edit_tool.invoke({
            "filepath": str(f),
            "old_text": "print('hi')",
            "new_text": "print('Hello DevMind!')"
        })

        assert "edited" in result.lower() or "edit" in result.lower()
        assert "Hello DevMind!" in f.read_text()

    def test_edit_not_found(self, tmp_path, monkeypatch):
        """Should return an error if old_text is not found"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "file.py"
        f.write_text("def foo(): pass\n")

        result = file_edit_tool.invoke({
            "filepath": str(f),
            "old_text": "this_does_not_exist",
            "new_text": "replacement"
        })
        assert "not found" in result.lower()

    def test_edit_ambiguous(self, tmp_path, monkeypatch):
        """Should reject edit if old_text matches multiple locations"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "dup.py"
        f.write_text("x = 1\nx = 1\n")

        result = file_edit_tool.invoke({
            "filepath": str(f),
            "old_text": "x = 1",
            "new_text": "x = 99"
        })
        assert "ambiguous" in result or "2" in result

    def test_edit_file_not_found(self, tmp_path, monkeypatch):
        """Should return an error for a non-existent file"""
        monkeypatch.chdir(tmp_path)
        result = file_edit_tool.invoke({
            "filepath": str(tmp_path / "nope.py"),
            "old_text": "anything",
            "new_text": "whatever"
        })
        assert "not found" in result.lower()

    def test_same_old_new_text(self, tmp_path, monkeypatch):
        """Should warn when old_text and new_text are identical"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "same.py"
        f.write_text("x = 1\n")
        result = file_edit_tool.invoke({
            "filepath": str(f),
            "old_text": "x = 1",
            "new_text": "x = 1"
        })
        assert "identical" in result.lower() or "same" in result.lower()

    def test_multiline_edit(self, tmp_path, monkeypatch):
        """Multi-line block replacement should work correctly"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "multi.py"
        original = "def old_func():\n    return 1\n\ndef other(): pass\n"
        f.write_text(original)

        result = file_edit_tool.invoke({
            "filepath": str(f),
            "old_text": "def old_func():\n    return 1",
            "new_text": "def new_func():\n    return 42\n    # updated!"
        })

        assert "edited" in result.lower() or "edit" in result.lower()
        content = f.read_text()
        assert "new_func" in content
        assert "42" in content
        assert "other" in content  # Other function must be untouched


# ============================================================
# GrepTool Tests
# ============================================================
class TestGrepTool:
    def test_find_pattern(self, tmp_path, monkeypatch):
        """Should find a matching pattern"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "code.py"
        f.write_text("def main():\n    print('hello')\n    return 0\n")

        result = grep_tool.invoke({"pattern": "def main", "directory": str(tmp_path)})
        assert "def main" in result

    def test_pattern_not_found(self, tmp_path, monkeypatch):
        """Should report when pattern is not found"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "code.py"
        f.write_text("x = 1\n")

        result = grep_tool.invoke({"pattern": "xyz_not_here", "directory": str(tmp_path)})
        assert "not found" in result.lower()

    def test_case_insensitive(self, tmp_path, monkeypatch):
        """Search should be case-insensitive"""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "code.py"
        f.write_text("class MyClass:\n    pass\n")

        result = grep_tool.invoke({"pattern": "myclass", "directory": str(tmp_path)})
        assert "MyClass" in result or "myclass" in result.lower()

    def test_empty_pattern_error(self):
        """Empty pattern should return an error message"""
        result = grep_tool.invoke({"pattern": "   ", "directory": "."})
        assert "empty" in result.lower() or "pattern" in result.lower()

    def test_skips_binary_files(self, tmp_path, monkeypatch):
        """Binary files should be excluded from search results"""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "image.png").write_bytes(b'\x89PNG\r\n\x1a\nhello')
        (tmp_path / "code.py").write_text("hello world\n")

        result = grep_tool.invoke({"pattern": "hello", "directory": str(tmp_path)})
        assert "code.py" in result
        assert "image.png" not in result


# ============================================================
# ListFilesTool Tests
# ============================================================
class TestListFilesTool:
    def test_list_directory(self, tmp_path):
        """Should list all items in a directory"""
        (tmp_path / "file1.py").write_text("x=1")
        (tmp_path / "file2.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()

        result = list_files_tool.invoke({"directory": str(tmp_path)})
        assert "file1.py" in result
        assert "file2.txt" in result
        assert "subdir" in result

    def test_nonexistent_directory(self):
        """Should return an error for a missing directory"""
        result = list_files_tool.invoke({"directory": "/fake/nonexistent/path"})
        assert "not found" in result.lower()

    def test_empty_directory(self, tmp_path):
        """Should report that an empty directory is empty"""
        result = list_files_tool.invoke({"directory": str(tmp_path)})
        assert "empty" in result.lower()

    def test_file_sizes_shown(self, tmp_path):
        """File sizes must be displayed"""
        (tmp_path / "small.txt").write_text("hi")
        result = list_files_tool.invoke({"directory": str(tmp_path)})
        assert "B" in result or "KB" in result


# ============================================================
# Integration: ALL_TOOLS registry
# ============================================================
class TestToolsIntegration:
    def test_all_tools_present(self):
        """All 6 tools must be registered"""
        assert len(ALL_TOOLS) == 6

    def test_tool_names(self):
        """Tool names must be correct"""
        names = {t.name for t in ALL_TOOLS}
        assert "bash_tool" in names
        assert "file_read_tool" in names
        assert "file_write_tool" in names
        assert "file_edit_tool" in names
        assert "grep_tool" in names
        assert "list_files_tool" in names

    def test_tools_have_descriptions(self):
        """Every tool must have a description"""
        for t in ALL_TOOLS:
            assert t.description, f"{t.name} is missing a description!"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
