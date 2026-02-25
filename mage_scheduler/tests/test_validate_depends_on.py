"""Tests for _validate_depends_on and _cascade_fail_dependents in api.py."""
from __future__ import annotations

import pytest

from tests.conftest import make_task


# ---------------------------------------------------------------------------
# _validate_depends_on
# ---------------------------------------------------------------------------

class TestValidateDependsOn:
    def _call(self, session, dep_ids):
        from api import _validate_depends_on
        return _validate_depends_on(session, dep_ids)

    def test_empty_list_is_immediate_schedule(self, db_session):
        errors, outcome = self._call(db_session, [])
        assert errors == []
        assert outcome == "immediate_schedule"

    def test_nonexistent_id_returns_invalid(self, db_session):
        errors, outcome = self._call(db_session, [9999])
        assert errors == ["depends_on_invalid"]
        assert outcome == "immediate_fail"

    def test_one_missing_among_valid_ids_returns_invalid(self, db_session):
        t = make_task(db_session, status="success")
        errors, outcome = self._call(db_session, [t.id, 9999])
        assert errors == ["depends_on_invalid"]
        assert outcome == "immediate_fail"

    @pytest.mark.parametrize("bad_status", ["failed", "cancelled", "blocked"])
    def test_terminal_bad_status_returns_immediate_fail(self, db_session, bad_status):
        # No errors in dep_errors — the endpoint's immediate_fail branch handles messaging.
        t = make_task(db_session, status=bad_status)
        errors, outcome = self._call(db_session, [t.id])
        assert errors == []
        assert outcome == "immediate_fail"

    def test_all_succeeded_is_immediate_schedule(self, db_session):
        t1 = make_task(db_session, status="success")
        t2 = make_task(db_session, status="success")
        errors, outcome = self._call(db_session, [t1.id, t2.id])
        assert errors == []
        assert outcome == "immediate_schedule"

    @pytest.mark.parametrize("in_flight_status", ["scheduled", "running", "waiting"])
    def test_one_success_one_in_flight_is_waiting(self, db_session, in_flight_status):
        done = make_task(db_session, status="success")
        pending = make_task(db_session, status=in_flight_status)
        errors, outcome = self._call(db_session, [done.id, pending.id])
        assert errors == []
        assert outcome == "waiting"

    def test_bad_status_takes_priority_over_in_flight(self, db_session):
        """A failed dep and a still-running dep → immediate_fail, not waiting."""
        failed = make_task(db_session, status="failed")
        running = make_task(db_session, status="running")
        errors, outcome = self._call(db_session, [failed.id, running.id])
        assert errors == []
        assert outcome == "immediate_fail"

    def test_single_in_flight_dep_is_waiting(self, db_session):
        t = make_task(db_session, status="running")
        errors, outcome = self._call(db_session, [t.id])
        assert errors == []
        assert outcome == "waiting"


# ---------------------------------------------------------------------------
# _cascade_fail_dependents
# ---------------------------------------------------------------------------

class TestCascadeFailDependents:
    def _call(self, session, task_id: int, reason: str = "upstream failed") -> None:
        from api import _cascade_fail_dependents
        _cascade_fail_dependents(session, task_id, reason)

    def test_no_dependents_is_noop(self, db_session):
        upstream = make_task(db_session, status="failed")
        # No TaskDependency rows — nothing should change
        self._call(db_session, upstream.id)
        db_session.flush()
        # Just verify it doesn't raise and upstream is untouched
        assert upstream.status == "failed"

    def test_waiting_dependent_is_failed(self, db_session):
        from models import TaskDependency
        upstream = make_task(db_session, status="failed")
        dependent = make_task(db_session, status="waiting")
        db_session.add(TaskDependency(task_id=dependent.id, depends_on_task_id=upstream.id))
        db_session.flush()

        self._call(db_session, upstream.id, reason="test cascade")

        assert dependent.status == "failed"
        assert dependent.error == "test cascade"

    def test_non_waiting_dependent_is_not_touched(self, db_session):
        from models import TaskDependency
        upstream = make_task(db_session, status="failed")
        already_running = make_task(db_session, status="running")
        db_session.add(TaskDependency(task_id=already_running.id, depends_on_task_id=upstream.id))
        db_session.flush()

        self._call(db_session, upstream.id)

        assert already_running.status == "running"

    def test_multiple_waiting_dependents_all_failed(self, db_session):
        from models import TaskDependency
        upstream = make_task(db_session, status="failed")
        dep1 = make_task(db_session, status="waiting")
        dep2 = make_task(db_session, status="waiting")
        db_session.add_all([
            TaskDependency(task_id=dep1.id, depends_on_task_id=upstream.id),
            TaskDependency(task_id=dep2.id, depends_on_task_id=upstream.id),
        ])
        db_session.flush()

        self._call(db_session, upstream.id, reason="cascade reason")

        assert dep1.status == "failed"
        assert dep1.error == "cascade reason"
        assert dep2.status == "failed"
        assert dep2.error == "cascade reason"

    def test_mixed_waiting_and_non_waiting_dependents(self, db_session):
        from models import TaskDependency
        upstream = make_task(db_session, status="failed")
        waiting = make_task(db_session, status="waiting")
        success = make_task(db_session, status="success")
        db_session.add_all([
            TaskDependency(task_id=waiting.id, depends_on_task_id=upstream.id),
            TaskDependency(task_id=success.id, depends_on_task_id=upstream.id),
        ])
        db_session.flush()

        self._call(db_session, upstream.id)

        assert waiting.status == "failed"
        assert success.status == "success"  # unchanged
