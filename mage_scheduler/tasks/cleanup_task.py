from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from db import SessionLocal, init_db
from models import Settings, TaskDependency, TaskRequest
from tasks.celery_app import app

_TERMINAL = {"success", "failed", "cancelled", "blocked"}


def _do_cleanup(session) -> int:
    """Core deletion logic — shared by beat task and manual trigger."""
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
        # Skip if any downstream task was created within the retention window
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


@app.task(name="tasks.cleanup_task.cleanup_old_tasks")
def cleanup_old_tasks():
    init_db()
    with SessionLocal() as session:
        deleted = _do_cleanup(session)
    return {"deleted": deleted}
