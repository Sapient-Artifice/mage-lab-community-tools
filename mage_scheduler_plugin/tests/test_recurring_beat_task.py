"""Tests for the recurring beat job and its helpers.

Adapted from test_recurring_beat_task.py — Celery apply_async replaced with
dispatch.schedule_command mocking.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from tests.conftest import make_action, make_recurring


def _session(factory):
    return factory()


def _mock_dispatch(monkeypatch, job_id: str = "fake-job-id"):
    """Patch dispatch.schedule_command to return a fake job_id."""
    import dispatch
    monkeypatch.setattr(dispatch, "schedule_command", lambda *a, **kw: job_id)
    return job_id


# ---------------------------------------------------------------------------
# _compute_next_run
# ---------------------------------------------------------------------------

class TestComputeNextRun:
    def test_returns_datetime(self):
        from jobs.recurring_check import _compute_next_run
        result = _compute_next_run("* * * * *", "UTC", datetime(2026, 1, 1, 12, 0, 0))
        assert isinstance(result, datetime)

    def test_result_is_after_from_dt(self):
        from jobs.recurring_check import _compute_next_run
        from_dt = datetime(2026, 1, 1, 12, 0, 0)
        assert _compute_next_run("* * * * *", "UTC", from_dt) > from_dt

    def test_hourly_cron_advances_to_next_hour(self):
        from jobs.recurring_check import _compute_next_run
        from_dt = datetime(2026, 1, 1, 12, 0, 0)
        result = _compute_next_run("0 * * * *", "UTC", from_dt)
        assert result.hour == 13
        assert result.minute == 0

    def test_result_is_naive(self):
        from jobs.recurring_check import _compute_next_run
        result = _compute_next_run("* * * * *", "UTC", datetime(2026, 1, 1, 12, 0, 0))
        assert result.tzinfo is None

    def test_invalid_timezone_falls_back_to_utc(self):
        from jobs.recurring_check import _compute_next_run
        result = _compute_next_run("* * * * *", "Invalid/Zone", datetime(2026, 1, 1, 12, 0, 0))
        assert isinstance(result, datetime)


# ---------------------------------------------------------------------------
# compute_initial_next_run
# ---------------------------------------------------------------------------

class TestComputeInitialNextRun:
    def test_returns_naive_datetime(self):
        from jobs.recurring_check import compute_initial_next_run
        result = compute_initial_next_run("* * * * *", "UTC")
        assert isinstance(result, datetime)
        assert result.tzinfo is None

    def test_result_is_in_the_future(self):
        from jobs.recurring_check import compute_initial_next_run
        before = datetime.utcnow()
        result = compute_initial_next_run("* * * * *", "UTC")
        assert result >= before


# ---------------------------------------------------------------------------
# _spawn_task
# ---------------------------------------------------------------------------

class TestSpawnTask:
    def test_creates_task_request(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import _spawn_task
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo ok")
        s.commit()

        _spawn_task(s, rt, datetime.utcnow())
        s.commit()

        tasks = s.execute(select(TaskRequest)).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].command == "echo ok"
        assert tasks[0].status == "scheduled"
        s.close()

    def test_task_row_committed_before_dispatch(self, rec_mem_db, monkeypatch):
        """TaskRequest row must be committed before schedule_command is called.

        If dispatch fires before session.commit(), the worker sees None for the
        row and silently fails with {"error": "task_request_not_found"}.
        """
        import dispatch
        from jobs.recurring_check import _spawn_task
        from models import TaskRequest

        visibility_at_dispatch: list[bool] = []

        def fake_schedule_command(task_id, command, run_at):
            fresh = rec_mem_db()
            row = fresh.get(TaskRequest, task_id)
            visibility_at_dispatch.append(row is not None)
            fresh.close()
            return "check-job-id"

        monkeypatch.setattr(dispatch, "schedule_command", fake_schedule_command)

        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo race")
        s.commit()

        _spawn_task(s, rt, datetime.utcnow())

        assert visibility_at_dispatch == [True], (
            "TaskRequest row was not committed before schedule_command was called"
        )
        s.close()

    def test_dispatch_called_with_correct_task_id_and_command(self, rec_mem_db, monkeypatch):
        import dispatch
        from jobs.recurring_check import _spawn_task

        calls = []
        def fake_schedule(task_id, command, run_at):
            calls.append((task_id, command, run_at))
            return "job-xyz"

        monkeypatch.setattr(dispatch, "schedule_command", fake_schedule)

        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo ok")
        s.commit()

        _spawn_task(s, rt, datetime.utcnow())

        assert len(calls) == 1
        called_task_id, called_command, _ = calls[0]
        assert called_command == "echo ok"
        s.close()

    def test_advances_next_run_at_and_sets_last_run_at(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import _spawn_task

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo ok")
        s.commit()

        now = datetime.utcnow()
        _spawn_task(s, rt, now)

        assert rt.last_run_at == now
        assert rt.next_run_at is not None
        assert rt.next_run_at > now
        s.close()

    def test_action_command_resolved_from_db(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import _spawn_task
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        make_action(s, name="my_act", command="echo from_action")
        rt = make_recurring(s, command="")
        rt.action_name = "my_act"
        s.commit()

        _spawn_task(s, rt, datetime.utcnow())
        s.commit()

        tasks = s.execute(select(TaskRequest)).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].command == "echo from_action"
        s.close()

    def test_missing_action_skips_task_creation(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import _spawn_task
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        rt = make_recurring(s, command="")
        rt.action_name = "nonexistent"
        s.commit()

        _spawn_task(s, rt, datetime.utcnow())
        s.commit()

        assert len(s.execute(select(TaskRequest)).scalars().all()) == 0
        assert rt.next_run_at is not None
        s.close()

    def test_no_command_no_action_skips_task_creation(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import _spawn_task
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        rt = make_recurring(s, command="")
        s.commit()

        _spawn_task(s, rt, datetime.utcnow())
        s.commit()

        assert len(s.execute(select(TaskRequest)).scalars().all()) == 0
        s.close()


# ---------------------------------------------------------------------------
# check_recurring_tasks
# ---------------------------------------------------------------------------

class TestCheckRecurringTasks:
    def test_due_task_spawns_task_request(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import check_recurring_tasks
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo due")
        rt.next_run_at = datetime(2000, 1, 1)
        s.commit()
        s.close()

        check_recurring_tasks()

        s2 = _session(rec_mem_db)
        tasks = s2.execute(select(TaskRequest)).scalars().all()
        assert any(t.command == "echo due" for t in tasks)
        s2.close()

    def test_future_task_not_spawned(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import check_recurring_tasks
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo future")
        rt.next_run_at = datetime(2099, 1, 1)
        s.commit()
        s.close()

        check_recurring_tasks()

        s2 = _session(rec_mem_db)
        assert s2.execute(select(TaskRequest)).scalars().all() == []
        s2.close()

    def test_disabled_task_not_spawned(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import check_recurring_tasks
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo disabled", enabled=0)
        rt.next_run_at = datetime(2000, 1, 1)
        s.commit()
        s.close()

        check_recurring_tasks()

        s2 = _session(rec_mem_db)
        assert s2.execute(select(TaskRequest)).scalars().all() == []
        s2.close()

    def test_multiple_due_tasks_all_spawned(self, rec_mem_db, monkeypatch):
        from jobs.recurring_check import check_recurring_tasks
        from models import TaskRequest

        _mock_dispatch(monkeypatch)
        s = _session(rec_mem_db)
        for i in range(3):
            rt = make_recurring(s, name=f"rt{i}", command=f"echo {i}")
            rt.next_run_at = datetime(2000, 1, 1)
        s.commit()
        s.close()

        check_recurring_tasks()

        s2 = _session(rec_mem_db)
        assert len(s2.execute(select(TaskRequest)).scalars().all()) == 3
        s2.close()
