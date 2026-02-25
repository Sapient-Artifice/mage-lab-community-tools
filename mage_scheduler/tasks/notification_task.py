from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from tasks.celery_app import app
from db import SessionLocal, init_db
from models import TaskRequest

ASK_ASSISTANT_ENDPOINT = "http://127.0.0.1:11115/ask_assistant"
NOTIFICATION_OUTPUT_MAX = 500
NOTIFICATION_ERROR_MAX = 300


def _send_completion_notification(task: TaskRequest, returncode: int) -> None:
    """POST a structured completion notice to ask_assistant. Never raises."""
    status_label = "SUCCESS" if returncode == 0 else "FAILED"
    action = task.action_name or "custom command"
    completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output_section = ""
    if task.result:
        snippet = task.result[-NOTIFICATION_OUTPUT_MAX:]
        prefix = "..." if len(task.result) > NOTIFICATION_OUTPUT_MAX else ""
        output_section += f"\nOutput:\n{prefix}{snippet}"
    if returncode != 0 and task.error:
        snippet = task.error[-NOTIFICATION_ERROR_MAX:]
        prefix = "..." if len(task.error) > NOTIFICATION_ERROR_MAX else ""
        output_section += f"\nError:\n{prefix}{snippet}"

    message = (
        f"[MAGE SCHEDULER — AUTOMATED TASK NOTIFICATION]\n"
        f"Task ID: {task.id} | Status: {status_label} | Action: {action}\n"
        f"Description: {task.description}\n"
        f"Completed: {completed_at} | Exit code: {returncode}"
        f"{output_section}"
    )

    payload = json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        ASK_ASSISTANT_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Notification failure must never affect task status


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
        notify = bool(task_request.notify_on_complete)
        action_name = task_request.action_name or "custom_command"
        description = task_request.description or ""
        session.commit()

    triggered_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    env = os.environ.copy()
    if env_json:
        try:
            env.update(json.loads(env_json))
        except json.JSONDecodeError:
            pass

    # Inject scheduler metadata so scripts like ask_assistant.py can build
    # a proper disclosure header without needing user-provided env vars.
    env["SCHEDULER_TASK_ID"] = str(task_request_id)
    env["SCHEDULER_TRIGGERED_AT"] = triggered_at
    env["SCHEDULER_ACTION_NAME"] = action_name
    env["SCHEDULER_DESCRIPTION"] = description

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
            max_retries = task_request.max_retries or 0
            retry_delay_secs = task_request.retry_delay or 60
            retry_count = task_request.retry_count or 0

            task_request.result = result.stdout.strip() if result.stdout else None
            task_request.error = result.stderr.strip() if result.stderr else None

            if result.returncode != 0 and retry_count < max_retries:
                task_request.retry_count = retry_count + 1
                task_request.status = "scheduled"
                session.commit()

                next_eta = datetime.now(timezone.utc) + timedelta(seconds=retry_delay_secs)
                new_celery_task = run_command_at.apply_async(
                    args=[task_request_id, command],
                    eta=next_eta,
                )
                task_request.celery_task_id = new_celery_task.id
                session.commit()
                return {
                    "retrying": True,
                    "attempt": retry_count + 1,
                    "max_retries": max_retries,
                }

            task_request.status = "success" if result.returncode == 0 else "failed"
            session.commit()

            if notify:
                _send_completion_notification(task_request, result.returncode)

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
