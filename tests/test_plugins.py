"""
tests/test_plugins.py - Tests for the plugin loader.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins import load_plugins, collect_plugin_tools


EXAMPLE_PLUGIN = '''
from langchain_core.tools import tool

@tool
def hello_plugin_tool(name: str) -> str:
    """Say hello from a plugin."""
    return f"hello {name}"

@tool
def second_plugin_tool(x: int) -> int:
    """Double an integer."""
    return x * 2
'''


BROKEN_PLUGIN = '''
this is not valid python !@#$
'''


class TestPluginLoading:
    def test_missing_dir_ok(self, tmp_path):
        result = load_plugins(tmp_path / "does_not_exist")
        assert result == []

    def test_empty_dir(self, tmp_path):
        assert load_plugins(tmp_path) == []

    def test_loads_good_plugin(self, tmp_path):
        (tmp_path / "hello.py").write_text(EXAMPLE_PLUGIN)
        plugins = load_plugins(tmp_path)
        assert len(plugins) == 1
        assert plugins[0].name == "hello"
        assert len(plugins[0].tools) == 2

    def test_collect_plugin_tools_flattens(self, tmp_path):
        (tmp_path / "hello.py").write_text(EXAMPLE_PLUGIN)
        tools = collect_plugin_tools(tmp_path)
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "hello_plugin_tool" in names
        assert "second_plugin_tool" in names

    def test_broken_plugin_is_skipped(self, tmp_path):
        (tmp_path / "good.py").write_text(EXAMPLE_PLUGIN)
        (tmp_path / "broken.py").write_text(BROKEN_PLUGIN)
        # Broken one should not blow up the loader
        plugins = load_plugins(tmp_path)
        names = {p.name for p in plugins}
        assert "good" in names
        assert "broken" not in names

    def test_ignores_private_files(self, tmp_path):
        (tmp_path / "_private.py").write_text(EXAMPLE_PLUGIN)
        plugins = load_plugins(tmp_path)
        assert all(not p.name.startswith("_") for p in plugins)
