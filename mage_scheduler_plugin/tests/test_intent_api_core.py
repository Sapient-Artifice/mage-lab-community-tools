"""Tests for POST /api/tasks/intent (non-dependency paths) and POST /api/tasks/intent/preview.

Covers:
  - Intent version validation
  - Timezone validation
  - Command / action resolution
  - Env key allowlist enforcement
  - run_in / run_at parsing
  - Retry field inheritance (task overrides action defaults, clamping)
  - Source metadata persistence
  - Action cwd resolution
  - Preview endpoint behaviour (no DB write, 400 on errors)
"""
from __future__ import annotations

import json

import pytest

from tests.conftest import make_action

INTENT_URL = "/api/tasks/intent"
PREVIEW_URL = "/api/tasks/intent/preview"


def _payload(extra: dict | None = None) -> dict:
    base = {
        "intent_version": "v1",
        "task": {
            "description": "test task",
            "command": "echo hello",
            "run_in": "5m",
        },
    }
    if extra:
        base.update(extra)
    return base


def _task_payload(**task_fields) -> dict:
    """Build a payload with the given task-level overrides."""
    return _payload({"task": {"description": "t", "command": "echo ok", "run_in": "5m", **task_fields}})


# ---------------------------------------------------------------------------
# Intent version errors
# ---------------------------------------------------------------------------

class TestIntentVersionErrors:
    def test_invalid_version_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_payload({"intent_version": "v99"}))
        assert resp.status_code == 400
        codes = [e["code"] for e in resp.json()["detail"]["errors"]]
        assert "unsupported_intent_version" in codes

    def test_alias_1_accepted(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_payload({"intent_version": "1"}))
        assert resp.status_code == 200

    def test_alias_1_0_accepted(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_payload({"intent_version": "1.0"}))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Timezone errors
# ---------------------------------------------------------------------------

class TestIntentTimezoneErrors:
    def test_invalid_timezone_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(timezone="Bogus/City"))
        assert resp.status_code == 400
        codes = [e["code"] for e in resp.json()["detail"]["errors"]]
        assert "invalid_timezone" in codes

    def test_valid_iana_timezone_accepted(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(timezone="America/New_York"))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Command / action resolution
# ---------------------------------------------------------------------------

class TestIntentCommandRequired:
    def test_no_command_and_no_action_returns_blocked(self, api_client):
        client, _ = api_client
        payload = _payload({"task": {"description": "t", "run_in": "5m"}})
        resp = client.post(INTENT_URL, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "blocked"
        codes = [e["code"] for e in (body.get("errors") or [])]
        assert "command_or_action_required" in codes

    def test_unknown_action_returns_blocked(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(action_name="nonexistent", command=None))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "blocked"
        codes = [e["code"] for e in (body.get("errors") or [])]
        assert "unknown_action" in codes

    def test_known_action_resolves_command(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="my_action", command="echo from_action")
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(action_name="my_action", command=None))
        assert resp.status_code == 200
        assert resp.json()["status"] == "scheduled"
        assert resp.json()["command"] == "echo from_action"

    def test_action_command_overrides_task_command(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="override_action", command="echo action_wins")
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(action_name="override_action", command="echo task_cmd"))
        assert resp.json()["command"] == "echo action_wins"


# ---------------------------------------------------------------------------
# Env validation
# ---------------------------------------------------------------------------

class TestIntentEnvValidation:
    def test_env_without_action_returns_blocked(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(env={"KEY": "val"}))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "blocked"
        assert "env_requires_action" in [e["code"] for e in (body.get("errors") or [])]

    def test_env_with_action_no_allowlist_returns_blocked(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="no_env_action", allowed_env_json=None)
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(
            action_name="no_env_action", command=None, env={"KEY": "val"}
        ))
        body = resp.json()
        assert body["status"] == "blocked"
        assert "env_not_allowed" in [e["code"] for e in (body.get("errors") or [])]

    def test_env_key_not_in_allowlist_returns_blocked(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="env_action", allowed_env_json=json.dumps(["ALLOWED"]))
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(
            action_name="env_action", command=None, env={"SECRET": "bad"}
        ))
        body = resp.json()
        assert body["status"] == "blocked"
        assert "env_key_not_allowed" in [e["code"] for e in (body.get("errors") or [])]

    def test_env_key_in_allowlist_succeeds(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="allowed_env_action", allowed_env_json=json.dumps(["ALLOWED_KEY"]))
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(
            action_name="allowed_env_action", command=None, env={"ALLOWED_KEY": "ok"}
        ))
        assert resp.json()["status"] == "scheduled"


# ---------------------------------------------------------------------------
# run_in / run_at parsing
# ---------------------------------------------------------------------------

class TestIntentRunInParsing:
    def test_valid_run_in_returns_scheduled(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(run_in="30m"))
        assert resp.json()["status"] == "scheduled"

    def test_invalid_run_in_returns_blocked(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(run_in="purple"))
        body = resp.json()
        assert body["status"] == "blocked"
        assert "run_in_invalid" in [e["code"] for e in (body.get("errors") or [])]

    def test_missing_run_at_and_run_in_returns_blocked(self, api_client):
        client, _ = api_client
        payload = _payload({"task": {"description": "t", "command": "echo ok"}})
        resp = client.post(INTENT_URL, json=payload)
        body = resp.json()
        assert body["status"] == "blocked"
        assert "run_at_or_run_in_required" in [e["code"] for e in (body.get("errors") or [])]

    def test_run_at_datetime_accepted(self, api_client):
        client, _ = api_client
        payload = _payload({"task": {
            "description": "t",
            "command": "echo ok",
            "run_at": "2099-06-01T12:00:00",
        }})
        resp = client.post(INTENT_URL, json=payload)
        assert resp.json()["status"] == "scheduled"


# ---------------------------------------------------------------------------
# Retry field inheritance
# ---------------------------------------------------------------------------

class TestIntentRetryFields:
    def test_task_level_max_retries_in_response(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(max_retries=3))
        assert resp.json()["max_retries"] == 3

    def test_task_max_retries_overrides_action_default(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="retry_action", max_retries=1)
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(
            action_name="retry_action", command=None, max_retries=5
        ))
        assert resp.json()["max_retries"] == 5

    def test_action_default_max_retries_used_when_task_omits(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="default_retry_action", max_retries=2)
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(action_name="default_retry_action", command=None))
        assert resp.json()["max_retries"] == 2

    def test_negative_max_retries_clamped_to_zero(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(max_retries=-5))
        assert resp.json()["max_retries"] == 0

    def test_retry_delay_below_1_clamped_to_1(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_task_payload(retry_delay=0))
        assert resp.json()["retry_delay"] == 1


# ---------------------------------------------------------------------------
# Source metadata
# ---------------------------------------------------------------------------

class TestIntentSourceMetadata:
    def test_source_from_meta_in_response(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json={
            **_payload(),
            "meta": {"source": "my_agent"},
        })
        assert resp.json()["source"] == "my_agent"

    def test_null_meta_source_is_none(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_payload())
        assert resp.json().get("source") is None


# ---------------------------------------------------------------------------
# Action CWD resolution
# ---------------------------------------------------------------------------

class TestIntentActionCwd:
    def test_action_default_cwd_used_when_task_omits(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="cwd_action", default_cwd="/tmp/action_home")
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(action_name="cwd_action", command=None))
        assert resp.json()["cwd"] == "/tmp/action_home"

    def test_task_cwd_overrides_action_default(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            make_action(s, name="cwd_override_action", default_cwd="/tmp/action_home")
            s.commit()

        resp = client.post(INTENT_URL, json=_task_payload(
            action_name="cwd_override_action", command=None, cwd="/tmp/task_home"
        ))
        assert resp.json()["cwd"] == "/tmp/task_home"


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

class TestIntentPreview:
    def test_preview_returns_status_preview_and_task_id_zero(self, api_client):
        client, _ = api_client
        resp = client.post(PREVIEW_URL, json=_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "preview"
        assert body["task_id"] == 0

    def test_preview_does_not_persist_to_db(self, api_client):
        from models import TaskRequest
        from sqlalchemy import select
        client, Factory = api_client
        client.post(PREVIEW_URL, json=_payload())
        with Factory() as s:
            count = len(s.execute(select(TaskRequest)).scalars().all())
        assert count == 0

    def test_preview_invalid_version_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(PREVIEW_URL, json=_payload({"intent_version": "v99"}))
        assert resp.status_code == 400

    def test_preview_missing_run_at_returns_400(self, api_client):
        client, _ = api_client
        payload = _payload({"task": {"description": "t", "command": "echo ok"}})
        resp = client.post(PREVIEW_URL, json=payload)
        assert resp.status_code == 400

    def test_preview_unknown_action_returns_400_not_blocked(self, api_client):
        """Preview raises 400 for validation errors; it never creates a blocked task."""
        client, _ = api_client
        resp = client.post(PREVIEW_URL, json=_task_payload(action_name="ghost", command=None))
        assert resp.status_code == 400

    def test_preview_env_requires_action_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post(PREVIEW_URL, json=_task_payload(env={"KEY": "val"}))
        assert resp.status_code == 400

    def test_preview_response_has_scheduled_time_fields(self, api_client):
        client, _ = api_client
        resp = client.post(PREVIEW_URL, json=_payload())
        body = resp.json()
        assert body.get("scheduled_at_local")
        assert body.get("scheduled_at_utc")

    def test_preview_source_from_meta(self, api_client):
        client, _ = api_client
        resp = client.post(PREVIEW_URL, json={**_payload(), "meta": {"source": "cli"}})
        assert resp.json()["source"] == "cli"
