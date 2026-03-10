"""Tests for jobs/dependency_check.py.

Covers:
  - _schedule_waiting_task_beat  (takes session directly; deferred import of dispatch.schedule_command)
  - _try_unblock_task_beat       (takes session directly)
  - check_waiting_tasks          (uses SessionLocal() internally — patched via dep_mem_db fixture)

Adapted from test_beat_task.py — Celery apply_async replaced with
dispatch.schedule_command mocking.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.conftest import make_task


# ---------------------------------------------------------------------------
# _schedule_waiting_task_beat
# ---------------------------------------------------------------------------

class TestScheduleWaitingTaskBeat:
    def _call(self, session, wt, job_id="fake-job-id"):
        import jobs.dependency_check as dc
        with patch("dispatch.schedule_command", return_value=job_id) as mock_sc:
            dc._schedule_waiting_task_beat(session, wt)
        return mock_sc

    def test_status_becomes_scheduled(self, db_session):
        wt = make_task(db_session, status="waiting")
        self._call(db_session, wt)
        assert wt.status == "scheduled"

    def test_celery_task_id_is_set(self, db_session):
        wt = make_task(db_session, status="waiting")
        self._call(db_session, wt, job_id="beat-job-123")
        assert wt.celery_task_id == "beat-job-123"

    def test_schedule_command_called_once(self, db_session):
        wt = make_task(db_session, status="waiting")
        mock_sc = self._call(db_session, wt)
        mock_sc.assert_called_once()


# ---------------------------------------------------------------------------
# _try_unblock_task_beat
# ---------------------------------------------------------------------------

class TestTryUnblockTaskBeat:
    def _call(self, session, wt):
        import jobs.dependency_check as dc
        with patch("dispatch.schedule_command", return_value="fake-job-id") as mock_sc:
            dc._try_unblock_task_beat(session, wt)
        return mock_sc

    def test_orphaned_task_gets_scheduled(self, db_session):
        """Waiting task with no dependency rows should be scheduled immediately."""
        wt = make_task(db_session, status="waiting")
        mock_sc = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_sc.assert_called_once()

    def test_all_deps_succeeded_schedules_task(self, db_session):
        from models import TaskDependency
        dep = make_task(db_session, status="success")
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=dep.id))
        db_session.flush()
        mock_sc = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_sc.assert_called_once()

    @pytest.mark.parametrize("bad_status", ["failed", "cancelled", "blocked"])
    def test_bad_dep_fails_task(self, db_session, bad_status):
        from models import TaskDependency
        bad_dep = make_task(db_session, status=bad_status)
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=bad_dep.id))
        db_session.flush()
        mock_sc = self._call(db_session, wt)
        assert wt.status == "failed"
        assert str(bad_dep.id) in wt.error
        mock_sc.assert_not_called()

    def test_in_flight_dep_leaves_task_waiting(self, db_session):
        from models import TaskDependency
        running = make_task(db_session, status="running")
        wt = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=wt.id, depends_on_task_id=running.id))
        db_session.flush()
        mock_sc = self._call(db_session, wt)
        assert wt.status == "waiting"
        mock_sc.assert_not_called()


# ---------------------------------------------------------------------------
# check_waiting_tasks  (integration)
# ---------------------------------------------------------------------------

class TestCheckWaitingTasks:
    def _call(self):
        import jobs.dependency_check as dc
        with patch("dispatch.schedule_command", return_value="fake-job-id") as mock_sc:
            dc.check_waiting_tasks()
        return mock_sc

    def test_no_waiting_tasks_is_noop(self, dep_mem_db):
        Factory = dep_mem_db
        with Factory() as s:
            make_task(s, status="scheduled")
            s.commit()

        mock_sc = self._call()
        mock_sc.assert_not_called()

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

        mock_sc = self._call()

        with Factory() as s:
            wt = s.get(TaskRequest, wt_id)
            assert wt.status == "waiting"
        mock_sc.assert_not_called()

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
