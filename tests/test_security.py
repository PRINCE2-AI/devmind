"""
tests/test_security.py - Tests for the security validation layer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from security import validate_command, validate_path, validate_string


class TestValidateString:
    def test_accepts_normal_string(self):
        ok, err = validate_string("hello world")
        assert ok is True
        assert err == ""

    def test_rejects_none(self):
        ok, err = validate_string(None)
        assert ok is False

    def test_rejects_non_string(self):
        ok, err = validate_string(123)
        assert ok is False

    def test_rejects_empty_by_default(self):
        ok, err = validate_string("")
        assert ok is False

    def test_allows_empty_when_flag_set(self):
        ok, err = validate_string("", allow_empty=True)
        assert ok is True

    def test_rejects_null_bytes(self):
        ok, err = validate_string("hello\x00world")
        assert ok is False
        assert "null" in err.lower()

    def test_rejects_over_length(self):
        ok, err = validate_string("x" * 101, max_length=100)
        assert ok is False


class TestValidateCommand:
    def test_accepts_simple_command(self):
        ok, err = validate_command("ls -la")
        assert ok is True

    def test_rejects_empty_command(self):
        ok, err = validate_command("")
        assert ok is False

    def test_blocks_rm_rf_root(self):
        ok, err = validate_command("rm -rf /")
        assert ok is False

    def test_blocks_sudo(self):
        ok, err = validate_command("sudo reboot")
        assert ok is False

    def test_blocks_fork_bomb(self):
        ok, err = validate_command(":(){ :|:& };:")
        assert ok is False

    def test_blocks_shutdown(self):
        ok, err = validate_command("shutdown -h now")
        assert ok is False

    def test_blocks_absolute_sudo(self):
        ok, err = validate_command("/usr/bin/sudo id")
        assert ok is False

    def test_blocks_sudo_through_env(self):
        ok, err = validate_command("env FOO=bar sudo id")
        assert ok is False

    def test_blocks_sudo_through_wrapper_options(self):
        for command in (
            "env -u FOO sudo id",
            "env -S 'sudo id'",
            "time -f '%E' sudo id",
            "timeout 5 sudo id",
            "xargs -I {} sudo id",
            "stdbuf -o 0 sudo id",
        ):
            ok, err = validate_command(command)
            assert ok is False, (command, err)

    def test_blocks_nested_shell_command(self):
        ok, err = validate_command("bash -lc 'sudo id'")
        assert ok is False
        ok, err = validate_command('cmd /k "sudo id"')
        assert ok is False

    def test_blocks_inline_python(self):
        ok, err = validate_command('python -c "import shutil; shutil.rmtree(\'.\')"')
        assert ok is False
        ok, err = validate_command('py -c "import os; os.system(\'calc\')"')
        assert ok is False

    def test_blocks_base64_pipe_to_shell(self):
        ok, err = validate_command("echo cm0gLXJmIC8= | base64 -d | bash")
        assert ok is False

    def test_blocks_command_substitution(self):
        ok, err = validate_command("echo $(sudo id)")
        assert ok is False

    def test_allows_python_module_command(self):
        ok, err = validate_command("python -m pytest -c pytest.ini -q")
        assert ok is True

    def test_allows_regular_dev_commands(self):
        for command in ("git status", "python --version", "pytest -q", "ls -la"):
            ok, err = validate_command(command)
            assert ok is True, (command, err)


class TestValidatePath:
    def test_accepts_normal_relative_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.txt").write_text("hello")
        ok, err, path = validate_path("a.txt")
        assert ok is True
        assert path is not None

    def test_rejects_empty(self):
        ok, err, path = validate_path("")
        assert ok is False

    def test_rejects_null_byte(self):
        ok, err, path = validate_path("bad\x00file.txt")
        assert ok is False

    def test_must_exist_false_ok(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ok, err, path = validate_path("new.txt", must_exist=False)
        assert ok is True

    def test_must_exist_true_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ok, err, path = validate_path("ghost.txt", must_exist=True)
        assert ok is False
