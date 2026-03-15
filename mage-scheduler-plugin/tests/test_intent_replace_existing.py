"""Tests for POST /api/tasks/intent with replace_existing=true.

Covers:
  - Cancels a matching scheduled task before creating the new one
  - Cancels a matching waiting task before creating the new one
  - Cancels multiple matching tasks (both scheduled and waiting)
  - Does NOT cancel tasks in terminal states (succeeded, failed, cancelled, blocked)
  - Does NOT cancel running tasks
  - Returns replaced_task_ids in the response
  - replace_existing=false (default) leaves existing tasks untouched
"""
from __future__ import annotations

import pytest

from tests.conftest import make_task

INTENT_URL = "/api/tasks/intent"
DESCRIPTION = "daily backup"


def _intent(description: str = DESCRIPTION, replace_existing: bool = True) -> dict:
    return {
        "intent_version": "v1",
        "task": {
            "description": description,
            "command": "echo backup",
            "run_in": "1h",
        },
        "replace_existing": replace_existing,
    }


def _session(factory):
    return factory()


def _make_named(session, *, status: str, description: str = DESCRIPTION):
    from models import TaskRequest
    from datetime import datetime, timezone

    task = TaskRequest(
        description=description,
        command="echo backup",
        run_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status=status,
    )
    session.add(task)
    session.flush()
    return task


# ---------------------------------------------------------------------------
# Basic replacement
# ---------------------------------------------------------------------------

class TestReplaceExistingScheduled:
    def test_cancels_matching_scheduled_task(self, api_client):
        """An existing scheduled task with same description is cancelled."""
        client, factory = api_client
        s = _session(factory)
        try:
            old = _make_named(s, status="scheduled")
            s.commit()
            old_id = old.id
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["replaced_task_ids"] == [old_id]

        s = _session(factory)
        try:
            from models import TaskRequest
            old_task = s.get(TaskRequest, old_id)
            assert old_task.status == "cancelled"
        finally:
            s.close()

    def test_cancels_matching_waiting_task(self, api_client):
        """An existing waiting task with same description is cancelled."""
        client, factory = api_client
        s = _session(factory)
        try:
            old = _make_named(s, status="waiting")
            s.commit()
            old_id = old.id
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent())
        assert resp.status_code == 200
        assert old_id in resp.json()["replaced_task_ids"]

        s = _session(factory)
        try:
            from models import TaskRequest
            assert s.get(TaskRequest, old_id).status == "cancelled"
        finally:
            s.close()

    def test_cancels_multiple_matching_tasks(self, api_client):
        """Multiple scheduled/waiting tasks with same description are all cancelled."""
        client, factory = api_client
        s = _session(factory)
        try:
            t1 = _make_named(s, status="scheduled")
            t2 = _make_named(s, status="waiting")
            s.commit()
            old_ids = {t1.id, t2.id}
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent())
        assert resp.status_code == 200
        assert set(resp.json()["replaced_task_ids"]) == old_ids

        s = _session(factory)
        try:
            from models import TaskRequest
            for tid in old_ids:
                assert s.get(TaskRequest, tid).status == "cancelled"
        finally:
            s.close()

    def test_new_task_is_created_after_replacement(self, api_client):
        """A new task is created even when replacement occurs."""
        client, factory = api_client
        s = _session(factory)
        try:
            old = _make_named(s, status="scheduled")
            s.commit()
            old_id = old.id
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent())
        assert resp.status_code == 200
        new_id = resp.json()["task_id"]
        assert new_id != old_id

        s = _session(factory)
        try:
            from models import TaskRequest
            new_task = s.get(TaskRequest, new_id)
            assert new_task is not None
            assert new_task.status == "scheduled"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Terminal and running states are not affected
# ---------------------------------------------------------------------------

class TestReplaceExistingTerminalStates:
    @pytest.mark.parametrize("terminal_status", ["succeeded", "failed", "cancelled", "blocked"])
    def test_does_not_cancel_terminal_tasks(self, api_client, terminal_status):
        """Tasks already in a terminal state are left unchanged."""
        client, factory = api_client
        s = _session(factory)
        try:
            old = _make_named(s, status=terminal_status)
            s.commit()
            old_id = old.id
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent())
        assert resp.status_code == 200
        # Terminal task should not appear in replaced_task_ids
        replaced = resp.json().get("replaced_task_ids") or []
        assert old_id not in replaced

        s = _session(factory)
        try:
            from models import TaskRequest
            task = s.get(TaskRequest, old_id)
            assert task.status == terminal_status  # unchanged
        finally:
            s.close()

    def test_does_not_cancel_running_tasks(self, api_client):
        """Running tasks are not cancelled by replace_existing."""
        client, factory = api_client
        s = _session(factory)
        try:
            old = _make_named(s, status="running")
            s.commit()
            old_id = old.id
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent())
        assert resp.status_code == 200
        replaced = resp.json().get("replaced_task_ids") or []
        assert old_id not in replaced

        s = _session(factory)
        try:
            from models import TaskRequest
            assert s.get(TaskRequest, old_id).status == "running"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Description scoping
# ---------------------------------------------------------------------------

class TestReplaceExistingScoping:
    def test_only_cancels_matching_description(self, api_client):
        """Tasks with a different description are not affected."""
        client, factory = api_client
        s = _session(factory)
        try:
            other = _make_named(s, status="scheduled", description="weekly report")
            s.commit()
            other_id = other.id
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent(description=DESCRIPTION))
        assert resp.status_code == 200
        replaced = resp.json().get("replaced_task_ids") or []
        assert other_id not in replaced

        s = _session(factory)
        try:
            from models import TaskRequest
            assert s.get(TaskRequest, other_id).status == "scheduled"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# replace_existing=false (default behaviour)
# ---------------------------------------------------------------------------

class TestReplaceExistingDisabled:
    def test_false_leaves_existing_tasks_untouched(self, api_client):
        """When replace_existing is false, existing tasks are not cancelled."""
        client, factory = api_client
        s = _session(factory)
        try:
            old = _make_named(s, status="scheduled")
            s.commit()
            old_id = old.id
        finally:
            s.close()

        resp = client.post(INTENT_URL, json=_intent(replace_existing=False))
        assert resp.status_code == 200
        assert (resp.json().get("replaced_task_ids") or []) == []

        s = _session(factory)
        try:
            from models import TaskRequest
            assert s.get(TaskRequest, old_id).status == "scheduled"
        finally:
            s.close()

    def test_default_omitted_leaves_existing_tasks_untouched(self, api_client):
        """Omitting replace_existing from the payload defaults to false."""
        client, factory = api_client
        s = _session(factory)
        try:
            old = _make_named(s, status="scheduled")
            s.commit()
            old_id = old.id
        finally:
            s.close()

        payload = {
            "intent_version": "v1",
            "task": {"description": DESCRIPTION, "command": "echo backup", "run_in": "1h"},
        }
        resp = client.post(INTENT_URL, json=payload)
        assert resp.status_code == 200
        assert (resp.json().get("replaced_task_ids") or []) == []

        s = _session(factory)
        try:
            from models import TaskRequest
            assert s.get(TaskRequest, old_id).status == "scheduled"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# No existing match — response field is absent/null
# ---------------------------------------------------------------------------

class TestReplaceExistingNoMatch:
    def test_no_match_replaced_task_ids_null(self, api_client):
        """When no tasks match, replaced_task_ids is null or absent in the response."""
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_intent())
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("replaced_task_ids") is None or data.get("replaced_task_ids") == []
