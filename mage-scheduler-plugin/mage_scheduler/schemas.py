from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class ActionCreate(BaseModel):
    name: str
    description: str | None = None
    command: str
    default_cwd: str | None = None
    allowed_env: list[str] | None = None
    allowed_command_dirs: list[str] | None = None
    allowed_cwd_dirs: list[str] | None = None
    max_retries: int = 0
    retry_delay: int = 60
    retain_result: bool = False


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
    max_retries: int = 0
    retry_delay: int = 60
    retain_result: bool = False

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
    max_retries: int = 0
    retry_delay: int = 60
    retain_result: bool = False


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
    max_retries: int | None = None
    retry_delay: int | None = None
    cron: str | None = None
    depends_on: list[int] | None = None
    retain_result: bool = False


class TaskIntentEnvelope(BaseModel):
    intent_version: str
    task: TaskIntent
    meta: dict | None = None
    replace_existing: bool = False


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
    max_retries: int = 0
    retry_delay: int = 60
    warnings: list[str]
    errors: list[ErrorDetail] | None = None
    cron: str | None = None
    next_run_at: str | None = None
    depends_on: list[int] | None = None
    retain_result: bool = False
    replaced_task_ids: list[int] | None = None


class RecurringTaskCreate(BaseModel):
    name: str
    description: str | None = None
    cron: str
    timezone: str = "UTC"
    action_name: str | None = None
    command: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    notify_on_complete: bool = False
    max_retries: int = 0
    retry_delay: int = 60
    enabled: bool = True


class RecurringTaskUpdate(BaseModel):
    name: str
    description: str | None = None
    cron: str
    timezone: str = "UTC"
    action_name: str | None = None
    command: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    notify_on_complete: bool = False
    max_retries: int = 0
    retry_delay: int = 60
    enabled: bool = True


class RecurringTaskRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    cron: str
    timezone: str
    action_name: str | None = None
    command: str | None = None
    cwd: str | None = None
    env_keys: list[str] | None = None
    notify_on_complete: bool = False
    max_retries: int = 0
    retry_delay: int = 60
    enabled: bool = True
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    command: str
    run_at: datetime
    description: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    notify_on_complete: bool = False
    max_retries: int = 0
    retry_delay: int = 60
    retain_result: bool = False


class TaskRunNow(BaseModel):
    command: str
    description: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    notify_on_complete: bool = False
    max_retries: int = 0
    retry_delay: int = 60
    retain_result: bool = False


class TaskRead(BaseModel):
    id: int
    created_at: datetime
    description: str
    command: str
    run_at: datetime
    status: str
    job_id: str | None = None
    result: str | None = None
    error: str | None = None
    action_id: int | None = None
    action_name: str | None = None
    cwd: str | None = None
    env_keys: list[str] | None = None
    notify_on_complete: bool = False
    max_retries: int = 0
    retry_delay: int = 60
    retry_count: int = 0
    recurring_task_id: int | None = None
    depends_on: list[int] | None = None
    retain_result: bool = False

    class Config:
        from_attributes = True


class TaskDependencyRead(BaseModel):
    task_id: int
    depends_on: list[int]
    blocking: list[int]

    class Config:
        from_attributes = True
