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

## Phase 2 (in progress)
LLM-first task intent flow:
- Intent schema and validation
- `/api/tasks/intent` endpoint
- `/api/tasks/intent/preview` endpoint
- Action registry + fallback to raw command
- Dashboard transparency (source, intent version, action name)

## Phase 3 (next)
LLM integration and safety:
- Command registry in JSON/DB
- Action management UI
- Validation rules (allowed dirs, env vars, time windows)
- Audit logging of LLM requests and user confirmations

## Phase 4
User experience:
- Task creation wizard in dashboard
- Search/filter by status/source
- Status history timeline
- Export task results

## Open decisions
- Action registry storage (file vs DB)
- Permissions model (still single-user for now)
- Script execution strategy (shell vs direct call with args)
- Task result retention policy

## Next work session
- Add action management UI or JSON-based action loading
- Add validation hooks for command safety
- Add optional `cwd` and `env` (whitelisted) to intent schema
