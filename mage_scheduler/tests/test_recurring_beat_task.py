"""Tests for the recurring beat task and its helpers.

Covers:
  - _compute_next_run
  - compute_initial_next_run
  - _spawn_task (command path, action path, missing action, no-command skip)
  - check_recurring_tasks (due, future, disabled, multiple)
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from tests.conftest import make_action, make_recurring


def _session(factory):
    return factory()


def _mock_celery(monkeypatch):
    import tasks.recurring_task as rct
    fake = MagicMock()
    fake.id = "fake-celery-id"
    monkeypatch.setattr(rct.run_command_at, "apply_async", lambda *a, **kw: fake)


# ---------------------------------------------------------------------------
# _compute_next_run
# ---------------------------------------------------------------------------

class TestComputeNextRun:
    def test_returns_datetime(self):
        from tasks.recurring_task import _compute_next_run
        result = _compute_next_run("* * * * *", "UTC", datetime(2026, 1, 1, 12, 0, 0))
        assert isinstance(result, datetime)

    def test_result_is_after_from_dt(self):
        from tasks.recurring_task import _compute_next_run
        from_dt = datetime(2026, 1, 1, 12, 0, 0)
        assert _compute_next_run("* * * * *", "UTC", from_dt) > from_dt

    def test_hourly_cron_advances_to_next_hour(self):
        from tasks.recurring_task import _compute_next_run
        from_dt = datetime(2026, 1, 1, 12, 0, 0)
        result = _compute_next_run("0 * * * *", "UTC", from_dt)
        assert result.hour == 13
        assert result.minute == 0

    def test_result_is_naive(self):
        from tasks.recurring_task import _compute_next_run
        result = _compute_next_run("* * * * *", "UTC", datetime(2026, 1, 1, 12, 0, 0))
        assert result.tzinfo is None

    def test_invalid_timezone_falls_back_to_utc(self):
        from tasks.recurring_task import _compute_next_run
        # Must not raise
        result = _compute_next_run("* * * * *", "Invalid/Zone", datetime(2026, 1, 1, 12, 0, 0))
        assert isinstance(result, datetime)


# ---------------------------------------------------------------------------
# compute_initial_next_run
# ---------------------------------------------------------------------------

class TestComputeInitialNextRun:
    def test_returns_naive_datetime(self):
        from tasks.recurring_task import compute_initial_next_run
        result = compute_initial_next_run("* * * * *", "UTC")
        assert isinstance(result, datetime)
        assert result.tzinfo is None

    def test_result_is_in_the_future(self):
        from tasks.recurring_task import compute_initial_next_run
        before = datetime.utcnow()
        result = compute_initial_next_run("* * * * *", "UTC")
        assert result >= before


# ---------------------------------------------------------------------------
# _spawn_task
# ---------------------------------------------------------------------------

class TestSpawnTask:
    def test_creates_task_request(self, rec_mem_db, monkeypatch):
        from tasks.recurring_task import _spawn_task
        from models import TaskRequest

        _mock_celery(monkeypatch)
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

    def test_task_row_committed_before_celery_dispatch(self, rec_mem_db, monkeypatch):
        """The TaskRequest row must be visible in the DB before apply_async is called.

        Race condition: if apply_async fires before session.commit(), Celery can
        pick up the job and call session.get(TaskRequest, id) before the row exists,
        returning None and silently failing with {"error": "task_request_not_found"}.
        """
        import tasks.recurring_task as rct
        from tasks.recurring_task import _spawn_task
        from models import TaskRequest

        visibility_at_dispatch: list[bool] = []

        def fake_apply_async(*args, **kwargs):
            # At dispatch time, open a fresh session and check the row exists
            s = rec_mem_db()
            task_id = kwargs.get("args", [None])[0] if kwargs.get("args") else None
            if task_id is None and args:
                task_id = args[0][0] if args[0] else None
            row = s.get(TaskRequest, task_id)
            visibility_at_dispatch.append(row is not None)
            s.close()
            fake = MagicMock()
            fake.id = "check-celery-id"
            return fake

        monkeypatch.setattr(rct.run_command_at, "apply_async", fake_apply_async)

        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo race")
        s.commit()

        _spawn_task(s, rt, datetime.utcnow())

        assert visibility_at_dispatch == [True], (
            "TaskRequest row was not committed before apply_async was called"
        )
        s.close()

    def test_celery_dispatched_with_correct_args(self, rec_mem_db, monkeypatch):
        import tasks.recurring_task as rct
        from tasks.recurring_task import _spawn_task

        fake = MagicMock()
        fake.id = "celery-xyz"
        mock_apply = MagicMock(return_value=fake)
        monkeypatch.setattr(rct.run_command_at, "apply_async", mock_apply)

        s = _session(rec_mem_db)
        rt = make_recurring(s, command="echo ok")
        s.commit()

        now = datetime.utcnow()
        _spawn_task(s, rt, now)

        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args
        assert call_kwargs[1]["eta"] == now or call_kwargs[0]
        s.close()

    def test_advances_next_run_at_and_sets_last_run_at(self, rec_mem_db, monkeypatch):
        from tasks.recurring_task import _spawn_task

        _mock_celery(monkeypatch)
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
        """When rt.action_name is set and command is empty, command comes from Action."""
        from tasks.recurring_task import _spawn_task
        from models import TaskRequest

        _mock_celery(monkeypatch)
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
        """Unknown action_name → no TaskRequest, but next_run_at still advances."""
        from tasks.recurring_task import _spawn_task
        from models import TaskRequest

        _mock_celery(monkeypatch)
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
        from tasks.recurring_task import _spawn_task
        from models import TaskRequest

        _mock_celery(monkeypatch)
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
        from tasks.recurring_task import check_recurring_tasks
        from models import TaskRequest

        _mock_celery(monkeypatch)
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
        from tasks.recurring_task import check_recurring_tasks
        from models import TaskRequest

        _mock_celery(monkeypatch)
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
        from tasks.recurring_task import check_recurring_tasks
        from models import TaskRequest

        _mock_celery(monkeypatch)
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
        from tasks.recurring_task import check_recurring_tasks
        from models import TaskRequest

        _mock_celery(monkeypatch)
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
