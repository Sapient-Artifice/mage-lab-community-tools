from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="function")
def db_session():
    """Provide a fresh in-memory SQLite session for each test."""
    from db import Base
    import models  # noqa: F401 — registers all models with Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def nt_mem_db(monkeypatch):
    """In-memory DB with SessionLocal patched inside tasks.notification_task.

    Yields the sessionmaker so tests can set up data and verify state
    using the same underlying engine that _trigger_dependents will use.
    """
    from db import Base
    import models  # noqa: F401
    import tasks.notification_task as nt

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(nt, "SessionLocal", Factory)

    yield Factory

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def dep_mem_db(monkeypatch):
    """In-memory DB with SessionLocal and init_db patched inside tasks.dependency_task.

    Used for testing check_waiting_tasks and its helpers.
    """
    from db import Base
    import models  # noqa: F401
    import tasks.dependency_task as dt

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(dt, "SessionLocal", Factory)
    monkeypatch.setattr(dt, "init_db", lambda: None)

    yield Factory

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_client(monkeypatch):
    """TestClient with a fully isolated in-memory DB.

    Patches api.SessionLocal and tasks.task_manager.SessionLocal to share
    a StaticPool engine so TaskManager writes are visible to the endpoint session.
    Also mocks run_command_at.apply_async to prevent Celery dispatch.

    Yields (TestClient, sessionmaker).
    """
    from unittest.mock import MagicMock
    from sqlalchemy.pool import StaticPool
    from fastapi.testclient import TestClient
    from db import Base
    import models  # noqa: F401
    import api
    import tasks.task_manager as tm

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(api, "SessionLocal", Factory)
    monkeypatch.setattr(tm, "SessionLocal", Factory)
    monkeypatch.setattr(tm, "init_db", lambda: None)

    # Bypass filesystem checks — not relevant to dependency feature tests
    monkeypatch.setattr(api, "_validate_command", lambda *a, **kw: None)
    monkeypatch.setattr(api, "_validate_cwd", lambda *a, **kw: None)

    fake_result = MagicMock()
    fake_result.id = "fake-celery-id"
    monkeypatch.setattr(tm.run_command_at, "apply_async", lambda *a, **kw: fake_result)

    with TestClient(api.app, raise_server_exceptions=True) as client:
        yield client, Factory

    Base.metadata.drop_all(bind=engine)


def make_task(session, *, status: str = "scheduled", command: str = "echo ok") -> "models.TaskRequest":
    """Create and persist a minimal TaskRequest, returning the flushed instance."""
    from models import TaskRequest

    task = TaskRequest(
        description="test task",
        command=command,
        run_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status=status,
    )
    session.add(task)
    session.flush()
    return task
