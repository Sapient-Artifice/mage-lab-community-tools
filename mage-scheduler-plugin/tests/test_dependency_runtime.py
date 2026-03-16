"""Tests for the dependency-runtime helpers in jobs/run_command.py.

Covers:
  - _schedule_waiting_task   (takes session directly)
  - _try_unblock_task        (takes session directly)
  - _trigger_dependents      (uses SessionLocal() internally — patched via nt_mem_db fixture)

Adapted from test_dependency_runtime.py — Celery apply_async replaced with
dispatch.schedule_command mocking.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests.conftest import make_task


# ---------------------------------------------------------------------------
# _schedule_waiting_task
# ---------------------------------------------------------------------------

class TestScheduleWaitingTask:
    def _call(self, session, wt, job_id="fake-job-id"):
        import jobs.run_command as rc
        with patch("dispatch.schedule_command", return_value=job_id) as mock_sc:
            rc._schedule_waiting_task(session, wt)
        return mock_sc

    def test_status_becomes_scheduled(self, db_session):
        wt = make_task(db_session, status="waiting")
        self._call(db_session, wt)
        assert wt.status == "scheduled"

    def test_job_id_is_set(self, db_session):
        wt = make_task(db_session, status="waiting")
        self._call(db_session, wt, job_id="rc-job-abc-123")
        assert wt.job_id == "rc-job-abc-123"

    def test_schedule_command_called_once(self, db_session):
        wt = make_task(db_session, status="waiting")
        mock_sc = self._call(db_session, wt)
        mock_sc.assert_called_once()

    def test_future_run_at_passed_as_run_at_arg(self, db_session):
        future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        wt = make_task(db_session, status="waiting")
        wt.run_at = future

        calls = []
        def fake_sc(task_id, command, run_at):
            calls.append(run_at)
            return "job-id"

        import jobs.run_command as rc
        with patch("dispatch.schedule_command", side_effect=fake_sc):
            rc._schedule_waiting_task(db_session, wt)

        assert len(calls) == 1
        # run_at should be tz-aware and approximately equal to the future naive time
        assert calls[0].tzinfo is not None
        assert calls[0] > datetime.now(timezone.utc)

    def test_past_run_at_replaced_with_now(self, db_session):
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        wt = make_task(db_session, status="waiting")
        wt.run_at = past

        calls = []
        def fake_sc(task_id, command, run_at):
            calls.append(run_at)
            return "job-id"

        import jobs.run_command as rc
        before = datetime.now(timezone.utc)
        with patch("dispatch.schedule_command", side_effect=fake_sc):
            rc._schedule_waiting_task(db_session, wt)
        after = datetime.now(timezone.utc)

        assert len(calls) == 1
        assert before <= calls[0] <= after


# ---------------------------------------------------------------------------
# _try_unblock_task
# ---------------------------------------------------------------------------

class TestTryUnblockTask:
    def _call(self, session, wt, job_id="fake-job-id"):
        import jobs.run_command as rc
        with patch("dispatch.schedule_command", return_value=job_id) as mock_sc:
            rc._try_unblock_task(session, wt)
        return mock_sc

    def test_orphaned_waiting_task_gets_scheduled(self, db_session):
        """A waiting task with no dep rows should be scheduled immediately."""
        wt = make_task(db_session, status="waiting")
        mock_sc = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_sc.assert_called_once()

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
        mock_sc = self._call(db_session, wt)
        assert wt.status == "scheduled"
        mock_sc.assert_called_once()

    @pytest.mark.parametrize("bad_status", ["failed", "cancelled", "blocked"])
    def test_bad_dep_fails_waiting_task(self, db_session, bad_status):
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
        done = make_task(db_session, status="success")
        running = make_task(db_session, status="running")
        wt = make_task(db_session, status="waiting")
        db_session.add_all([
            TaskDependency(task_id=wt.id, depends_on_task_id=done.id),
            TaskDependency(task_id=wt.id, depends_on_task_id=running.id),
        ])
        db_session.flush()
        mock_sc = self._call(db_session, wt)
        assert wt.status == "waiting"
        mock_sc.assert_not_called()

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
    def _call(self, completed_task_id: int, completed_status: str):
        import jobs.run_command as rc
        with patch("dispatch.schedule_command", return_value="fake-job-id") as mock_sc:
            rc._trigger_dependents(completed_task_id, completed_status)
        return mock_sc

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

        mock_sc = self._call(upstream_id, "success")

        with Factory() as s:
            dep = s.get(TaskRequest, dependent_id)
            assert dep.status == "scheduled"
        mock_sc.assert_called_once()

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

        mock_sc = self._call(upstream_id, "success")

        with Factory() as s:
            dep = s.get(TaskRequest, dependent_id)
            assert dep.status == "waiting"
        mock_sc.assert_not_called()

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
