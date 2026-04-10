# DevMind

**Autonomous AI coding assistant — runs in your terminal, built with Python + LangGraph.**

Inspired by the internal architecture of Anthropic's Claude Code.

---

## What is DevMind?

Your personal coding agent that lives in the terminal. Ask any coding question — it will read files, run commands, find bugs, and respond with real answers.

```
You: are there any bugs in this project?
DevMind: [reading files...] [running tests...]
         Yes, there is an issue on line 42 of main.py...
```

## Features

### Core
- **Real-time Streaming** — Responses appear token by token, just like Claude is thinking live
- **Tool Use** — Reads, writes, edits files, runs commands, searches code
- **Smart Retry** — Exponential backoff with jitter on API failures (retryable codes + max attempts are fully configurable)
- **Cost Tracking** — Tracks token count and USD cost for every API call
- **Task Management** — Tracks the full lifecycle of each operation (pending → running → completed/failed)
- **Git Aware** — Automatically injects current branch, status, and recent commits into context
- **CLAUDE.md Support** — Project-specific instructions loaded from a CLAUDE.md file
- **Smart History** — Long conversations are automatically summarized to preserve context

### Reliability & Observability
- **Metrics Registry** — p50/p95/p99 latency, success rate, per-tool stats, retry counts
- **Rate Limiting** — Thread-safe token bucket prevents runaway API usage
- **Session Persistence** — Save/load/list/delete named conversation sessions with atomic writes
- **Structured Logging** — JSON logs, rotating files (5 MB × 5 backups), automatic secret masking (API keys, bearer tokens)
- **Autosave** — Conversations are autosaved every N turns so you never lose work

### Security & Sandboxing
- **Path traversal protection** — Null-byte, symlink-escape, and base-dir enforcement
- **Command validation** — Blocks rm -rf /, fork bombs, sudo, shutdown, etc. (fully configurable)
- **String validation** — Length caps and null-byte rejection on all user-supplied text
- **Secret scrubbing** — API keys and tokens are masked before they reach logs or disk

### Extensibility
- **Plugin system** — Drop any `@tool`-decorated Python file in `~/.devmind/plugins/` and it's auto-discovered
- **Centralized Config** — All settings in `config.py` with full environment-variable overrides

## Architecture (Inspired by Claude Code)

```
┌─────────────────────────────────────────────────┐
│                    main.py                       │
│              (Terminal REPL + UI)                │
├─────────────────────────────────────────────────┤
│                   agent.py                       │
│         (LangGraph Agent Loop + Retry)           │
├──────────┬──────────┬───────────┬───────────────┤
│ tools.py │context.py│  task.py  │cost_tracker.py│
│ (6 Tools)│(Sys Prompt)│(Lifecycle)│ (Cost Track) │
├──────────┴──────────┴───────────┴───────────────┤
│  config.py  │  logger.py  │   exceptions.py      │
│  (Settings) │  (Logging)  │   (Error Types)      │
└─────────────┴─────────────┴──────────────────────┘
```

| DevMind File      | Claude Code Source   | Purpose                                  |
|-------------------|----------------------|------------------------------------------|
| main.py           | main.tsx             | Terminal REPL + streaming display        |
| agent.py          | query.ts             | LangGraph agent loop + retry + streaming |
| tools.py          | tools.ts             | 6 tools + security                       |
| context.py        | context.ts           | System prompt builder (git + CLAUDE.md)  |
| task.py           | Task.ts              | Task lifecycle management                |
| cost_tracker.py   | cost-tracker.ts      | Token cost tracking + session persistence|
| config.py         | —                    | Centralized configuration                |
| logger.py         | —                    | Structured logging system                |
| exceptions.py     | —                    | Custom exception hierarchy               |

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-username/devmind.git
cd devmind

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API key to a .env file
echo "ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx" > .env

# 5. Run it!
python main.py
```

## Commands

| Command              | Description                                         |
|----------------------|-----------------------------------------------------|
| `/help`              | Show help message                                   |
| `/cost`              | Show API usage cost (tokens + USD)                  |
| `/metrics`           | Show latency percentiles, success rate, tool stats  |
| `/tasks`             | Show all tasks in the current session               |
| `/history`           | Show recent chat history                            |
| `/save <name>`       | Save the current conversation to a named session    |
| `/load <name>`       | Load a previously saved conversation                |
| `/sessions`          | List all saved sessions                             |
| `/delete <name>`     | Delete a saved session                              |
| `/clear`             | Clear chat history                                  |
| `/cd <path>`         | Change working directory                            |
| `/exit`              | Exit DevMind                                        |

## Tools (6 Core + Unlimited Plugins)

| Tool             | Description                                           |
|------------------|-------------------------------------------------------|
| `bash_tool`      | Run terminal commands (with dangerous command blocking)|
| `file_read_tool` | Read file contents (with path validation)             |
| `file_write_tool`| Create or fully overwrite files                       |
| `file_edit_tool` | Find and replace specific text (Claude Code style)    |
| `grep_tool`      | Search the codebase (text files only)                 |
| `list_files_tool`| List directory contents with file sizes               |

Every tool invocation is automatically timed and recorded in the metrics registry, so `/metrics` shows success rates and average latencies per tool.

### Writing a plugin

Drop a `.py` file into `~/.devmind/plugins/`:

```python
from langchain_core.tools import tool

@tool
def word_count_tool(text: str) -> str:
    """Return the number of words in the given text."""
    return str(len(text.split()))
```

That's it. On next startup DevMind discovers the file, imports it, validates the tool, and appends it to `ALL_TOOLS`. A broken plugin never breaks the others — loader failures are logged and skipped.

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_tools.py -v

# Short traceback output
python -m pytest tests/ -v --tb=short
```

## Configuration

All settings are in `config.py`. You can also override via environment variables:

| Environment Variable        | Description                              | Default                   |
|-----------------------------|------------------------------------------|---------------------------|
| `ANTHROPIC_API_KEY`         | Anthropic API key (required)             | —                         |
| `DEVMIND_MODEL`             | Model name                               | `claude-sonnet-4-6`       |
| `DEVMIND_DEBUG`             | Enable debug mode                        | `false`                   |
| `DEVMIND_LOG_LEVEL`         | Logging level                            | `INFO`                    |
| `DEVMIND_LOG_JSON`          | Emit JSON-formatted logs                 | `false`                   |
| `DEVMIND_MAX_RETRIES`       | Retry attempts on transient failures     | `4`                       |
| `DEVMIND_RATE_LIMIT_RPM`    | Max requests per minute (0 = disabled)   | `50`                      |
| `DEVMIND_RATE_LIMIT_BURST`  | Token-bucket burst size                  | `10`                      |
| `DEVMIND_SESSIONS_DIR`      | Where to store saved conversations       | `~/.devmind/sessions`     |
| `DEVMIND_AUTOSAVE_EVERY`    | Autosave every N turns (0 = disabled)    | `5`                       |
| `DEVMIND_METRICS_DIR`       | Where to persist metrics snapshots       | `~/.devmind/metrics`      |
| `DEVMIND_PLUGINS_DIR`       | Plugin discovery directory               | `~/.devmind/plugins`      |

## Project Structure

```
devmind/
├── main.py              # Entry point + REPL (slash commands: /cost /metrics /save /load ...)
├── agent.py             # LangGraph agent brain + retry/backoff + rate limiting
├── tools.py             # 6 timed tools + security-hardened implementations
├── context.py           # System prompt builder
├── task.py              # Task lifecycle
├── cost_tracker.py      # Token cost tracking
├── config.py            # Centralized configuration (env-var overrides)
├── logger.py            # Rotating + JSON logging with secret masking
├── exceptions.py        # Custom exception hierarchy
├── metrics.py           # p50/p95/p99 latency + per-tool stats + persistence
├── rate_limiter.py      # Thread-safe token bucket rate limiter
├── persistence.py       # Save/load/list/delete conversation sessions
├── security.py          # Path/command/string validators
├── plugins.py           # Auto-discovery of user @tool plugins
├── requirements.txt     # Python dependencies
├── .env                 # API key (gitignored)
├── .gitignore
└── tests/               # 156 tests across 13 files
    ├── test_tools.py
    ├── test_task.py
    ├── test_cost_tracker.py
    ├── test_config.py
    ├── test_exceptions.py
    ├── test_context.py
    ├── test_main.py
    ├── test_security.py
    ├── test_rate_limiter.py
    ├── test_metrics.py
    ├── test_persistence.py
    └── test_plugins.py
```

## Tech Stack

- **Python 3.11+**
- **LangGraph** — Agentic loop (tool use → response cycle)
- **LangChain + Anthropic API** — Claude integration
- **Rich** — Beautiful terminal UI

---

*Inspired by Anthropic's Claude Code internal architecture*
