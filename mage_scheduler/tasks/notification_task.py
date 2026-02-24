from __future__ import annotations

import json
import os
import subprocess
from tasks.celery_app import app
from db import SessionLocal, init_db
from models import TaskRequest

@app.task
def run_command_at(task_request_id: int, command: str):
    init_db()

    with SessionLocal() as session:
        task_request = session.get(TaskRequest, task_request_id)
        if task_request is None:
            return {"error": "task_request_not_found"}
        task_request.status = "running"
        env_json = task_request.env_json
        cwd = task_request.cwd
        session.commit()

    env = os.environ.copy()
    if env_json:
        try:
            env.update(json.loads(env_json))
        except json.JSONDecodeError:
            pass

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )

    with SessionLocal() as session:
        task_request = session.get(TaskRequest, task_request_id)
        if task_request is not None:
            task_request.status = "success" if result.returncode == 0 else "failed"
            task_request.result = result.stdout.strip() if result.stdout else None
            task_request.error = result.stderr.strip() if result.stderr else None
            session.commit()

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
