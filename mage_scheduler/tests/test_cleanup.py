"""Tests for the cleanup beat task and related API endpoints.

Covers:
  - _do_cleanup: no-op when cleanup disabled
  - _do_cleanup: deletes terminal tasks past cutoff
  - _do_cleanup: skips retain_result=1 tasks
  - _do_cleanup: skips when a downstream task was created within retention window
  - _do_cleanup: deletes when all downstream tasks are also past cutoff
  - cleanup_old_tasks beat task integration
  - POST /api/tasks/cleanup endpoint
  - GET /api/tasks/stats counts
  - retain_result inherited from action in intent flow
  - retain_result passable in TaskCreate / TaskRunNow
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Fixture — isolated in-memory DB patched into tasks.cleanup_task
# ---------------------------------------------------------------------------

@pytest.fixture
def cln_mem_db(monkeypatch):
    """In-memory DB with SessionLocal and init_db patched inside tasks.cleanup_task."""
    from db import Base
    import models  # noqa: F401
    import tasks.cleanup_task as ct

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(ct, "SessionLocal", Factory)
    monkeypatch.setattr(ct, "init_db", lambda: None)

    yield Factory

    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_terminal_task(session, *, status="success", retain_result=0, created_at=None):
    from models import TaskRequest

    task = TaskRequest(
        description="old task",
        command="echo done",
        run_at=datetime(2000, 1, 1),
        status=status,
        retain_result=retain_result,
    )
    if created_at is not None:
        task.created_at = created_at
    session.add(task)
    session.flush()
    return task


def _make_settings(session, *, cleanup_enabled=1, retention_days=30):
    from models import Settings

    s = Settings(cleanup_enabled=cleanup_enabled, task_retention_days=retention_days)
    session.add(s)
    session.flush()
    return s


# ---------------------------------------------------------------------------
# _do_cleanup — core logic
# ---------------------------------------------------------------------------

class TestDoCleanup:
    def test_noop_when_no_settings(self, db_session):
        from tasks.cleanup_task import _do_cleanup

        # no Settings row → cleanup disabled
        result = _do_cleanup(db_session)
        assert result == 0

    def test_noop_when_cleanup_disabled(self, db_session):
        from tasks.cleanup_task import _do_cleanup

        _make_settings(db_session, cleanup_enabled=0)
        cutoff = datetime.utcnow() - timedelta(days=60)
        _make_terminal_task(db_session, status="success", created_at=cutoff - timedelta(days=1))
        db_session.commit()

        assert _do_cleanup(db_session) == 0

    def test_deletes_terminal_task_past_cutoff(self, db_session):
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest

        _make_settings(db_session, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=31)
        _make_terminal_task(db_session, status="success", created_at=old_date)
        db_session.commit()

        deleted = _do_cleanup(db_session)

        assert deleted == 1
        assert db_session.execute(select(TaskRequest)).scalars().all() == []

    def test_does_not_delete_recent_task(self, db_session):
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest

        _make_settings(db_session, retention_days=30)
        recent = datetime.utcnow() - timedelta(days=5)
        _make_terminal_task(db_session, status="success", created_at=recent)
        db_session.commit()

        deleted = _do_cleanup(db_session)

        assert deleted == 0
        assert len(db_session.execute(select(TaskRequest)).scalars().all()) == 1

    def test_does_not_delete_non_terminal_task(self, db_session):
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest

        _make_settings(db_session, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)
        _make_terminal_task(db_session, status="scheduled", created_at=old_date)
        db_session.commit()

        assert _do_cleanup(db_session) == 0
        assert len(db_session.execute(select(TaskRequest)).scalars().all()) == 1

    def test_skips_retain_result_task(self, db_session):
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest

        _make_settings(db_session, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)
        _make_terminal_task(db_session, status="success", retain_result=1, created_at=old_date)
        db_session.commit()

        assert _do_cleanup(db_session) == 0
        assert len(db_session.execute(select(TaskRequest)).scalars().all()) == 1

    def test_all_terminal_statuses_are_eligible(self, db_session):
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest

        _make_settings(db_session, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)
        for st in ("success", "failed", "cancelled", "blocked"):
            _make_terminal_task(db_session, status=st, created_at=old_date)
        db_session.commit()

        deleted = _do_cleanup(db_session)

        assert deleted == 4
        assert db_session.execute(select(TaskRequest)).scalars().all() == []

    def test_skips_task_with_recent_downstream(self, db_session):
        """Upstream task has a downstream created within retention window → keep upstream."""
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest, TaskDependency

        _make_settings(db_session, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)
        recent_date = datetime.utcnow() - timedelta(days=5)

        upstream = _make_terminal_task(db_session, status="success", created_at=old_date)
        downstream = _make_terminal_task(db_session, status="success", created_at=recent_date)

        dep = TaskDependency(task_id=downstream.id, depends_on_task_id=upstream.id)
        db_session.add(dep)
        db_session.commit()

        deleted = _do_cleanup(db_session)

        assert deleted == 0
        tasks = db_session.execute(select(TaskRequest)).scalars().all()
        assert len(tasks) == 2

    def test_deletes_when_all_downstream_also_past_cutoff(self, db_session):
        """Upstream and downstream both old → upstream is deleted."""
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest, TaskDependency

        _make_settings(db_session, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)

        upstream = _make_terminal_task(db_session, status="success", created_at=old_date)
        downstream = _make_terminal_task(db_session, status="success", created_at=old_date)

        dep = TaskDependency(task_id=downstream.id, depends_on_task_id=upstream.id)
        db_session.add(dep)
        db_session.commit()

        deleted = _do_cleanup(db_session)

        # both upstream and downstream are eligible — both deleted
        assert deleted == 2
        assert db_session.execute(select(TaskRequest)).scalars().all() == []

    def test_retention_days_zero_defaults_to_30(self, db_session):
        """retention_days=0 falls back to 30."""
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest

        _make_settings(db_session, retention_days=0)
        old_date = datetime.utcnow() - timedelta(days=31)
        _make_terminal_task(db_session, status="success", created_at=old_date)
        db_session.commit()

        deleted = _do_cleanup(db_session)
        assert deleted == 1

    def test_multiple_tasks_mixed_eligibility(self, db_session):
        from tasks.cleanup_task import _do_cleanup
        from models import TaskRequest

        _make_settings(db_session, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)
        recent_date = datetime.utcnow() - timedelta(days=5)

        _make_terminal_task(db_session, status="success", created_at=old_date)
        _make_terminal_task(db_session, status="failed", created_at=old_date)
        _make_terminal_task(db_session, status="success", created_at=recent_date)
        _make_terminal_task(db_session, status="success", retain_result=1, created_at=old_date)
        db_session.commit()

        deleted = _do_cleanup(db_session)

        assert deleted == 2
        remaining = db_session.execute(select(TaskRequest)).scalars().all()
        assert len(remaining) == 2


# ---------------------------------------------------------------------------
# cleanup_old_tasks beat task
# ---------------------------------------------------------------------------

class TestCleanupOldTasksBeat:
    def test_returns_deleted_count(self, cln_mem_db):
        from tasks.cleanup_task import cleanup_old_tasks

        s = cln_mem_db()
        _make_settings(s, cleanup_enabled=0)
        s.commit()
        s.close()

        result = cleanup_old_tasks()
        assert result == {"deleted": 0}

    def test_beat_task_deletes_eligible_tasks(self, cln_mem_db):
        from tasks.cleanup_task import cleanup_old_tasks
        from models import TaskRequest

        s = cln_mem_db()
        _make_settings(s, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)
        _make_terminal_task(s, status="success", created_at=old_date)
        s.commit()
        s.close()

        result = cleanup_old_tasks()
        assert result["deleted"] == 1

        s2 = cln_mem_db()
        assert s2.execute(select(TaskRequest)).scalars().all() == []
        s2.close()


# ---------------------------------------------------------------------------
# POST /api/tasks/cleanup  and  GET /api/tasks/stats
# ---------------------------------------------------------------------------

class TestCleanupEndpoint:
    def test_manual_cleanup_returns_deleted_count(self, api_client):
        client, Factory = api_client

        # Seed: cleanup disabled → no deletions
        s = Factory()
        _make_settings(s, cleanup_enabled=0)
        old_date = datetime.utcnow() - timedelta(days=60)
        _make_terminal_task(s, status="success", created_at=old_date)
        s.commit()
        s.close()

        resp = client.post("/api/tasks/cleanup")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 0}

    def test_manual_cleanup_deletes_eligible_tasks(self, api_client):
        from models import TaskRequest

        client, Factory = api_client

        s = Factory()
        _make_settings(s, retention_days=30)
        old_date = datetime.utcnow() - timedelta(days=60)
        _make_terminal_task(s, status="success", created_at=old_date)
        s.commit()
        s.close()

        resp = client.post("/api/tasks/cleanup")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1


class TestStatsEndpoint:
    def test_empty_db_returns_zeros(self, api_client):
        client, _ = api_client

        resp = client.get("/api/tasks/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["by_status"] == {}

    def test_counts_by_status(self, api_client):
        client, Factory = api_client

        s = Factory()
        for st in ("success", "success", "failed", "scheduled"):
            _make_terminal_task(s, status=st)
        s.commit()
        s.close()

        resp = client.get("/api/tasks/stats")
        data = resp.json()
        assert data["total"] == 4
        assert data["by_status"]["success"] == 2
        assert data["by_status"]["failed"] == 1
        assert data["by_status"]["scheduled"] == 1


# ---------------------------------------------------------------------------
# retain_result in TaskCreate / TaskRunNow (via POST /api/tasks)
# ---------------------------------------------------------------------------

class TestRetainResultTaskCreate:
    def test_task_create_retain_result_false_by_default(self, api_client):
        from models import TaskRequest

        client, Factory = api_client

        payload = {
            "command": "/usr/bin/echo",
            "run_at": "2099-01-01T00:00:00",
            "description": "no retain",
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200

        s = Factory()
        task = s.execute(select(TaskRequest)).scalars().first()
        assert task.retain_result == 0
        s.close()

    def test_task_create_retain_result_true(self, api_client):
        from models import TaskRequest

        client, Factory = api_client

        payload = {
            "command": "/usr/bin/echo",
            "run_at": "2099-01-01T00:00:00",
            "description": "keep me",
            "retain_result": True,
        }
        resp = client.post("/api/tasks", json=payload)
        assert resp.status_code == 200

        s = Factory()
        task = s.execute(select(TaskRequest)).scalars().first()
        assert task.retain_result == 1
        s.close()

    def test_run_now_retain_result_stored(self, api_client):
        from models import TaskRequest

        client, Factory = api_client

        payload = {
            "command": "/usr/bin/echo",
            "description": "run now retain",
            "retain_result": True,
        }
        resp = client.post("/api/tasks/run_now", json=payload)
        assert resp.status_code == 200

        s = Factory()
        task = s.execute(select(TaskRequest)).scalars().first()
        assert task.retain_result == 1
        s.close()


# ---------------------------------------------------------------------------
# retain_result inherited from action in intent flow
# ---------------------------------------------------------------------------

class TestRetainResultIntentInheritance:
    def _schedule_intent(self, client, *, action_name=None, task_retain=False, command=None):
        task = {
            "description": "test intent",
            "run_in": "1h",
            "retain_result": task_retain,
        }
        if action_name:
            task["action_name"] = action_name
        if command:
            task["command"] = command
        payload = {"intent_version": "v1", "task": task}
        return client.post("/api/tasks/intent", json=payload)

    def test_task_level_retain_result_stored(self, api_client):
        from models import TaskRequest

        client, Factory = api_client

        resp = self._schedule_intent(client, command="/usr/bin/echo", task_retain=True)
        assert resp.status_code == 200

        s = Factory()
        task = s.execute(select(TaskRequest)).scalars().first()
        assert task.retain_result == 1
        s.close()

    def test_task_level_retain_false_by_default(self, api_client):
        from models import TaskRequest

        client, Factory = api_client

        resp = self._schedule_intent(client, command="/usr/bin/echo", task_retain=False)
        assert resp.status_code == 200

        s = Factory()
        task = s.execute(select(TaskRequest)).scalars().first()
        assert task.retain_result == 0
        s.close()

    def test_action_retain_result_wins_over_task_false(self, api_client):
        """Action.retain_result=1 overrides task.retain_result=False."""
        from models import Action, TaskRequest

        client, Factory = api_client

        s = Factory()
        action = Action(
            name="sticky_action",
            command="/usr/bin/echo",
            retain_result=1,
        )
        s.add(action)
        s.commit()
        s.close()

        resp = self._schedule_intent(client, action_name="sticky_action", task_retain=False)
        assert resp.status_code == 200

        s2 = Factory()
        task = s2.execute(select(TaskRequest)).scalars().first()
        assert task.retain_result == 1
        s2.close()

    def test_action_retain_false_task_retain_true_stored(self, api_client):
        """Action.retain_result=0, task.retain_result=True → task flag wins."""
        from models import Action, TaskRequest

        client, Factory = api_client

        s = Factory()
        action = Action(
            name="normal_action",
            command="/usr/bin/echo",
            retain_result=0,
        )
        s.add(action)
        s.commit()
        s.close()

        resp = self._schedule_intent(client, action_name="normal_action", task_retain=True)
        assert resp.status_code == 200

        s2 = Factory()
        task = s2.execute(select(TaskRequest)).scalars().first()
        assert task.retain_result == 1
        s2.close()

    def test_intent_response_includes_retain_result(self, api_client):
        client, _ = api_client

        resp = self._schedule_intent(client, command="/usr/bin/echo", task_retain=True)
        assert resp.status_code == 200
        assert resp.json()["retain_result"] is True
