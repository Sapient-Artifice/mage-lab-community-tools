"""
cleanup — APScheduler beat job that deletes old terminal tasks.

Replaces tasks/cleanup_task.py. Identical business logic; Celery
decorator replaced with a plain function called by APScheduler interval job.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from db import SessionLocal, init_db
from models import Settings, TaskDependency, TaskRequest

_TERMINAL = {"success", "failed", "cancelled", "blocked"}


def _do_cleanup(session) -> int:
    """Core deletion logic — shared by beat job and manual API trigger."""
    settings = session.execute(select(Settings)).scalar_one_or_none()
    if not settings or not settings.cleanup_enabled:
        return 0

    retention_days = settings.task_retention_days or 30
    cutoff = datetime.utcnow() - timedelta(days=retention_days)

    candidates = session.execute(
        select(TaskRequest).where(
            TaskRequest.status.in_(list(_TERMINAL)),
            TaskRequest.created_at < cutoff,
            TaskRequest.retain_result == 0,
        )
    ).scalars().all()

    deleted = 0
    for task in candidates:
        downstream = session.execute(
            select(TaskDependency).where(TaskDependency.depends_on_task_id == task.id)
        ).scalars().all()
        if downstream:
            ids = [r.task_id for r in downstream]
            if session.execute(
                select(TaskRequest).where(
                    TaskRequest.id.in_(ids),
                    TaskRequest.created_at >= cutoff,
                )
            ).first():
                continue
        session.delete(task)
        deleted += 1

    session.commit()
    return deleted


def cleanup_old_tasks() -> dict:
    """Beat job: delete old terminal tasks based on retention settings."""
    init_db()
    with SessionLocal() as session:
        deleted = _do_cleanup(session)
    return {"deleted": deleted}
