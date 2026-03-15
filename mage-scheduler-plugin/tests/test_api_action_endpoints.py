"""Tests for action-related endpoints and helpers.

Covers:
  - _validate_dirs_list unit tests
  - _validate_action_payload unit tests
  - GET  /api/actions
  - POST /api/actions
  - PUT  /api/actions/{id}
  - DELETE /api/actions/{id}
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from tests.conftest import make_action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _min_payload(name: str = "my_action") -> dict:
    """Minimal valid ActionCreate payload."""
    return {"name": name, "command": "echo ok"}


def _session(factory):
    return factory()


# ---------------------------------------------------------------------------
# _validate_dirs_list — direct unit tests
# ---------------------------------------------------------------------------

class TestValidateDirsList:
    def setup_method(self):
        import api as api_module
        self._fn = api_module._validate_dirs_list

    def test_none_passes(self):
        self._fn(None, "should_not_raise")  # no exception

    def test_empty_list_passes(self):
        self._fn([], "should_not_raise")

    def test_relative_path_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            self._fn(["relative/path"], "my_error_code")
        assert exc_info.value.detail == "my_error_code"

    def test_nonexistent_absolute_path_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            self._fn(["/nonexistent/totally/fake/dir"], "my_error_code")
        assert exc_info.value.detail == "my_error_code"

    def test_valid_absolute_dir_passes(self, tmp_path):
        self._fn([str(tmp_path)], "should_not_raise")  # no exception

    def test_multiple_dirs_one_invalid_raises(self, tmp_path):
        with pytest.raises(HTTPException) as exc_info:
            self._fn([str(tmp_path), "relative/bad"], "err_code")
        assert exc_info.value.detail == "err_code"


# ---------------------------------------------------------------------------
# _validate_action_payload — direct unit tests
# ---------------------------------------------------------------------------

class TestValidateActionPayload:
    """Tests for _validate_action_payload, with _validate_command/_validate_cwd stubbed out."""

    def _call(self, payload, settings, monkeypatch):
        import api as api_module
        monkeypatch.setattr(api_module, "_validate_command", lambda *a, **kw: None)
        monkeypatch.setattr(api_module, "_validate_cwd", lambda *a, **kw: None)
        return api_module._validate_action_payload(payload, settings)

    def _settings(self, command_dirs=None, cwd_dirs=None):
        """Return a lightweight Settings-like object."""
        from unittest.mock import MagicMock
        s = MagicMock()
        s.allowed_command_dirs = command_dirs
        s.allowed_cwd_dirs = cwd_dirs
        return s

    def test_relative_command_dir_raises(self, tmp_path, monkeypatch):
        from schemas import ActionCreate
        payload = ActionCreate(
            name="act",
            command="echo ok",
            allowed_command_dirs=["relative/path"],
        )
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, self._settings(), monkeypatch)
        assert exc_info.value.detail == "action_command_dirs_invalid"

    def test_relative_cwd_dir_raises(self, tmp_path, monkeypatch):
        from schemas import ActionCreate
        payload = ActionCreate(
            name="act",
            command="echo ok",
            allowed_cwd_dirs=["relative/path"],
        )
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, self._settings(), monkeypatch)
        assert exc_info.value.detail == "action_cwd_dirs_invalid"

    def test_command_dir_outside_settings_raises(self, tmp_path, monkeypatch):
        """Action's allowed_command_dirs entry not within global settings dirs → error."""
        from schemas import ActionCreate

        action_dir = tmp_path / "action_bin"
        action_dir.mkdir()

        payload = ActionCreate(
            name="act",
            command="echo ok",
            allowed_command_dirs=[str(action_dir)],
        )
        # Global setting restricts to /usr/bin — action_dir is outside that
        settings = self._settings(command_dirs=["/usr/bin"])
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, settings, monkeypatch)
        assert exc_info.value.detail == "action_command_dir_outside_settings"

    def test_command_dir_mismatch_raises(self, tmp_path, monkeypatch):
        """Executable not within action's own allowed_command_dirs → error."""
        from schemas import ActionCreate

        action_dir = tmp_path / "action_bin"
        action_dir.mkdir()

        payload = ActionCreate(
            name="act",
            command="/usr/bin/echo",  # executable is /usr/bin/echo
            allowed_command_dirs=[str(action_dir)],  # /usr/bin/echo is not under action_dir
        )
        # No global restriction so outside-settings check is skipped
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, self._settings(), monkeypatch)
        assert exc_info.value.detail == "action_command_dir_mismatch"

    def test_cwd_dir_outside_settings_raises(self, tmp_path, monkeypatch):
        from schemas import ActionCreate

        cwd_dir = tmp_path / "work"
        cwd_dir.mkdir()

        payload = ActionCreate(
            name="act",
            command="echo ok",
            allowed_cwd_dirs=[str(cwd_dir)],
        )
        settings = self._settings(cwd_dirs=["/var/data"])
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, settings, monkeypatch)
        assert exc_info.value.detail == "action_cwd_dir_outside_settings"

    def test_cwd_dir_mismatch_raises(self, tmp_path, monkeypatch):
        """default_cwd not within action's own allowed_cwd_dirs → error."""
        from schemas import ActionCreate

        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        payload = ActionCreate(
            name="act",
            command="echo ok",
            allowed_cwd_dirs=[str(allowed_dir)],
            default_cwd=str(other_dir),  # not inside allowed_dir
        )
        with pytest.raises(HTTPException) as exc_info:
            self._call(payload, self._settings(), monkeypatch)
        assert exc_info.value.detail == "action_cwd_dir_mismatch"

    def test_valid_payload_returns_dirs(self, tmp_path, monkeypatch):
        """Clean payload with no optional dirs returns (None, None)."""
        from schemas import ActionCreate
        payload = ActionCreate(name="act", command="echo ok")
        result = self._call(payload, self._settings(), monkeypatch)
        assert result == (None, None)

    def test_valid_payload_with_matching_dirs_returns_dirs(self, tmp_path, monkeypatch):
        """Payload with matching dirs should succeed and return them."""
        from schemas import ActionCreate

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        exe = bin_dir / "mytool"
        exe.touch()

        payload = ActionCreate(
            name="act",
            command=str(exe),
            allowed_command_dirs=[str(bin_dir)],
        )
        result = self._call(payload, self._settings(), monkeypatch)
        assert result[0] == [str(bin_dir)]


# ---------------------------------------------------------------------------
# GET /api/actions
# ---------------------------------------------------------------------------

class TestListActions:
    def test_empty_list(self, api_client):
        client, _ = api_client
        resp = client.get("/api/actions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_actions(self, api_client):
        client, factory = api_client
        s = _session(factory)
        try:
            make_action(s, name="beta")
            make_action(s, name="alpha")
            s.commit()
        finally:
            s.close()

        resp = client.get("/api/actions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_ordered_by_name_asc(self, api_client):
        client, factory = api_client
        s = _session(factory)
        try:
            make_action(s, name="zebra")
            make_action(s, name="apple")
            make_action(s, name="mango")
            s.commit()
        finally:
            s.close()

        resp = client.get("/api/actions")
        names = [a["name"] for a in resp.json()]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# POST /api/actions
# ---------------------------------------------------------------------------

class TestCreateAction:
    def test_create_basic_action(self, api_client):
        client, _ = api_client
        resp = client.post("/api/actions", json=_min_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my_action"
        assert data["command"] == "echo ok"
        assert "id" in data

    def test_duplicate_name_returns_400(self, api_client):
        client, _ = api_client
        client.post("/api/actions", json=_min_payload("dup"))
        resp = client.post("/api/actions", json=_min_payload("dup"))
        assert resp.status_code == 400
        assert resp.json()["detail"] == "action_name_exists"

    def test_description_persisted(self, api_client):
        client, _ = api_client
        payload = {**_min_payload(), "description": "does stuff"}
        resp = client.post("/api/actions", json=payload)
        assert resp.status_code == 200
        assert resp.json()["description"] == "does stuff"

    def test_allowed_env_persisted(self, api_client):
        client, _ = api_client
        payload = {**_min_payload(), "allowed_env": ["FOO", "BAR"]}
        resp = client.post("/api/actions", json=payload)
        assert resp.status_code == 200
        assert set(resp.json()["allowed_env"]) == {"FOO", "BAR"}

    def test_negative_max_retries_clamped_to_zero(self, api_client):
        client, _ = api_client
        payload = {**_min_payload(), "max_retries": -3}
        resp = client.post("/api/actions", json=payload)
        assert resp.status_code == 200
        assert resp.json()["max_retries"] == 0

    def test_zero_retry_delay_clamped_to_one(self, api_client):
        client, _ = api_client
        payload = {**_min_payload(), "retry_delay": 0}
        resp = client.post("/api/actions", json=payload)
        assert resp.status_code == 200
        assert resp.json()["retry_delay"] >= 1


# ---------------------------------------------------------------------------
# PUT /api/actions/{id}
# ---------------------------------------------------------------------------

class TestUpdateAction:
    def _create(self, client, name="orig_action"):
        resp = client.post("/api/actions", json={"name": name, "command": "echo old"})
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_update_action_fields(self, api_client):
        client, _ = api_client
        action_id = self._create(client)
        payload = {"name": "updated_action", "command": "echo new", "description": "new desc"}
        resp = client.put(f"/api/actions/{action_id}", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated_action"
        assert data["command"] == "echo new"
        assert data["description"] == "new desc"

    def test_update_not_found_returns_404(self, api_client):
        client, _ = api_client
        payload = {"name": "x", "command": "echo x"}
        resp = client.put("/api/actions/9999", json=payload)
        assert resp.status_code == 404

    def test_update_name_conflict_returns_400(self, api_client):
        """Renaming to a name already used by another action is rejected."""
        client, _ = api_client
        self._create(client, "first_action")
        second_id = self._create(client, "second_action")
        payload = {"name": "first_action", "command": "echo ok"}
        resp = client.put(f"/api/actions/{second_id}", json=payload)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "action_name_exists"

    def test_update_own_name_allowed(self, api_client):
        """Updating an action while keeping the same name must not raise a conflict."""
        client, _ = api_client
        action_id = self._create(client, "same_name")
        payload = {"name": "same_name", "command": "echo updated"}
        resp = client.put(f"/api/actions/{action_id}", json=payload)
        assert resp.status_code == 200
        assert resp.json()["command"] == "echo updated"


# ---------------------------------------------------------------------------
# DELETE /api/actions/{id}
# ---------------------------------------------------------------------------

class TestDeleteAction:
    def test_delete_existing_action(self, api_client):
        client, _ = api_client
        create_resp = client.post("/api/actions", json=_min_payload("to_delete"))
        action_id = create_resp.json()["id"]

        resp = client.delete(f"/api/actions/{action_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert resp.json()["action_id"] == action_id

    def test_deleted_action_no_longer_returned(self, api_client):
        client, _ = api_client
        create_resp = client.post("/api/actions", json=_min_payload("gone"))
        action_id = create_resp.json()["id"]

        client.delete(f"/api/actions/{action_id}")
        get_resp = client.get(f"/api/tasks/{action_id}")
        # action should be gone — confirm list is empty
        list_resp = client.get("/api/actions")
        ids = [a["id"] for a in list_resp.json()]
        assert action_id not in ids

    def test_delete_not_found_returns_404(self, api_client):
        client, _ = api_client
        resp = client.delete("/api/actions/9999")
        assert resp.status_code == 404
