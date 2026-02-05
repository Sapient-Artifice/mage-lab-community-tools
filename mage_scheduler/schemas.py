from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class TaskCreate(BaseModel):
    command: str
    run_at: datetime
    description: str | None = None


class TaskRead(BaseModel):
    id: int
    created_at: datetime
    description: str
    command: str
    run_at: datetime
    status: str
    celery_task_id: str | None = None
    result: str | None = None
    error: str | None = None

    class Config:
        from_attributes = True
