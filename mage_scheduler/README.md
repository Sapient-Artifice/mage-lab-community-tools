# Mage Scheduler

Mage Scheduler is a small task scheduling service built on Celery + Redis with a FastAPI dashboard/API. It is designed to accept structured task intents (from LLMs or humans) and provide clear visibility into scheduled jobs.

## What it does
- Schedules shell commands at a specified time
- Stores task metadata in SQLite
- Provides an HTML dashboard for verification
- Exposes JSON endpoints for LLM-driven task creation

## Requirements
- Python 3.11+
- Redis (default broker/backend at `redis://localhost:6379/0`)

## Setup
```bash
uv venv
uv sync
```

## Run
Start the API:
```bash
uv run uvicorn api:app --reload --port 8000
```

Start Celery (worker + beat):
```bash
uv run celery -A celery_app worker --beat --loglevel=info
```

## Dashboard
Open `http://127.0.0.1:8000/` to view tasks and create new ones.
The dashboard now includes a Recent Results section for quick verification.

## Actions
Actions are named, vetted commands. You can manage them at `/actions` and set a default working directory plus allowed environment keys.
Action commands must be absolute paths to executables.

## Settings
Global directory allowlists live at `/settings`. Actions can optionally override allowed command/cwd directories.

## API

### Create task (direct)
```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"command":"echo Hello Mage","run_at":"2026-02-05T18:00:00"}'
```

### Create task (LLM intent)
```bash
curl -X POST http://127.0.0.1:8000/api/tasks/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent_version":"v1",
    "task":{
      "description":"Back up home directory",
      "command":"/usr/local/bin/backup_home.sh",
      "run_at":"2026-02-05T18:00:00",
      "timezone":"America/Los_Angeles",
      "action_name":"backup_home"
    },
    "meta":{
      "source":"mage-lab-llm"
    }
  }'
```

### Preview intent (no scheduling)
```bash
curl -X POST http://127.0.0.1:8000/api/tasks/intent/preview \
  -H "Content-Type: application/json" \
  -d '{
    "intent_version":"v1",
    "task":{
      "description":"Back up home directory",
      "command":"/usr/local/bin/backup_home.sh",
      "run_at":"2026-02-05T18:00:00",
      "timezone":"America/Los_Angeles",
      "action_name":"backup_home"
    },
    "meta":{
      "source":"mage-lab-llm"
    }
  }'
```

### Run now (API)
```bash
curl -X POST http://127.0.0.1:8000/api/tasks/run_now \
  -H "Content-Type: application/json" \
  -d '{
    "command": "/usr/bin/true",
    "description": "Quick health check"
  }'
```

### Health check
```bash
curl http://127.0.0.1:8000/health
```

### Create action (API)
```bash
curl -X POST http://127.0.0.1:8000/api/actions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "backup_home",
    "description": "Back up home directory",
    "command": "/usr/local/bin/backup_home.sh",
    "default_cwd": "/usr/local/bin",
    "allowed_env": ["PROJECT_ID"],
    "allowed_command_dirs": ["/usr/local/bin"],
    "allowed_cwd_dirs": ["/usr/local/bin"]
  }'
```

## Notes
- Times in the UI are shown in local system time.
- SQLite DB file: `mage_scheduler.db`.
- Local artifacts are ignored via `mage_scheduler/.gitignore`.
