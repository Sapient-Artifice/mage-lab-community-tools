from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from tasks.celery_app import app
from db import SessionLocal, init_db
from models import TaskDependency, TaskRequest

ASK_ASSISTANT_ENDPOINT = os.getenv("MAGE_ASK_ASSISTANT_URL", "http://127.0.0.1:11115/ask_assistant")
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

            final_status = "success" if result.returncode == 0 else "failed"
            task_request.status = final_status
            session.commit()

            _trigger_dependents(task_request_id, final_status)

            if notify and action_name != "ask_assistant":
                _send_completion_notification(task_request, result.returncode)

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

_TERMINAL_BAD = {"failed", "cancelled", "blocked"}
_TERMINAL_GOOD = {"success"}


def _trigger_dependents(completed_task_id: int, completed_status: str) -> None:
    """After a task reaches a terminal status, unblock or cascade-fail its dependents."""
    if completed_status not in ("success", "failed", "cancelled"):
        return
    from sqlalchemy import select  # noqa: PLC0415 — local import to avoid module-level cycle risk

    with SessionLocal() as session:
        dep_rows = session.execute(
            select(TaskDependency).where(TaskDependency.depends_on_task_id == completed_task_id)
        ).scalars().all()
        candidate_ids = [r.task_id for r in dep_rows]
        if not candidate_ids:
            return
        waiting = session.execute(
            select(TaskRequest).where(
                TaskRequest.id.in_(candidate_ids),
                TaskRequest.status == "waiting",
            )
        ).scalars().all()
        for wt in waiting:
            if completed_status in _TERMINAL_BAD:
                wt.status = "failed"
                wt.error = f"Dependency task {completed_task_id} failed or was cancelled."
            else:
                _try_unblock_task(session, wt)
        session.commit()


def _try_unblock_task(session, wt: TaskRequest) -> None:
    """Re-evaluate a waiting task: schedule it if all deps succeeded, fail if any dep failed."""
    from sqlalchemy import select  # noqa: PLC0415

    dep_rows = session.execute(
        select(TaskDependency).where(TaskDependency.task_id == wt.id)
    ).scalars().all()

    if not dep_rows:
        _schedule_waiting_task(session, wt)
        return

    dep_ids = [r.depends_on_task_id for r in dep_rows]
    dep_tasks = session.execute(
        select(TaskRequest).where(TaskRequest.id.in_(dep_ids))
    ).scalars().all()
    status_map = {t.id: t.status for t in dep_tasks}

    if any(status_map.get(i, "failed") in _TERMINAL_BAD for i in dep_ids):
        bad_id = next(i for i in dep_ids if status_map.get(i, "failed") in _TERMINAL_BAD)
        wt.status = "failed"
        wt.error = f"Dependency task {bad_id} failed or was cancelled."
    elif all(status_map.get(i, "") in _TERMINAL_GOOD for i in dep_ids):
        _schedule_waiting_task(session, wt)
    # else: still waiting — leave as-is


def _schedule_waiting_task(session, wt: TaskRequest) -> None:
    """Transition a waiting task to scheduled and dispatch its Celery job."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    run_at = wt.run_at if wt.run_at and wt.run_at > now_utc else now_utc
    wt.status = "scheduled"
    session.commit()  # commit before dispatch so Celery sees the updated row
    result = run_command_at.apply_async(args=[wt.id, wt.command], eta=run_at)
    wt.celery_task_id = result.id
