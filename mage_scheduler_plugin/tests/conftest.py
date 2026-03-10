from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Point all DB writes at a throwaway temp path during tests
os.environ.setdefault("SCHEDULER_DATA_DIR", "/tmp/mage_scheduler_plugin_test")


@pytest.fixture(scope="function")
def db_session():
    """Provide a fresh in-memory SQLite session for each test."""
    from db import Base
    import models  # noqa: F401

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
    """In-memory DB with SessionLocal patched inside jobs.run_command."""
    from db import Base
    import models  # noqa: F401
    import jobs.run_command as rc

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(rc, "SessionLocal", Factory)

    yield Factory

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def dep_mem_db(monkeypatch):
    """In-memory DB with SessionLocal and init_db patched inside jobs.dependency_check."""
    from db import Base
    import models  # noqa: F401
    import jobs.dependency_check as dc

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(dc, "SessionLocal", Factory)
    monkeypatch.setattr(dc, "init_db", lambda: None)

    yield Factory

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def rec_mem_db(monkeypatch):
    """In-memory DB with SessionLocal and init_db patched inside jobs.recurring_check."""
    from db import Base
    import models  # noqa: F401
    import jobs.recurring_check as rct

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(rct, "SessionLocal", Factory)
    monkeypatch.setattr(rct, "init_db", lambda: None)

    yield Factory

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def cln_mem_db(monkeypatch):
    """In-memory DB with SessionLocal and init_db patched inside jobs.cleanup."""
    from db import Base
    import models  # noqa: F401
    import jobs.cleanup as ct

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


@pytest.fixture
def api_client(monkeypatch):
    """TestClient with a fully isolated in-memory DB.

    - Shares one StaticPool engine across api.SessionLocal and task_manager.SessionLocal
    - Mocks scheduler.start_scheduler / stop_scheduler (no APScheduler in tests)
    - Mocks dispatch.schedule_command (no real job dispatch)
    - Mocks api.cancel_command (no APScheduler job lookup)
    - Bypasses filesystem path validation

    Yields (TestClient, sessionmaker).
    """
    from sqlalchemy.pool import StaticPool
    from fastapi.testclient import TestClient
    from db import Base
    import models  # noqa: F401
    import api
    import task_manager as tm
    import scheduler
    import dispatch

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

    # Suppress APScheduler lifecycle in the FastAPI lifespan handler
    monkeypatch.setattr(scheduler, "start_scheduler", lambda: None)
    monkeypatch.setattr(scheduler, "stop_scheduler", lambda: None)

    # Bypass filesystem checks — not relevant to logic tests
    monkeypatch.setattr(api, "_validate_command", lambda *a, **kw: None)
    monkeypatch.setattr(api, "_validate_cwd", lambda *a, **kw: None)

    # Mock dispatch — no real APScheduler jobs during tests
    monkeypatch.setattr(tm, "schedule_command", lambda *a, **kw: "fake-job-id")
    monkeypatch.setattr(api, "cancel_command", lambda *a, **kw: None)

    with TestClient(api.app, raise_server_exceptions=True) as client:
        yield client, Factory

    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Shared row-creation helpers (not fixtures — import directly)
# ---------------------------------------------------------------------------

def make_task(
    session,
    *,
    status: str = "scheduled",
    command: str = "echo ok",
) -> "models.TaskRequest":
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


def make_action(
    session,
    *,
    name: str = "test_action",
    command: str = "echo ok",
    allowed_env_json: str | None = None,
    max_retries: int = 0,
    retry_delay: int = 60,
    default_cwd: str | None = None,
) -> "models.Action":
    from models import Action

    action = Action(
        name=name,
        command=command,
        allowed_env_json=allowed_env_json,
        max_retries=max_retries,
        retry_delay=retry_delay,
        default_cwd=default_cwd,
    )
    session.add(action)
    session.flush()
    return action


def make_recurring(
    session,
    *,
    name: str = "test_recurring",
    cron: str = "* * * * *",
    command: str = "echo ok",
    enabled: int = 1,
    timezone: str = "UTC",
) -> "models.RecurringTask":
    from models import RecurringTask

    rt = RecurringTask(
        name=name,
        cron=cron,
        command=command,
        timezone=timezone,
        enabled=enabled,
    )
    session.add(rt)
    session.flush()
    return rt
