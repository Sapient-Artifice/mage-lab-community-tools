"""Tests for recurring task endpoints and _recurring_from_payload helper.

Covers:
  - _recurring_from_payload unit tests (validation, DB checks, field mapping)
  - GET  /api/recurring
  - POST /api/recurring
  - PUT  /api/recurring/{id}
  - DELETE /api/recurring/{id}
  - POST /api/recurring/{id}/toggle
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.conftest import make_action, make_recurring


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _min_payload(name: str = "my_rec", command: str = "echo ok") -> dict:
    return {"name": name, "cron": "* * * * *", "command": command}


def _session(factory):
    return factory()


# ---------------------------------------------------------------------------
# _recurring_from_payload — direct unit tests
# ---------------------------------------------------------------------------

class TestRecurringFromPayload:
    """Call _recurring_from_payload directly with a db_session."""

    def _call(self, payload, session, monkeypatch, existing_id=None):
        import api as api_module
        monkeypatch.setattr(api_module, "_validate_command", lambda *a, **kw: None)
        monkeypatch.setattr(api_module, "_validate_cwd", lambda *a, **kw: None)
        return api_module._recurring_from_payload(payload, session, existing_id=existing_id)

    def test_invalid_cron_raises(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(name="x", cron="not-a-cron", command="echo ok")
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, db_session, monkeypatch)
        assert exc_info.value.detail == "cron_invalid"

    def test_invalid_timezone_raises(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(name="x", cron="* * * * *", command="echo ok", timezone="Fake/Zone")
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, db_session, monkeypatch)
        assert exc_info.value.detail == "invalid_timezone"

    def test_no_command_no_action_raises(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(name="x", cron="* * * * *")
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, db_session, monkeypatch)
        assert exc_info.value.detail == "command_or_action_required"

    def test_unknown_action_raises(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(name="x", cron="* * * * *", action_name="nonexistent")
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, db_session, monkeypatch)
        assert exc_info.value.detail == "unknown_action"

    def test_duplicate_name_raises(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        make_recurring(db_session, name="clash")
        db_session.commit()
        payload = RecurringTaskCreate(name="clash", cron="* * * * *", command="echo ok")
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, db_session, monkeypatch)
        assert exc_info.value.detail == "recurring_name_exists"

    def test_update_own_name_no_conflict(self, db_session, monkeypatch):
        """existing_id excludes self from name uniqueness check."""
        from schemas import RecurringTaskUpdate
        rt = make_recurring(db_session, name="self_name")
        db_session.commit()
        payload = RecurringTaskUpdate(name="self_name", cron="* * * * *", command="echo ok")
        result = self._call(payload, db_session, monkeypatch, existing_id=rt.id)
        assert result is not None

    def test_env_with_command_raises(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(
            name="x", cron="* * * * *", command="echo ok", env={"FOO": "bar"}
        )
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, db_session, monkeypatch)
        assert exc_info.value.detail == "env_requires_action"

    def test_valid_command_path_returns_recurring_task(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        from models import RecurringTask
        payload = RecurringTaskCreate(name="good", cron="0 * * * *", command="echo ok")
        result = self._call(payload, db_session, monkeypatch)
        assert isinstance(result, RecurringTask)
        assert result.command == "echo ok"
        assert result.cron == "0 * * * *"

    def test_next_run_at_populated(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(name="timed", cron="* * * * *", command="echo ok")
        result = self._call(payload, db_session, monkeypatch)
        assert result.next_run_at is not None

    def test_negative_max_retries_clamped(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(name="r", cron="* * * * *", command="echo ok", max_retries=-5)
        result = self._call(payload, db_session, monkeypatch)
        assert result.max_retries == 0

    def test_zero_retry_delay_clamped(self, db_session, monkeypatch):
        from schemas import RecurringTaskCreate
        payload = RecurringTaskCreate(name="r", cron="* * * * *", command="echo ok", retry_delay=0)
        result = self._call(payload, db_session, monkeypatch)
        assert result.retry_delay >= 1

    def test_action_name_stored_when_action_given(self, db_session, monkeypatch):
        """When action_name is given, the returned task stores action_name (not the resolved command)."""
        from schemas import RecurringTaskCreate
        make_action(db_session, name="my_act", command="echo from_action")
        db_session.commit()
        payload = RecurringTaskCreate(name="r", cron="* * * * *", action_name="my_act")
        result = self._call(payload, db_session, monkeypatch)
        # command column stays None; action_name is the reference used at spawn time
        assert result.action_name == "my_act"
        assert result.command is None


# ---------------------------------------------------------------------------
# GET /api/recurring
# ---------------------------------------------------------------------------

class TestListRecurring:
    def test_empty_list(self, api_client):
        client, _ = api_client
        resp = client.get("/api/recurring")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_recurring(self, api_client):
        client, _ = api_client
        client.post("/api/recurring", json=_min_payload("a"))
        client.post("/api/recurring", json=_min_payload("b"))
        resp = client.get("/api/recurring")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_ordered_by_name_asc(self, api_client):
        client, _ = api_client
        for name in ("zebra", "apple", "mango"):
            client.post("/api/recurring", json=_min_payload(name))
        resp = client.get("/api/recurring")
        names = [r["name"] for r in resp.json()]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# POST /api/recurring
# ---------------------------------------------------------------------------

class TestCreateRecurring:
    def test_create_basic(self, api_client):
        client, _ = api_client
        resp = client.post("/api/recurring", json=_min_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my_rec"
        assert data["cron"] == "* * * * *"
        assert "id" in data

    def test_invalid_cron_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post("/api/recurring", json={"name": "x", "cron": "not-a-cron", "command": "echo ok"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "cron_invalid"

    def test_invalid_timezone_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post("/api/recurring", json={**_min_payload(), "timezone": "Bad/Zone"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_timezone"

    def test_duplicate_name_returns_400(self, api_client):
        client, _ = api_client
        client.post("/api/recurring", json=_min_payload("dup"))
        resp = client.post("/api/recurring", json=_min_payload("dup"))
        assert resp.status_code == 400
        assert resp.json()["detail"] == "recurring_name_exists"

    def test_next_run_at_populated(self, api_client):
        client, _ = api_client
        resp = client.post("/api/recurring", json=_min_payload())
        assert resp.status_code == 200
        assert resp.json()["next_run_at"] is not None

    def test_description_persisted(self, api_client):
        client, _ = api_client
        payload = {**_min_payload(), "description": "runs every minute"}
        resp = client.post("/api/recurring", json=payload)
        assert resp.status_code == 200
        assert resp.json()["description"] == "runs every minute"

    def test_enabled_defaults_true(self, api_client):
        client, _ = api_client
        resp = client.post("/api/recurring", json=_min_payload())
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_create_disabled(self, api_client):
        client, _ = api_client
        resp = client.post("/api/recurring", json={**_min_payload(), "enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# PUT /api/recurring/{id}
# ---------------------------------------------------------------------------

class TestUpdateRecurring:
    def _create(self, client, name="orig") -> int:
        resp = client.post("/api/recurring", json=_min_payload(name))
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_update_fields(self, api_client):
        client, _ = api_client
        rid = self._create(client)
        payload = {"name": "updated", "cron": "0 * * * *", "command": "echo new"}
        resp = client.put(f"/api/recurring/{rid}", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated"
        assert data["cron"] == "0 * * * *"

    def test_update_not_found_returns_404(self, api_client):
        client, _ = api_client
        resp = client.put("/api/recurring/9999", json=_min_payload())
        assert resp.status_code == 404

    def test_update_name_conflict_returns_400(self, api_client):
        client, _ = api_client
        self._create(client, "first")
        second_id = self._create(client, "second")
        resp = client.put(f"/api/recurring/{second_id}", json={**_min_payload("first"), "cron": "* * * * *"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "recurring_name_exists"

    def test_update_own_name_allowed(self, api_client):
        client, _ = api_client
        rid = self._create(client, "same")
        resp = client.put(f"/api/recurring/{rid}", json={"name": "same", "cron": "0 * * * *", "command": "echo updated"})
        assert resp.status_code == 200
        assert resp.json()["command"] == "echo updated"


# ---------------------------------------------------------------------------
# DELETE /api/recurring/{id}
# ---------------------------------------------------------------------------

class TestDeleteRecurring:
    def test_delete_existing(self, api_client):
        client, _ = api_client
        rid = client.post("/api/recurring", json=_min_payload()).json()["id"]
        resp = client.delete(f"/api/recurring/{rid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert resp.json()["recurring_id"] == rid

    def test_deleted_no_longer_listed(self, api_client):
        client, _ = api_client
        rid = client.post("/api/recurring", json=_min_payload()).json()["id"]
        client.delete(f"/api/recurring/{rid}")
        ids = [r["id"] for r in client.get("/api/recurring").json()]
        assert rid not in ids

    def test_delete_not_found_returns_404(self, api_client):
        client, _ = api_client
        resp = client.delete("/api/recurring/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/recurring/{id}/toggle
# ---------------------------------------------------------------------------

class TestToggleRecurring:
    def test_toggle_enabled_to_disabled(self, api_client):
        client, _ = api_client
        rid = client.post("/api/recurring", json=_min_payload()).json()["id"]
        resp = client.post(f"/api/recurring/{rid}/toggle")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    def test_toggle_disabled_to_enabled(self, api_client):
        client, _ = api_client
        rid = client.post("/api/recurring", json={**_min_payload(), "enabled": False}).json()["id"]
        resp = client.post(f"/api/recurring/{rid}/toggle")
        assert resp.status_code == 200
        assert resp.json()["status"] == "enabled"

    def test_toggle_to_enabled_rearmed_next_run_at(self, api_client):
        """Re-enabling must set a fresh next_run_at."""
        client, factory = api_client
        rid = client.post("/api/recurring", json={**_min_payload(), "enabled": False}).json()["id"]

        # Null out next_run_at directly in DB to simulate stale state
        s = _session(factory)
        try:
            from models import RecurringTask
            rt = s.get(RecurringTask, rid)
            rt.next_run_at = None
            s.commit()
        finally:
            s.close()

        client.post(f"/api/recurring/{rid}/toggle")

        s2 = _session(factory)
        try:
            from models import RecurringTask
            rt = s2.get(RecurringTask, rid)
            assert rt.next_run_at is not None
        finally:
            s2.close()

    def test_toggle_not_found_returns_404(self, api_client):
        client, _ = api_client
        resp = client.post("/api/recurring/9999/toggle")
        assert resp.status_code == 404
