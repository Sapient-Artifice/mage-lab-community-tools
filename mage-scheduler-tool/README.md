# Mage Scheduler Community Tool

This tool connects mage lab to the Mage Scheduler service so the assistant can schedule tasks on your behalf.

> **Companion service:** This tool is the mage lab interface to the [`mage_scheduler`](../mage_scheduler/README.md) service. The tool handles assistant-side communication; the service handles execution. Both must be installed.

## Install
1) Copy the python file mage_scheduler_tool.py into `~/Mage/Tools`.
2. Copy the mage-lab-scheduler folder into `~/Mage/Skills`
2) Restart mage lab and enable the skill in Settings → Skills&Plugins.
3) Ensure the scheduler service is running (see below).

## Scheduler Service Setup
The tool expects the Mage Scheduler service to run locally (FastAPI + Celery).

Default service path:
- `~/Mage/Workspace/mage_scheduler` (based on your workspace path)

Override with env vars in `~/.config/magelab/.env`:
```
MAGE_SCHEDULER_HOME=/absolute/path/to/mage_scheduler
MAGE_SCHEDULER_PORT=8012
MAGE_SCHEDULER_URL=http://127.0.0.1:8012
MAGE_SCHEDULER_PYTHON=/absolute/path/to/python
```

If you use a dedicated venv, set `MAGE_SCHEDULER_PYTHON` to that venv's Python.

## Tool Functions
- `mage_scheduler_start(port)`
- `mage_scheduler_stop()`
- `mage_scheduler_status()`
- `mage_scheduler_open_dashboard()`
- `mage_scheduler_open_actions()`
- `mage_scheduler_open_settings()`
- `mage_scheduler_preview_intent(intent_json)`
- `mage_scheduler_schedule_intent(intent_json)`
- `mage_scheduler_run_now(task_json)`
- `mage_scheduler_cancel_task(task_id)`
- `mage_scheduler_list_tasks(limit)`
- `mage_scheduler_list_actions()`
- `mage_scheduler_get_validation()`
- `mage_scheduler_create_action(action_json)`
- `mage_scheduler_update_action(action_id, action_json)`
- `mage_scheduler_delete_action(action_id)`

## Notes
- Logs are written to `~/.mage_scheduler/api.log` and `~/.mage_scheduler/worker.log` inside your workspace.
- The tool communicates with the scheduler via HTTP; the scheduler must be running for API calls to succeed.
- The tool uses the scheduler `/health` endpoint to confirm readiness.
- The `mage_scheduler_run_now` tool requires a JSON payload that includes a `command` field.

## Longer-term roadmap 
- Secrets/vault integration, RBAC & approval flows, better observability and retry policies, UI preview/confirm, recurrence & dependencies, hardened sandboxing.
