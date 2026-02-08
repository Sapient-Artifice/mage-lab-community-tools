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
- `mage_scheduler_list_tasks(limit)`
- `mage_scheduler_list_actions()`
- `mage_scheduler_create_action(action_json)`
- `mage_scheduler_update_action(action_id, action_json)`
- `mage_scheduler_delete_action(action_id)`

## Workflow
1) Confirm the scheduler service is running.
   - Use `mage_scheduler_status()`; if not running, call `mage_scheduler_start()`.
2) If the user wants a reusable action, create or update an action first.
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
    "timezone": "America/Los_Angeles",
    "cwd": "/path/to/working/dir",
    "env": {"KEY": "VALUE"}
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

## Run-Now Schema
Use this structure for immediate execution:
```json
{
  "command": "/absolute/path/to/script.sh",
  "description": "Optional summary",
  "cwd": "/path/to/working/dir",
  "env": {"KEY": "VALUE"}
}
```

Rules:
- `command` is required and must be an absolute executable path.
- `env` is optional and should be a string-to-string map.

## Action Schema
```json
{
  "name": "backup_home",
  "description": "Back up home directory",
  "command": "/usr/local/bin/backup_home.sh",
  "default_cwd": "/usr/local/bin",
  "allowed_env": ["PROJECT_ID"],
  "allowed_command_dirs": ["/usr/local/bin"],
  "allowed_cwd_dirs": ["/usr/local/bin"]
}
```

## Error Handling
- If a request is blocked, the task will be created with `status: "blocked"` and `error` set to the reason.
- Intent validation errors return `detail.errors[]` objects with `code`, `message`, and optional `hint`.
- Use `mage_scheduler_get_validation()` to explain constraints to the user.

## Leaving Notifications for Future Self
- If a user wants the mage lab desktop app / or embedded LLM to do something specific at a later time you can schedule a reminder to self via this endpoint https://127.0.0.1:11115/ask_assistant
- Example ` /usr/bin/curl -s -X POST http://127.0.0.1:11115/ask_assistant -H 'Content-Type: application/json' -d '{"message": "It is time to do the thing now."}' `
