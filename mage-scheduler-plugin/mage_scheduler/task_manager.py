from __future__ import annotations

import json
from datetime import datetime, timezone

from db import SessionLocal, init_db
from models import TaskRequest
from dispatch import schedule_command


class TaskManager:
    def schedule_command(
        self,
        command: str,
        run_at: datetime,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> int:
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

            run_at_aware = run_at_utc.replace(tzinfo=timezone.utc)
            job_id = schedule_command(task_request.id, command, run_at_aware)
            task_request.job_id = job_id
            session.commit()

            return task_request.id


def _ensure_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return dt.replace(tzinfo=local_tz).astimezone(timezone.utc).replace(tzinfo=None)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
