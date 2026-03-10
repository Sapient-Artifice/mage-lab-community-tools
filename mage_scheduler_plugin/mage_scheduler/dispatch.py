"""
Dispatch shim — thin wrapper around APScheduler that replaces
Celery's apply_async / AsyncResult.revoke interface.

All task scheduling and cancellation in api.py and task_manager.py
goes through these two functions.
"""
from __future__ import annotations

from datetime import datetime, timezone


def schedule_command(task_id: int, command: str, run_at: datetime) -> str:
    """Schedule run_command to execute at run_at (UTC). Returns APScheduler job ID."""
    from scheduler import get_scheduler
    from jobs.run_command import run_command

    run_at_utc = _to_utc_aware(run_at)
    sched = get_scheduler()
    job = sched.add_job(
        run_command,
        "date",
        run_date=run_at_utc,
        args=[task_id, command],
        misfire_grace_time=300,
    )
    return job.id


def cancel_command(job_id: str | None, terminate: bool = False) -> None:
    """Cancel a scheduled job by its APScheduler job ID.

    For jobs that are already running, this has no effect — the subprocess
    will run to completion but the DB status has already been set to
    'cancelled'. If terminate=True is requested for a running job, the
    cancellation is best-effort (the job may still complete).

    Silently ignores missing or already-completed jobs.
    """
    if not job_id:
        return
    from scheduler import get_scheduler

    sched = get_scheduler()
    try:
        sched.remove_job(job_id)
    except Exception:
        pass  # Job already ran or was removed — not an error


def _to_utc_aware(dt: datetime) -> datetime:
    """Ensure datetime is UTC-aware for APScheduler."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
