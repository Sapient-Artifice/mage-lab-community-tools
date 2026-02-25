"""Tests for the dependency-runtime helpers in tasks/notification_task.py.

Covers:
  - _schedule_waiting_task   (takes session directly)
  - _try_unblock_task        (takes session directly)
  - _trigger_dependents      (uses SessionLocal() internally — patched via nt_mem_db fixture)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_apply_async(celery_id: str = "fake-celery-id"):
    """Return a mock whose .apply_async() returns an object with .id = celery_id."""
    mock_task = MagicMock()
    mock_task.apply_async.return_value = MagicMock(id=celery_id)
    return mock_task


# ---------------------------------------------------------------------------
# _schedule_waiting_task
# ---------------------------------------------------------------------------

class TestScheduleWaitingTask:
    def _call(self, session, wt, mock_task=None):
        import tasks.notification_task as nt
        if mock_task is None:
            mock_task = _fake_apply_async()
        with patch.object(nt, "run_command_at", mock_task):
            nt._schedule_waiting_task(session, wt)
        return mock_task

    def test_status_becomes_scheduled(self, db_session):
        wt = make_task(db_session, status="waiting")
        self._call(db_session, wt)
        assert wt.status == "scheduled"

    def test_celery_task_id_is_set(self, db_session):
        wt = make_task(db_session, status="waiting")
        mock_task = _fake_apply_async("celery-abc-123")
        self._call(db_session, wt, mock_task)
        assert wt.celery_task_id == "celery-abc-123"

    def test_apply_async_called_once(self, db_session):
        wt = make_task(db_session, status="waiting")
        mock_task = self._call(db_session, wt)
        mock_task.apply_async.assert_called_once()

    def test_future_run_at_used_as_eta(self, db_session):
        future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        wt = make_task(db_session, status="waiting")
        wt.run_at = future
        mock_task = _fake_apply_async()
        with patch("tasks.notification_task.run_command_at", mock_task):
            import tasks.notification_task as nt
            nt._schedule_waiting_task(db_session, wt)
        _, kwargs = mock_task.apply_async.call_args
        assert kwargs["eta"] == future

    def test_past_run_at_replaced_with_now(self, db_session):
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        wt = make_task(db_session, status="waiting")
        wt.run_at = past
        mock_task = _fake_apply_async()
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        with patch("tasks.notification_task.run_command_at", mock_task):
            import tasks.notification_task as nt
            nt._schedule_waiting_task(db_session, wt)
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        _, kwargs = mock_task.apply_async.call_args
        assert before <= kwargs["eta"] <= after


# ---------------------------------------------------------------------------
# _try_unblock_task
# ---------------------------------------------------------------------------

class TestTryUnblockTask:
    def _call(self, session, wt, mock_task=None):
        import tasks.notification_task as nt
        if mock_task is None:
            mock_task = _fake_apply_async()
        with patch.object(nt, "run_command_at", mock_task):
            nt._try_unblock_task(session, wt)
        return mock_task

    def test_orphaned_waiting_task_gets_scheduled(self, db_session):
        """A waiting task with no dep rows should be scheduled immediately."""
        wt = make_task(db_session, status="waiting")
        mock_task = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_task.apply_async.assert_called_once()

    def test_all_deps_succeeded_schedules_task(self, db_session):
        from models import TaskDependency
        dep1 = make_task(db_session, status="success")
        dep2 = make_task(db_session, status="success")
        wt = make_task(db_session, status="waiting")
        db_session.add_all([
            TaskDependency(task_id=wt.id, depends_on_task_id=dep1.id),
            TaskDependency(task_id=wt.id, depends_on_task_id=dep2.id),
        ])
        db_session.flush()
        mock_task = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_task.apply_async.assert_called_once()

    @pytest.mark.parametrize("bad_status", ["failed", "cancelled", "blocked"])
    def test_bad_dep_fails_waiting_task(self, db_session, bad_status):
        from models import TaskDependency
        bad_dep = make_task(db_session, status=bad_status)
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=bad_dep.id))
        db_session.flush()
        mock_task = self._call(db_session, wt)
        assert wt.status == "failed"
        assert str(bad_dep.id) in wt.error
        mock_task.apply_async.assert_not_called()

    def test_in_flight_dep_leaves_task_waiting(self, db_session):
        from models import TaskDependency
        done = make_task(db_session, status="success")
        running = make_task(db_session, status="running")
        wt = make_task(db_session, status="waiting")
        db_session.add_all([
            TaskDependency(task_id=wt.id, depends_on_task_id=done.id),
            TaskDependency(task_id=wt.id, depends_on_task_id=running.id),
        ])
        db_session.flush()
        mock_task = self._call(db_session, wt)
        assert wt.status == "waiting"
        mock_task.apply_async.assert_not_called()

    def test_bad_dep_beats_in_flight_dep(self, db_session):
        """If any dep is bad, task fails even if other deps are still running."""
        from models import TaskDependency
        failed_dep = make_task(db_session, status="failed")
        running_dep = make_task(db_session, status="running")
        wt = make_task(db_session, status="waiting")
        db_session.add_all([
            TaskDependency(task_id=wt.id, depends_on_task_id=failed_dep.id),
            TaskDependency(task_id=wt.id, depends_on_task_id=running_dep.id),
        ])
        db_session.flush()
        self._call(db_session, wt)
        assert wt.status == "failed"

    def test_error_message_names_the_bad_dep_id(self, db_session):
        from models import TaskDependency
        bad = make_task(db_session, status="failed")
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=bad.id))
        db_session.flush()
        self._call(db_session, wt)
        assert f"Dependency task {bad.id} failed or was cancelled." == wt.error


# ---------------------------------------------------------------------------
# _trigger_dependents
# ---------------------------------------------------------------------------

class TestTriggerDependents:
    def _call(self, completed_task_id: int, completed_status: str, mock_task=None):
        import tasks.notification_task as nt
        if mock_task is None:
            mock_task = _fake_apply_async()
        with patch.object(nt, "run_command_at", mock_task):
            nt._trigger_dependents(completed_task_id, completed_status)
        return mock_task

    def test_non_terminal_status_is_noop(self, nt_mem_db):
        Factory = nt_mem_db
        with Factory() as s:
            upstream = make_task(s, status="running")
            dependent = make_task(s, status="waiting")
            s.commit()
            upstream_id, dependent_id = upstream.id, dependent.id

        self._call(upstream_id, "running")

        with Factory() as s:
            dep = s.get(__import__("models").TaskRequest, dependent_id)
            assert dep.status == "waiting"

    def test_no_dependents_is_noop(self, nt_mem_db):
        Factory = nt_mem_db
        with Factory() as s:
            upstream = make_task(s, status="success")
            s.commit()
            upstream_id = upstream.id

        # Should return without error
        self._call(upstream_id, "success")

    @pytest.mark.parametrize("bad_status", ["failed", "cancelled"])
    def test_bad_terminal_cascades_fail_to_waiting(self, nt_mem_db, bad_status):
        from models import TaskDependency, TaskRequest
        Factory = nt_mem_db
        with Factory() as s:
            upstream = make_task(s, status=bad_status)
            dependent = make_task(s, status="waiting")
            s.add(TaskDependency(task_id=dependent.id, depends_on_task_id=upstream.id))
            s.commit()
            upstream_id, dependent_id = upstream.id, dependent.id

        self._call(upstream_id, bad_status)

        with Factory() as s:
            dep = s.get(TaskRequest, dependent_id)
            assert dep.status == "failed"
            assert str(upstream_id) in dep.error

    def test_success_schedules_waiting_dependent(self, nt_mem_db):
        from models import TaskDependency, TaskRequest
        Factory = nt_mem_db
        with Factory() as s:
            upstream = make_task(s, status="success")
            dependent = make_task(s, status="waiting")
            s.add(TaskDependency(task_id=dependent.id, depends_on_task_id=upstream.id))
            s.commit()
            upstream_id, dependent_id = upstream.id, dependent.id

        mock_task = self._call(upstream_id, "success")

        with Factory() as s:
            dep = s.get(TaskRequest, dependent_id)
            assert dep.status == "scheduled"
        mock_task.apply_async.assert_called_once()

    def test_success_leaves_waiting_when_other_dep_still_running(self, nt_mem_db):
        from models import TaskDependency, TaskRequest
        Factory = nt_mem_db
        with Factory() as s:
            upstream = make_task(s, status="success")
            other_dep = make_task(s, status="running")
            dependent = make_task(s, status="waiting")
            s.add_all([
                TaskDependency(task_id=dependent.id, depends_on_task_id=upstream.id),
                TaskDependency(task_id=dependent.id, depends_on_task_id=other_dep.id),
            ])
            s.commit()
            upstream_id, dependent_id = upstream.id, dependent.id

        mock_task = self._call(upstream_id, "success")

        with Factory() as s:
            dep = s.get(TaskRequest, dependent_id)
            assert dep.status == "waiting"
        mock_task.apply_async.assert_not_called()

    def test_non_waiting_dependents_are_not_touched(self, nt_mem_db):
        from models import TaskDependency, TaskRequest
        Factory = nt_mem_db
        with Factory() as s:
            upstream = make_task(s, status="failed")
            already_running = make_task(s, status="running")
            s.add(TaskDependency(task_id=already_running.id, depends_on_task_id=upstream.id))
            s.commit()
            upstream_id, running_id = upstream.id, already_running.id

        self._call(upstream_id, "failed")

        with Factory() as s:
            running = s.get(TaskRequest, running_id)
            assert running.status == "running"
