"""
APScheduler singleton — replaces Celery + Redis as the scheduling engine.

All task dispatch goes through dispatch.py. This module owns the scheduler
instance lifecycle and registers the four periodic beat jobs.
"""
from __future__ import annotations

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    """Return the module-level scheduler instance, creating it if needed."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            executors={"default": ThreadPoolExecutor(10)},
            timezone="UTC",
            job_defaults={"misfire_grace_time": 300, "coalesce": True},
        )
    return _scheduler


def start_scheduler() -> BackgroundScheduler:
    """Start the scheduler and register all periodic beat jobs.

    Call once at application startup (from the FastAPI lifespan handler).
    Safe to call multiple times — checks if already running.
    """
    # Deferred imports to avoid circular dependency at module load time
    from jobs.recurring_check import check_recurring_tasks
    from jobs.dependency_check import check_waiting_tasks
    from jobs.cleanup import cleanup_old_tasks

    sched = get_scheduler()
    if sched.running:
        return sched

    sched.add_job(
        check_recurring_tasks,
        "interval",
        seconds=60,
        id="beat_recurring",
        replace_existing=True,
    )
    sched.add_job(
        check_waiting_tasks,
        "interval",
        seconds=60,
        id="beat_dependency",
        replace_existing=True,
    )
    sched.add_job(
        cleanup_old_tasks,
        "interval",
        seconds=86400,
        id="beat_cleanup",
        replace_existing=True,
    )
    sched.start()
    return sched


def stop_scheduler() -> None:
    """Gracefully stop the scheduler. Called from FastAPI shutdown handler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
