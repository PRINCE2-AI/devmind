"""
cost_tracker.py — DevMind's Cost Tracker
Inspired by Claude Code's cost-tracker.ts + costHook.ts.
Tracks token usage and USD cost for every API call.

Features:
  - Per-call cost tracking with timestamps
  - Session-level aggregation
  - Persistent cost logging to disk
  - Multi-model price support
"""

import json
import atexit
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from logger import log


# ============================================================
# Claude model prices (per 1 million tokens)
# ============================================================
MODEL_PRICES: dict[str, dict[str, float]] = {
    "claude-opus-4":       {"input": 15.0,  "output": 75.0},
    "claude-sonnet-4":     {"input": 3.0,   "output": 15.0},
    "claude-sonnet-4-6":   {"input": 3.0,   "output": 15.0},
    "claude-haiku-4":      {"input": 0.80,  "output": 4.0},
    "claude-haiku-3-5":    {"input": 0.25,  "output": 1.25},
    "default":             {"input": 3.0,   "output": 15.0},
}


# ============================================================
# Session cost data
# ============================================================
@dataclass
class SessionCosts:
    """Complete cost information for one session."""
    session_id: str
    start_time: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    model: str = "claude-sonnet-4-6-20250929"
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    total_cost_usd: float = 0.0
    calls_log: list[dict] = field(default_factory=list)


# ============================================================
# Global session tracker
# ============================================================
_session: Optional[SessionCosts] = None


def init_tracker(model: str = "claude-sonnet-4-6-20250929") -> SessionCosts:
    """
    Initialize a new session tracker.

    Args:
        model: Default model name for this session

    Returns:
        New SessionCosts instance
    """
    global _session
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    _session = SessionCosts(session_id=session_id, model=model)
    log.debug(f"Cost tracker initialized: session={session_id}, model={model}")
    return _session


def get_session() -> SessionCosts:
    """
    Get the current session (or create a new one).

    Returns:
        Current SessionCosts instance
    """
    global _session
    if _session is None:
        _session = init_tracker()
    return _session


# ============================================================
# Cost calculation
# ============================================================
def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """
    Calculate the USD cost for a given token usage.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name for price lookup

    Returns:
        Cost in USD (rounded to 6 decimal places)
    """
    prices = MODEL_PRICES.get(model, MODEL_PRICES["default"])
    input_cost = (input_tokens / 1_000_000) * prices["input"]
    output_cost = (output_tokens / 1_000_000) * prices["output"]
    return round(input_cost + output_cost, 6)


# ============================================================
# Track an API call
# ============================================================
def track_call(
    input_tokens: int,
    output_tokens: int,
    model: Optional[str] = None,
) -> float:
    """
    Record the cost of one API call.

    Args:
        input_tokens: Input tokens used
        output_tokens: Output tokens used
        model: Model name (defaults to session model)

    Returns:
        Cost of this call in USD
    """
    session = get_session()
    model = model or session.model

    cost = calculate_cost(input_tokens, output_tokens, model)

    session.total_input_tokens += input_tokens
    session.total_output_tokens += output_tokens
    session.total_calls += 1
    session.total_cost_usd += cost

    session.calls_log.append({
        "call_num": session.total_calls,
        "time": datetime.now().strftime("%H:%M:%S"),
        "input": input_tokens,
        "output": output_tokens,
        "cost_usd": cost,
    })

    log.debug(
        f"API call #{session.total_calls}: "
        f"{input_tokens}in/{output_tokens}out = ${cost:.6f}"
    )
    return cost


# ============================================================
# Format cost summary
# ============================================================
def format_cost_summary() -> str:
    """
    Return a formatted summary of the entire session's cost.

    Returns:
        Formatted summary string
    """
    session = get_session()
    if session.total_calls == 0:
        return "No API calls made in this session."

    total_tokens = session.total_input_tokens + session.total_output_tokens

    lines = [
        "",
        "=" * 40,
        "  DevMind Session Summary",
        "=" * 40,
        f"  Total API calls : {session.total_calls}",
        f"  Input tokens    : {session.total_input_tokens:,}",
        f"  Output tokens   : {session.total_output_tokens:,}",
        f"  Total tokens    : {total_tokens:,}",
        f"  Total cost      : ${session.total_cost_usd:.4f} USD",
        f"  Model used      : {session.model}",
        "=" * 40,
    ]
    return "\n".join(lines)


# ============================================================
# Save session to disk
# ============================================================
def save_session_costs() -> None:
    """Save session costs to ~/.devmind/costs/"""
    session = get_session()
    if session.total_calls == 0:
        return

    try:
        costs_dir = Path.home() / ".devmind" / "costs"
        costs_dir.mkdir(parents=True, exist_ok=True)

        filename = costs_dir / f"session_{session.session_id}.json"
        with open(filename, "w") as f:
            json.dump(asdict(session), f, indent=2)

        log.info(f"Session costs saved: {filename}")
    except Exception as e:
        log.warning(f"Failed to save session costs: {e}")


# ============================================================
# Auto-print and save on exit
# ============================================================
def register_exit_hook() -> None:
    """Print cost summary and save to disk when the app exits."""
    def on_exit():
        session = get_session()
        if session.total_calls > 0:
            print(format_cost_summary())
            save_session_costs()

    atexit.register(on_exit)


if __name__ == "__main__":
    init_tracker("claude-sonnet-4-6-20250929")
    track_call(1500, 300, "claude-sonnet-4-6-20250929")
    track_call(2000, 500, "claude-sonnet-4-6-20250929")
    print(format_cost_summary())
