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
    celery_task_id = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    intent_version = Column(Text, nullable=True)
    source = Column(Text, nullable=True)
    action_id = Column(Integer, nullable=True)
    action_name = Column(Text, nullable=True)
    cwd = Column(Text, nullable=True)
    env_json = Column(Text, nullable=True)

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
