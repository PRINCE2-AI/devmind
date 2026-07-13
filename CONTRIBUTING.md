# Contributing

Thanks for helping improve DevMind.

## Development setup

```bash
python -m venv .venv
pip install -r requirements-dev.txt
```

Activate the environment, then run the quality gates:

```bash
ruff check .
black --check .
mypy .
pytest -q
```

The test suite must run without an Anthropic API key and without paid API calls.

## Pull requests

1. Keep each change focused and explain its user-visible behavior.
2. Add or update tests for logic, security, persistence, or tool changes.
3. Preserve support for Python 3.11 and for Git Bash on Windows.
4. Do not commit `.env`, API keys, logs, metrics, costs, or saved sessions.
5. Call out any change that expands file access or shell execution.

## Bug reports

Include the operating system, Python version, command used, expected behavior, and a minimal traceback with secrets removed. Security issues should follow [SECURITY.md](SECURITY.md), not a public issue.
