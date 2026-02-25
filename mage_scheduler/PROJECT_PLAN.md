# Mage Scheduler Project Plan

## Goal
Provide a task scheduling service that accepts structured LLM task intents, validates them, schedules execution via Celery, and exposes clear user-facing visibility in a dashboard.

## Phase 1 (done)
- Celery + Redis scheduling
- SQLite persistence via SQLAlchemy
- FastAPI app with HTML dashboard
- Task list + detail view
- Task creation form
- Task deletion

## Phase 2 (done)
LLM-first task intent flow:
- Intent schema (v1) and validation
- `/api/tasks/intent` and `/api/tasks/intent/preview` endpoints
- Action registry + fallback to raw command
- Dashboard transparency (source, intent version, action name)
- `ask_assistant` built-in action for future self-messages
- Allowlist-based safety (commands, cwd, env vars)

## Phase 3 (done)
Feedback loop and UX:
- `run_in` duration shorthand (`"2h"`, `"30m"`, `"1d"`, `"90s"`)
- `notify_on_complete` — automated task completion notifications via ask_assistant
- Automated message disclosure headers (LLM can distinguish scheduler messages from user input)
- Task cancellation (`POST /api/tasks/{id}/cancel`)
- Schema auto-migration on startup

## Phase 4 (next)
Resilience and workflow:
- Retry policy on actions (max_retries, retry_delay)
- Task dependencies (`depends_on: [task_id]`)
- Recurrence / cron expressions
- Approval gate (`require_approval` on actions)
- Result retention / auto-cleanup of old terminal tasks
- Task stats endpoint (`GET /api/tasks/stats`)

## Phase 5
User experience:
- Task creation wizard in dashboard
- Search/filter by status/source/action
- Status history timeline
- Export task results
- Outbound webhooks on task completion

## Open decisions
- Permissions model (still single-user for now)
- Script execution strategy (shell vs direct call with args)
- Secret management for env vars at rest
