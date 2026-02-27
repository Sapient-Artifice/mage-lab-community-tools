from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import re
import shlex
import time
from zoneinfo import ZoneInfo
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse
from celery.result import AsyncResult
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from croniter import croniter

from db import SessionLocal, init_db
from models import Action, RecurringTask, Settings, TaskDependency, TaskRequest
from schemas import (
    ActionCreate,
    ActionRead,
    ActionUpdate,
    RecurringTaskCreate,
    RecurringTaskRead,
    RecurringTaskUpdate,
    TaskCreate,
    TaskDependencyRead,
    TaskRead,
    TaskIntentEnvelope,
    TaskIntentResponse,
    TaskRunNow,
)
from tasks.task_manager import TaskManager
from tasks.celery_app import app as celery_app
from tasks.recurring_task import compute_initial_next_run
from nl_parser import parse_request

app = FastAPI(title="Mage Scheduler")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["local_time"] = lambda dt: _to_local_time(dt)
START_TIME = time.time()
INTENT_VERSION_ALIASES = {
    "v1": "v1",
    "1": "v1",
    "1.0": "v1",
}
INTENT_ERROR_MESSAGES = {
    "unsupported_intent_version": "Unsupported intent_version.",
    "invalid_timezone": "Invalid timezone.",
    "unknown_action": "Unknown action_name.",
    "command_or_action_required": "Command or action_name is required.",
    "env_requires_action": "Environment variables require an action_name.",
    "env_not_allowed": "Environment variables are not allowed for this action.",
    "env_key_not_allowed": "One or more env keys are not allowed for this action.",
    "command_required": "Command is required.",
    "command_invalid": "Command is invalid.",
    "command_must_be_absolute": "Command must be an absolute path.",
    "command_not_found": "Command executable not found.",
    "command_not_executable": "Command is not executable.",
    "command_dir_not_allowed": "Command is outside allowed directories.",
    "cwd_must_be_absolute": "cwd must be an absolute path.",
    "cwd_not_found": "cwd does not exist.",
    "cwd_dir_not_allowed": "cwd is outside allowed directories.",
    "run_in_invalid": "run_in value is not a valid duration.",
    "run_at_or_run_in_required": "Either run_at or run_in is required.",
    "cron_invalid": "cron expression is invalid.",
    "cron_and_run_at_exclusive": "cron and run_at/run_in are mutually exclusive.",
    "recurring_name_required": "description is used as the recurring task name and must be unique.",
    "recurring_name_exists": "A recurring task with this name already exists.",
    "depends_on_invalid": "depends_on contains invalid task IDs.",
    "depends_on_already_failed": "One or more dependencies have already failed or been cancelled.",
    "depends_on_cron_unsupported": "depends_on is not supported for recurring (cron) tasks.",
}
INTENT_ERROR_HINTS = {
    "unsupported_intent_version": "intent_version must be 'v1' (aliases: '1', '1.0').",
    "invalid_timezone": "Use an IANA timezone like 'America/Los_Angeles'.",
    "unknown_action": "Create the action first or provide a command.",
    "command_or_action_required": "Provide either action_name or command.",
    "env_requires_action": "Move env under an action_name allowlist.",
    "env_not_allowed": "Remove env or update the action allowlist.",
    "env_key_not_allowed": "Remove disallowed keys or update the action allowlist.",
    "command_required": "Provide an absolute command path.",
    "command_invalid": "Provide a valid command string.",
    "command_must_be_absolute": "Use an absolute path like /usr/local/bin/tool.",
    "command_not_found": "Verify the command path exists on the host.",
    "command_not_executable": "Ensure the command has execute permissions.",
    "command_dir_not_allowed": "Move the command under an allowed directory.",
    "cwd_must_be_absolute": "Use an absolute path like /var/tmp.",
    "cwd_not_found": "Ensure the cwd exists on the host.",
    "cwd_dir_not_allowed": "Move cwd under an allowed directory.",
    "run_in_invalid": "Use a duration like '30m', '2h', '1d', or '90s'.",
    "run_at_or_run_in_required": "Provide run_at (datetime) or run_in (duration string).",
    "cron_invalid": "Use a 5-field cron like '0 9 * * 1' (Mon 9am).",
    "cron_and_run_at_exclusive": "Remove run_at/run_in when using cron.",
    "recurring_name_required": "Provide a unique description to name the recurring task.",
    "recurring_name_exists": "Choose a different description/name.",
    "depends_on_invalid": "Each ID in depends_on must be an existing task_id integer.",
    "depends_on_already_failed": "Check dependency task statuses before scheduling.",
    "depends_on_cron_unsupported": "Recurring tasks run indefinitely; dependency semantics do not apply.",
}


_RUN_IN_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(s|sec|secs|seconds?|m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)$",
    re.IGNORECASE,
)
_RUN_IN_MULTIPLIERS: dict[str, float] = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}


def _parse_run_in(run_in: str) -> timedelta | None:
    """Parse '30m', '2h', '1d', '90s' etc. into a timedelta. Returns None on failure."""
    m = _RUN_IN_PATTERN.match(run_in.strip())
    if not m:
        return None
    seconds = float(m.group(1)) * _RUN_IN_MULTIPLIERS.get(m.group(2).lower(), 0)
    if seconds <= 0:
        return None
    return timedelta(seconds=seconds)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _to_local_time(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_tz = datetime.now().astimezone().tzinfo
    return dt.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_intent_version(value: str) -> tuple[str | None, list[str]]:
    normalized = INTENT_VERSION_ALIASES.get(value)
    if normalized is None:
        return None, ["unsupported_intent_version"]
    return normalized, []


def _intent_error(code: str) -> dict:
    message = INTENT_ERROR_MESSAGES.get(code, code)
    hint = INTENT_ERROR_HINTS.get(code)
    payload = {"code": code, "message": message}
    if hint:
        payload["hint"] = hint
    return payload


def _raise_intent_validation(errors: list[str]) -> None:
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"errors": [_intent_error(code) for code in errors]},
        )


def _parse_allowed_env(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = []
    for piece in value.replace("\n", ",").split(","):
        item = piece.strip()
        if item:
            parts.append(item)
    return parts or None


def _parse_allowed_dirs(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = []
    for piece in value.replace("\n", ",").split(","):
        item = piece.strip()
        if item:
            parts.append(item)
    return parts or None


def _get_settings(session: Session) -> Settings:
    settings = session.execute(select(Settings)).scalar_one_or_none()
    if settings is None:
        settings = Settings()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def _validate_command(command: str, allowed_dirs: list[str] | None = None) -> None:
    if not command:
        raise HTTPException(status_code=400, detail="command_required")
    try:
        tokens = shlex.split(command)
    except ValueError:
        raise HTTPException(status_code=400, detail="command_invalid")
    if not tokens:
        raise HTTPException(status_code=400, detail="command_invalid")
    executable = tokens[0]
    if not os.path.isabs(executable):
        raise HTTPException(status_code=400, detail="command_must_be_absolute")
    if not os.path.exists(executable):
        raise HTTPException(status_code=400, detail="command_not_found")
    if not os.access(executable, os.X_OK):
        raise HTTPException(status_code=400, detail="command_not_executable")
    if allowed_dirs:
        if not _is_path_allowed(executable, allowed_dirs):
            raise HTTPException(status_code=400, detail="command_dir_not_allowed")


def _get_executable(command: str) -> str:
    try:
        tokens = shlex.split(command)
    except ValueError:
        raise HTTPException(status_code=400, detail="command_invalid")
    if not tokens:
        raise HTTPException(status_code=400, detail="command_invalid")
    return tokens[0]


def _validate_cwd(cwd: str | None, allowed_dirs: list[str] | None = None) -> None:
    if not cwd:
        return
    if not os.path.isabs(cwd):
        raise HTTPException(status_code=400, detail="cwd_must_be_absolute")
    if not os.path.isdir(cwd):
        raise HTTPException(status_code=400, detail="cwd_not_found")
    if allowed_dirs:
        if not _is_path_allowed(cwd, allowed_dirs):
            raise HTTPException(status_code=400, detail="cwd_dir_not_allowed")


def _create_blocked_task(
    db: Session,
    description: str,
    command: str,
    error_detail: str,
) -> TaskRequest:
    task = TaskRequest(
        description=description,
        command=command,
        run_at=datetime.utcnow(),
        status="blocked",
        error=error_detail,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _is_path_allowed(path: str, allowed_dirs: list[str]) -> bool:
    normalized = os.path.realpath(path)
    for base in allowed_dirs:
        base_path = os.path.realpath(base)
        if normalized == base_path or normalized.startswith(base_path + os.sep):
            return True
    return False


def _validate_cron(expr: str) -> bool:
    return croniter.is_valid(expr)


_DEP_TERMINAL_BAD = {"failed", "cancelled", "blocked"}
_DEP_TERMINAL_GOOD = {"success"}


def _validate_depends_on(
    session: Session,
    dep_ids: list[int],
) -> tuple[list[str], str]:
    """Validate dependency IDs and determine the scheduling outcome.

    Returns (errors, outcome) where outcome is one of:
      "immediate_schedule" — all deps succeeded (or list is empty)
      "waiting"            — at least one dep still in-flight
      "immediate_fail"     — at least one dep already failed/cancelled/blocked
    """
    if not dep_ids:
        return [], "immediate_schedule"

    dep_tasks = session.execute(
        select(TaskRequest).where(TaskRequest.id.in_(dep_ids))
    ).scalars().all()
    found_ids = {t.id for t in dep_tasks}
    missing = [i for i in dep_ids if i not in found_ids]
    if missing:
        return ["depends_on_invalid"], "immediate_fail"

    status_map = {t.id: t.status for t in dep_tasks}

    if any(status_map[i] in _DEP_TERMINAL_BAD for i in dep_ids):
        return [], "immediate_fail"

    if all(status_map[i] in _DEP_TERMINAL_GOOD for i in dep_ids):
        return [], "immediate_schedule"

    return [], "waiting"


def _cascade_fail_dependents(db: Session, task_id: int, reason: str) -> None:
    """Mark all waiting tasks that depend on task_id as failed."""
    dep_rows = db.execute(
        select(TaskDependency).where(TaskDependency.depends_on_task_id == task_id)
    ).scalars().all()
    candidate_ids = [r.task_id for r in dep_rows]
    if not candidate_ids:
        return
    waiting = db.execute(
        select(TaskRequest).where(
            TaskRequest.id.in_(candidate_ids),
            TaskRequest.status == "waiting",
        )
    ).scalars().all()
    for wt in waiting:
        wt.status = "failed"
        wt.error = reason


def _validate_dirs_list(dirs_list: list[str] | None, error_code: str) -> None:
    if not dirs_list:
        return
    for item in dirs_list:
        if not os.path.isabs(item):
            raise HTTPException(status_code=400, detail=error_code)
        if not os.path.isdir(item):
            raise HTTPException(status_code=400, detail=error_code)


def _validate_action_payload(
    payload: ActionCreate | ActionUpdate,
    settings: Settings,
) -> tuple[list[str] | None, list[str] | None]:
    allowed_command_dirs = payload.allowed_command_dirs
    allowed_cwd_dirs = payload.allowed_cwd_dirs
    _validate_dirs_list(allowed_command_dirs, "action_command_dirs_invalid")
    _validate_dirs_list(allowed_cwd_dirs, "action_cwd_dirs_invalid")
    _validate_command(payload.command, settings.allowed_command_dirs)
    _validate_cwd(payload.default_cwd, settings.allowed_cwd_dirs)
    if allowed_command_dirs:
        if settings.allowed_command_dirs:
            for item in allowed_command_dirs:
                if not _is_path_allowed(item, settings.allowed_command_dirs):
                    raise HTTPException(status_code=400, detail="action_command_dir_outside_settings")
        executable = _get_executable(payload.command)
        if not _is_path_allowed(executable, allowed_command_dirs):
            raise HTTPException(status_code=400, detail="action_command_dir_mismatch")
    if allowed_cwd_dirs:
        if settings.allowed_cwd_dirs:
            for item in allowed_cwd_dirs:
                if not _is_path_allowed(item, settings.allowed_cwd_dirs):
                    raise HTTPException(status_code=400, detail="action_cwd_dir_outside_settings")
        if payload.default_cwd and not _is_path_allowed(payload.default_cwd, allowed_cwd_dirs):
            raise HTTPException(status_code=400, detail="action_cwd_dir_mismatch")
    return allowed_command_dirs, allowed_cwd_dirs


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    tasks = db.execute(
        select(TaskRequest).order_by(TaskRequest.created_at.desc()).limit(100)
    ).scalars().all()
    actions = db.execute(select(Action).order_by(Action.name.asc())).scalars().all()
    recent_results = db.execute(
        select(TaskRequest)
        .where(TaskRequest.status.in_(["success", "failed"]))
        .order_by(TaskRequest.created_at.desc())
        .limit(5)
    ).scalars().all()
    blocked_tasks = db.execute(
        select(TaskRequest)
        .where(TaskRequest.status == "blocked")
        .order_by(TaskRequest.created_at.desc())
        .limit(5)
    ).scalars().all()
    waiting_tasks = db.execute(
        select(TaskRequest)
        .where(TaskRequest.status == "waiting")
        .order_by(TaskRequest.created_at.desc())
        .limit(10)
    ).scalars().all()
    recurring_tasks = db.execute(
        select(RecurringTask).order_by(RecurringTask.name.asc())
    ).scalars().all()
    settings = _get_settings(db)
    return templates.TemplateResponse(
        "tasks.html",
        {
            "request": request,
            "tasks": tasks,
            "actions": actions,
            "recent_results": recent_results,
            "blocked_tasks": blocked_tasks,
            "waiting_tasks": waiting_tasks,
            "recurring_tasks": recurring_tasks,
            "cleanup_enabled": bool(settings.cleanup_enabled),
            "retention_days": settings.task_retention_days or 30,
        },
    )


@app.post("/tasks")
def create_task_form(
    command: str | None = Form(None),
    run_at: datetime = Form(...),
    description: str | None = Form(None),
    action_id: int | None = Form(None),
):
    action_name = None
    action_cwd = None
    allowed_command_dirs = None
    allowed_cwd_dirs = None
    if action_id:
        with SessionLocal() as session:
            action = session.get(Action, action_id)
            if action is None:
                raise HTTPException(status_code=400, detail="Invalid action")
            settings = _get_settings(session)
            allowed_command_dirs = action.allowed_command_dirs or settings.allowed_command_dirs
            allowed_cwd_dirs = action.allowed_cwd_dirs or settings.allowed_cwd_dirs
            _validate_command(action.command, allowed_command_dirs)
            command = action.command
            action_name = action.name
            action_cwd = action.default_cwd
            if not description:
                description = action.description or action.name
    elif not command:
        raise HTTPException(status_code=400, detail="Command or action is required")
    else:
        with SessionLocal() as session:
            settings = _get_settings(session)
            allowed_command_dirs = settings.allowed_command_dirs
        _validate_command(command, allowed_command_dirs)

    _validate_cwd(action_cwd, allowed_cwd_dirs)
    manager = TaskManager()
    task_id = manager.schedule_command(command, run_at, cwd=action_cwd)

    with SessionLocal() as session:
        task = session.get(TaskRequest, task_id)
        if task is not None:
            if description:
                task.description = description
            task.action_id = action_id
            task.action_name = action_name
            task.cwd = action_cwd
            session.commit()

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(task_id: int, request: Request, db: Session = Depends(get_db)):
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return templates.TemplateResponse("task_detail.html", {"request": request, "task": task})


@app.post("/tasks/{task_id}/delete")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.celery_task_id:
        AsyncResult(task.celery_task_id, app=celery_app).revoke(terminate=False)

    db.delete(task)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("scheduled", "running", "waiting"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task with status '{task.status}'",
        )
    if task.celery_task_id:
        AsyncResult(task.celery_task_id, app=celery_app).revoke(terminate=True)
    task.status = "cancelled"
    db.commit()
    _cascade_fail_dependents(db, task_id, f"Dependency task {task_id} failed or was cancelled.")
    db.commit()
    return {"status": "cancelled", "task_id": task_id}


@app.post("/api/parse")
def parse_nl_request(payload: dict):
    text = str(payload.get("text", "")).strip()
    try:
        parsed = parse_request(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_at_local = parsed.run_at.strftime("%Y-%m-%dT%H:%M")
    run_at_iso = parsed.run_at.isoformat()
    return {
        "command": parsed.command,
        "run_at_local": run_at_local,
        "run_at_iso": run_at_iso,
        "description": text,
        "confidence": parsed.confidence,
        "interpretation": parsed.interpretation,
        "warnings": parsed.warnings,
    }


@app.get("/api/tasks", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    return db.execute(select(TaskRequest).order_by(TaskRequest.created_at.desc())).scalars().all()


@app.get("/api/tasks/stats")
def task_stats(db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import func
    rows = db.execute(
        select(TaskRequest.status, func.count(TaskRequest.id))
        .group_by(TaskRequest.status)
    ).all()
    counts = {status: count for status, count in rows}
    return {"total": sum(counts.values()), "by_status": counts}


@app.get("/api/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/api/tasks/{task_id}/dependencies", response_model=TaskDependencyRead)
def get_task_dependencies(task_id: int, db: Session = Depends(get_db)):
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    upstream = db.execute(
        select(TaskDependency).where(TaskDependency.task_id == task_id)
    ).scalars().all()
    downstream = db.execute(
        select(TaskDependency).where(TaskDependency.depends_on_task_id == task_id)
    ).scalars().all()
    downstream_ids = [r.task_id for r in downstream]
    if downstream_ids:
        blocking_tasks = db.execute(
            select(TaskRequest).where(
                TaskRequest.id.in_(downstream_ids),
                TaskRequest.status == "waiting",
            )
        ).scalars().all()
        blocking_ids = [t.id for t in blocking_tasks]
    else:
        blocking_ids = []
    return TaskDependencyRead(
        task_id=task_id,
        depends_on=[r.depends_on_task_id for r in upstream],
        blocking=blocking_ids,
    )


@app.get("/api/validation")
def validation_info(db: Session = Depends(get_db)) -> dict:
    settings = _get_settings(db)
    return {
        "allowed_command_dirs": settings.allowed_command_dirs or [],
        "allowed_cwd_dirs": settings.allowed_cwd_dirs or [],
        "rules": [
            "command_must_be_absolute",
            "command_must_exist",
            "command_must_be_executable",
            "command_dir_must_be_allowed",
            "cwd_must_be_absolute_if_provided",
            "cwd_must_exist_if_provided",
            "cwd_dir_must_be_allowed",
            "env_requires_action",
            "env_keys_must_be_allowed",
            "action_allowed_dirs_must_be_within_settings",
        ],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME)}


@app.get("/health/worker")
def worker_health() -> dict:
    try:
        replies = celery_app.control.ping(timeout=1.0) or []
        alive = bool(replies)
    except Exception:
        alive = False
    return {"worker_alive": alive}


@app.post("/api/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    settings = _get_settings(db)
    try:
        _validate_command(payload.command, settings.allowed_command_dirs)
        _validate_cwd(payload.cwd, settings.allowed_cwd_dirs)
    except HTTPException as exc:
        blocked = _create_blocked_task(
            db,
            payload.description or payload.command,
            payload.command,
            str(exc.detail),
        )
        return blocked
    manager = TaskManager()
    task_id = manager.schedule_command(
        payload.command,
        payload.run_at,
        cwd=payload.cwd,
        env=payload.env,
    )
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=500, detail="Failed to create task")
    if payload.description:
        task.description = payload.description
    task.cwd = payload.cwd
    task.env_json = json.dumps(payload.env) if payload.env else None
    task.notify_on_complete = 1 if payload.notify_on_complete else 0
    task.max_retries = max(0, payload.max_retries)
    task.retry_delay = max(1, payload.retry_delay)
    task.retain_result = 1 if payload.retain_result else 0
    db.commit()
    db.refresh(task)
    return task


@app.post("/api/tasks/run_now", response_model=TaskRead)
def run_task_now(payload: TaskRunNow, db: Session = Depends(get_db)):
    settings = _get_settings(db)
    try:
        _validate_command(payload.command, settings.allowed_command_dirs)
        _validate_cwd(payload.cwd, settings.allowed_cwd_dirs)
    except HTTPException as exc:
        blocked = _create_blocked_task(
            db,
            payload.description or payload.command,
            payload.command,
            str(exc.detail),
        )
        return blocked
    manager = TaskManager()
    task_id = manager.schedule_command(
        payload.command,
        datetime.now(),
        cwd=payload.cwd,
        env=payload.env,
    )
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=500, detail="Failed to create task")
    if payload.description:
        task.description = payload.description
    task.cwd = payload.cwd
    task.env_json = json.dumps(payload.env) if payload.env else None
    task.notify_on_complete = 1 if payload.notify_on_complete else 0
    task.max_retries = max(0, payload.max_retries)
    task.retry_delay = max(1, payload.retry_delay)
    task.retain_result = 1 if payload.retain_result else 0
    db.commit()
    db.refresh(task)
    return task


@app.get("/actions", response_class=HTMLResponse)
def actions_dashboard(request: Request, db: Session = Depends(get_db)):
    actions = db.execute(select(Action).order_by(Action.name.asc())).scalars().all()
    return templates.TemplateResponse("actions.html", {"request": request, "actions": actions})


@app.get("/settings", response_class=HTMLResponse)
def settings_dashboard(request: Request, db: Session = Depends(get_db)):
    settings = _get_settings(db)
    return templates.TemplateResponse("settings.html", {"request": request, "settings": settings})


@app.post("/settings")
def settings_update(
    request: Request,
    allowed_command_dirs: str | None = Form(None),
    allowed_cwd_dirs: str | None = Form(None),
    cleanup_enabled: str | None = Form(None),
    task_retention_days: int | None = Form(None),
):
    allowed_command_dirs_list = _parse_allowed_dirs(allowed_command_dirs)
    allowed_cwd_dirs_list = _parse_allowed_dirs(allowed_cwd_dirs)
    try:
        _validate_dirs_list(allowed_command_dirs_list, "settings_command_dirs_invalid")
        _validate_dirs_list(allowed_cwd_dirs_list, "settings_cwd_dirs_invalid")
    except HTTPException as exc:
        with SessionLocal() as session:
            settings = _get_settings(session)
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "settings": settings,
                "error": exc.detail,
                "form": {
                    "allowed_command_dirs": allowed_command_dirs or "",
                    "allowed_cwd_dirs": allowed_cwd_dirs or "",
                    "cleanup_enabled": cleanup_enabled or "",
                },
            },
            status_code=400,
        )
    with SessionLocal() as session:
        settings = _get_settings(session)
        settings.allowed_command_dirs_json = (
            json.dumps(allowed_command_dirs_list) if allowed_command_dirs_list else None
        )
        settings.allowed_cwd_dirs_json = (
            json.dumps(allowed_cwd_dirs_list) if allowed_cwd_dirs_list else None
        )
        settings.cleanup_enabled = 1 if cleanup_enabled == "1" else 0
        if task_retention_days is not None:
            settings.task_retention_days = max(1, task_retention_days)
        session.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/actions/new", response_class=HTMLResponse)
def actions_new(request: Request):
    return templates.TemplateResponse("action_form.html", {"request": request})


@app.post("/actions/new")
def actions_create(
    request: Request,
    name: str = Form(...),
    command: str = Form(...),
    description: str | None = Form(None),
    default_cwd: str | None = Form(None),
    allowed_env: str | None = Form(None),
    allowed_command_dirs: str | None = Form(None),
    allowed_cwd_dirs: str | None = Form(None),
    max_retries: int = Form(0),
    retry_delay: int = Form(60),
):
    allowed_command_dirs_list = _parse_allowed_dirs(allowed_command_dirs)
    allowed_cwd_dirs_list = _parse_allowed_dirs(allowed_cwd_dirs)
    with SessionLocal() as session:
        settings = _get_settings(session)
        try:
            _validate_action_payload(
                ActionCreate(
                    name=name,
                    description=description,
                    command=command,
                    default_cwd=default_cwd,
                    allowed_env=_parse_allowed_env(allowed_env),
                    allowed_command_dirs=allowed_command_dirs_list,
                    allowed_cwd_dirs=allowed_cwd_dirs_list,
                ),
                settings,
            )
        except HTTPException as exc:
            return templates.TemplateResponse(
                "action_form.html",
                {
                    "request": request,
                    "error": exc.detail,
                    "form": {
                        "name": name,
                        "description": description or "",
                        "command": command,
                        "default_cwd": default_cwd or "",
                        "allowed_env": allowed_env or "",
                        "allowed_command_dirs": allowed_command_dirs or "",
                        "allowed_cwd_dirs": allowed_cwd_dirs or "",
                    },
                },
                status_code=400,
            )
    allowed_env_list = _parse_allowed_env(allowed_env)
    with SessionLocal() as session:
        existing = session.execute(select(Action).where(Action.name == name)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Action name already exists")
        action = Action(
            name=name,
            command=command,
            description=description,
            default_cwd=default_cwd,
            allowed_env_json=json.dumps(allowed_env_list) if allowed_env_list else None,
            allowed_command_dirs_json=(
                json.dumps(allowed_command_dirs_list) if allowed_command_dirs_list else None
            ),
            allowed_cwd_dirs_json=json.dumps(allowed_cwd_dirs_list) if allowed_cwd_dirs_list else None,
            max_retries=max(0, max_retries),
            retry_delay=max(1, retry_delay),
        )
        session.add(action)
        session.commit()
    return RedirectResponse(url="/actions", status_code=303)


@app.post("/actions/{action_id}/delete")
def actions_delete(action_id: int):
    with SessionLocal() as session:
        action = session.get(Action, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="Action not found")
        session.delete(action)
        session.commit()
    return RedirectResponse(url="/actions", status_code=303)


@app.get("/actions/{action_id}/edit", response_class=HTMLResponse)
def actions_edit(action_id: int, request: Request):
    with SessionLocal() as session:
        action = session.get(Action, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="Action not found")
        return templates.TemplateResponse("action_edit.html", {"request": request, "action": action})


@app.post("/actions/{action_id}/edit")
def actions_update(
    request: Request,
    action_id: int,
    name: str = Form(...),
    command: str = Form(...),
    description: str | None = Form(None),
    default_cwd: str | None = Form(None),
    allowed_env: str | None = Form(None),
    allowed_command_dirs: str | None = Form(None),
    allowed_cwd_dirs: str | None = Form(None),
    max_retries: int = Form(0),
    retry_delay: int = Form(60),
):
    allowed_command_dirs_list = _parse_allowed_dirs(allowed_command_dirs)
    allowed_cwd_dirs_list = _parse_allowed_dirs(allowed_cwd_dirs)
    with SessionLocal() as session:
        action = session.get(Action, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="Action not found")
        settings = _get_settings(session)
        try:
            _validate_action_payload(
                ActionUpdate(
                    name=name,
                    description=description,
                    command=command,
                    default_cwd=default_cwd,
                    allowed_env=_parse_allowed_env(allowed_env),
                    allowed_command_dirs=allowed_command_dirs_list,
                    allowed_cwd_dirs=allowed_cwd_dirs_list,
                ),
                settings,
            )
            existing = session.execute(
                select(Action).where(Action.name == name, Action.id != action_id)
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(status_code=400, detail="action_name_exists")
        except HTTPException as exc:
            return templates.TemplateResponse(
                "action_edit.html",
                {
                    "request": request,
                    "action": action,
                    "error": exc.detail,
                    "form": {
                        "name": name,
                        "description": description or "",
                        "command": command,
                        "default_cwd": default_cwd or "",
                        "allowed_env": allowed_env or "",
                        "allowed_command_dirs": allowed_command_dirs or "",
                        "allowed_cwd_dirs": allowed_cwd_dirs or "",
                    },
                },
                status_code=400,
            )
        allowed_env_list = _parse_allowed_env(allowed_env)
        action.name = name
        action.command = command
        action.description = description
        action.default_cwd = default_cwd
        action.allowed_env_json = json.dumps(allowed_env_list) if allowed_env_list else None
        action.allowed_command_dirs_json = (
            json.dumps(allowed_command_dirs_list) if allowed_command_dirs_list else None
        )
        action.allowed_cwd_dirs_json = (
            json.dumps(allowed_cwd_dirs_list) if allowed_cwd_dirs_list else None
        )
        action.max_retries = max(0, max_retries)
        action.retry_delay = max(1, retry_delay)
        session.commit()
    return RedirectResponse(url="/actions", status_code=303)


@app.get("/api/actions", response_model=list[ActionRead])
def list_actions(db: Session = Depends(get_db)):
    return db.execute(select(Action).order_by(Action.name.asc())).scalars().all()


@app.post("/api/actions", response_model=ActionRead)
def create_action(payload: ActionCreate, db: Session = Depends(get_db)):
    settings = _get_settings(db)
    _validate_action_payload(payload, settings)
    existing = db.execute(select(Action).where(Action.name == payload.name)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="action_name_exists")
    action = Action(
        name=payload.name,
        command=payload.command,
        description=payload.description,
        default_cwd=payload.default_cwd,
        allowed_env_json=json.dumps(payload.allowed_env) if payload.allowed_env else None,
        allowed_command_dirs_json=(
            json.dumps(payload.allowed_command_dirs) if payload.allowed_command_dirs else None
        ),
        allowed_cwd_dirs_json=(
            json.dumps(payload.allowed_cwd_dirs) if payload.allowed_cwd_dirs else None
        ),
        max_retries=max(0, payload.max_retries),
        retry_delay=max(1, payload.retry_delay),
        retain_result=1 if payload.retain_result else 0,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@app.put("/api/actions/{action_id}", response_model=ActionRead)
def update_action(action_id: int, payload: ActionUpdate, db: Session = Depends(get_db)):
    action = db.get(Action, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action_not_found")
    settings = _get_settings(db)
    _validate_action_payload(payload, settings)
    existing = db.execute(
        select(Action).where(Action.name == payload.name, Action.id != action_id)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="action_name_exists")
    action.name = payload.name
    action.command = payload.command
    action.description = payload.description
    action.default_cwd = payload.default_cwd
    action.allowed_env_json = json.dumps(payload.allowed_env) if payload.allowed_env else None
    action.allowed_command_dirs_json = (
        json.dumps(payload.allowed_command_dirs) if payload.allowed_command_dirs else None
    )
    action.allowed_cwd_dirs_json = (
        json.dumps(payload.allowed_cwd_dirs) if payload.allowed_cwd_dirs else None
    )
    action.max_retries = max(0, payload.max_retries)
    action.retry_delay = max(1, payload.retry_delay)
    action.retain_result = 1 if payload.retain_result else 0
    db.commit()
    db.refresh(action)
    return action


@app.delete("/api/actions/{action_id}")
def delete_action(action_id: int, db: Session = Depends(get_db)):
    action = db.get(Action, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action_not_found")
    db.delete(action)
    db.commit()
    return {"status": "deleted", "action_id": action_id}


@app.post("/api/tasks/cleanup")
def manual_cleanup(db: Session = Depends(get_db)):
    from tasks.cleanup_task import _do_cleanup
    deleted = _do_cleanup(db)
    return {"deleted": deleted}


def _handle_recurring_intent(payload, session, normalized_intent_version, tzinfo):
    """Create (or update) a RecurringTask from an intent with a cron field."""
    task = payload.task
    errors: list[str] = []

    # depends_on not supported for recurring tasks
    if task.depends_on:
        errors.append("depends_on_cron_unsupported")

    # cron and run_at/run_in are mutually exclusive
    if task.run_at is not None or task.run_in is not None:
        errors.append("cron_and_run_at_exclusive")

    if not _validate_cron(task.cron):
        errors.append("cron_invalid")

    _raise_intent_validation(errors)

    # Resolve command/action
    resolved_command = task.command or ""
    action_name = task.action_name
    action_id = None
    resolved_cwd = task.cwd
    env = task.env
    allowed_command_dirs = None
    allowed_cwd_dirs = None
    effective_max_retries = task.max_retries if task.max_retries is not None else 0
    effective_retry_delay = task.retry_delay if task.retry_delay is not None else 60

    def _blocked_recurring(error_detail: str, command_value: str):
        blocked = _create_blocked_task(session, task.description, command_value, error_detail)
        return TaskIntentResponse(
            status="blocked",
            task_id=blocked.id,
            scheduled_at_local=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            scheduled_at_utc=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            command=command_value,
            description=task.description,
            action_name=action_name,
            intent_version=normalized_intent_version,
            source=payload.meta.get("source") if payload.meta else None,
            cwd=task.cwd,
            env_keys=list(env.keys()) if env else None,
            warnings=["blocked"],
            errors=[_intent_error(error_detail)],
            cron=task.cron,
        )

    if action_name:
        action = session.execute(
            select(Action).where(Action.name == action_name)
        ).scalar_one_or_none()
        if action is None:
            return _blocked_recurring("unknown_action", resolved_command)
        settings = _get_settings(session)
        allowed_command_dirs = action.allowed_command_dirs or settings.allowed_command_dirs
        allowed_cwd_dirs = action.allowed_cwd_dirs or settings.allowed_cwd_dirs
        try:
            _validate_command(action.command, allowed_command_dirs)
        except HTTPException as exc:
            return _blocked_recurring(str(exc.detail), action.command)
        resolved_command = action.command
        action_id = action.id
        if resolved_cwd is None:
            resolved_cwd = action.default_cwd
        if task.max_retries is None:
            effective_max_retries = action.max_retries or 0
        if task.retry_delay is None:
            effective_retry_delay = action.retry_delay or 60
        allowed_env = action.allowed_env or []
        if env:
            if not allowed_env:
                return _blocked_recurring("env_not_allowed", action.command)
            invalid_keys = sorted(set(env.keys()) - set(allowed_env))
            if invalid_keys:
                return _blocked_recurring("env_key_not_allowed", action.command)
    else:
        if not resolved_command:
            return _blocked_recurring("command_or_action_required", "")
        settings = _get_settings(session)
        allowed_command_dirs = settings.allowed_command_dirs
        allowed_cwd_dirs = settings.allowed_cwd_dirs
        try:
            _validate_command(resolved_command, allowed_command_dirs)
        except HTTPException as exc:
            return _blocked_recurring(str(exc.detail), resolved_command)
        if env:
            return _blocked_recurring("env_requires_action", resolved_command)

    try:
        _validate_cwd(resolved_cwd, allowed_cwd_dirs)
    except HTTPException as exc:
        return _blocked_recurring(str(exc.detail), resolved_command)

    # Check for name conflict
    existing = session.execute(
        select(RecurringTask).where(RecurringTask.name == task.description)
    ).scalar_one_or_none()
    if existing:
        return _blocked_recurring("recurring_name_exists", resolved_command)

    source = payload.meta.get("source") if payload.meta else None
    tz_name = task.timezone or "UTC"
    next_run_at = compute_initial_next_run(task.cron, tz_name)

    rt = RecurringTask(
        name=task.description,
        description=task.description,
        cron=task.cron,
        timezone=tz_name,
        action_name=action_name,
        command=task.command,
        cwd=resolved_cwd,
        env_json=json.dumps(env) if env else None,
        notify_on_complete=1 if task.notify_on_complete else 0,
        max_retries=max(0, effective_max_retries),
        retry_delay=max(1, effective_retry_delay),
        enabled=1,
        next_run_at=next_run_at,
    )
    session.add(rt)
    session.commit()
    session.refresh(rt)

    return TaskIntentResponse(
        status="recurring_scheduled",
        task_id=rt.id,
        scheduled_at_local=next_run_at.strftime("%Y-%m-%dT%H:%M:%S"),
        scheduled_at_utc=next_run_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        command=resolved_command,
        description=task.description,
        action_name=action_name,
        intent_version=normalized_intent_version,
        source=source,
        cwd=resolved_cwd,
        env_keys=list(env.keys()) if env else None,
        notify_on_complete=task.notify_on_complete,
        max_retries=effective_max_retries,
        retry_delay=effective_retry_delay,
        warnings=[],
        cron=task.cron,
        next_run_at=next_run_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


@app.post("/api/tasks/intent", response_model=TaskIntentResponse)
def create_task_from_intent(payload: TaskIntentEnvelope):
    session = SessionLocal()
    try:
        errors: list[str] = []
        normalized_intent_version, version_errors = _normalize_intent_version(
            payload.intent_version
        )
        errors.extend(version_errors)

        try:
            tzinfo = ZoneInfo(payload.task.timezone)
        except Exception:
            tzinfo = None
            errors.append("invalid_timezone")

        _raise_intent_validation(errors)

        # --- Cron / recurring path ---
        if payload.task.cron is not None:
            return _handle_recurring_intent(payload, session, normalized_intent_version, tzinfo)


        warnings: list[str] = []
        resolved_command = payload.task.command or ""
        action_name = payload.task.action_name
        action_id = None
        resolved_cwd = payload.task.cwd
        env = payload.task.env
        allowed_command_dirs = None
        allowed_cwd_dirs = None
        effective_max_retries = 0
        effective_retry_delay = 60

        def _blocked(error_detail: str, command_value: str) -> TaskIntentResponse:
            blocked = _create_blocked_task(
                session,
                payload.task.description,
                command_value,
                error_detail,
            )
            return TaskIntentResponse(
                status="blocked",
                task_id=blocked.id,
                scheduled_at_local=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                scheduled_at_utc=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                command=command_value,
                description=payload.task.description,
                action_name=action_name,
                intent_version=normalized_intent_version,
                source=payload.meta.get("source") if payload.meta else None,
                cwd=payload.task.cwd,
                env_keys=list(env.keys()) if env else None,
                warnings=["blocked"],
                errors=[_intent_error(error_detail)],
            )

        if action_name:
            action = session.execute(select(Action).where(Action.name == action_name)).scalar_one_or_none()
            if action is None:
                return _blocked("unknown_action", resolved_command)
            settings = _get_settings(session)
            allowed_command_dirs = action.allowed_command_dirs or settings.allowed_command_dirs
            allowed_cwd_dirs = action.allowed_cwd_dirs or settings.allowed_cwd_dirs
            try:
                _validate_command(action.command, allowed_command_dirs)
            except HTTPException as exc:
                return _blocked(str(exc.detail), action.command)
            resolved_command = action.command
            action_id = action.id
            if resolved_cwd is None:
                resolved_cwd = action.default_cwd
            effective_max_retries = action.max_retries or 0
            effective_retry_delay = action.retry_delay or 60
            allowed_env = action.allowed_env or []
            if env:
                if not allowed_env:
                    return _blocked("env_not_allowed", action.command)
                invalid_keys = sorted(set(env.keys()) - set(allowed_env))
                if invalid_keys:
                    return _blocked("env_key_not_allowed", action.command)
        else:
            if not resolved_command:
                return _blocked("command_or_action_required", "")
            settings = _get_settings(session)
            allowed_command_dirs = settings.allowed_command_dirs
            allowed_cwd_dirs = settings.allowed_cwd_dirs
            try:
                _validate_command(resolved_command, allowed_command_dirs)
            except HTTPException as exc:
                return _blocked(str(exc.detail), resolved_command)
            if env:
                return _blocked("env_requires_action", resolved_command)

        if payload.task.run_in:
            delta = _parse_run_in(payload.task.run_in)
            if delta is None:
                return _blocked("run_in_invalid", resolved_command)
            run_at_utc = datetime.now(timezone.utc) + delta
            run_at_local = run_at_utc.astimezone(tzinfo) if tzinfo else run_at_utc
            schedule_run_at = run_at_utc  # UTC-aware: TaskManager won't misapply local offset
        elif payload.task.run_at is not None:
            run_at_local = payload.task.run_at
            if run_at_local.tzinfo is None:
                run_at_local = run_at_local.replace(tzinfo=tzinfo)
            else:
                run_at_local = run_at_local.astimezone(tzinfo)
            schedule_run_at = run_at_local.replace(tzinfo=None)  # existing local-naive convention
        else:
            return _blocked("run_at_or_run_in_required", resolved_command)

        try:
            _validate_cwd(resolved_cwd, allowed_cwd_dirs)
        except HTTPException as exc:
            return _blocked(str(exc.detail), resolved_command)

        source = None
        if payload.meta and isinstance(payload.meta, dict):
            source = payload.meta.get("source")
        # Task-level intent overrides action defaults
        if payload.task.max_retries is not None:
            effective_max_retries = max(0, payload.task.max_retries)
        if payload.task.retry_delay is not None:
            effective_retry_delay = max(1, payload.task.retry_delay)
        # retain_result: action flag wins; otherwise use task-level flag
        effective_retain_result = 0
        if action_name:
            action_obj = session.execute(
                select(Action).where(Action.name == action_name)
            ).scalar_one_or_none()
            if action_obj and action_obj.retain_result == 1:
                effective_retain_result = 1
            elif payload.task.retain_result:
                effective_retain_result = 1
        elif payload.task.retain_result:
            effective_retain_result = 1

        # --- Dependency branching ---
        unique_dep_ids = list(dict.fromkeys(payload.task.depends_on or []))
        dep_errors, dep_outcome = _validate_depends_on(session, unique_dep_ids)
        if dep_errors:
            return _blocked(dep_errors[0], resolved_command)

        if dep_outcome == "immediate_fail":
            # All dep IDs exist but at least one already failed/cancelled
            task_req = TaskRequest(
                description=payload.task.description,
                command=resolved_command,
                run_at=schedule_run_at.replace(tzinfo=None) if hasattr(schedule_run_at, "tzinfo") else schedule_run_at,
                status="failed",
                error="One or more dependencies have already failed or been cancelled.",
                intent_version=normalized_intent_version,
                source=source,
                action_id=action_id,
                action_name=action_name,
                cwd=resolved_cwd,
                env_json=json.dumps(env) if env else None,
                notify_on_complete=1 if payload.task.notify_on_complete else 0,
                max_retries=effective_max_retries,
                retry_delay=effective_retry_delay,
                retain_result=effective_retain_result,
            )
            session.add(task_req)
            session.flush()
            for dep_id in unique_dep_ids:
                session.add(TaskDependency(task_id=task_req.id, depends_on_task_id=dep_id))
            session.commit()
            return TaskIntentResponse(
                status="failed",
                task_id=task_req.id,
                scheduled_at_local=run_at_local.strftime("%Y-%m-%dT%H:%M:%S"),
                scheduled_at_utc=run_at_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                command=resolved_command,
                description=payload.task.description,
                action_name=action_name,
                intent_version=normalized_intent_version,
                source=source,
                cwd=resolved_cwd,
                env_keys=list(env.keys()) if env else None,
                notify_on_complete=payload.task.notify_on_complete,
                max_retries=effective_max_retries,
                retry_delay=effective_retry_delay,
                warnings=["dependency_failed"],
                errors=[_intent_error("depends_on_already_failed")],
                depends_on=unique_dep_ids,
                retain_result=bool(effective_retain_result),
            )

        if dep_outcome == "waiting":
            run_at_naive = schedule_run_at.replace(tzinfo=None) if hasattr(schedule_run_at, "tzinfo") and schedule_run_at.tzinfo is not None else schedule_run_at
            task_req = TaskRequest(
                description=payload.task.description,
                command=resolved_command,
                run_at=run_at_naive,
                status="waiting",
                intent_version=normalized_intent_version,
                source=source,
                action_id=action_id,
                action_name=action_name,
                cwd=resolved_cwd,
                env_json=json.dumps(env) if env else None,
                notify_on_complete=1 if payload.task.notify_on_complete else 0,
                max_retries=effective_max_retries,
                retry_delay=effective_retry_delay,
                retain_result=effective_retain_result,
            )
            session.add(task_req)
            session.flush()
            for dep_id in unique_dep_ids:
                session.add(TaskDependency(task_id=task_req.id, depends_on_task_id=dep_id))
            session.commit()
            return TaskIntentResponse(
                status="waiting",
                task_id=task_req.id,
                scheduled_at_local=run_at_local.strftime("%Y-%m-%dT%H:%M:%S"),
                scheduled_at_utc=run_at_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                command=resolved_command,
                description=payload.task.description,
                action_name=action_name,
                intent_version=normalized_intent_version,
                source=source,
                cwd=resolved_cwd,
                env_keys=list(env.keys()) if env else None,
                notify_on_complete=payload.task.notify_on_complete,
                max_retries=effective_max_retries,
                retry_delay=effective_retry_delay,
                warnings=[],
                depends_on=unique_dep_ids,
                retain_result=bool(effective_retain_result),
            )

        # dep_outcome == "immediate_schedule" — fall through to normal scheduling
        manager = TaskManager()
        task_id = manager.schedule_command(
            resolved_command,
            schedule_run_at,
            cwd=resolved_cwd,
            env=env,
        )

        task = session.get(TaskRequest, task_id)
        if task is not None:
            task.intent_version = normalized_intent_version
            task.source = source
            task.description = payload.task.description
            task.action_id = action_id
            task.action_name = action_name
            task.cwd = resolved_cwd
            task.env_json = json.dumps(env) if env else None
            task.notify_on_complete = 1 if payload.task.notify_on_complete else 0
            task.max_retries = effective_max_retries
            task.retry_delay = effective_retry_delay
            task.retain_result = effective_retain_result
            session.flush()
            for dep_id in unique_dep_ids:
                session.add(TaskDependency(task_id=task_id, depends_on_task_id=dep_id))
            session.commit()

        return TaskIntentResponse(
            status="scheduled",
            task_id=task_id,
            scheduled_at_local=run_at_local.strftime("%Y-%m-%dT%H:%M:%S"),
            scheduled_at_utc=run_at_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            command=resolved_command,
            description=payload.task.description,
            action_name=action_name,
            intent_version=normalized_intent_version,
            source=source,
            cwd=resolved_cwd,
            env_keys=list(env.keys()) if env else None,
            notify_on_complete=payload.task.notify_on_complete,
            max_retries=effective_max_retries,
            retry_delay=effective_retry_delay,
            warnings=warnings,
            depends_on=unique_dep_ids if unique_dep_ids else None,
            retain_result=bool(effective_retain_result),
        )
    finally:
        session.close()


@app.post("/api/tasks/intent/preview", response_model=TaskIntentResponse)
def preview_task_intent(payload: TaskIntentEnvelope):
    errors: list[str] = []
    normalized_intent_version, version_errors = _normalize_intent_version(
        payload.intent_version
    )
    errors.extend(version_errors)

    try:
        tzinfo = ZoneInfo(payload.task.timezone)
    except Exception:
        tzinfo = None
        errors.append("invalid_timezone")

    _raise_intent_validation(errors)

    warnings: list[str] = []
    resolved_command = payload.task.command or ""
    action_name = payload.task.action_name
    resolved_cwd = payload.task.cwd
    env = payload.task.env
    allowed_command_dirs = None
    allowed_cwd_dirs = None
    if action_name:
        with SessionLocal() as session:
            action = session.execute(select(Action).where(Action.name == action_name)).scalar_one_or_none()
            if action is None:
                _raise_intent_validation(["unknown_action"])
            settings = _get_settings(session)
            allowed_command_dirs = action.allowed_command_dirs or settings.allowed_command_dirs
            allowed_cwd_dirs = action.allowed_cwd_dirs or settings.allowed_cwd_dirs
            try:
                _validate_command(action.command, allowed_command_dirs)
            except HTTPException as exc:
                _raise_intent_validation([str(exc.detail)])
            resolved_command = action.command
            if resolved_cwd is None:
                resolved_cwd = action.default_cwd
            allowed_env = action.allowed_env or []
            if env:
                if not allowed_env:
                    _raise_intent_validation(["env_not_allowed"])
                invalid_keys = sorted(set(env.keys()) - set(allowed_env))
                if invalid_keys:
                    _raise_intent_validation(["env_key_not_allowed"])
    else:
        if not payload.task.command:
            _raise_intent_validation(["command_or_action_required"])
        with SessionLocal() as session:
            settings = _get_settings(session)
            allowed_command_dirs = settings.allowed_command_dirs
            allowed_cwd_dirs = settings.allowed_cwd_dirs
        try:
            _validate_command(payload.task.command, allowed_command_dirs)
        except HTTPException as exc:
            _raise_intent_validation([str(exc.detail)])
        if env:
            _raise_intent_validation(["env_requires_action"])
    if payload.task.run_in:
        delta = _parse_run_in(payload.task.run_in)
        if delta is None:
            _raise_intent_validation(["run_in_invalid"])
        run_at_local = datetime.now(timezone.utc) + delta
        if tzinfo:
            run_at_local = run_at_local.astimezone(tzinfo)
    elif payload.task.run_at is not None:
        run_at_local = payload.task.run_at
        if run_at_local.tzinfo is None:
            run_at_local = run_at_local.replace(tzinfo=tzinfo)
        else:
            run_at_local = run_at_local.astimezone(tzinfo)
    else:
        _raise_intent_validation(["run_at_or_run_in_required"])

    try:
        _validate_cwd(resolved_cwd, allowed_cwd_dirs)
    except HTTPException as exc:
        _raise_intent_validation([str(exc.detail)])
    source = None
    if payload.meta and isinstance(payload.meta, dict):
        source = payload.meta.get("source")

    return TaskIntentResponse(
        status="preview",
        task_id=0,
        scheduled_at_local=run_at_local.strftime("%Y-%m-%dT%H:%M:%S"),
        scheduled_at_utc=run_at_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        command=resolved_command,
        description=payload.task.description,
        action_name=action_name,
        intent_version=normalized_intent_version,
        source=source,
        cwd=resolved_cwd,
        env_keys=list(env.keys()) if env else None,
        notify_on_complete=payload.task.notify_on_complete,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Recurring task helpers
# ---------------------------------------------------------------------------

def _recurring_from_payload(
    payload: RecurringTaskCreate | RecurringTaskUpdate,
    session,
    existing_id: int | None = None,
) -> RecurringTask | None:
    """Validate and build a RecurringTask ORM object. Returns None and raises on error."""
    if not _validate_cron(payload.cron):
        raise HTTPException(status_code=400, detail="cron_invalid")

    try:
        ZoneInfo(payload.timezone)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_timezone")

    resolved_command = payload.command or ""
    resolved_cwd = payload.cwd
    env = payload.env
    allowed_command_dirs = None
    allowed_cwd_dirs = None

    settings = _get_settings(session)

    if payload.action_name:
        action = session.execute(
            select(Action).where(Action.name == payload.action_name)
        ).scalar_one_or_none()
        if action is None:
            raise HTTPException(status_code=400, detail="unknown_action")
        allowed_command_dirs = action.allowed_command_dirs or settings.allowed_command_dirs
        allowed_cwd_dirs = action.allowed_cwd_dirs or settings.allowed_cwd_dirs
        _validate_command(action.command, allowed_command_dirs)
        resolved_command = action.command
        if resolved_cwd is None:
            resolved_cwd = action.default_cwd
        allowed_env = action.allowed_env or []
        if env:
            if not allowed_env:
                raise HTTPException(status_code=400, detail="env_not_allowed")
            invalid_keys = sorted(set(env.keys()) - set(allowed_env))
            if invalid_keys:
                raise HTTPException(status_code=400, detail="env_key_not_allowed")
    elif resolved_command:
        allowed_command_dirs = settings.allowed_command_dirs
        allowed_cwd_dirs = settings.allowed_cwd_dirs
        _validate_command(resolved_command, allowed_command_dirs)
        if env:
            raise HTTPException(status_code=400, detail="env_requires_action")
    else:
        raise HTTPException(status_code=400, detail="command_or_action_required")

    _validate_cwd(resolved_cwd, allowed_cwd_dirs)

    # Name uniqueness check
    query = select(RecurringTask).where(RecurringTask.name == payload.name)
    if existing_id is not None:
        from sqlalchemy import and_
        query = select(RecurringTask).where(
            RecurringTask.name == payload.name,
            RecurringTask.id != existing_id,
        )
    name_conflict = session.execute(query).scalar_one_or_none()
    if name_conflict:
        raise HTTPException(status_code=400, detail="recurring_name_exists")

    next_run_at = compute_initial_next_run(payload.cron, payload.timezone)

    return RecurringTask(
        name=payload.name,
        description=payload.description,
        cron=payload.cron,
        timezone=payload.timezone,
        action_name=payload.action_name,
        command=payload.command,
        cwd=resolved_cwd,
        env_json=json.dumps(env) if env else None,
        notify_on_complete=1 if payload.notify_on_complete else 0,
        max_retries=max(0, payload.max_retries),
        retry_delay=max(1, payload.retry_delay),
        enabled=1 if payload.enabled else 0,
        next_run_at=next_run_at,
    )


# ---------------------------------------------------------------------------
# /api/recurring  CRUD endpoints
# ---------------------------------------------------------------------------

@app.get("/api/recurring", response_model=list[RecurringTaskRead])
def list_recurring(db: Session = Depends(get_db)):
    return db.execute(
        select(RecurringTask).order_by(RecurringTask.name.asc())
    ).scalars().all()


@app.post("/api/recurring", response_model=RecurringTaskRead)
def create_recurring(payload: RecurringTaskCreate, db: Session = Depends(get_db)):
    rt = _recurring_from_payload(payload, db)
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return rt


@app.put("/api/recurring/{recurring_id}", response_model=RecurringTaskRead)
def update_recurring(
    recurring_id: int, payload: RecurringTaskUpdate, db: Session = Depends(get_db)
):
    rt = db.get(RecurringTask, recurring_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="recurring_task_not_found")
    updated = _recurring_from_payload(payload, db, existing_id=recurring_id)
    # Copy fields onto existing row
    rt.name = updated.name
    rt.description = updated.description
    rt.cron = updated.cron
    rt.timezone = updated.timezone
    rt.action_name = updated.action_name
    rt.command = updated.command
    rt.cwd = updated.cwd
    rt.env_json = updated.env_json
    rt.notify_on_complete = updated.notify_on_complete
    rt.max_retries = updated.max_retries
    rt.retry_delay = updated.retry_delay
    rt.enabled = updated.enabled
    rt.next_run_at = updated.next_run_at
    db.commit()
    db.refresh(rt)
    return rt


@app.delete("/api/recurring/{recurring_id}")
def delete_recurring(recurring_id: int, db: Session = Depends(get_db)):
    rt = db.get(RecurringTask, recurring_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="recurring_task_not_found")
    db.delete(rt)
    db.commit()
    return {"status": "deleted", "recurring_id": recurring_id}


@app.post("/api/recurring/{recurring_id}/toggle")
def toggle_recurring(recurring_id: int, db: Session = Depends(get_db)):
    rt = db.get(RecurringTask, recurring_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="recurring_task_not_found")
    rt.enabled = 0 if rt.enabled else 1
    if rt.enabled:
        # Re-arm next_run_at from now
        rt.next_run_at = compute_initial_next_run(rt.cron, rt.timezone)
    db.commit()
    return {"status": "enabled" if rt.enabled else "disabled", "recurring_id": recurring_id}


# ---------------------------------------------------------------------------
# /recurring  HTML routes
# ---------------------------------------------------------------------------

@app.get("/recurring", response_class=HTMLResponse)
def recurring_dashboard(request: Request, db: Session = Depends(get_db)):
    tasks = db.execute(
        select(RecurringTask).order_by(RecurringTask.name.asc())
    ).scalars().all()
    return templates.TemplateResponse(
        "recurring.html", {"request": request, "tasks": tasks}
    )


@app.get("/recurring/new", response_class=HTMLResponse)
def recurring_new(request: Request, db: Session = Depends(get_db)):
    actions = db.execute(select(Action).order_by(Action.name.asc())).scalars().all()
    return templates.TemplateResponse(
        "recurring_form.html",
        {"request": request, "actions": actions, "form": {}, "editing": False},
    )


@app.post("/recurring/new")
def recurring_create_form(
    request: Request,
    name: str = Form(...),
    cron: str = Form(...),
    timezone: str = Form("UTC"),
    description: str | None = Form(None),
    action_name: str | None = Form(None),
    command: str | None = Form(None),
    notify_on_complete: str | None = Form(None),
    max_retries: int = Form(0),
    retry_delay: int = Form(60),
    enabled: str | None = Form(None),
    db: Session = Depends(get_db),
):
    form_data = {
        "name": name, "cron": cron, "timezone": timezone,
        "description": description or "", "action_name": action_name or "",
        "command": command or "",
        "notify_on_complete": notify_on_complete,
        "max_retries": max_retries, "retry_delay": retry_delay,
        "enabled": enabled,
    }
    actions = db.execute(select(Action).order_by(Action.name.asc())).scalars().all()
    try:
        payload = RecurringTaskCreate(
            name=name,
            description=description,
            cron=cron,
            timezone=timezone,
            action_name=action_name or None,
            command=command or None,
            notify_on_complete=bool(notify_on_complete),
            max_retries=max_retries,
            retry_delay=retry_delay,
            enabled=bool(enabled),
        )
        rt = _recurring_from_payload(payload, db)
        db.add(rt)
        db.commit()
    except HTTPException as exc:
        return templates.TemplateResponse(
            "recurring_form.html",
            {"request": request, "actions": actions, "form": form_data,
             "editing": False, "error": exc.detail},
            status_code=400,
        )
    return RedirectResponse(url="/recurring", status_code=303)


@app.get("/recurring/{recurring_id}/edit", response_class=HTMLResponse)
def recurring_edit(recurring_id: int, request: Request, db: Session = Depends(get_db)):
    rt = db.get(RecurringTask, recurring_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="Recurring task not found")
    actions = db.execute(select(Action).order_by(Action.name.asc())).scalars().all()
    return templates.TemplateResponse(
        "recurring_form.html",
        {"request": request, "actions": actions, "form": rt, "editing": True,
         "recurring_id": recurring_id},
    )


@app.post("/recurring/{recurring_id}/edit")
def recurring_update_form(
    request: Request,
    recurring_id: int,
    name: str = Form(...),
    cron: str = Form(...),
    timezone: str = Form("UTC"),
    description: str | None = Form(None),
    action_name: str | None = Form(None),
    command: str | None = Form(None),
    notify_on_complete: str | None = Form(None),
    max_retries: int = Form(0),
    retry_delay: int = Form(60),
    enabled: str | None = Form(None),
    db: Session = Depends(get_db),
):
    rt = db.get(RecurringTask, recurring_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="Recurring task not found")
    form_data = {
        "name": name, "cron": cron, "timezone": timezone,
        "description": description or "", "action_name": action_name or "",
        "command": command or "",
        "notify_on_complete": notify_on_complete,
        "max_retries": max_retries, "retry_delay": retry_delay,
        "enabled": enabled,
    }
    actions = db.execute(select(Action).order_by(Action.name.asc())).scalars().all()
    try:
        payload = RecurringTaskUpdate(
            name=name,
            description=description,
            cron=cron,
            timezone=timezone,
            action_name=action_name or None,
            command=command or None,
            notify_on_complete=bool(notify_on_complete),
            max_retries=max_retries,
            retry_delay=retry_delay,
            enabled=bool(enabled),
        )
        updated = _recurring_from_payload(payload, db, existing_id=recurring_id)
        rt.name = updated.name
        rt.description = updated.description
        rt.cron = updated.cron
        rt.timezone = updated.timezone
        rt.action_name = updated.action_name
        rt.command = updated.command
        rt.cwd = updated.cwd
        rt.env_json = updated.env_json
        rt.notify_on_complete = updated.notify_on_complete
        rt.max_retries = updated.max_retries
        rt.retry_delay = updated.retry_delay
        rt.enabled = updated.enabled
        rt.next_run_at = updated.next_run_at
        db.commit()
    except HTTPException as exc:
        return templates.TemplateResponse(
            "recurring_form.html",
            {"request": request, "actions": actions, "form": form_data,
             "editing": True, "recurring_id": recurring_id, "error": exc.detail},
            status_code=400,
        )
    return RedirectResponse(url="/recurring", status_code=303)


@app.post("/recurring/{recurring_id}/delete")
def recurring_delete_form(recurring_id: int, db: Session = Depends(get_db)):
    rt = db.get(RecurringTask, recurring_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="Recurring task not found")
    db.delete(rt)
    db.commit()
    return RedirectResponse(url="/recurring", status_code=303)


@app.post("/recurring/{recurring_id}/toggle")
def recurring_toggle_form(recurring_id: int, db: Session = Depends(get_db)):
    rt = db.get(RecurringTask, recurring_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="Recurring task not found")
    rt.enabled = 0 if rt.enabled else 1
    if rt.enabled:
        rt.next_run_at = compute_initial_next_run(rt.cron, rt.timezone)
    db.commit()
    return RedirectResponse(url="/recurring", status_code=303)
