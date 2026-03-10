---
name: mage-scheduler
description: Use this skill when the user wants to schedule, run, or manage tasks and actions using Mage Scheduler, including validation, previews, and dashboard/status operations.
metadata:
  short-description: Schedule and manage tasks with Mage Scheduler
---

# Mage Scheduler

Use this skill when the user wants to schedule tasks or manage actions, recurring tasks, and settings.

The scheduler starts automatically when this plugin is activated — no setup required.

## Mental model

**Actions** are reusable, vetted command templates registered by name (e.g. `backup_home`, `ask_assistant`). Create an Action once; schedule it many times.

**Tasks** are individual scheduled runs — a specific execution of a command or Action at a specific time.

**Recurring tasks** are cron-driven wrappers that automatically spawn a new Task each time they fire.

You will mostly schedule tasks by referencing an Action name. Use a raw `command` only when no suitable Action exists.

## Quick start

Call `scheduler_context` first. It returns in one call:
- Whether the service is running
- All available Actions and their allowed env keys
- Recent tasks with status and any errors
- Task counts by status
- Allowed command/cwd directories

## Available MCP Tools

### Orientation
- `scheduler_context` — bootstrap call: service status + actions + recent tasks + stats + validation
- `scheduler_status` — lightweight liveness check

### Scheduling
- `scheduler_schedule_intent(intent_json)` — primary scheduling tool (one-off, recurring, chained)
- `scheduler_preview_intent(intent_json)` — validate and preview timing without creating a task
- `scheduler_run_now(task_json)` — dispatch a command for immediate execution

### Task inspection & management
- `scheduler_list_tasks(limit, status)` — list tasks; filter by status e.g. `"scheduled,running"`
- `scheduler_get_task(task_id)` — full task detail: command, result output, error, retry count, deps
- `scheduler_get_dependencies(task_id)` — dependency graph
- `scheduler_cancel_task(task_id)` — cancel a scheduled/running/waiting task
- `scheduler_cleanup` — delete all terminal tasks

### Recurring tasks
- `scheduler_list_recurring` — list all recurring tasks with schedule, next run, enabled status
- `scheduler_toggle_recurring(recurring_id)` — enable or disable a recurring task
- `scheduler_delete_recurring(recurring_id)` — permanently delete a recurring task

### Actions management
- `scheduler_list_actions` — list all actions
- `scheduler_create_action(action_json)` — register a new action
- `scheduler_update_action(action_id, action_json)` — update an action
- `scheduler_delete_action(action_id)` — delete an action

### Validation & settings
- `scheduler_get_validation` — get allowed command/cwd directories

### Dashboard
- `scheduler_open_dashboard` — open task dashboard in browser
- `scheduler_open_actions` — open actions page
- `scheduler_open_settings` — open settings page

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
- Commands and `cwd` must fall within allowed directories; `scheduler_context` includes these.
- Use either `run_at` (datetime) or `run_in` (duration string) — not both. Omit both when `cron` is set.
- `timezone` defaults to `"UTC"` if omitted.
- `cron` — 5-field cron expression (e.g. `"0 9 * * 1"` = Monday 9am). Creates a RecurringTask.
- `depends_on` — list of `task_id` integers that must complete before this task runs.

## Common patterns

### Schedule a reminder to yourself

```json
{
  "intent_version": "v1",
  "task": {
    "description": "Reminder: check deployment status",
    "action_name": "ask_assistant",
    "env": { "MESSAGE": "Time to review the deployment." },
    "run_in": "2d",
    "timezone": "America/Los_Angeles"
  },
  "meta": { "source": "mage-lab-llm" }
}
```

### notify_on_complete

Set `"notify_on_complete": true` on any task where the outcome matters. The scheduler posts a structured notification to the assistant when the task finishes.

**Important:** These are automated scheduler messages. Process the result conversationally; only interrupt the user if the outcome requires attention.

## Error handling

- `status: "blocked"` in a schedule response → validation failed; `error` field explains why.
- Intent validation errors return `detail.errors[]` with `code`, `message`, and `hint`.
- Use `scheduler_get_task(task_id)` to inspect a failed task.
