from __future__ import annotations

import json
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select

from db import SessionLocal, init_db
from models import RecurringTask, TaskRequest
from tasks.celery_app import app
from tasks.notification_task import run_command_at


@app.task(name="tasks.recurring_task.check_recurring_tasks")
def check_recurring_tasks():
    """Beat task: fire any recurring tasks that are due, then advance next_run_at."""
    init_db()
    now_utc = datetime.utcnow()

    with SessionLocal() as session:
        due = session.execute(
            select(RecurringTask).where(
                RecurringTask.enabled == 1,
                RecurringTask.next_run_at <= now_utc,
            )
        ).scalars().all()

        for rt in due:
            _spawn_task(session, rt, now_utc)

        session.commit()


def _compute_next_run(cron: str, tz_name: str, from_dt: datetime) -> datetime:
    """Return the next UTC-naive datetime after from_dt for the given cron+tz."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    # Convert from_dt (UTC naive) to tz-aware for croniter
    from_aware = from_dt.replace(tzinfo=timezone.utc).astimezone(tz)
    it = croniter(cron, from_aware)
    next_local = it.get_next(datetime)
    # Return as UTC naive
    return next_local.astimezone(timezone.utc).replace(tzinfo=None)


def compute_initial_next_run(cron: str, tz_name: str) -> datetime:
    """Compute the first next_run_at for a newly created recurring task."""
    return _compute_next_run(cron, tz_name, datetime.utcnow())


def _spawn_task(session, rt: RecurringTask, now_utc: datetime) -> None:
    """Create a TaskRequest from a RecurringTask and schedule it immediately."""
    command = rt.command or ""
    if rt.action_name and not command:
        from models import Action
        action = session.execute(
            select(Action).where(Action.name == rt.action_name)
        ).scalar_one_or_none()
        if action is not None:
            command = action.command

    if not command:
        # No executable command — advance next_run_at and skip
        rt.last_run_at = now_utc
        rt.next_run_at = _compute_next_run(rt.cron, rt.timezone, now_utc)
        return

    task_request = TaskRequest(
        description=rt.description or rt.name,
        command=command,
        run_at=now_utc,
        status="scheduled",
        action_name=rt.action_name,
        cwd=rt.cwd,
        env_json=rt.env_json,
        notify_on_complete=rt.notify_on_complete,
        max_retries=rt.max_retries,
        retry_delay=rt.retry_delay,
        recurring_task_id=rt.id,
    )
    session.add(task_request)
    session.flush()   # get task_request.id

    # Commit the task row before dispatching to Celery. apply_async puts the
    # job on the broker immediately; if Celery picks it up before the outer
    # session.commit() the worker's session.get() returns None and the task
    # silently fails with {"error": "task_request_not_found"}.
    session.commit()

    result = run_command_at.apply_async(
        args=[task_request.id, command],
        eta=now_utc,
    )
    task_request.celery_task_id = result.id

    rt.last_run_at = now_utc
    rt.next_run_at = _compute_next_run(rt.cron, rt.timezone, now_utc)
