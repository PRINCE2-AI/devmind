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

- **Real-time Streaming** — Responses appear token by token, just like Claude is thinking live
- **Tool Use** — Reads, writes, edits files, runs commands, searches code
- **Smart Retry** — Automatically retries on API failures (configurable attempts)
- **Cost Tracking** — Tracks token count and USD cost for every API call
- **Task Management** — Tracks the full lifecycle of each operation (pending → running → completed/failed)
- **Git Aware** — Automatically injects current branch, status, and recent commits into context
- **CLAUDE.md Support** — Project-specific instructions loaded from a CLAUDE.md file
- **Security** — Path traversal protection, dangerous command blocking, binary file filtering
- **Centralized Config** — All settings in one place (config.py), no hardcoded values
- **Structured Logging** — File + console logging with DEBUG/INFO/WARNING/ERROR levels
- **Smart History** — Long conversations are automatically summarized to preserve context

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
│ (6 Tools)│(Sys Prompt│(Lifecycle)│ (Cost Track) │
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

| Command         | Description                          |
|-----------------|--------------------------------------|
| `/help`         | Show help message                    |
| `/cost`         | Show API usage cost (tokens + USD)   |
| `/tasks`        | Show all tasks in the current session|
| `/clear`        | Clear chat history                   |
| `/cd <path>`    | Change working directory             |
| `/exit`         | Exit DevMind                         |

## Tools (6 Available)

| Tool             | Description                                           |
|------------------|-------------------------------------------------------|
| `bash_tool`      | Run terminal commands (with dangerous command blocking)|
| `file_read_tool` | Read file contents (with path validation)             |
| `file_write_tool`| Create or fully overwrite files                       |
| `file_edit_tool` | Find and replace specific text (Claude Code style)    |
| `grep_tool`      | Search the codebase (text files only)                 |
| `list_files_tool`| List directory contents with file sizes               |

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

| Environment Variable  | Description                    | Default            |
|-----------------------|--------------------------------|--------------------|
| `ANTHROPIC_API_KEY`   | Anthropic API key (required)   | —                  |
| `DEVMIND_DEBUG`       | Enable debug mode              | `false`            |
| `DEVMIND_LOG_LEVEL`   | Logging level                  | `INFO`             |

## Project Structure

```
devmind/
├── main.py              # Entry point + REPL
├── agent.py             # LangGraph agent brain
├── tools.py             # 6 tools + security
├── context.py           # System prompt builder
├── task.py              # Task lifecycle
├── cost_tracker.py      # Token cost tracking
├── config.py            # Centralized configuration
├── logger.py            # Logging system
├── exceptions.py        # Custom exception hierarchy
├── requirements.txt     # Python dependencies
├── .env                 # API key (gitignored)
├── .gitignore
└── tests/
    ├── __init__.py
    ├── test_tools.py
    ├── test_task.py
    ├── test_cost_tracker.py
    ├── test_config.py
    ├── test_exceptions.py
    ├── test_context.py
    └── test_main.py
```

## Tech Stack

- **Python 3.11+**
- **LangGraph** — Agentic loop (tool use → response cycle)
- **LangChain + Anthropic API** — Claude integration
- **Rich** — Beautiful terminal UI

---

*Inspired by Anthropic's Claude Code internal architecture*
