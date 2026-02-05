from __future__ import annotations

from datetime import datetime, timezone
from celery.result import AsyncResult
from db import SessionLocal, init_db
from models import TaskRequest
from tasks.notification_task import run_command_at

class TaskManager:
    def schedule_command(self, command: str, run_at: datetime):
        """Schedule the command to run at run_at datetime (UTC)."""
        init_db()
        run_at_utc = _ensure_utc_naive(run_at)

        with SessionLocal() as session:
            description = command
            task_request = TaskRequest(
                description=description,
                command=command,
                run_at=run_at_utc,
                status="scheduled",
            )
            session.add(task_request)
            session.commit()
            session.refresh(task_request)

            result = run_command_at.apply_async(
                args=[task_request.id, command],
                eta=run_at_utc,
            )
            task_request.celery_task_id = result.id
            session.commit()

            task_request_id = task_request.id

        return task_request_id

    def get_task_status(self, task_id: str):
        """Get the status and info for a scheduled task by task_id."""
        result = AsyncResult(task_id)
        return {
            "task_id": task_id,
            "state": result.state,
            "result": result.result if result.ready() else None
        }


def _ensure_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return dt.replace(tzinfo=local_tz).astimezone(timezone.utc).replace(tzinfo=None)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
