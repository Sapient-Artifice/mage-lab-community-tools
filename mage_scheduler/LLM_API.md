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

Only valid for tasks with status `scheduled` or `running`. Returns `{"status": "cancelled", "task_id": N}` or a 400 if the task is already in a terminal state.

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
    "notify_on_complete": false
  },
  "meta": {
    "source": "mage-lab-llm",
    "user_confirmed": true
  }
}
```

### Rules
- Prefer `action_name` when possible. It maps to a user-defined Action.
- Use `command` only if no Action exists; it must be an absolute executable path.
- Provide either `run_at` (ISO datetime) or `run_in` (duration string) — not both.
- `run_in` accepts durations like `"30m"`, `"2h"`, `"1d"`, `"90s"`. Time is computed from now in UTC.
- `timezone` must be an IANA timezone (e.g., `America/Los_Angeles`). Defaults to `"UTC"` if omitted; primarily affects how `scheduled_at_local` is displayed in the response.
- `intent_version` accepts `v1`, `1`, or `1.0` and is normalized to `v1`.
- `env` is only allowed when `action_name` is provided, and keys must be in the Action's allowlist.
- `cwd` must be an absolute path when provided.
- Commands and `cwd` must fall under the allowed directory settings (global or action-specific).
- Set `notify_on_complete: true` to receive an automated message via the ask_assistant endpoint when the task finishes. The notification includes task ID, status, exit code, and truncated output.

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

Other validation failures return the same `code`/`message`/`hint` structure.

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
