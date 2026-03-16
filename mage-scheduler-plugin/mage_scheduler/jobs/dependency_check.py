"""
dependency_check — APScheduler beat job that re-evaluates waiting tasks.

Replaces tasks/dependency_task.py. Identical business logic; Celery
decorator replaced with a plain function called by APScheduler interval job.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from db import SessionLocal, init_db
from models import TaskDependency, TaskRequest

_TERMINAL_BAD = {"failed", "cancelled", "blocked"}
_TERMINAL_GOOD = {"success"}


def check_waiting_tasks() -> None:
    """Beat job: re-evaluate all waiting tasks and unblock or cascade-fail them."""
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


def _schedule_waiting_task_beat(session, wt: TaskRequest) -> None:
    from dispatch import schedule_command

    now_utc = datetime.now(timezone.utc)
    run_at = wt.run_at
    if run_at is not None and run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    if run_at is None or run_at <= now_utc:
        run_at = now_utc

    wt.status = "scheduled"
    session.flush()
    job_id = schedule_command(wt.id, wt.command, run_at)
    wt.job_id = job_id
