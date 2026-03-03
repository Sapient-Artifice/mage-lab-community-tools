---
name: mage-scheduler-tool
description: Use this skill when the user wants to schedule, run, or manage tasks and actions using Mage Scheduler, including validation, previews, and dashboard/status operations.
metadata:
  short-description: Schedule and manage tasks with Mage Scheduler
---

# Mage Scheduler Tool Skill

Use this skill when the user wants to schedule tasks via Mage Scheduler or manage actions/settings.

## Mental model

**Actions** are reusable, vetted command templates registered by name (e.g. `backup_home`, `ask_assistant`). Create an Action once; schedule it many times.

**Tasks** are individual scheduled runs — a specific execution of a command or Action at a specific time.

**Recurring tasks** are cron-driven wrappers that automatically spawn a new Task each time they fire.

You will mostly schedule tasks by referencing an Action name. Use a raw `command` only when no suitable Action exists.

## Quick start

At the start of any scheduling session, call `mage_scheduler_context()`. It returns in one call:
- Whether the service is running (and a start hint if not)
- All available Actions and their allowed env keys
- Recent tasks with status and any errors
- Task counts by status (see how many are scheduled, failed, etc.)
- Allowed command/cwd directories

After that, you have everything you need to schedule confidently.

If any tool returns a connection error, call `mage_scheduler_start()` — do not check status first on every call.

## Available Tools

### Orientation
- `mage_scheduler_context()` — bootstrap call: service status + actions + recent tasks + stats + validation
- `mage_scheduler_status()` — lightweight liveness check (api/worker ready, pids)

### Service lifecycle
- `mage_scheduler_start(port)` — start API and worker
- `mage_scheduler_stop()` — stop both services

### Scheduling
- `mage_scheduler_schedule_intent(intent_json)` — primary scheduling tool (one-off, recurring, chained)
- `mage_scheduler_preview_intent(intent_json)` — validate and preview timing without creating a task
- `mage_scheduler_run_now(task_json)` — dispatch a command for immediate execution

### Task inspection & management
- `mage_scheduler_list_tasks(limit, status)` — list tasks; filter by status e.g. `"scheduled,running"`
- `mage_scheduler_get_task(task_id)` — full task detail: command, result output, error, retry count, deps
- `mage_scheduler_get_dependencies(task_id)` — dependency graph: what this task depends on and what it blocks
- `mage_scheduler_cancel_task(task_id)` — cancel a scheduled/running/waiting task; cascades to dependents
- `mage_scheduler_cleanup()` — delete all terminal tasks (succeeded/failed/cancelled/blocked) to reduce noise

### Recurring tasks
- `mage_scheduler_list_recurring()` — list all recurring tasks with schedule, next run, enabled status
- `mage_scheduler_toggle_recurring(recurring_id)` — enable or disable a recurring task
- `mage_scheduler_delete_recurring(recurring_id)` — permanently delete a recurring task

### Actions management
- `mage_scheduler_list_actions()` — list all actions (name, command, allowed_env, retry policy)
- `mage_scheduler_create_action(action_json)` — register a new action
- `mage_scheduler_update_action(action_id, action_json)` — update an action (full replace)
- `mage_scheduler_delete_action(action_id)` — delete an action

### Validation & settings
- `mage_scheduler_get_validation()` — get allowed command/cwd directories; check when a path is rejected

### Dashboard
- `mage_scheduler_open_dashboard()` — open task dashboard in browser
- `mage_scheduler_open_actions()` — open actions page
- `mage_scheduler_open_settings()` — open settings page

## Recommended workflow

1. Call `mage_scheduler_context()` to orient yourself.
2. If an Action exists for what the user wants, schedule it by `action_name`.
   - If a needed Action doesn't exist yet, create it with `mage_scheduler_create_action()` first.
3. Preview with `mage_scheduler_preview_intent()` when user confirmation is needed.
4. Schedule with `mage_scheduler_schedule_intent()` (or `mage_scheduler_run_now()` for immediate execution).
5. Confirm with `mage_scheduler_list_tasks(status="scheduled,running")` or open the dashboard.
6. After sessions with many cancelled/duplicate tasks, call `mage_scheduler_cleanup()`.

## Intent Schema (v1)

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
    "retry_delay": 60,
    "retain_result": false
  },
  "replace_existing": false,
  "meta": {
    "source": "mage-lab-llm",
    "user_confirmed": true
  }
}
```

Rules:
- Prefer `action_name`; use `command` only when no action exists.
- `intent_version` accepts `v1`, `1`, or `1.0`.
- `command` must be an absolute executable path.
- `env` is only allowed with `action_name` and must be whitelisted by the action.
- Commands and `cwd` must fall within allowed directories; `mage_scheduler_context()` includes these.
- Use either `run_at` (datetime) or `run_in` (duration string) — not both. Omit both when `cron` is set.
- `timezone` defaults to `"UTC"` if omitted; required for correct `run_at` interpretation.
- `max_retries` (default `0`) — automatic retry attempts on failure. Per-task override; inherits from action.
- `retry_delay` (default `60`) — seconds between retry attempts.
- `retain_result` (default `false`) — when `true`, the task is excluded from auto-cleanup.
- `replace_existing` (top-level field, default `false`) — when `true`, cancels any `scheduled` or `waiting` task with the same `description` before creating the new one. Response includes `replaced_task_ids`.
- `cron` — 5-field cron expression (e.g. `"0 9 * * 1"` = Monday 9am). Creates a RecurringTask. `run_at`/`run_in` must be omitted. The `description` becomes the unique recurring task name.
- `depends_on` — list of `task_id` integers that must complete successfully before this task runs. Not compatible with `cron`.

### cron — recurring tasks

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

Response has `"status": "recurring_scheduled"` and `next_run_at`. Manage with `mage_scheduler_list_recurring()` and `mage_scheduler_toggle_recurring()`.

**Common cron patterns:**

| Cron | Meaning |
|------|---------|
| `"0 9 * * 1"` | Every Monday at 9am |
| `"0 */6 * * *"` | Every 6 hours |
| `"*/5 * * * *"` | Every 5 minutes |
| `"0 0 * * *"` | Daily at midnight |
| `"0 8 1 * *"` | 1st of each month at 8am |

### run_in — relative delay shorthand

| Value | Meaning |
|-------|---------|
| `"30m"` | 30 minutes from now |
| `"2h"` | 2 hours from now |
| `"1d"` | 1 day from now |
| `"90s"` | 90 seconds from now |

### depends_on — task chaining

Use `depends_on` to chain tasks. Three scheduling outcomes:
- All deps succeeded → task is scheduled immediately (`status: "scheduled"`)
- Any dep already failed/cancelled → task is created as `failed` immediately
- At least one dep still in-flight → task is created as `waiting`; auto-scheduled when all deps succeed, or failed if any dep fails/cancels

After scheduling a dependency chain, use `mage_scheduler_get_dependencies(task_id)` to inspect the graph.

## Common patterns

### Schedule a reminder to yourself

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Reminder: check deployment status",
    "action_name": "ask_assistant",
    "env": { "MESSAGE": "Time to review the deployment. Check build logs and confirm status." },
    "run_in": "2d",
    "timezone": "America/Los_Angeles"
  },
  "meta": { "source": "mage-lab-llm" }
}
```

Always use `action_name: "ask_assistant"` for future messages to yourself. `MESSAGE` is the only allowed env key.

### Run a command now with completion notification

```json
{
  "command": "/usr/local/bin/backup_home.sh",
  "description": "Manual backup run",
  "notify_on_complete": true
}
```

Pass this to `mage_scheduler_run_now()`.

### Replace a stale scheduled task

Set `replace_existing: true` at the top level of the intent — the scheduler will cancel any existing `scheduled` or `waiting` task with the same description before creating the new one:

```json
{
  "intent_version": "v1",
  "task": {
    "description": "daily backup",
    "action_name": "backup_home",
    "run_in": "1d"
  },
  "replace_existing": true,
  "meta": { "source": "mage-lab-llm" }
}
```

The response includes `replaced_task_ids` listing what was cancelled. This prevents stale entries from accumulating when rescheduling.

### Clean up after a messy session

```python
mage_scheduler_cleanup()   # remove all terminal tasks
mage_scheduler_list_tasks(status="scheduled,running,waiting")  # verify what remains
```

## notify_on_complete — closing the feedback loop

Set `"notify_on_complete": true` on any task where the outcome matters. The scheduler posts a structured notification to the assistant when the task finishes:

```
[MAGE SCHEDULER — AUTOMATED TASK NOTIFICATION]
Task ID: 43 | Status: SUCCESS | Action: backup_home
Description: Back up home directory
Completed: 2026-02-24T18:03:22Z | Exit code: 0
Output:
Backup completed. 2.3GB written to /backup/db_20260224.tar.gz
```

**Important:** These are automated scheduler messages, not user input. Do not address them to the user as if they just spoke. Process the result, surface it conversationally if appropriate, and only interrupt the user if the outcome requires their attention.

## Cancelling tasks

`mage_scheduler_cancel_task(task_id)` works on tasks with status `scheduled`, `running`, or `waiting`. Cancelling cascades: all waiting tasks that depend on the cancelled task are immediately failed. Cancelled tasks cannot be un-cancelled; create a new task if needed.

## Error handling

- Connection error from any tool → call `mage_scheduler_start()` then retry.
- `status: "blocked"` in a schedule response → validation failed; `error` field explains why. Use `mage_scheduler_get_validation()` to check allowed paths.
- Intent validation errors return `detail.errors[]` with `code`, `message`, and `hint`.
- Use `mage_scheduler_get_task(task_id)` to inspect a failed or unexpected task — it includes the full error message, result output, and retry count.

## Run-Now Schema

```json
{
  "command": "/absolute/path/to/script.sh",
  "description": "Optional summary",
  "cwd": "/path/to/working/dir",
  "notify_on_complete": false
}
```

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

`max_retries` and `retry_delay` set the default retry policy for all tasks using this action. Per-task intent values override these.
