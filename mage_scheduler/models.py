from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, Text
from db import Base


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
