# Mage Scheduler

Simple task scheduler built on Celery, including periodic GPU monitoring and ad‐hoc command scheduling.

## Requirements

- Python 3.11+
- Redis server (default broker/backend at `redis://localhost:6379/0`)
- Celery>=5.5.3
- Flower>=2.0.1 (optional web UI)

Install the Python dependencies:
```bash
# If you use pip and a virtualenv:
pip install celery[redis] flower
```

## Running Celery Worker and Beat

From the project root directory, start the Celery worker with beat:
```bash
celery -A celery_app worker --beat --loglevel=info
```

The GPU monitor task (`tasks.gpu_tasks.gpu_monitor`) is preconfigured to run every 60 seconds.

## Scheduling Ad‐Hoc Commands

Use the `TaskManager` in `tasks/task_manager.py` to schedule shell commands at a given local datetime:
```python
from tasks.task_manager import TaskManager
manager = TaskManager()
task_id = manager.schedule_command("echo 'Hello'", datetime.utcnow())
```

## FastAPI Dashboard + API

Run the web app:
```bash
uvicorn api:app --reload --port 8000
```

The dashboard is at `/`, and the JSON API is under `/api/tasks`.
