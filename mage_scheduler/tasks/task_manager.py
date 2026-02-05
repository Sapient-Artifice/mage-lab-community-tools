from __future__ import annotations

from datetime import datetime, timezone
import json
from celery.result import AsyncResult
from db import SessionLocal, init_db
from models import TaskRequest
from tasks.notification_task import run_command_at

class TaskManager:
    def schedule_command(
        self,
        command: str,
        run_at: datetime,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ):
        """Schedule the command to run at run_at datetime (UTC)."""
        init_db()
        run_at_utc = _ensure_utc_naive(run_at)

        with SessionLocal() as session:
            task_request = TaskRequest(
                description=command,
                command=command,
                run_at=run_at_utc,
                status="scheduled",
                cwd=cwd,
                env_json=json.dumps(env) if env else None,
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
