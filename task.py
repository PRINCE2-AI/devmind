"""
task.py — DevMind's Task System
Inspired by Claude Code's Task.ts.
Tracks the lifecycle of every operation performed by the agent.
"""

import secrets
import string
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# Task Types — the kinds of work the agent can do
# ============================================================
class TaskType(Enum):
    BASH = "bash"               # Running a terminal command
    FILE_READ = "file_read"     # Reading a file
    FILE_WRITE = "file_write"   # Writing a file
    WEB_SEARCH = "web_search"   # Searching the internet
    AGENT = "agent"             # Querying Claude


# ============================================================
# Task Status — the current state of a task
# (Inspired by Task.ts: TaskStatus)
# ============================================================
class TaskStatus(Enum):
    PENDING = "pending"       # Not started yet
    RUNNING = "running"       # Currently in progress
    COMPLETED = "completed"   # Finished successfully
    FAILED = "failed"         # Failed with an error
    KILLED = "killed"         # Terminated mid-execution


def is_terminal_status(status: TaskStatus) -> bool:
    """Return True if the task can no longer change state. (Task.ts: isTerminalTaskStatus)"""
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED)


# ============================================================
# Task ID generation — unique token per task
# e.g. "b4f7k2m9" for a bash task
# (Inspired by Task.ts: generateTaskId)
# ============================================================
TASK_PREFIXES = {
    TaskType.BASH: "b",
    TaskType.FILE_READ: "r",
    TaskType.FILE_WRITE: "w",
    TaskType.WEB_SEARCH: "s",
    TaskType.AGENT: "a",
}

ALPHABET = string.digits + string.ascii_lowercase  # 0-9 + a-z


def generate_task_id(task_type: TaskType) -> str:
    """Generate a secure random ID like 'b4f7k2m9'."""
    prefix = TASK_PREFIXES.get(task_type, "x")
    random_part = "".join(
        ALPHABET[b % len(ALPHABET)]
        for b in secrets.token_bytes(8)
    )
    return prefix + random_part


# ============================================================
# TaskState — full information about one task
# (Inspired by Task.ts: TaskStateBase)
# ============================================================
@dataclass
class TaskState:
    id: str
    type: TaskType
    description: str
    status: TaskStatus = TaskStatus.PENDING
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None


def create_task(task_type: TaskType, description: str) -> TaskState:
    """Create a new task."""
    return TaskState(
        id=generate_task_id(task_type),
        type=task_type,
        description=description,
    )


def complete_task(task: TaskState, result: str) -> TaskState:
    """Mark a task as successfully completed."""
    task.status = TaskStatus.COMPLETED
    task.end_time = time.time()
    task.result = result
    return task


def fail_task(task: TaskState, error: str) -> TaskState:
    """Mark a task as failed."""
    task.status = TaskStatus.FAILED
    task.end_time = time.time()
    task.error = error
    return task


def get_duration(task: TaskState) -> Optional[float]:
    """Return how many seconds the task took, or None if still running."""
    if task.end_time and task.start_time:
        return round(task.end_time - task.start_time, 2)
    return None


if __name__ == "__main__":
    t = create_task(TaskType.BASH, "run git status")
    print(f"Task created: {t.id} | Status: {t.status.value}")
    t = complete_task(t, "On branch main, nothing to commit")
    print(f"Done! Duration: {get_duration(t)}s")
    print(f"Terminal status? {is_terminal_status(t.status)}")
