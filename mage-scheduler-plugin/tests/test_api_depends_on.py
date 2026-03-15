"""Integration tests for the depends_on feature via POST /api/tasks/intent.

Uses the api_client fixture from conftest which provides a TestClient backed
by an isolated in-memory SQLite DB (StaticPool) and mocked Celery dispatch.
"""
from __future__ import annotations

import pytest

from tests.conftest import make_task

INTENT_URL = "/api/tasks/intent"

# Minimal valid base payload — command and run_in are the least-surprising
# non-action fields that pass all pre-dependency validation.
BASE_TASK = {
    "description": "dep test task",
    "command": "echo hello",
    "run_in": "5 minutes",
}


def _payload(extra_task_fields: dict | None = None) -> dict:
    task = {**BASE_TASK, **(extra_task_fields or {})}
    return {"intent_version": "v1", "task": task}


class TestApiDependsOn:

    def test_nonexistent_dep_id_returns_blocked(self, api_client):
        client, _ = api_client
        resp = client.post(INTENT_URL, json=_payload({"depends_on": [99999]}))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "blocked"
        error_codes = [e["code"] for e in (body.get("errors") or [])]
        assert "depends_on_invalid" in error_codes

    def test_already_failed_dep_returns_failed(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            dep = make_task(s, status="failed")
            s.commit()
            dep_id = dep.id

        resp = client.post(INTENT_URL, json=_payload({"depends_on": [dep_id]}))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        error_codes = [e["code"] for e in (body.get("errors") or [])]
        assert "depends_on_already_failed" in error_codes

    def test_already_cancelled_dep_returns_failed(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            dep = make_task(s, status="cancelled")
            s.commit()
            dep_id = dep.id

        resp = client.post(INTENT_URL, json=_payload({"depends_on": [dep_id]}))
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    def test_in_flight_dep_returns_waiting(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            dep = make_task(s, status="running")
            s.commit()
            dep_id = dep.id

        resp = client.post(INTENT_URL, json=_payload({"depends_on": [dep_id]}))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "waiting"
        assert dep_id in body["depends_on"]

    def test_all_deps_succeeded_returns_scheduled(self, api_client):
        client, Factory = api_client
        with Factory() as s:
            dep = make_task(s, status="success")
            s.commit()
            dep_id = dep.id

        resp = client.post(INTENT_URL, json=_payload({"depends_on": [dep_id]}))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "scheduled"
        assert dep_id in (body.get("depends_on") or [])

    def test_cron_with_depends_on_returns_400(self, api_client):
        client, _ = api_client
        payload = _payload({
            "cron": "0 * * * *",
            "depends_on": [1],
        })
        # cron tasks don't use run_in — remove it so the only error is depends_on_cron_unsupported
        del payload["task"]["run_in"]
        resp = client.post(INTENT_URL, json=payload)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        error_codes = [e["code"] for e in detail["errors"]]
        assert "depends_on_cron_unsupported" in error_codes

    def test_duplicate_dep_ids_are_deduplicated(self, api_client):
        """Passing the same ID three times should behave identically to passing it once."""
        client, Factory = api_client
        with Factory() as s:
            dep = make_task(s, status="running")
            s.commit()
            dep_id = dep.id

        resp = client.post(INTENT_URL, json=_payload({"depends_on": [dep_id, dep_id, dep_id]}))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "waiting"
        # Deduplicated: only one entry
        assert body["depends_on"].count(dep_id) == 1

    def test_waiting_task_dep_ids_persisted(self, api_client):
        """TaskDependency rows are written to the DB for a waiting task."""
        from models import TaskDependency
        from sqlalchemy import select
        client, Factory = api_client
        with Factory() as s:
            dep = make_task(s, status="running")
            s.commit()
            dep_id = dep.id

        resp = client.post(INTENT_URL, json=_payload({"depends_on": [dep_id]}))
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        with Factory() as s:
            rows = s.execute(
                select(TaskDependency).where(TaskDependency.task_id == task_id)
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].depends_on_task_id == dep_id
