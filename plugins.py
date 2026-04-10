"""
plugins.py — Plugin / extension system for DevMind tools

Drop a Python file into ~/.devmind/plugins/ that either:

1. Defines any number of `@tool`-decorated callables, and/or
2. Exposes a top-level list variable named `TOOLS` containing LangChain
   tool objects.

Example plugin (`~/.devmind/plugins/wordcount.py`):

    from langchain_core.tools import tool

    @tool
    def word_count_tool(text: str) -> str:
        '''Return the number of words in text.'''
        return str(len(text.split()))

On startup DevMind auto-discovers all `*.py` files in the plugin directory,
imports them in a safe sandbox, collects their tools, and appends them
to ALL_TOOLS. Failures in one plugin never break the others.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from exceptions import PluginError
from logger import get_logger

log = get_logger("plugins")


@dataclass
class LoadedPlugin:
    name: str
    path: Path
    tools: list[Any]


def _is_langchain_tool(obj: Any) -> bool:
    """Duck-typed check for a LangChain tool (avoids hard import).

    Note: we intentionally do not require ``callable(obj)`` — some LangChain
    tool variants (e.g. ``StructuredTool``) don't implement ``__call__``
    directly but still expose ``name``/``description``/``invoke``.
    """
    return (
        obj is not None
        and not isinstance(obj, type)
        and hasattr(obj, "name")
        and hasattr(obj, "description")
        and hasattr(obj, "invoke")
    )


def _collect_tools_from_module(module: Any) -> list[Any]:
    """Gather tools exposed by a plugin module."""
    tools: list[Any] = []

    # Explicit TOOLS list wins
    explicit = getattr(module, "TOOLS", None)
    if isinstance(explicit, (list, tuple)):
        for t in explicit:
            if _is_langchain_tool(t):
                tools.append(t)
            else:
                log.warning(
                    f"Plugin {module.__name__}: TOOLS entry {t!r} is not a tool"
                )
        return tools

    # Otherwise, scan module globals for tool-decorated callables
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        obj = getattr(module, attr_name, None)
        if _is_langchain_tool(obj):
            tools.append(obj)

    return tools


def _load_one_plugin(path: Path) -> LoadedPlugin:
    module_name = f"devmind_plugin_{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise PluginError(path.stem, "cannot create import spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        sys.modules.pop(module_name, None)
        raise PluginError(path.stem, f"import failed: {e}") from e

    tools = _collect_tools_from_module(module)
    if not tools:
        log.debug(f"Plugin {path.stem}: no tools found")
    return LoadedPlugin(name=path.stem, path=path, tools=tools)


def load_plugins(plugins_dir: str | Path) -> list[LoadedPlugin]:
    """
    Discover and load every `*.py` plugin in `plugins_dir`.

    Returns a list of LoadedPlugin objects — one per successfully loaded file.
    Failing plugins are logged and skipped.
    """
    d = Path(plugins_dir).expanduser()
    if not d.exists() or not d.is_dir():
        log.debug(f"No plugins directory at {d}")
        return []

    loaded: list[LoadedPlugin] = []
    for py_file in sorted(d.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            plugin = _load_one_plugin(py_file)
            loaded.append(plugin)
            log.info(
                f"Loaded plugin {plugin.name} ({len(plugin.tools)} tool"
                f"{'s' if len(plugin.tools) != 1 else ''})"
            )
        except PluginError as e:
            log.error(str(e))
        except Exception as e:
            log.error(f"Unexpected error loading plugin {py_file.name}: {e}")
    return loaded


def collect_plugin_tools(plugins_dir: str | Path) -> list[Any]:
    """Flatten all tools from every loaded plugin into a single list."""
    tools: list[Any] = []
    seen: set[str] = set()
    for plugin in load_plugins(plugins_dir):
        for t in plugin.tools:
            name = getattr(t, "name", None)
            if name and name in seen:
                log.warning(
                    f"Duplicate tool name '{name}' from plugin {plugin.name} — skipping"
                )
                continue
            if name:
                seen.add(name)
            tools.append(t)
    return tools


if __name__ == "__main__":
    from config import config
    tools = collect_plugin_tools(config.plugins.plugins_dir)
    print(f"Loaded {len(tools)} plugin tools")
    for t in tools:
        print(f"  - {t.name}")
