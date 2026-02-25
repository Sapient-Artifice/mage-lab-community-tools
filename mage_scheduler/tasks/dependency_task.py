from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from db import SessionLocal, init_db
from models import TaskDependency, TaskRequest
from tasks.celery_app import app

_TERMINAL_BAD = {"failed", "cancelled", "blocked"}
_TERMINAL_GOOD = {"success"}


@app.task(name="tasks.dependency_task.check_waiting_tasks")
def check_waiting_tasks():
    """Beat task: re-evaluate all waiting tasks and unblock or cascade-fail them."""
    init_db()
    with SessionLocal() as session:
        waiting = session.execute(
            select(TaskRequest).where(TaskRequest.status == "waiting")
        ).scalars().all()
        for wt in waiting:
            _try_unblock_task_beat(session, wt)
        session.commit()


def _try_unblock_task_beat(session, wt: TaskRequest) -> None:
    dep_rows = session.execute(
        select(TaskDependency).where(TaskDependency.task_id == wt.id)
    ).scalars().all()

    if not dep_rows:
        # Orphaned waiting task — schedule it directly
        _schedule_waiting_task_beat(session, wt)
        return

    dep_ids = [r.depends_on_task_id for r in dep_rows]
    dep_tasks = session.execute(
        select(TaskRequest).where(TaskRequest.id.in_(dep_ids))
    ).scalars().all()
    status_map = {t.id: t.status for t in dep_tasks}

    if any(status_map.get(i, "failed") in _TERMINAL_BAD for i in dep_ids):
        bad_id = next(i for i in dep_ids if status_map.get(i, "failed") in _TERMINAL_BAD)
        wt.status = "failed"
        wt.error = f"Dependency task {bad_id} failed or was cancelled."
    elif all(status_map.get(i, "") in _TERMINAL_GOOD for i in dep_ids):
        _schedule_waiting_task_beat(session, wt)
    # else: still waiting — leave as-is


def _schedule_waiting_task_beat(session, wt: TaskRequest) -> None:
    # Deferred import to break circular: celery_app → dependency_task → notification_task → celery_app
    from tasks.notification_task import run_command_at  # noqa: PLC0415

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    run_at = wt.run_at if wt.run_at and wt.run_at > now_utc else now_utc
    wt.status = "scheduled"
    session.flush()
    result = run_command_at.apply_async(args=[wt.id, wt.command], eta=run_at)
    wt.celery_task_id = result.id
