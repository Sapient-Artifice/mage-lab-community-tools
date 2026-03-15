# Mage Scheduler Plugin

A task scheduler plugin for [Mage Lab](https://github.com/mage-lab/mage-lab). Schedule one-off commands, set up cron-driven recurring tasks, chain tasks with dependency graphs, and get completion notifications — all without any external services.

Drop the directory into `~/Mage/Skills/mage-scheduler/` and it works.

---

## Features

- **Zero external dependencies** — no Redis, no Celery, no message broker. APScheduler runs in-process.
- **One-off tasks** — schedule a command to run at a specific time or after a delay (`run_at`, `run_in`).
- **Recurring tasks** — cron-driven schedules (`0 9 * * 1` = every Monday at 9am) with per-timezone support.
- **Dependency chains** — `depends_on: [task_id, ...]` holds a task as `waiting` until its upstream tasks complete or cascade-fail it.
- **Actions** — reusable, vetted command templates. Register once, schedule many times. Restrict allowed env keys and working directories per action.
- **Retries** — configurable `max_retries` and `retry_delay` per task or action.
- **Completion notifications** — opt-in per task; posts a structured result back to the assistant when the task finishes.
- **Auto-cleanup** — configurable retention policy deletes old terminal tasks automatically.
- **Web dashboard** — Jinja2-rendered HTML UI at `http://127.0.0.1:8012` for task/action/settings management.
- **22 MCP tools** — full scheduling, inspection, and management surface exposed to the LLM via MCP stdio.
- **`/scheduler` slash command** — natural language scheduling or dashboard access in one keystroke.

---

## Installation

```bash
cp -r mage_scheduler_plugin ~/Mage/Skills/mage-scheduler
```

That's it. The plugin activates automatically the next time Claude Code starts (or when you reload plugins). The backend server starts on first use and persists between sessions — scheduled tasks continue firing even when Claude Code is closed.

### Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (used to run the plugin in an isolated venv)

All Python dependencies are managed by `pyproject.toml` and installed automatically by `uv run`.

---

## How It Works

```
Claude Code
    │
    ├── MCP stdio  ──►  mcp_server/__main__.py
    │                        │ starts (if not running)
    │                        ▼
    │                   uvicorn → mage_scheduler/api.py  (FastAPI)
    │                                   │
    │                                   ├── APScheduler (in-process)
    │                                   │     ├── beat_recurring  (every 60s)
    │                                   │     ├── beat_dependency (every 60s)
    │                                   │     └── beat_cleanup    (every 24h)
    │                                   │
    │                                   └── SQLite  (~/.mage_scheduler/scheduler.db)
    │
    └── /scheduler  ──►  commands/scheduler.md  (slash command)
```

**MCP server startup:** When Claude Code activates the plugin, `mcp_server/__main__.py` delegates to `mcp_server/backend.py` to check if the FastAPI backend is already running on the configured port. If not, `backend.py` spawns a `uvicorn` subprocess with `start_new_session=True` (detached from the MCP process), waits up to 15 seconds for it to become healthy, then the MCP stdio server starts. On subsequent activations the backend is already running and the health check passes immediately. The `scheduler_restart_backend` MCP tool uses the same `backend.py` logic to kill and respawn the backend on demand.

**Task execution:** Each task is stored as a `TaskRequest` row with `status = "scheduled"`. APScheduler fires `run_command(task_id, command)` at the scheduled time. The job reads the row, runs the command as a subprocess, writes stdout/stderr back to the row, and updates the status to `success` or `failed`.

---

## Core Concepts

### Actions

An **Action** is a named, reusable command template stored in the database.

```
Action: "backup_home"
  command:         /usr/local/bin/backup.sh
  default_cwd:     /home/user
  allowed_env:     ["DEST_PATH", "COMPRESSION"]
  max_retries:     2
  retry_delay:     300
```

Actions act as a security boundary: only whitelisted env keys can be passed in at schedule time, and allowed directory restrictions can be set per action. Create an action once; schedule it many times without repeating the command path.

### Tasks

A **Task** (`TaskRequest`) is a single scheduled execution. Fields:

| Field | Description |
|---|---|
| `id` | Integer primary key |
| `description` | Human-readable label |
| `command` | Shell command to run |
| `run_at` | UTC datetime to execute |
| `status` | `scheduled` → `running` → `success` / `failed` / `cancelled` |
| `celery_task_id` | APScheduler job ID (used for cancellation) |
| `result` | Captured stdout (truncated to 4000 chars) |
| `error` | Captured stderr or failure reason |
| `action_name` | Source action if scheduled via an action |
| `env_json` | JSON dict of env vars injected into the subprocess |
| `cwd` | Working directory override |
| `notify_on_complete` | Post completion notification to assistant |
| `max_retries` / `retry_count` / `retry_delay` | Retry configuration |
| `retain_result` | Exempt from automatic cleanup |
| `recurring_task_id` | Link back to the parent `RecurringTask` |

### Recurring Tasks

A **RecurringTask** holds a cron schedule and spawns a new `TaskRequest` each time it fires. The beat job (`check_recurring_tasks`) runs every 60 seconds, finds tasks whose `next_run_at <= now`, spawns the task, and advances `next_run_at` to the next occurrence.

```
RecurringTask: "weekly_report"
  cron:      0 9 * * 1          ← Monday 09:00
  timezone:  America/New_York
  action:    generate_report
  enabled:   true
  next_run_at: 2026-03-16T14:00:00Z
```

### Dependency Chains

Set `depends_on: [task_id, ...]` to hold a task as `waiting` until all upstream tasks complete:

- If all upstream tasks reach `success` → the waiting task is scheduled.
- If any upstream task reaches `failed`, `cancelled`, or `blocked` → the waiting task is cascade-failed.
- A `cancelled` parent propagates `failed` (not `cancelled`) to dependents, so the error is surfaced.

The dependency beat job (`check_waiting_tasks`) re-evaluates all waiting tasks every 60 seconds.

---

## MCP Tools

All 21 tools are available via the `scheduler` MCP server. The naming convention is `scheduler_<action>`.

### Orientation
| Tool | Description |
|---|---|
| `scheduler_context` | Bootstrap call: service status, all actions, recent tasks, counts, validation rules |
| `scheduler_status` | Lightweight liveness check |

### Scheduling
| Tool | Description |
|---|---|
| `scheduler_schedule_intent(intent_json)` | Primary scheduling tool — one-off, recurring, and chained tasks |
| `scheduler_preview_intent(intent_json)` | Validate and preview timing without creating anything |
| `scheduler_run_now(task_json)` | Dispatch a command for immediate execution |

### Task Inspection & Management
| Tool | Description |
|---|---|
| `scheduler_list_tasks(limit, status)` | List tasks; filter by status e.g. `"scheduled,running"` |
| `scheduler_get_task(task_id)` | Full task detail: output, error, retry count, dependencies |
| `scheduler_get_dependencies(task_id)` | Dependency graph: `depends_on` + `blocking` lists |
| `scheduler_cancel_task(task_id)` | Cancel a scheduled/running/waiting task |
| `scheduler_cleanup` | Delete all terminal tasks now |

### Recurring Tasks
| Tool | Description |
|---|---|
| `scheduler_list_recurring` | List all recurring tasks with schedule and next run |
| `scheduler_toggle_recurring(recurring_id)` | Enable or disable a recurring task |
| `scheduler_delete_recurring(recurring_id)` | Permanently delete a recurring task |

### Actions
| Tool | Description |
|---|---|
| `scheduler_list_actions` | List all registered actions |
| `scheduler_create_action(action_json)` | Register a new action |
| `scheduler_update_action(action_id, action_json)` | Update an action |
| `scheduler_delete_action(action_id)` | Delete an action |

### Validation & Dashboard
| Tool | Description |
|---|---|
| `scheduler_get_validation` | Get allowed command/cwd directories |
| `scheduler_open_dashboard` | Open task dashboard in browser |
| `scheduler_open_actions` | Open actions management page |
| `scheduler_open_settings` | Open settings page |

### Backend Management
| Tool | Description |
|---|---|
| `scheduler_restart_backend` | Kill the running backend (if any) and start a fresh one; waits up to 15 s for readiness |

---

## Slash Command

Type `/scheduler` in Claude Code to open the dashboard or schedule from natural language:

```
/scheduler open                          → opens dashboard
/scheduler status                        → service health + recent tasks
/scheduler remind me to run the backup in 2 hours
/scheduler run echo hello every weekday at 9am Pacific
```

---

## Intent Schema (v1)

All scheduling goes through the `POST /api/tasks/intent` endpoint (or the `scheduler_schedule_intent` MCP tool), which accepts a structured intent object:

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Weekly database backup",
    "action_name": "backup_db",
    "command": "/usr/local/bin/backup.sh",
    "run_at": "2026-03-10T18:00:00",
    "run_in": "2h",
    "cron": "0 2 * * 0",
    "timezone": "America/New_York",
    "cwd": "/var/backups",
    "env": { "DEST": "/mnt/nas/backups" },
    "depends_on": [42, 43],
    "notify_on_complete": true,
    "max_retries": 2,
    "retry_delay": 300,
    "retain_result": false,
    "replace_existing": false
  },
  "replace_existing": false,
  "meta": {
    "source": "mage-lab-llm",
    "user_confirmed": true
  }
}
```

**Scheduling rules:**
- Use `action_name` when a matching action exists; fall back to `command` for ad-hoc tasks.
- Provide exactly one of `run_at`, `run_in`, or `cron`. Do not combine them.
- `run_in` accepts natural duration strings: `"30m"`, `"2h"`, `"1d"`, `"1w"`.
- `command` must be an absolute path (e.g. `/usr/bin/python3`, not `python3`).
- `env` is only allowed when `action_name` is set, and keys must be whitelisted by the action.
- `timezone` defaults to `"UTC"`. Affects cron scheduling and response display only — storage is always UTC.
- `cron` creates a `RecurringTask`. Incompatible with `run_at`, `run_in`, and `depends_on`.
- `replace_existing: true` cancels any existing `scheduled` or `waiting` tasks with the same description before creating the new one.

**Response statuses:**
- `"scheduled"` — task created successfully.
- `"recurring_scheduled"` — recurring task registered.
- `"blocked"` — validation failed; see `error` or `errors[]` for codes.

---

## Common Patterns

### Schedule a one-off task in 2 hours

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Run database vacuum",
    "action_name": "db_vacuum",
    "run_in": "2h"
  }
}
```

### Set up a cron job in a specific timezone

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Morning sync",
    "action_name": "sync_files",
    "cron": "0 8 * * 1-5",
    "timezone": "Europe/London"
  }
}
```

### Chain tasks — run step 2 after step 1

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Deploy step 2",
    "action_name": "deploy_backend",
    "run_in": "5m",
    "depends_on": [101]
  }
}
```

### Ask the assistant to follow up after a long task

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Post-training review",
    "action_name": "ask_assistant",
    "env": { "MESSAGE": "Training finished. Please review the validation metrics." },
    "run_in": "4h",
    "notify_on_complete": true
  }
}
```

### Replace the previous backup job with a new one

```json
{
  "intent_version": "v1",
  "task": {
    "description": "nightly backup",
    "action_name": "backup_home",
    "cron": "0 3 * * *"
  },
  "replace_existing": true
}
```

---

## Environment Variables

Set in `.claude-plugin/plugin.json` under `mcpServers.env`, or export before starting.

| Variable | Default | Description |
|---|---|---|
| `SCHEDULER_DATA_DIR` | `~/.mage_scheduler` | Directory for the SQLite database and log file |
| `SCHEDULER_PORT` | `8012` | Port the FastAPI backend listens on |
| `SCHEDULER_HOST` | `127.0.0.1` | Bind address for the FastAPI backend |

The backend log is written to `$SCHEDULER_DATA_DIR/scheduler.log`. If the backend fails to start, check there first.

---

## REST API

The FastAPI backend is also directly accessible. Base URL: `http://127.0.0.1:8012`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check; returns `{"status":"ok","uptime_seconds":N}` |
| `GET` | `/api/tasks` | List tasks (`?status=scheduled,running` to filter) |
| `GET` | `/api/tasks/{id}` | Get a single task |
| `POST` | `/api/tasks` | Create a task directly (JSON `TaskCreate` body) |
| `POST` | `/api/tasks/run_now` | Schedule a task for immediate execution |
| `POST` | `/api/tasks/intent` | Schedule via intent object (recommended) |
| `POST` | `/api/tasks/{id}/cancel` | Cancel a task |
| `GET` | `/api/tasks/{id}/dependencies` | Get dependency graph for a task |
| `GET` | `/api/tasks/stats` | Count tasks by status |
| `POST` | `/api/tasks/cleanup` | Manually trigger cleanup |
| `GET` | `/api/parse` | Parse a natural language string to an intent |
| `GET` | `/api/actions` | List actions |
| `POST` | `/api/actions` | Create an action |
| `PUT` | `/api/actions/{id}` | Update an action |
| `DELETE` | `/api/actions/{id}` | Delete an action |
| `GET` | `/api/recurring` | List recurring tasks |
| `POST` | `/api/recurring` | Create a recurring task directly |
| `PUT` | `/api/recurring/{id}` | Update a recurring task |
| `DELETE` | `/api/recurring/{id}` | Delete a recurring task |
| `POST` | `/api/recurring/{id}/toggle` | Enable/disable a recurring task |
| `GET` | `/api/settings` | Get global settings |
| `PUT` | `/api/settings` | Update global settings |
| `GET` | `/api/validation` | Get allowed command/cwd directory rules |

Interactive docs are available at `http://127.0.0.1:8012/docs`.

---

## Data Storage

All data lives in `$SCHEDULER_DATA_DIR` (default `~/.mage_scheduler`):

```
~/.mage_scheduler/
├── scheduler.db      ← SQLite database
└── scheduler.log     ← Backend stdout/stderr
```

**Tables:**

| Table | Description |
|---|---|
| `task_requests` | All scheduled and historical tasks |
| `actions` | Registered action templates |
| `recurring_tasks` | Cron schedules |
| `task_dependencies` | Dependency edges between tasks |
| `settings` | Global configuration (allowed dirs, cleanup policy) |

The database is created automatically on first run. No migrations are required for the current schema version.

---

## Subprocess Environment

Every task subprocess receives these environment variables in addition to the system environment:

| Variable | Value |
|---|---|
| `SCHEDULER_TASK_ID` | Integer task ID |
| `SCHEDULER_TRIGGERED_AT` | ISO 8601 UTC timestamp of when the job fired |
| `SCHEDULER_ACTION_NAME` | Action name, or empty string |

Plus any keys from the task's `env_json`.

---

## Project Structure

```
mage_scheduler_plugin/
├── .claude-plugin/
│   └── plugin.json              ← Plugin manifest (MCP server declaration)
├── commands/
│   └── scheduler.md             ← /scheduler slash command
├── SKILL.md                     ← MCP tool reference for the LLM
├── pyproject.toml               ← Dependencies and pytest config
│
├── mage_scheduler/              ← FastAPI application (sys.path root)
│   ├── api.py                   ← FastAPI routes + lifespan handler
│   ├── task_manager.py          ← TaskManager class (intent → DB row + dispatch)
│   ├── scheduler.py             ← APScheduler singleton + beat job registration
│   ├── dispatch.py              ← schedule_command / cancel_command shim
│   ├── db.py                    ← SQLAlchemy engine + SessionLocal factory
│   ├── models.py                ← ORM models
│   ├── schemas.py               ← Pydantic request/response schemas
│   ├── nl_parser.py             ← Natural language → ParsedRequest
│   ├── jobs/
│   │   ├── run_command.py       ← Task executor + dependency helpers + notify
│   │   ├── dependency_check.py  ← Beat job: unblock waiting tasks
│   │   ├── recurring_check.py   ← Beat job: spawn recurring task instances
│   │   └── cleanup.py           ← Beat job: delete old terminal tasks
│   └── templates/               ← Jinja2 HTML templates (dashboard, actions, settings)
│
├── mcp_server/
│   ├── __main__.py              ← Entry point: start backend → serve MCP stdio
│   ├── backend.py               ← Backend process management (start, health-check, restart)
│   └── tools.py                 ← 22 FastMCP tool definitions (httpx → REST API)
│
└── tests/
    ├── conftest.py              ← Pytest fixtures (in-memory DB, mocked scheduler)
    ├── test_api_action_endpoints.py      ← GET/POST/PUT/DELETE /api/actions
    ├── test_api_create_task_form.py      ← POST /tasks (HTML form; error → dashboard, success → redirect)
    ├── test_api_depends_on.py            ← depends_on validation in intent API
    ├── test_api_recurring_endpoints.py   ← /api/recurring CRUD and toggle
    ├── test_api_settings_endpoints.py    ← GET/POST /settings; dashboard cleanup pill
    ├── test_api_task_endpoints.py        ← /api/tasks CRUD, cancel, dependencies, health
    ├── test_backend_restart.py           ← mcp_server/backend.py: _is_ready, _find_backend_pid, restart_backend
    ├── test_beat_task.py                 ← APScheduler beat job wiring
    ├── test_cleanup.py                   ← cleanup beat job logic
    ├── test_dependency_runtime.py        ← dependency resolution at runtime
    ├── test_intent_api_core.py           ← /api/tasks/intent core scheduling paths
    ├── test_intent_api_recurring.py      ← /api/tasks/intent cron/recurring paths
    ├── test_intent_replace_existing.py   ← replace_existing cancellation logic
    ├── test_intent_utilities.py          ← intent helpers and edge cases
    ├── test_nl_parser.py                 ← natural language → ParsedRequest
    ├── test_recurring_beat_task.py       ← recurring beat job spawning logic
    ├── test_run_command.py               ← task executor: success, failure, retries, notify
    └── test_validate_depends_on.py       ← depends_on schema validation
    — 412 tests total
```

---

## Development

### Running Tests

```bash
cd mage_scheduler_plugin
uv run pytest tests/ -v
```

All 412 tests run in approximately 3 seconds against an in-memory SQLite database. No backend needs to be running.

### Test Architecture

Tests use two isolation strategies:

**`db_session` fixture** — a fresh in-memory SQLite session per test. Used for unit tests of functions that accept a session directly.

**Module-patching fixtures** — for functions that call `SessionLocal()` internally, the fixture monkeypatches the module attribute before the test:

```python
# conftest.py pattern
monkeypatch.setattr(jobs.run_command, "SessionLocal", Factory)
```

Available fixtures:
- `db_session` — bare SQLAlchemy session
- `nt_mem_db` — patches `jobs.run_command.SessionLocal`
- `dep_mem_db` — patches `jobs.dependency_check.SessionLocal`
- `rec_mem_db` — patches `jobs.recurring_check.SessionLocal`
- `cln_mem_db` — patches `jobs.cleanup.SessionLocal`
- `api_client` — full FastAPI `TestClient` with StaticPool shared DB; mocks APScheduler lifecycle and dispatch

APScheduler is never started during tests — `scheduler.start_scheduler` and `scheduler.stop_scheduler` are patched to no-ops, and `dispatch.schedule_command` returns a fake job ID string.

### Running the Backend Standalone

```bash
cd mage_scheduler_plugin/mage_scheduler
SCHEDULER_DATA_DIR=/tmp/sched_dev uv run uvicorn api:app --port 8012 --reload
```

The dashboard will be available at `http://127.0.0.1:8012`.

---

## Architecture Notes

### Backend Persistence

The uvicorn backend runs as a detached subprocess (`start_new_session=True`). It survives past the MCP server process and continues firing scheduled tasks between sessions. On next activation, the MCP server's health check detects it and skips the startup step.

### Windows Compatibility

The architecture is Windows-compatible in principle. Known remaining gaps:

- `signal.SIGTERM` is not available on Windows; cancellation of running tasks is best-effort.
- Subprocess shell behaviour differs (`cmd.exe` vs `bash`); absolute paths are required.
- File path separators in `allowed_command_dirs` checks use `os.path` and should be portable.

Full Windows support is tracked as a future improvement.
