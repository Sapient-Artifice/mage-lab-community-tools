"""Tests for the core task REST endpoints.

Covers:
  - GET  /api/tasks               (list, ordering)
  - GET  /api/tasks/{id}          (found, 404)
  - GET  /api/tasks/{id}/dependencies  (empty, upstream, blocking)
  - POST /api/tasks/{id}/cancel   (status guards, cascade, cancel_command, 404)
  - POST /api/tasks               (JSON create path)
  - POST /api/tasks/run_now
  - GET  /api/validation
  - GET  /health

Adapted from test_api_task_endpoints.py — AsyncResult.revoke replaced with
cancel_command mocking.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from tests.conftest import make_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_at_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session(factory):
    """Open a raw session from the Factory for direct DB manipulation."""
    return factory()


def _add_dependency(factory, *, task_id: int, depends_on_task_id: int):
    """Insert a TaskDependency row directly."""
    from models import TaskDependency

    s = _session(factory)
    try:
        row = TaskDependency(task_id=task_id, depends_on_task_id=depends_on_task_id)
        s.add(row)
        s.commit()
    finally:
        s.close()


# ---------------------------------------------------------------------------
# GET /api/tasks
# ---------------------------------------------------------------------------

class TestListTasks:
    def test_empty_list(self, api_client):
        client, _ = api_client
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_tasks(self, api_client):
        client, factory = api_client
        s = _session(factory)
        try:
            make_task(s, status="scheduled")
            make_task(s, status="completed")
            s.commit()
        finally:
            s.close()

        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_ordered_by_created_at_desc(self, api_client):
        """Most recently created task must appear first."""
        client, factory = api_client
        s = _session(factory)
        try:
            t1 = make_task(s, status="scheduled")
            t2 = make_task(s, status="scheduled")
            s.commit()
            id1, id2 = t1.id, t2.id
        finally:
            s.close()

        resp = client.get("/api/tasks")
        ids = [t["id"] for t in resp.json()]
        # t2 was created after t1 so it should be first
        assert ids.index(id2) < ids.index(id1)

    def test_status_filter_single_status(self, api_client):
        """?status=scheduled returns only scheduled tasks."""
        client, factory = api_client
        s = _session(factory)
        try:
            t = make_task(s, status="scheduled")
            make_task(s, status="failed")
            make_task(s, status="cancelled")
            s.commit()
            scheduled_id = t.id
        finally:
            s.close()

        resp = client.get("/api/tasks?status=scheduled")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == scheduled_id
        assert data[0]["status"] == "scheduled"

    def test_status_filter_comma_separated(self, api_client):
        """?status=scheduled,running returns tasks matching either status."""
        client, factory = api_client
        s = _session(factory)
        try:
            t1 = make_task(s, status="scheduled")
            t2 = make_task(s, status="running")
            make_task(s, status="failed")
            s.commit()
            active_ids = {t1.id, t2.id}
        finally:
            s.close()

        resp = client.get("/api/tasks?status=scheduled,running")
        assert resp.status_code == 200
        returned_ids = {t["id"] for t in resp.json()}
        assert returned_ids == active_ids

    def test_status_filter_no_match_returns_empty(self, api_client):
        """?status=running returns empty list when no running tasks exist."""
        client, factory = api_client
        s = _session(factory)
        try:
            make_task(s, status="scheduled")
            s.commit()
        finally:
            s.close()

        resp = client.get("/api/tasks?status=running")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_status_filter_unknown_status_returns_empty(self, api_client):
        """An unrecognised status value returns an empty list, not an error."""
        client, factory = api_client
        s = _session(factory)
        try:
            make_task(s, status="scheduled")
            s.commit()
        finally:
            s.close()

        resp = client.get("/api/tasks?status=does_not_exist")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_no_status_filter_returns_all(self, api_client):
        """Omitting ?status still returns every task (backwards compatibility)."""
        client, factory = api_client
        s = _session(factory)
        try:
            make_task(s, status="scheduled")
            make_task(s, status="failed")
            make_task(s, status="cancelled")
            s.commit()
        finally:
            s.close()

        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# GET /api/tasks/{id}
# ---------------------------------------------------------------------------

class TestGetTask:
    def test_returns_existing_task(self, api_client):
        client, factory = api_client
        s = _session(factory)
        try:
            t = make_task(s, status="scheduled", command="echo hi")
            s.commit()
            task_id = t.id
        finally:
            s.close()

        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert data["command"] == "echo hi"
        assert data["status"] == "scheduled"

    def test_missing_task_returns_404(self, api_client):
        client, _ = api_client
        resp = client.get("/api/tasks/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/tasks/{id}/dependencies
# ---------------------------------------------------------------------------

class TestGetTaskDependencies:
    def test_no_dependencies_empty_lists(self, api_client):
        client, factory = api_client
        s = _session(factory)
        try:
            t = make_task(s)
            s.commit()
            task_id = t.id
        finally:
            s.close()

        resp = client.get(f"/api/tasks/{task_id}/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["depends_on"] == []
        assert data["blocking"] == []

    def test_depends_on_populated(self, api_client):
        """depends_on lists IDs of tasks this task depends on."""
        client, factory = api_client
        s = _session(factory)
        try:
            parent = make_task(s, status="completed")
            child = make_task(s, status="scheduled")
            s.commit()
            parent_id, child_id = parent.id, child.id
        finally:
            s.close()

        _add_dependency(factory, task_id=child_id, depends_on_task_id=parent_id)

        resp = client.get(f"/api/tasks/{child_id}/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert parent_id in data["depends_on"]
        assert data["blocking"] == []

    def test_blocking_includes_waiting_downstream(self, api_client):
        """blocking lists tasks that are waiting on this task."""
        client, factory = api_client
        s = _session(factory)
        try:
            parent = make_task(s, status="scheduled")
            child = make_task(s, status="waiting")
            s.commit()
            parent_id, child_id = parent.id, child.id
        finally:
            s.close()

        _add_dependency(factory, task_id=child_id, depends_on_task_id=parent_id)

        resp = client.get(f"/api/tasks/{parent_id}/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert child_id in data["blocking"]
        assert data["depends_on"] == []

    def test_blocking_excludes_non_waiting_downstream(self, api_client):
        """Downstream tasks that are not 'waiting' must not appear in blocking."""
        client, factory = api_client
        s = _session(factory)
        try:
            parent = make_task(s, status="scheduled")
            child = make_task(s, status="scheduled")  # not waiting
            s.commit()
            parent_id, child_id = parent.id, child.id
        finally:
            s.close()

        _add_dependency(factory, task_id=child_id, depends_on_task_id=parent_id)

        resp = client.get(f"/api/tasks/{parent_id}/dependencies")
        assert resp.status_code == 200
        assert resp.json()["blocking"] == []

    def test_missing_task_returns_404(self, api_client):
        client, _ = api_client
        resp = client.get("/api/tasks/9999/dependencies")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/tasks/{id}/cancel
# ---------------------------------------------------------------------------

class TestCancelTask:
    @pytest.mark.parametrize("status", ["scheduled", "running", "waiting"])
    def test_cancellable_statuses(self, status, api_client):
        client, factory = api_client
        s = _session(factory)
        try:
            t = make_task(s, status=status)
            s.commit()
            task_id = t.id
        finally:
            s.close()

        resp = client.post(f"/api/tasks/{task_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        assert resp.json()["task_id"] == task_id

    @pytest.mark.parametrize("status", ["completed", "failed", "blocked", "cancelled"])
    def test_non_cancellable_statuses_return_400(self, status, api_client):
        client, factory = api_client
        s = _session(factory)
        try:
            t = make_task(s, status=status)
            s.commit()
            task_id = t.id
        finally:
            s.close()

        resp = client.post(f"/api/tasks/{task_id}/cancel")
        assert resp.status_code == 400
        assert "status" in resp.json()["detail"].lower()

    def test_cancel_not_found_returns_404(self, api_client):
        client, _ = api_client
        resp = client.post("/api/tasks/9999/cancel")
        assert resp.status_code == 404

    def test_cancel_cascades_to_waiting_dependents(self, api_client):
        """Cancelling a task must fail any waiting tasks that depend on it."""
        client, factory = api_client
        s = _session(factory)
        try:
            parent = make_task(s, status="scheduled")
            child = make_task(s, status="waiting")
            s.commit()
            parent_id, child_id = parent.id, child.id
        finally:
            s.close()

        _add_dependency(factory, task_id=child_id, depends_on_task_id=parent_id)

        resp = client.post(f"/api/tasks/{parent_id}/cancel")
        assert resp.status_code == 200

        s2 = _session(factory)
        try:
            from models import TaskRequest
            child_task = s2.get(TaskRequest, child_id)
            assert child_task.status == "failed"
        finally:
            s2.close()

    def test_cancel_does_not_cascade_to_non_waiting(self, api_client):
        """Non-waiting downstream tasks must not be affected by cascading."""
        client, factory = api_client
        s = _session(factory)
        try:
            parent = make_task(s, status="scheduled")
            child = make_task(s, status="scheduled")  # not waiting
            s.commit()
            parent_id, child_id = parent.id, child.id
        finally:
            s.close()

        _add_dependency(factory, task_id=child_id, depends_on_task_id=parent_id)

        client.post(f"/api/tasks/{parent_id}/cancel")

        s2 = _session(factory)
        try:
            from models import TaskRequest
            child_task = s2.get(TaskRequest, child_id)
            assert child_task.status == "scheduled"
        finally:
            s2.close()

    def test_cancel_calls_cancel_command(self, api_client, monkeypatch):
        """When celery_task_id is set, cancel_command must be called with the job_id."""
        client, factory = api_client
        s = _session(factory)
        try:
            from models import TaskRequest
            t = TaskRequest(
                description="apscheduler job task",
                command="echo ok",
                run_at=datetime.now(timezone.utc).replace(tzinfo=None),
                status="running",
                celery_task_id="apscheduler-job-abc-123",
            )
            s.add(t)
            s.commit()
            task_id = t.id
        finally:
            s.close()

        import api as api_module
        cancel_calls = []
        monkeypatch.setattr(
            api_module,
            "cancel_command",
            lambda job_id, terminate: cancel_calls.append((job_id, terminate)),
        )

        resp = client.post(f"/api/tasks/{task_id}/cancel")
        assert resp.status_code == 200
        assert any(job_id == "apscheduler-job-abc-123" for job_id, _ in cancel_calls)


# ---------------------------------------------------------------------------
# POST /api/tasks
# ---------------------------------------------------------------------------

class TestCreateTask:
    def test_create_task_returns_scheduled(self, api_client):
        client, _ = api_client
        payload = {
            "command": "echo hello",
            "run_at": _run_at_str(),
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["command"] == "echo hello"

    def test_create_task_description_persisted(self, api_client):
        client, _ = api_client
        payload = {
            "command": "echo hello",
            "run_at": _run_at_str(),
            "description": "my important task",
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200
        assert resp.json()["description"] == "my important task"

    def test_create_task_env_persisted(self, api_client):
        client, factory = api_client
        payload = {
            "command": "echo hello",
            "run_at": _run_at_str(),
            "env": {"FOO": "bar"},
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        s = _session(factory)
        try:
            from models import TaskRequest
            t = s.get(TaskRequest, task_id)
            assert json.loads(t.env_json) == {"FOO": "bar"}
        finally:
            s.close()

    def test_create_task_notify_on_complete(self, api_client):
        client, factory = api_client
        payload = {
            "command": "echo hello",
            "run_at": _run_at_str(),
            "notify_on_complete": True,
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        s = _session(factory)
        try:
            from models import TaskRequest
            t = s.get(TaskRequest, task_id)
            assert t.notify_on_complete == 1
        finally:
            s.close()

    def test_create_task_negative_max_retries_clamped_to_zero(self, api_client):
        client, factory = api_client
        payload = {
            "command": "echo hello",
            "run_at": _run_at_str(),
            "max_retries": -5,
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        s = _session(factory)
        try:
            from models import TaskRequest
            t = s.get(TaskRequest, task_id)
            assert t.max_retries == 0
        finally:
            s.close()

    def test_create_task_zero_retry_delay_clamped_to_one(self, api_client):
        client, factory = api_client
        payload = {
            "command": "echo hello",
            "run_at": _run_at_str(),
            "retry_delay": 0,
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        s = _session(factory)
        try:
            from models import TaskRequest
            t = s.get(TaskRequest, task_id)
            assert t.retry_delay >= 1
        finally:
            s.close()

    def test_create_task_validation_failure_returns_blocked(self, api_client, monkeypatch):
        """When _validate_command raises, endpoint returns a blocked task (200)."""
        import api as api_module

        client, _ = api_client
        monkeypatch.setattr(
            api_module,
            "_validate_command",
            lambda *a, **kw: (_ for _ in ()).throw(
                HTTPException(status_code=400, detail="command_dir_not_allowed")
            ),
        )
        payload = {
            "command": "/bad/path/cmd",
            "run_at": _run_at_str(),
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked"
        assert "command_dir_not_allowed" in data["error"]


# ---------------------------------------------------------------------------
# POST /api/tasks/run_now
# ---------------------------------------------------------------------------

class TestRunTaskNow:
    def test_run_now_creates_scheduled_task(self, api_client):
        client, _ = api_client
        payload = {"command": "echo now"}
        resp = client.post("/api/tasks/run_now", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["command"] == "echo now"

    def test_run_now_description_persisted(self, api_client):
        client, _ = api_client
        payload = {"command": "echo now", "description": "urgent job"}
        resp = client.post("/api/tasks/run_now", json=payload)
        assert resp.status_code == 200
        assert resp.json()["description"] == "urgent job"

    def test_run_now_validation_failure_returns_blocked(self, api_client, monkeypatch):
        import api as api_module

        client, _ = api_client
        monkeypatch.setattr(
            api_module,
            "_validate_command",
            lambda *a, **kw: (_ for _ in ()).throw(
                HTTPException(status_code=400, detail="command_dir_not_allowed")
            ),
        )
        payload = {"command": "/bad/cmd"}
        resp = client.post("/api/tasks/run_now", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "blocked"


# ---------------------------------------------------------------------------
# GET /api/validation
# ---------------------------------------------------------------------------

class TestValidationInfo:
    def test_returns_rules_list(self, api_client):
        client, _ = api_client
        resp = client.get("/api/validation")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert isinstance(data["rules"], list)
        assert len(data["rules"]) > 0

    def test_empty_dirs_with_default_settings(self, api_client):
        client, _ = api_client
        resp = client.get("/api/validation")
        assert resp.status_code == 200
        data = resp.json()
        # Default Settings has no dirs configured → both are null/empty
        assert data["allowed_command_dirs"] in (None, [])
        assert data["allowed_cwd_dirs"] in (None, [])

    def test_configured_dirs_returned(self, api_client, monkeypatch):
        """When Settings has dirs configured they appear in the response."""
        import api as api_module
        from models import Settings

        # Override _get_settings to return a configured Settings object
        fake_settings = Settings()
        fake_settings.allowed_command_dirs_json = json.dumps(["/usr/bin"])
        fake_settings.allowed_cwd_dirs_json = json.dumps(["/tmp"])
        monkeypatch.setattr(api_module, "_get_settings", lambda db: fake_settings)

        client, _ = api_client
        resp = client.get("/api/validation")
        assert resp.status_code == 200
        data = resp.json()
        assert "/usr/bin" in data["allowed_command_dirs"]
        assert "/tmp" in data["allowed_cwd_dirs"]

    def test_known_rules_present(self, api_client):
        """Spot-check a few of the documented validation rules."""
        client, _ = api_client
        resp = client.get("/api/validation")
        rules = resp.json()["rules"]
        for expected in ("command_must_be_absolute", "env_requires_action"):
            assert expected in rules


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, api_client):
        client, _ = api_client
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], int)

    def test_health_uptime_non_negative(self, api_client):
        client, _ = api_client
        resp = client.get("/health")
        assert resp.json()["uptime_seconds"] >= 0
