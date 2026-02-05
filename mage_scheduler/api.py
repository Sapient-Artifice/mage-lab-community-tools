from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse
from celery.result import AsyncResult
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal, init_db
from models import TaskRequest
from schemas import TaskCreate, TaskRead
from tasks.task_manager import TaskManager
from tasks.celery_app import app as celery_app

app = FastAPI(title="Mage Scheduler")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["local_time"] = lambda dt: _to_local_time(dt)


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


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    tasks = db.execute(select(TaskRequest).order_by(TaskRequest.created_at.desc())).scalars().all()
    return templates.TemplateResponse("tasks.html", {"request": request, "tasks": tasks})


@app.post("/tasks")
def create_task_form(
    command: str = Form(...),
    run_at: datetime = Form(...),
    description: str | None = Form(None),
):
    manager = TaskManager()
    task_id = manager.schedule_command(command, run_at)

    if description:
        with SessionLocal() as session:
            task = session.get(TaskRequest, task_id)
            if task is not None:
                task.description = description
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


@app.get("/api/tasks", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    return db.execute(select(TaskRequest).order_by(TaskRequest.created_at.desc())).scalars().all()


@app.get("/api/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/api/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    manager = TaskManager()
    task_id = manager.schedule_command(payload.command, payload.run_at)
    task = db.get(TaskRequest, task_id)
    if task is None:
        raise HTTPException(status_code=500, detail="Failed to create task")
    if payload.description:
        task.description = payload.description
        db.commit()
        db.refresh(task)
    return task
