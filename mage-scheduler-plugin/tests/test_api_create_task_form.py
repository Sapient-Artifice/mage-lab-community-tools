"""Tests for POST /tasks (HTML form endpoint).

Covers error handling and success path for the redesigned schedule form:
  - No command and no action_id → 400 with error message in HTML
  - Invalid action_id (not in DB) → 400 with error message in HTML
  - Valid command → 303 redirect to /tasks/{id}
"""
from __future__ import annotations

from datetime import date, timedelta


def _form_date() -> str:
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")


_FORM_TIME = "09:00"
_TIMEZONE  = "UTC"


class TestCreateTaskFormErrors:
    def test_no_command_no_action_returns_dashboard_with_error(self, api_client):
        """Neither command nor action_id submitted → error shown in dashboard."""
        client, _ = api_client

        resp = client.post("/tasks", data={
            "run_date": _form_date(),
            "run_time": _FORM_TIME,
            "timezone": _TIMEZONE,
        })

        assert resp.status_code == 400
        assert "error-msg" in resp.text

    def test_invalid_action_id_returns_dashboard_with_error(self, api_client):
        """action_id that doesn't exist in DB → 400 with error."""
        client, _ = api_client

        resp = client.post("/tasks", data={
            "action_id": "9999",
            "run_date": _form_date(),
            "run_time": _FORM_TIME,
            "timezone": _TIMEZONE,
        })

        assert resp.status_code == 400
        assert "error-msg" in resp.text


class TestCreateTaskFormSuccess:
    def test_valid_command_redirects_to_task(self, api_client):
        """Valid command → 303 redirect to /tasks/{id}."""
        client, _ = api_client

        resp = client.post(
            "/tasks",
            data={
                "command": "/bin/echo hello",
                "run_date": _form_date(),
                "run_time": _FORM_TIME,
                "timezone": _TIMEZONE,
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/tasks/")
