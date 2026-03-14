"""Tests for GET/POST /settings and GET / (dashboard cleanup indicator).

Covers:
  - POST /settings: cleanup_enabled preserved in error response when dir validation fails
  - POST /settings: cleanup_enabled not checked when not submitted on error
  - GET /: cleanup pill shown when cleanup enabled (correct retention_days)
  - GET /: cleanup pill hidden when cleanup disabled
  - GET /: cleanup pill hidden when no settings row exists
"""
from __future__ import annotations

import re

# A path that is absolute but guaranteed not to exist on any test machine.
_BAD_DIR = "/tmp/mage_nonexistent_dir_xyzzy_test"


def _checkbox_is_checked(html: str) -> bool:
    """Return True if the cleanup_enabled checkbox tag contains the 'checked' attribute."""
    match = re.search(r'<input[^>]*id="cleanup_enabled"[^>]*>', html, re.DOTALL)
    assert match is not None, "cleanup_enabled checkbox not found in HTML"
    return "checked" in match.group(0)


class TestSettingsErrorPath:
    def test_cleanup_enabled_preserved_on_dir_validation_error(self, api_client):
        """cleanup_enabled=1 submitted alongside an invalid dir → 400 with checkbox checked."""
        client, _ = api_client

        resp = client.post(
            "/settings",
            data={"allowed_command_dirs": _BAD_DIR, "cleanup_enabled": "1"},
        )

        assert resp.status_code == 400
        assert _checkbox_is_checked(resp.text)

    def test_cleanup_not_checked_when_not_submitted_on_error(self, api_client):
        """cleanup_enabled not submitted → 400 error page shows checkbox unchecked."""
        client, _ = api_client

        resp = client.post(
            "/settings",
            data={"allowed_command_dirs": _BAD_DIR},
        )

        assert resp.status_code == 400
        assert not _checkbox_is_checked(resp.text)


class TestDashboardCleanupPill:
    def test_pill_shown_when_cleanup_enabled(self, api_client):
        """GET / with cleanup enabled → pill with correct retention_days appears."""
        from models import Settings

        client, Factory = api_client

        s = Factory()
        s.add(Settings(cleanup_enabled=1, task_retention_days=14))
        s.commit()
        s.close()

        resp = client.get("/")
        assert resp.status_code == 200
        assert "auto-cleanup 14d" in resp.text

    def test_pill_hidden_when_cleanup_disabled(self, api_client):
        """GET / with cleanup disabled → pill absent."""
        from models import Settings

        client, Factory = api_client

        s = Factory()
        s.add(Settings(cleanup_enabled=0, task_retention_days=30))
        s.commit()
        s.close()

        resp = client.get("/")
        assert resp.status_code == 200
        assert "auto-cleanup" not in resp.text

    def test_pill_hidden_when_no_settings_row(self, api_client):
        """GET / with no Settings row at all → pill absent (cleanup defaults to disabled)."""
        client, _ = api_client

        resp = client.get("/")
        assert resp.status_code == 200
        assert "auto-cleanup" not in resp.text
