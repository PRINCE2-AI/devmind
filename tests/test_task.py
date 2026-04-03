"""
tests/test_task.py — Tests for the task lifecycle system
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from task import (
    TaskType, TaskStatus,
    create_task, complete_task, fail_task, get_duration,
    generate_task_id, is_terminal_status, TaskState,
)


class TestTaskCreation:
    def test_create_task(self):
        """Task should be created with correct defaults"""
        t = create_task(TaskType.BASH, "run git status")
        assert t.type == TaskType.BASH
        assert t.description == "run git status"
        assert t.status == TaskStatus.PENDING
        assert t.id.startswith("b")  # BASH prefix

    def test_unique_ids(self):
        """Every task should have a unique ID"""
        ids = {create_task(TaskType.AGENT, "test").id for _ in range(20)}
        assert len(ids) == 20

    def test_task_id_prefixes(self):
        """Each task type should have its own prefix"""
        assert create_task(TaskType.BASH, "x").id.startswith("b")
        assert create_task(TaskType.FILE_READ, "x").id.startswith("r")
        assert create_task(TaskType.FILE_WRITE, "x").id.startswith("w")
        assert create_task(TaskType.AGENT, "x").id.startswith("a")

    def test_task_has_start_time(self):
        """Task must record a start time"""
        t = create_task(TaskType.AGENT, "test")
        assert t.start_time > 0

    def test_task_state_dataclass(self):
        """TaskState must be a proper dataclass"""
        t = create_task(TaskType.AGENT, "test")
        assert isinstance(t, TaskState)
        assert hasattr(t, "id")
        assert hasattr(t, "type")
        assert hasattr(t, "description")
        assert hasattr(t, "status")


class TestTaskLifecycle:
    def test_complete_task(self):
        """Task should be marked as completed"""
        t = create_task(TaskType.AGENT, "some work")
        t.status = TaskStatus.RUNNING
        complete_task(t, "Done!")

        assert t.status == TaskStatus.COMPLETED
        assert t.result == "Done!"
        assert t.end_time is not None

    def test_fail_task(self):
        """Task should be marked as failed"""
        t = create_task(TaskType.BASH, "bad command")
        fail_task(t, "Command not found")

        assert t.status == TaskStatus.FAILED
        assert t.error == "Command not found"

    def test_get_duration(self):
        """Duration should be calculated correctly"""
        t = create_task(TaskType.AGENT, "timing test")
        t.status = TaskStatus.RUNNING
        time.sleep(0.1)
        complete_task(t, "done")

        dur = get_duration(t)
        assert dur is not None
        assert dur >= 0.1

    def test_duration_pending_task(self):
        """A pending task should return None for duration"""
        t = create_task(TaskType.AGENT, "not finished yet")
        assert get_duration(t) is None

    def test_failed_task_has_end_time(self):
        """A failed task must record an end time"""
        t = create_task(TaskType.AGENT, "fail test")
        fail_task(t, "error")
        assert t.end_time is not None


class TestTerminalStatus:
    def test_completed_is_terminal(self):
        t = create_task(TaskType.AGENT, "x")
        complete_task(t, "ok")
        assert is_terminal_status(t.status) is True

    def test_failed_is_terminal(self):
        t = create_task(TaskType.AGENT, "x")
        fail_task(t, "err")
        assert is_terminal_status(t.status) is True

    def test_pending_not_terminal(self):
        t = create_task(TaskType.AGENT, "x")
        assert is_terminal_status(t.status) is False

    def test_running_not_terminal(self):
        t = create_task(TaskType.AGENT, "x")
        t.status = TaskStatus.RUNNING
        assert is_terminal_status(t.status) is False

    def test_killed_is_terminal(self):
        t = create_task(TaskType.AGENT, "x")
        t.status = TaskStatus.KILLED
        assert is_terminal_status(t.status) is True


class TestTaskTypes:
    def test_all_task_types_exist(self):
        """All expected task types must exist"""
        assert TaskType.BASH
        assert TaskType.FILE_READ
        assert TaskType.FILE_WRITE
        assert TaskType.WEB_SEARCH
        assert TaskType.AGENT

    def test_all_statuses_exist(self):
        """All expected statuses must exist"""
        assert TaskStatus.PENDING
        assert TaskStatus.RUNNING
        assert TaskStatus.COMPLETED
        assert TaskStatus.FAILED
        assert TaskStatus.KILLED


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
