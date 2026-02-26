"""Tests for the recurring (cron) path through POST /api/tasks/intent.

Covers _handle_recurring_intent: pre-validation, name uniqueness, action/command
resolution, env validation, DB state, and response structure.
"""
from __future__ import annotations

import json

import pytest

from tests.conftest import make_action

INTENT_URL = "/api/tasks/intent"
VALID_CRON = "0 * * * *"


def _cron_payload(description: str = "my recurring task",
                  cron: str = VALID_CRON,
                  command: str = "echo hello",
                  **extra_task) -> dict:
    task = {"description": description, "cron": cron, **extra_task}
    if command is not None:
        task["command"] = command
    return {"intent_version": "v1", "task": task}


# ---------------------------------------------------------------------------
# Pre-validation (raises 400 before any DB work)
# ---------------------------------------------------------------------------

class TestRecurringPreValidation:
    def test_invalid_cron_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(cron="not a cron"))
        assert resp.status_code == 400
        codes = [e["code"] for e in resp.json()["detail"]["errors"]]
        assert "cron_invalid" in codes

    def test_cron_with_run_in_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(run_in="5m"))
        assert resp.status_code == 400
        codes = [e["code"] for e in resp.json()["detail"]["errors"]]
        assert "cron_and_run_at_exclusive" in codes

    def test_cron_with_run_at_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(run_at="2099-01-01T00:00:00"))
        assert resp.status_code == 400
        codes = [e["code"] for e in resp.json()["detail"]["errors"]]
        assert "cron_and_run_at_exclusive" in codes

    def test_cron_with_depends_on_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(depends_on=[1]))
        assert resp.status_code == 400
        codes = [e["code"] for e in resp.json()["detail"]["errors"]]
        assert "depends_on_cron_unsupported" in codes

    def test_multiple_pre_validation_errors_bundled(self, api_client):
        """Invalid cron + depends_on → both codes in the 400 response."""
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(cron="bad", depends_on=[1]))
        assert resp.status_code == 400
        codes = [e["code"] for e in resp.json()["detail"]["errors"]]
        assert "cron_invalid" in codes
        assert "depends_on_cron_unsupported" in codes


# ---------------------------------------------------------------------------
# Name uniqueness (returns "blocked", not 400)
# ---------------------------------------------------------------------------

class TestRecurringNameUniqueness:
    def test_duplicate_description_returns_blocked(self, api_client):
        client, _ = api_client
        client.post(INTENT_URL, json=_cron_payload(description="unique name"))
        resp = client.post(INTENT_URL, json=_cron_payload(description="unique name"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "blocked"
        codes = [e["code"] for e in (body.get("errors") or [])]
        assert "recurring_name_exists" in codes

    def test_distinct_descriptions_both_succeed(self, api_client):
        client, _ = api_client
        r1 = client.post(INTENT_URL, json=_cron_payload(description="task A"))
        r2 = client.post(INTENT_URL, json=_cron_payload(description="task B"))
        assert r1.json()["status"] == "recurring_scheduled"
        assert r2.json()["status"] == "recurring_scheduled"


# ---------------------------------------------------------------------------
# Command path
# ---------------------------------------------------------------------------

class TestRecurringCommandPath:
    def test_no_command_or_action_returns_blocked(self, api_client):
        client, _ = api_client
        payload = {"intent_version": "v1", "task": {"description": "t", "cron": VALID_CRON}}
        resp = client.post(INTENT_URL, json=payload)
        body = resp.json()
        assert body["status"] == "blocked"
        codes = [e["code"] for e in (body.get("errors") or [])]
        assert "command_or_action_required" in codes

    def test_env_without_action_returns_blocked(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(env={"KEY": "val"}))
        body = resp.json()
        assert body["status"] == "blocked"
        assert "env_requires_action" in [e["code"] for e in (body.get("errors") or [])]

    def test_valid_command_creates_recurring_task(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload())
        assert resp.json()["status"] == "recurring_scheduled"


# ---------------------------------------------------------------------------
# Action path
# ---------------------------------------------------------------------------

class TestRecurringActionPath:
    def test_unknown_action_returns_blocked(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(action_name="ghost", command=None))
        body = resp.json()
        assert body["status"] == "blocked"
        assert "unknown_action" in [e["code"] for e in (body.get("errors") or [])]

    def test_known_action_resolves_command(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="rec_action", command="echo recurring")
            s.commit()

        resp = client.post(INTENT_URL, json=_cron_payload(action_name="rec_action", command=None))
        assert resp.json()["status"] == "recurring_scheduled"
        assert resp.json()["command"] == "echo recurring"

    def test_env_key_not_in_allowlist_returns_blocked(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="strict_action", allowed_env_json=json.dumps(["SAFE"]))
            s.commit()

        resp = client.post(INTENT_URL, json=_cron_payload(
            action_name="strict_action", command=None, env={"UNSAFE": "val"}
        ))
        body = resp.json()
        assert body["status"] == "blocked"
        assert "env_key_not_allowed" in [e["code"] for e in (body.get("errors") or [])]

    def test_action_default_cwd_used(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="cwd_rec_action", default_cwd="/tmp/rec_home")
            s.commit()

        resp = client.post(INTENT_URL, json=_cron_payload(action_name="cwd_rec_action", command=None))
        assert resp.json()["cwd"] == "/tmp/rec_home"


# ---------------------------------------------------------------------------
# DB state
# ---------------------------------------------------------------------------

class TestRecurringDbState:
    def test_recurring_task_row_created(self, api_client):
        from models import RecurringTask
        from sqlalchemy import select
        client, Factory = api_client
        client.post(INTENT_URL, json=_cron_payload(description="db check task"))
        with Factory() as s:
            rows = s.execute(select(RecurringTask)).scalars().all()
        assert len(rows) == 1
        assert rows[0].name == "db check task"

    def test_next_run_at_is_populated(self, api_client):
        from models import RecurringTask
        from sqlalchemy import select
        client, Factory = api_client
        client.post(INTENT_URL, json=_cron_payload(description="next run task"))
        with Factory() as s:
            rt = s.execute(select(RecurringTask)).scalar_one()
        assert rt.next_run_at is not None

    def test_cron_stored_on_recurring_task(self, api_client):
        from models import RecurringTask
        from sqlalchemy import select
        client, Factory = api_client
        client.post(INTENT_URL, json=_cron_payload(description="cron store task", cron="30 6 * * 1"))
        with Factory() as s:
            rt = s.execute(select(RecurringTask)).scalar_one()
        assert rt.cron == "30 6 * * 1"


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

class TestRecurringResponseStructure:
    def test_status_is_recurring_scheduled(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload())
        assert resp.json()["status"] == "recurring_scheduled"

    def test_cron_echoed_in_response(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(cron="15 3 * * *"))
        assert resp.json()["cron"] == "15 3 * * *"

    def test_next_run_at_in_response(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload())
        assert resp.json().get("next_run_at") is not None

    def test_max_retries_in_response(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_cron_payload(max_retries=3))
        assert resp.json()["max_retries"] == 3

    def test_task_max_retries_overrides_action_default(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="rec_retry_action", max_retries=1)
            s.commit()

        resp = client.post(INTENT_URL, json=_cron_payload(
            action_name="rec_retry_action", command=None, max_retries=7
        ))
        assert resp.json()["max_retries"] == 7
