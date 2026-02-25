from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class TaskCreate(BaseModel):
    command: str
    run_at: datetime
    description: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    notify_on_complete: bool = False


class TaskRunNow(BaseModel):
    command: str
    description: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    notify_on_complete: bool = False


class ActionCreate(BaseModel):
    name: str
    description: str | None = None
    command: str
    default_cwd: str | None = None
    allowed_env: list[str] | None = None
    allowed_command_dirs: list[str] | None = None
    allowed_cwd_dirs: list[str] | None = None


class ActionRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    command: str
    created_at: datetime
    default_cwd: str | None = None
    allowed_env: list[str] | None = None
    allowed_command_dirs: list[str] | None = None
    allowed_cwd_dirs: list[str] | None = None

    class Config:
        from_attributes = True


class ActionUpdate(BaseModel):
    name: str
    description: str | None = None
    command: str
    default_cwd: str | None = None
    allowed_env: list[str] | None = None
    allowed_command_dirs: list[str] | None = None
    allowed_cwd_dirs: list[str] | None = None


class TaskIntent(BaseModel):
    description: str
    command: str | None = None
    run_at: datetime | None = None
    run_in: str | None = None
    timezone: str = "UTC"
    action_name: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    notify_on_complete: bool = False


class TaskIntentEnvelope(BaseModel):
    intent_version: str
    task: TaskIntent
    meta: dict | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    hint: str | None = None


class TaskIntentResponse(BaseModel):
    status: str
    task_id: int
    scheduled_at_local: str
    scheduled_at_utc: str
    command: str
    description: str
    action_name: str | None = None
    intent_version: str | None = None
    source: str | None = None
    cwd: str | None = None
    env_keys: list[str] | None = None
    notify_on_complete: bool = False
    warnings: list[str]
    errors: list[ErrorDetail] | None = None


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
    action_id: int | None = None
    action_name: str | None = None
    cwd: str | None = None
    env_keys: list[str] | None = None
    notify_on_complete: bool = False

    class Config:
        from_attributes = True
