from __future__ import annotations

from datetime import datetime, timezone
import json
import os
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

from db import SessionLocal, init_db
from models import Action, Settings, TaskRequest
from schemas import (
    ActionCreate,
    ActionRead,
    ActionUpdate,
    TaskCreate,
    TaskRead,
    TaskIntentEnvelope,
    TaskIntentResponse,
    TaskRunNow,
)
from tasks.task_manager import TaskManager
from tasks.celery_app import app as celery_app
from nl_parser import parse_request

app = FastAPI(title="Mage Scheduler")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["local_time"] = lambda dt: _to_local_time(dt)
START_TIME = time.time()


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
    tasks = db.execute(select(TaskRequest).order_by(TaskRequest.created_at.desc())).scalars().all()
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
    return templates.TemplateResponse(
        "tasks.html",
        {
            "request": request,
            "tasks": tasks,
            "actions": actions,
            "recent_results": recent_results,
            "blocked_tasks": blocked_tasks,
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


@app.get("/api/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


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


@app.post("/api/tasks/intent", response_model=TaskIntentResponse)
def create_task_from_intent(payload: TaskIntentEnvelope):
    session = SessionLocal()
    try:
        errors: list[str] = []
        if payload.intent_version != "v1":
            errors.append("unsupported_intent_version")

        try:
            tzinfo = ZoneInfo(payload.task.timezone)
        except Exception:
            tzinfo = None
            errors.append("invalid_timezone")

        if errors:
            raise HTTPException(status_code=400, detail=errors)

        warnings: list[str] = []
        resolved_command = payload.task.command or ""
        action_name = payload.task.action_name
        action_id = None
        resolved_cwd = payload.task.cwd
        env = payload.task.env
        allowed_command_dirs = None
        allowed_cwd_dirs = None

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
                intent_version=payload.intent_version,
                source=payload.meta.get("source") if payload.meta else None,
                cwd=payload.task.cwd,
                env_keys=list(env.keys()) if env else None,
                warnings=["blocked"],
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

        run_at_local = payload.task.run_at
        if run_at_local.tzinfo is None:
            run_at_local = run_at_local.replace(tzinfo=tzinfo)
        else:
            run_at_local = run_at_local.astimezone(tzinfo)

        run_at_local_naive = run_at_local.replace(tzinfo=None)
        try:
            _validate_cwd(resolved_cwd, allowed_cwd_dirs)
        except HTTPException as exc:
            return _blocked(str(exc.detail), resolved_command)

        manager = TaskManager()
        task_id = manager.schedule_command(
            resolved_command,
            run_at_local_naive,
            cwd=resolved_cwd,
            env=env,
        )

        source = None
        if payload.meta and isinstance(payload.meta, dict):
            source = payload.meta.get("source")
        task = session.get(TaskRequest, task_id)
        if task is not None:
            task.intent_version = payload.intent_version
            task.source = source
            task.description = payload.task.description
            task.action_id = action_id
            task.action_name = action_name
            task.cwd = resolved_cwd
            task.env_json = json.dumps(env) if env else None
            session.commit()

        return TaskIntentResponse(
            status="scheduled",
            task_id=task_id,
            scheduled_at_local=run_at_local.strftime("%Y-%m-%dT%H:%M:%S"),
            scheduled_at_utc=run_at_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            command=resolved_command,
            description=payload.task.description,
            action_name=action_name,
            intent_version=payload.intent_version,
            source=source,
            cwd=resolved_cwd,
            env_keys=list(env.keys()) if env else None,
            warnings=warnings,
        )
    finally:
        session.close()


@app.post("/api/tasks/intent/preview", response_model=TaskIntentResponse)
def preview_task_intent(payload: TaskIntentEnvelope):
    errors: list[str] = []
    if payload.intent_version != "v1":
        errors.append("unsupported_intent_version")

    try:
        tzinfo = ZoneInfo(payload.task.timezone)
    except Exception:
        tzinfo = None
        errors.append("invalid_timezone")

    if errors:
        raise HTTPException(status_code=400, detail=errors)

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
                raise HTTPException(status_code=400, detail=["unknown_action"])
            settings = _get_settings(session)
            allowed_command_dirs = action.allowed_command_dirs or settings.allowed_command_dirs
            allowed_cwd_dirs = action.allowed_cwd_dirs or settings.allowed_cwd_dirs
            _validate_command(action.command, allowed_command_dirs)
            resolved_command = action.command
            if resolved_cwd is None:
                resolved_cwd = action.default_cwd
            allowed_env = action.allowed_env or []
            if env:
                if not allowed_env:
                    raise HTTPException(status_code=400, detail=["env_not_allowed"])
                invalid_keys = sorted(set(env.keys()) - set(allowed_env))
                if invalid_keys:
                    raise HTTPException(status_code=400, detail=["env_key_not_allowed"])
    else:
        if not payload.task.command:
            raise HTTPException(status_code=400, detail=["command_or_action_required"])
        with SessionLocal() as session:
            settings = _get_settings(session)
            allowed_command_dirs = settings.allowed_command_dirs
            allowed_cwd_dirs = settings.allowed_cwd_dirs
        _validate_command(payload.task.command, allowed_command_dirs)
        if env:
            raise HTTPException(status_code=400, detail=["env_requires_action"])
    run_at_local = payload.task.run_at
    if run_at_local.tzinfo is None:
        run_at_local = run_at_local.replace(tzinfo=tzinfo)
    else:
        run_at_local = run_at_local.astimezone(tzinfo)

    _validate_cwd(resolved_cwd, allowed_cwd_dirs)
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
        intent_version=payload.intent_version,
        source=source,
        cwd=resolved_cwd,
        env_keys=list(env.keys()) if env else None,
        warnings=warnings,
    )
