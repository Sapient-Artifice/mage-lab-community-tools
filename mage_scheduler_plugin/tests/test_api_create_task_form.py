"""Tests for POST /tasks (HTML form endpoint).

Covers the new error-handling behaviour introduced alongside _dashboard_context:
  - No command and no action_id → 200 with error message in HTML (not a 303)
  - Invalid action_id (not in DB) → 200 with error message in HTML
  - Valid command → 303 redirect to /tasks/{id}
"""
from __future__ import annotations

from datetime import datetime, timezone


def _run_at() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestCreateTaskFormErrors:
    def test_no_command_no_action_returns_dashboard_with_error(self, api_client):
        """Neither command nor action_id submitted → error shown in dashboard."""
        client, _ = api_client

        resp = client.post("/tasks", data={"run_at": _run_at()})

        assert resp.status_code == 200
        assert "error-msg" in resp.text
        assert "Command or action" in resp.text

    def test_invalid_action_id_returns_dashboard_with_error(self, api_client):
        """action_id that doesn't exist in DB → 200 with error, no crash."""
        client, _ = api_client

        resp = client.post("/tasks", data={"action_id": "9999", "run_at": _run_at()})

        assert resp.status_code == 200
        assert "error-msg" in resp.text


class TestCreateTaskFormSuccess:
    def test_valid_command_redirects_to_task(self, api_client):
        """Valid command → 303 redirect to /tasks/{id}."""
        client, _ = api_client

        resp = client.post(
            "/tasks",
            data={"command": "/bin/echo hello", "run_at": _run_at()},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/tasks/")
