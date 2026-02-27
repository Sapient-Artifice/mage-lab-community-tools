# Mage Scheduler

Mage Scheduler is a small task scheduling service built on Celery + Redis with a FastAPI dashboard/API. It is designed to accept structured task intents (from LLMs or humans) and provide clear visibility into scheduled jobs.

> **Companion tool:** [`mage-scheduler-tool`](../mage-scheduler-tool/README.md) is the mage lab skill that connects the assistant to this service — install both to schedule tasks by talking to Mage.

## What it does
- Schedules shell commands at a specified time or after a duration (`run_at` / `run_in`)
- Supports recurring tasks via cron expressions (with timezone control)
- Chains tasks with dependencies (`depends_on: [task_id]`) — waiting tasks auto-unblock or cascade-fail
- Retry policy per action (`max_retries`, `retry_delay`)
- Auto-cleanup of old terminal tasks (configurable retention)
- Stores task metadata in SQLite
- Provides an HTML dashboard for verification
- Exposes JSON endpoints for LLM-driven task creation via the intent API
- Sends automated notifications back to the assistant on task completion

## Requirements
- Python 3.11+
- Redis (default broker/backend at `redis://localhost:6379/0`)

## Platform support
- Linux and macOS only for now.
- Windows is not supported yet and will be revisited.

## Setup
```bash
uv venv
uv sync
```

## Run
The easiest way to start both services together:
```bash
bash RunMageScheduler.sh
```
Press Ctrl+C to stop both. For a persistent session that survives terminal close, run inside `tmux` or `screen`.

Or start each service manually:
```bash
uv run uvicorn api:app --port 8012
uv run celery -A celery_app worker --beat --loglevel=info
```

## Dashboard
Open `http://127.0.0.1:8012/` to view tasks and create new ones.
The dashboard includes a Recent Results section for quick verification.

## Actions
Actions are named, vetted commands. You can manage them at `/actions` and set a default working directory plus allowed environment keys.
Action commands must be absolute paths to executables.

### Built-in action: `ask_assistant`
The `ask_assistant` action is automatically registered on first startup. It sends a scheduled message to the Mage Lab assistant — the primary way to schedule a future reminder or re-injection back to Mage.

All messages sent via `ask_assistant` (whether from a scheduled reminder or a completion notification) include a structured disclosure header so the receiving LLM can identify them as automated:

```
[MAGE SCHEDULER — AUTOMATED MESSAGE]
Task ID: 42 | Action: ask_assistant | Triggered: 2026-02-24T18:00:02Z
Description: Deployment review reminder
---
Time to review the deployment status.
```

Schedule a reminder via the intent API using `run_in` for a relative delay:
```bash
curl -X POST http://127.0.0.1:8012/api/tasks/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent_version": "v1",
    "task": {
      "description": "Deployment review reminder",
      "action_name": "ask_assistant",
      "env": { "MESSAGE": "Time to review the deployment status." },
      "run_in": "2h",
      "timezone": "America/Los_Angeles"
    },
    "meta": { "source": "mage-lab-llm" }
  }'
```

The `MESSAGE` env key is the only allowed variable for this action.

## Settings
Global directory allowlists live at `/settings`. Actions can optionally override allowed command/cwd directories.

## API

### Create task (direct)
```bash
curl -X POST http://127.0.0.1:8012/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"command":"echo Hello Mage","run_at":"2026-02-05T18:00:00"}'
```

### Create task (LLM intent)
```bash
curl -X POST http://127.0.0.1:8012/api/tasks/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent_version":"v1",
    "task":{
      "description":"Back up home directory",
      "action_name":"backup_home",
      "run_in":"1d",
      "timezone":"America/Los_Angeles",
      "notify_on_complete": true
    },
    "meta":{
      "source":"mage-lab-llm"
    }
  }'
```

Notes:
- Use `run_in` for relative delays (`"30m"`, `"2h"`, `"1d"`, `"90s"`) or `run_at` for a specific datetime.
- `timezone` defaults to `"UTC"` if omitted.
- Set `notify_on_complete: true` to receive an automated message when the task finishes.
- `intent_version` accepts `v1`, `1`, or `1.0` and is normalized to `v1`.
- Validation failures return `detail.errors[]` with `code`, `message`, and optional `hint`.

### Preview intent (no scheduling)
```bash
curl -X POST http://127.0.0.1:8012/api/tasks/intent/preview \
  -H "Content-Type: application/json" \
  -d '{
    "intent_version":"v1",
    "task":{
      "description":"Back up home directory",
      "action_name":"backup_home",
      "run_in":"1d",
      "timezone":"America/Los_Angeles"
    },
    "meta":{
      "source":"mage-lab-llm"
    }
  }'
```

### Run now (API)
```bash
curl -X POST http://127.0.0.1:8012/api/tasks/run_now \
  -H "Content-Type: application/json" \
  -d '{
    "command": "/usr/bin/true",
    "description": "Quick health check",
    "notify_on_complete": true
  }'
```

### Cancel task
```bash
curl -X POST http://127.0.0.1:8012/api/tasks/42/cancel
```
Only works on tasks with status `scheduled` or `running`.

### Health check
```bash
curl http://127.0.0.1:8012/health
```

### Validation rules
```bash
curl http://127.0.0.1:8012/api/validation
```

## Validation behavior
- Commands must be absolute, exist, and be executable.
- `cwd` must be absolute and exist when provided.
- Commands and `cwd` must fall under allowed directory settings.
- Env vars are only allowed for actions and must be whitelisted per action.
- Blocked requests are stored with `status="blocked"` and `error` set to the failure reason.

### Create action (API)
```bash
curl -X POST http://127.0.0.1:8012/api/actions \
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

## Recurring tasks

Create a recurring task via the dashboard at `/recurring` or via the intent API:

```bash
curl -X POST http://127.0.0.1:8012/api/recurring \
  -H "Content-Type: application/json" \
  -d '{
    "name": "daily_report",
    "cron": "0 9 * * 1-5",
    "action_name": "send_report",
    "timezone": "America/New_York",
    "enabled": true
  }'
```

## Task dependencies

Use `depends_on` to chain tasks. Waiting tasks are unblocked automatically when their dependencies succeed; if a dependency fails or is cancelled, the waiting task is cascade-failed:

```bash
curl -X POST http://127.0.0.1:8012/api/tasks/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent_version": "v1",
    "task": {
      "description": "Deploy after build",
      "action_name": "deploy",
      "depends_on": [42]
    },
    "meta": { "source": "mage-lab-llm" }
  }'
```

## Mage Scheduler Tool

The `mage-scheduler-tool/` directory at the repo root contains a mage lab skill and Python tool that lets the assistant schedule tasks directly without constructing curl commands.

Copy the `mage-scheduler-tool` folder to `~/Mage/Tools` and enable it in **Settings → Tools → Community**. The assistant then has access to:

```
mage_scheduler_schedule_intent(intent_json)
mage_scheduler_preview_intent(intent_json)
mage_scheduler_list_tasks(limit)
mage_scheduler_cancel_task(task_id)
mage_scheduler_run_now(task_json)
mage_scheduler_open_dashboard()
mage_scheduler_start(port)
mage_scheduler_status()
```

## Running tests

```bash
# From the mage_scheduler/ directory:
uv run pytest tests/ -v
```

All 367 tests should pass. Tests use an in-memory SQLite database and mock Celery dispatch; no running Redis or worker is required.

## Notes
- Times in the UI are shown in local system time.
- SQLite DB file: `mage_scheduler.db`. Schema migrations run automatically on startup.
- Local artifacts are ignored via `mage_scheduler/.gitignore`.

## License

MIT — see [LICENSE](../LICENSE) at the repo root.
