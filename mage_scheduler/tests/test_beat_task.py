"""Tests for tasks/dependency_task.py.

Covers:
  - _schedule_waiting_task_beat  (takes session directly; deferred import of run_command_at)
  - _try_unblock_task_beat       (takes session directly)
  - check_waiting_tasks          (uses SessionLocal() internally — patched via dep_mem_db fixture)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_task


def _mock_run_command_at(celery_id: str = "fake-celery-id"):
    """Return a mock that stands in for run_command_at with a usable apply_async."""
    mock = MagicMock()
    mock.apply_async.return_value = MagicMock(id=celery_id)
    return mock


# ---------------------------------------------------------------------------
# _schedule_waiting_task_beat
# ---------------------------------------------------------------------------

class TestScheduleWaitingTaskBeat:
    def _call(self, session, wt, mock_run=None):
        import tasks.dependency_task as dt
        if mock_run is None:
            mock_run = _mock_run_command_at()
        with patch("tasks.notification_task.run_command_at", mock_run):
            dt._schedule_waiting_task_beat(session, wt)
        return mock_run

    def test_status_becomes_scheduled(self, db_session):
        wt = make_task(db_session, status="waiting")
        self._call(db_session, wt)
        assert wt.status == "scheduled"

    def test_celery_task_id_is_set(self, db_session):
        wt = make_task(db_session, status="waiting")
        self._call(db_session, wt, _mock_run_command_at("beat-celery-123"))
        assert wt.celery_task_id == "beat-celery-123"

    def test_apply_async_called_once(self, db_session):
        wt = make_task(db_session, status="waiting")
        mock_run = self._call(db_session, wt)
        mock_run.apply_async.assert_called_once()


# ---------------------------------------------------------------------------
# _try_unblock_task_beat
# ---------------------------------------------------------------------------

class TestTryUnblockTaskBeat:
    def _call(self, session, wt):
        import tasks.dependency_task as dt
        mock_run = _mock_run_command_at()
        with patch("tasks.notification_task.run_command_at", mock_run):
            dt._try_unblock_task_beat(session, wt)
        return mock_run

    def test_orphaned_task_gets_scheduled(self, db_session):
        """Waiting task with no dependency rows should be scheduled immediately."""
        wt = make_task(db_session, status="waiting")
        mock_run = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_run.apply_async.assert_called_once()

    def test_all_deps_succeeded_schedules_task(self, db_session):
        from models import TaskDependency
        dep = make_task(db_session, status="success")
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=dep.id))
        db_session.flush()
        mock_run = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_run.apply_async.assert_called_once()

    @pytest.mark.parametrize("bad_status", ["failed", "cancelled", "blocked"])
    def test_bad_dep_fails_task(self, db_session, bad_status):
        from models import TaskDependency
        bad_dep = make_task(db_session, status=bad_status)
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=bad_dep.id))
        db_session.flush()
        mock_run = self._call(db_session, wt)
        assert wt.status == "failed"
        assert str(bad_dep.id) in wt.error
        mock_run.apply_async.assert_not_called()

    def test_in_flight_dep_leaves_task_waiting(self, db_session):
        from models import TaskDependency
        running = make_task(db_session, status="running")
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=running.id))
        db_session.flush()
        mock_run = self._call(db_session, wt)
        assert wt.status == "waiting"
        mock_run.apply_async.assert_not_called()


# ---------------------------------------------------------------------------
# check_waiting_tasks  (integration)
# ---------------------------------------------------------------------------

class TestCheckWaitingTasks:
    def _call(self, mock_run=None):
        import tasks.dependency_task as dt
        if mock_run is None:
            mock_run = _mock_run_command_at()
        with patch("tasks.notification_task.run_command_at", mock_run):
            dt.check_waiting_tasks()
        return mock_run

    def test_no_waiting_tasks_is_noop(self, dep_mem_db):
        Factory = dep_mem_db
        with Factory() as s:
            make_task(s, status="scheduled")
            s.commit()

        mock_run = self._call()
        mock_run.apply_async.assert_not_called()

    def test_waiting_task_with_done_dep_gets_scheduled(self, dep_mem_db):
        from models import TaskDependency, TaskRequest
        Factory = dep_mem_db
        with Factory() as s:
            dep = make_task(s, status="success")
            wt = make_task(s, status="waiting")
            s.add(TaskDependency(task_id=wt.id, depends_on_task_id=dep.id))
            s.commit()
            wt_id = wt.id

        self._call()

        with Factory() as s:
            wt = s.get(TaskRequest, wt_id)
            assert wt.status == "scheduled"

    def test_waiting_task_with_failed_dep_gets_failed(self, dep_mem_db):
        from models import TaskDependency, TaskRequest
        Factory = dep_mem_db
        with Factory() as s:
            dep = make_task(s, status="failed")
            wt = make_task(s, status="waiting")
            s.add(TaskDependency(task_id=wt.id, depends_on_task_id=dep.id))
            s.commit()
            wt_id = wt.id

        self._call()

        with Factory() as s:
            wt = s.get(TaskRequest, wt_id)
            assert wt.status == "failed"

    def test_waiting_task_with_in_flight_dep_stays_waiting(self, dep_mem_db):
        from models import TaskDependency, TaskRequest
        Factory = dep_mem_db
        with Factory() as s:
            dep = make_task(s, status="running")
            wt = make_task(s, status="waiting")
            s.add(TaskDependency(task_id=wt.id, depends_on_task_id=dep.id))
            s.commit()
            wt_id = wt.id

        mock_run = self._call()

        with Factory() as s:
            wt = s.get(TaskRequest, wt_id)
            assert wt.status == "waiting"
        mock_run.apply_async.assert_not_called()

    def test_multiple_waiting_tasks_each_evaluated(self, dep_mem_db):
        from models import TaskDependency, TaskRequest
        Factory = dep_mem_db
        with Factory() as s:
            done_dep = make_task(s, status="success")
            bad_dep = make_task(s, status="failed")
            wt_ready = make_task(s, status="waiting")
            wt_blocked = make_task(s, status="waiting")
            s.add(TaskDependency(task_id=wt_ready.id, depends_on_task_id=done_dep.id))
            s.add(TaskDependency(task_id=wt_blocked.id, depends_on_task_id=bad_dep.id))
            s.commit()
            ready_id, blocked_id = wt_ready.id, wt_blocked.id

        self._call()

        with Factory() as s:
            assert s.get(TaskRequest, ready_id).status == "scheduled"
            assert s.get(TaskRequest, blocked_id).status == "failed"
