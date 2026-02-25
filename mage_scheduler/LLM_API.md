# Mage Scheduler LLM API

This document defines the LLM-facing contract for creating tasks.

## Primary workflow
1) The LLM builds a structured intent.
2) The system validates it and returns a preview.
3) On user confirmation, the LLM submits the final intent to schedule.

## Endpoints

### Preview intent (no scheduling)
`POST /api/tasks/intent/preview`

### Schedule intent
`POST /api/tasks/intent`

### Run now
`POST /api/tasks/run_now`

### Cancel task
`POST /api/tasks/{task_id}/cancel`

Only valid for tasks with status `scheduled`, `running`, or `waiting`. Returns `{"status": "cancelled", "task_id": N}` or a 400 if the task is already in a terminal state. Cancelling a task immediately fails all tasks that depend on it (`waiting` dependents become `failed`).

### Task dependencies
`GET /api/tasks/{task_id}/dependencies`

Returns `{"task_id": N, "depends_on": [...], "blocking": [...]}` where `depends_on` lists the upstream tasks this task requires, and `blocking` lists the currently-waiting tasks that depend on it.

### Validation rules
`GET /api/validation`

### Create action
`POST /api/actions`

### Update action
`PUT /api/actions/{action_id}`

### Delete action
`DELETE /api/actions/{action_id}`

## Intent schema (v1)
```json
{
  "intent_version": "v1",
  "task": {
    "description": "Short user-facing summary",
    "action_name": "backup_home",
    "command": "/usr/local/bin/backup_home.sh",
    "run_at": "2026-02-05T18:00:00",
    "run_in": "2h",
    "timezone": "America/Los_Angeles",
    "cwd": "/usr/local/bin",
    "env": {
      "PROJECT_ID": "example"
    },
    "notify_on_complete": false,
    "max_retries": 0,
    "retry_delay": 60,
    "cron": null,
    "depends_on": null
  },
  "meta": {
    "source": "mage-lab-llm",
    "user_confirmed": true
  }
}
```

### Recurring task intent (cron)
When `cron` is set, omit `run_at` and `run_in`:
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

Response:
```json
{
  "status": "recurring_scheduled",
  "task_id": 1,
  "scheduled_at_local": "2026-02-28T09:00:00",
  "scheduled_at_utc": "2026-02-28T17:00:00Z",
  "command": "/usr/local/bin/backup_home.sh",
  "description": "Weekly Monday backup",
  "cron": "0 9 * * 1",
  "next_run_at": "2026-02-28T17:00:00Z",
  "warnings": []
}
```

### Recurring task management
```
GET    /api/recurring              list all recurring tasks
POST   /api/recurring              create recurring task
PUT    /api/recurring/{id}         update recurring task (full replace)
DELETE /api/recurring/{id}         delete recurring task
POST   /api/recurring/{id}/toggle  enable / disable
```

### Rules
- Prefer `action_name` when possible. It maps to a user-defined Action.
- Use `command` only if no Action exists; it must be an absolute executable path.
- Provide either `run_at` (ISO datetime) or `run_in` (duration string) — not both. Omit both when `cron` is set.
- `run_in` accepts durations like `"30m"`, `"2h"`, `"1d"`, `"90s"`. Time is computed from now in UTC.
- `timezone` must be an IANA timezone (e.g., `America/Los_Angeles`). Defaults to `"UTC"` if omitted; primarily affects how `scheduled_at_local` is displayed in the response.
- `intent_version` accepts `v1`, `1`, or `1.0` and is normalized to `v1`.
- `env` is only allowed when `action_name` is provided, and keys must be in the Action's allowlist.
- `cwd` must be an absolute path when provided.
- Commands and `cwd` must fall under the allowed directory settings (global or action-specific).
- Set `notify_on_complete: true` to receive an automated message via the ask_assistant endpoint when the task finishes. The notification includes task ID, status, exit code, and truncated output.
- `max_retries` (integer, default `0`) — number of automatic retry attempts on non-zero exit. Inherits from the action's policy; per-task value overrides.
- `retry_delay` (integer, default `60`) — seconds to wait between retry attempts. Retry attempts increment `retry_count` on the task row and reschedule in place. Notification (if enabled) fires only after the final attempt.
- `cron` (string, optional) — 5-field cron expression (e.g., `"0 9 * * 1"` for every Monday at 9am). When present, creates a **RecurringTask** instead of a one-off TaskRequest. `run_at` and `run_in` must be omitted. The `description` field becomes the unique recurring task name. Returns `status: "recurring_scheduled"` and includes `next_run_at`.
- `depends_on` (array of integers, optional) — list of `task_id` values that must complete successfully before this task runs. Cannot be used with `cron`. Three scheduling outcomes based on current dep statuses:
  - **All succeeded** → task is scheduled immediately (`status: "scheduled"`).
  - **Any failed/cancelled** → task is created as `failed` immediately (`warnings: ["dependency_failed"]`).
  - **At least one still in-flight** → task is created as `waiting` (`status: "waiting"`); it will be auto-scheduled when all deps succeed, or immediately failed if any dep fails/cancels.

## Example preview response
```json
{
  "status": "preview",
  "task_id": 0,
  "scheduled_at_local": "2026-02-05T18:00:00",
  "scheduled_at_utc": "2026-02-06T02:00:00Z",
  "command": "/usr/local/bin/backup_home.sh",
  "description": "Back up home directory",
  "action_name": "backup_home",
  "intent_version": "v1",
  "source": "mage-lab-llm",
  "cwd": "/usr/local/bin",
  "env_keys": ["PROJECT_ID"],
  "notify_on_complete": false,
  "warnings": []
}
```

## Example schedule response
```json
{
  "status": "scheduled",
  "task_id": 42,
  "scheduled_at_local": "2026-02-05T18:00:00",
  "scheduled_at_utc": "2026-02-06T02:00:00Z",
  "command": "/usr/local/bin/backup_home.sh",
  "description": "Back up home directory",
  "action_name": "backup_home",
  "intent_version": "v1",
  "source": "mage-lab-llm",
  "cwd": "/usr/local/bin",
  "env_keys": ["PROJECT_ID"],
  "notify_on_complete": false,
  "warnings": []
}
```

## Error responses (intent endpoints)
```json
{
  "detail": {
    "errors": [
      {
        "code": "unsupported_intent_version",
        "message": "Unsupported intent_version.",
        "hint": "intent_version must be 'v1' (aliases: '1', '1.0')."
      }
    ]
  }
}
```

```json
{
  "detail": {
    "errors": [
      {
        "code": "invalid_timezone",
        "message": "Invalid timezone.",
        "hint": "Use an IANA timezone like 'America/Los_Angeles'."
      }
    ]
  }
}
```

```json
{
  "detail": {
    "errors": [
      {
        "code": "run_in_invalid",
        "message": "run_in value is not a valid duration.",
        "hint": "Use a duration like '30m', '2h', '1d', or '90s'."
      }
    ]
  }
}
```

```json
{
  "detail": {
    "errors": [
      {
        "code": "run_at_or_run_in_required",
        "message": "Either run_at or run_in is required.",
        "hint": "Provide run_at (datetime) or run_in (duration string)."
      }
    ]
  }
}
```

```json
{
  "detail": {
    "errors": [
      {
        "code": "unknown_action",
        "message": "Unknown action_name.",
        "hint": "Create the action first or provide a command."
      }
    ]
  }
}
```

Other validation failures return the same `code`/`message`/`hint` structure, including:
- `depends_on_invalid` — one or more IDs in `depends_on` do not correspond to existing tasks.
- `depends_on_already_failed` — all IDs are valid but at least one dependency has already failed or been cancelled; results in an immediate `failed` task (not a 400).
- `depends_on_cron_unsupported` — `depends_on` cannot be combined with `cron`.

```json
{
  "detail": {
    "errors": [
      {
        "code": "command_must_be_absolute",
        "message": "Command must be an absolute path.",
        "hint": "Use an absolute path like /usr/local/bin/tool."
      }
    ]
  }
}
```

### Blocked tasks
When a task is blocked by validation, the API returns a task with `status: "blocked"`, `error` set to the failure reason, and an `errors` array with the same `code`/`message`/`hint` structure.

## Error responses (action endpoints)
```json
{
  "detail": "action_name_exists"
}
```

```json
{
  "detail": "action_command_dir_outside_settings"
}
```

```json
{
  "detail": "action_cwd_dir_outside_settings"
}
```

```json
{
  "detail": "action_command_dir_mismatch"
}
```

```json
{
  "detail": "action_cwd_dir_mismatch"
}
```
