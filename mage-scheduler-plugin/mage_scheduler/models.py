from __future__ import annotations

from datetime import datetime
import json
from sqlalchemy import Column, DateTime, Integer, Text
from db import Base


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    command = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    default_cwd = Column(Text, nullable=True)
    allowed_env_json = Column(Text, nullable=True)
    allowed_command_dirs_json = Column(Text, nullable=True)
    allowed_cwd_dirs_json = Column(Text, nullable=True)
    max_retries = Column(Integer, default=0, nullable=False)
    retry_delay = Column(Integer, default=60, nullable=False)
    retain_result = Column(Integer, default=0, nullable=False)

    @property
    def allowed_env(self) -> list[str] | None:
        if not self.allowed_env_json:
            return None
        try:
            return json.loads(self.allowed_env_json)
        except json.JSONDecodeError:
            return None

    @property
    def allowed_command_dirs(self) -> list[str] | None:
        if not self.allowed_command_dirs_json:
            return None
        try:
            return json.loads(self.allowed_command_dirs_json)
        except json.JSONDecodeError:
            return None

    @property
    def allowed_cwd_dirs(self) -> list[str] | None:
        if not self.allowed_cwd_dirs_json:
            return None
        try:
            return json.loads(self.allowed_cwd_dirs_json)
        except json.JSONDecodeError:
            return None


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    allowed_command_dirs_json = Column(Text, nullable=True)
    allowed_cwd_dirs_json = Column(Text, nullable=True)
    cleanup_enabled = Column(Integer, default=0, nullable=False)
    task_retention_days = Column(Integer, default=30, nullable=False)

    @property
    def allowed_command_dirs(self) -> list[str] | None:
        if not self.allowed_command_dirs_json:
            return None
        try:
            return json.loads(self.allowed_command_dirs_json)
        except json.JSONDecodeError:
            return None

    @property
    def allowed_cwd_dirs(self) -> list[str] | None:
        if not self.allowed_cwd_dirs_json:
            return None
        try:
            return json.loads(self.allowed_cwd_dirs_json)
        except json.JSONDecodeError:
            return None


class TaskRequest(Base):
    __tablename__ = "task_requests"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    description = Column(Text, nullable=False)
    command = Column(Text, nullable=False)
    run_at = Column(DateTime, nullable=False)
    status = Column(Text, default="scheduled", nullable=False)
    job_id = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    intent_version = Column(Text, nullable=True)
    source = Column(Text, nullable=True)
    action_id = Column(Integer, nullable=True)
    action_name = Column(Text, nullable=True)
    cwd = Column(Text, nullable=True)
    env_json = Column(Text, nullable=True)
    notify_on_complete = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=0, nullable=False)
    retry_delay = Column(Integer, default=60, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    recurring_task_id = Column(Integer, nullable=True)
    retain_result = Column(Integer, default=0, nullable=False)

    @property
    def env_keys(self) -> list[str] | None:
        if not self.env_json:
            return None
        try:
            data = json.loads(self.env_json)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            return list(data.keys())
        return None


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    depends_on_task_id = Column(Integer, nullable=False, index=True)


class RecurringTask(Base):
    __tablename__ = "recurring_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    cron = Column(Text, nullable=False)
    timezone = Column(Text, nullable=False, default="UTC")
    action_name = Column(Text, nullable=True)
    command = Column(Text, nullable=True)
    cwd = Column(Text, nullable=True)
    env_json = Column(Text, nullable=True)
    notify_on_complete = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=0, nullable=False)
    retry_delay = Column(Integer, default=60, nullable=False)
    enabled = Column(Integer, default=1, nullable=False)
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    @property
    def env_keys(self) -> list[str] | None:
        if not self.env_json:
            return None
        try:
            data = json.loads(self.env_json)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            return list(data.keys())
        return None
