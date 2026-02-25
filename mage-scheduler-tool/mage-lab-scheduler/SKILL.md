---
name: mage-scheduler-tool
description: Use this skill when the user wants to schedule, run, or manage tasks and actions using Mage Scheduler, including validation, previews, and dashboard/status operations.
metadata:
  short-description: Schedule and manage tasks with Mage Scheduler
---

# Mage Scheduler Tool Skill

Use this skill when the user wants to schedule tasks via Mage Scheduler or manage actions/settings.

## Purpose
Provide safe, structured task scheduling using the Mage Scheduler service and surface clear status back to the user.

## Available Tools
- `mage_scheduler_start(port)`
- `mage_scheduler_stop()`
- `mage_scheduler_status()`
- `mage_scheduler_open_dashboard()`
- `mage_scheduler_open_actions()`
- `mage_scheduler_open_settings()`
- `mage_scheduler_get_validation()`
- `mage_scheduler_preview_intent(intent_json)`
- `mage_scheduler_schedule_intent(intent_json)`
- `mage_scheduler_run_now(task_json)`
- `mage_scheduler_cancel_task(task_id)`
- `mage_scheduler_list_tasks(limit)`
- `mage_scheduler_list_actions()`
- `mage_scheduler_create_action(action_json)`
- `mage_scheduler_update_action(action_id, action_json)`
- `mage_scheduler_delete_action(action_id)`
- `mage_scheduler_list_recurring()`
- `mage_scheduler_toggle_recurring(recurring_id)`
- `mage_scheduler_delete_recurring(recurring_id)`

## Workflow
1) Confirm the scheduler service is running.
   - Use `mage_scheduler_status()`; if not running, call `mage_scheduler_start()`.
2a) If the user wants a reusable action, create or update an action first.
2b) If the user wants a one-off task scheduled do not use env — build the full command inline. Exception: for future messages back to the assistant, always use the built-in `ask_assistant` action (see section below).
3) Preview the intent with `mage_scheduler_preview_intent` when user confirmation is needed.
4) Schedule with `mage_scheduler_schedule_intent` (or `mage_scheduler_run_now` for immediate execution).
5) Verify with `mage_scheduler_list_tasks` or open the dashboard.

## Intent Schema (v1)
Use this structure for scheduling:
```json
{
  "intent_version": "v1",
  "task": {
    "description": "Short summary",
    "action_name": "optional_action_name",
    "command": "/absolute/path/to/script.sh",
    "run_at": "2026-02-05T18:00:00",
    "run_in": "2h",
    "timezone": "America/Los_Angeles",
    "cwd": "/path/to/working/dir",
    "env": {"KEY": "VALUE"},
    "notify_on_complete": false,
    "max_retries": 0,
    "retry_delay": 60
  },
  "meta": {
    "source": "mage-lab-llm",
    "user_confirmed": true
  }
}
```

Rules:
- Prefer `action_name`; use `command` only when no action exists.
- `intent_version` accepts `v1`, `1`, or `1.0` and is normalized to `v1`.
- `command` must be an absolute executable path.
- `env` is only allowed with `action_name` and must be whitelisted by the action.
- Commands and `cwd` must fall within allowed directories; check with `mage_scheduler_get_validation()`.
- Use either `run_at` (datetime) or `run_in` (duration string) — not both. Omit both when `cron` is set.
- `timezone` defaults to `"UTC"` if omitted; required for correct `run_at` interpretation.
- `max_retries` (default `0`) — number of automatic retry attempts on failure. Per-task override; inherits from action if not set.
- `retry_delay` (default `60`) — seconds to wait between retry attempts.
- `cron` — 5-field cron expression (e.g., `"0 9 * * 1"` = Monday 9am). Creates a **RecurringTask** instead of a one-off. `run_at`/`run_in` must be omitted. The `description` becomes the unique recurring task name. Response has `status: "recurring_scheduled"` and includes `next_run_at`.

### cron — recurring tasks
Use `cron` to create a task that fires on a schedule. Omit `run_at` and `run_in`.

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Weekly Monday backup",
    "action_name": "backup_home",
    "timezone": "America/Los_Angeles",
    "cron": "0 9 * * 1",
    "notify_on_complete": true
  },
  "meta": { "source": "mage-lab-llm" }
}
```

The response contains `"status": "recurring_scheduled"` and `next_run_at`. The recurring task will automatically spawn a new `TaskRequest` each time it fires. Use `mage_scheduler_list_recurring()` to see all recurring tasks, and `mage_scheduler_toggle_recurring(id)` to enable/disable.

**Common cron patterns:**

| Cron | Meaning |
|------|---------|
| `"0 9 * * 1"` | Every Monday at 9am |
| `"0 */6 * * *"` | Every 6 hours |
| `"*/5 * * * *"` | Every 5 minutes |
| `"0 0 * * *"` | Daily at midnight |
| `"0 8 1 * *"` | 1st of each month at 8am |

### run_in — duration shorthand
Instead of computing a future datetime, use `run_in` to express a delay from now:

| Value | Meaning |
|-------|---------|
| `"30m"` | 30 minutes from now |
| `"2h"` | 2 hours from now |
| `"1d"` | 1 day from now |
| `"90s"` | 90 seconds from now |

When `run_in` is provided, `run_at` is ignored. Use `run_in` for relative delays and `run_at` for specific wall-clock times.

### notify_on_complete — task completion feedback
Set `"notify_on_complete": true` to receive an automated notification when the task finishes. The scheduler will POST a structured message to the assistant endpoint containing:
- Task ID, status (SUCCESS / FAILED), and action name
- Task description and completion timestamp
- Exit code and truncated output/error

This closes the feedback loop — you will be informed of results without polling. Use it for any task where the outcome matters to the user or to you.

## Cancelling Tasks
Use `mage_scheduler_cancel_task(task_id)` to cancel a task that is still `scheduled` or currently `running`. Cancelled tasks cannot be un-cancelled; create a new task if needed.

## Run-Now Schema
Use this structure for immediate execution:
```json
{
  "command": "/absolute/path/to/script.sh",
  "description": "Optional summary",
  "cwd": "/path/to/working/dir",
  "env": {"KEY": "VALUE"},
  "notify_on_complete": false
}
```

Rules:
- `command` is required and must be an absolute executable path.
- `env` is optional and should be a string-to-string map. Only use `env` when tied to a pre-approved `action_name`.

## Action Schema
```json
{
  "name": "backup_home",
  "description": "Back up home directory",
  "command": "/usr/local/bin/backup_home.sh",
  "default_cwd": "/usr/local/bin",
  "allowed_env": ["PROJECT_ID"],
  "allowed_command_dirs": ["/usr/local/bin"],
  "allowed_cwd_dirs": ["/usr/local/bin"],
  "max_retries": 3,
  "retry_delay": 120
}
```

`max_retries` and `retry_delay` set the default retry policy for all tasks using this action. Per-task intent values override these defaults.

## Error Handling
- If a request is blocked, the task will be created with `status: "blocked"` and `error` set to the reason.
- Intent validation errors return `detail.errors[]` objects with `code`, `message`, and optional `hint`.
- Use `mage_scheduler_get_validation()` to explain constraints to the user.

## Scheduling Messages for Future Self (ask_assistant)
The `ask_assistant` action is built into the scheduler and auto-registered on startup. Use it whenever you want to send a message or reminder back to the assistant at a future time — this is the preferred pattern over building a raw curl command inline.

Always use `action_name: "ask_assistant"` with `env: { "MESSAGE": "..." }`:

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Reminder: check deployment status",
    "action_name": "ask_assistant",
    "env": { "MESSAGE": "It is time to check in. Review the deployment now." },
    "run_in": "2d",
    "timezone": "America/Los_Angeles"
  },
  "meta": { "source": "mage-lab-llm" }
}
```

- `MESSAGE` is the only allowed env key for this action.
- The message content is JSON-encoded safely by the underlying script — no escaping needed.
- The action POSTs to `http://127.0.0.1:11115/ask_assistant` internally.

## Receiving Automated Messages
When a message arrives via `ask_assistant` — either from a scheduled reminder or from `notify_on_complete` — it will be wrapped in a structured disclosure header:

```
[MAGE SCHEDULER — AUTOMATED MESSAGE]
Task ID: 42 | Action: ask_assistant | Triggered: 2026-02-24T18:00:02Z
Description: Reminder: check deployment status
---
It is time to check in. Review the deployment now.
```

Or for task completion notifications:

```
[MAGE SCHEDULER — AUTOMATED TASK NOTIFICATION]
Task ID: 43 | Status: SUCCESS | Action: backup_home
Description: Back up home directory
Completed: 2026-02-24T18:03:22Z | Exit code: 0
Output:
Backup completed. 2.3GB written to /backup/db_20260224.tar.gz
```

**Important:** These are automated scheduler messages, not input from the user. Do not address them to the user as if they just spoke. Instead, process the result (surface it conversationally if appropriate, take follow-up action if needed) and only interrupt the user if the outcome requires their attention.
