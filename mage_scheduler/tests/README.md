# Mage Scheduler — Test Suite

## Running the tests

```bash
# From the mage_scheduler/ directory:
uv run pytest tests/ -v
```

No running Redis, Celery worker, or API server required. All tests use an in-memory SQLite database and mock Celery dispatch.

**398 tests, all passing.**

---

## Fixtures (`conftest.py`)

| Fixture | Scope | What it provides |
|---------|-------|------------------|
| `db_session` | function | Bare in-memory SQLite session — for pure unit tests that need a DB but no API layer |
| `api_client` | function | Full FastAPI `TestClient` with a StaticPool in-memory DB shared across `api` and `tasks.task_manager`; `_validate_command`, `_validate_cwd`, and `run_command_at.apply_async` are mocked. Yields `(client, Factory)` |
| `nt_mem_db` | function | Patches `tasks.notification_task.SessionLocal`; yields `Factory` |
| `dep_mem_db` | function | Patches `tasks.dependency_task.SessionLocal` + `init_db`; yields `Factory` |
| `rec_mem_db` | function | Patches `tasks.recurring_task.SessionLocal` + `init_db`; yields `Factory` |

### Helper factories

| Helper | Description |
|--------|-------------|
| `make_task(session, *, status, command)` | Creates and flushes a minimal `TaskRequest` |
| `make_action(session, *, name, command, ...)` | Creates and flushes a minimal `Action` |
| `make_recurring(session, *, name, cron, command, ...)` | Creates and flushes a minimal `RecurringTask` |

---

## Test files

### API — task endpoints (`test_api_task_endpoints.py`) — 42 tests
Covers the core task REST surface:
- `GET /api/tasks` — list, ordering, `?status=` filter (single, comma-separated, no-match, unknown, omitted)
- `GET /api/tasks/{id}` — found, 404
- `GET /api/tasks/{id}/dependencies` — empty graph, upstream deps, blocking deps
- `POST /api/tasks/{id}/cancel` — status guards, cascade to dependents, Celery revoke, 404
- `POST /api/tasks` — direct JSON create
- `POST /api/tasks/run_now`
- `GET /api/validation`
- `GET /health`

### API — action endpoints (`test_api_action_endpoints.py`) — 30 tests
Covers the actions REST surface and its private validation helpers:
- `_validate_dirs_list` — None passthrough, empty list, relative paths, nonexistent dirs
- `_validate_action_payload` — command/cwd dir mismatches, outside-settings rejections
- `GET /api/actions` — list, ordering
- `POST /api/actions` — create, duplicate name, field persistence, retry clamping
- `PUT /api/actions/{id}` — update, 404, name conflict, self-rename allowed
- `DELETE /api/actions/{id}` — delete, 404

### API — recurring endpoints (`test_api_recurring_endpoints.py`) — 34 tests
Covers the recurring task REST surface and `_recurring_from_payload`:
- `_recurring_from_payload` — invalid cron/timezone, missing command/action, env validation, name uniqueness, retry clamping, `next_run_at` population
- `GET /api/recurring` — list, ordering
- `POST /api/recurring` — create, validation errors, defaults
- `PUT /api/recurring/{id}` — update, 404, name conflict, self-rename allowed
- `DELETE /api/recurring/{id}` — delete, 404
- `POST /api/recurring/{id}/toggle` — enable→disable, disable→enable, re-arm `next_run_at` on enable, 404

### API — settings endpoints (`test_api_settings_endpoints.py`) — 5 tests
- Settings error path: cleanup state preserved on dir validation failure
- Dashboard cleanup pill: shown/hidden based on settings state

### Intent API — core (`test_intent_api_core.py`) — 34 tests
Covers `POST /api/tasks/intent` and `POST /api/tasks/intent/preview` for the one-shot (non-dependency, non-cron) path:
- Intent version validation and aliasing (`v1`, `1`, `1.0`)
- Timezone validation
- Command / action resolution
- Env key allowlist enforcement
- `run_in` / `run_at` parsing and scheduling
- Retry field inheritance (task overrides action defaults, clamping)
- `source` metadata persistence
- Action `cwd` resolution
- Preview endpoint: no DB write, validation errors return 400

### Intent API — recurring (`test_intent_api_recurring.py`) — 28 tests
Covers `_handle_recurring_intent` via `POST /api/tasks/intent` when `cron` is set:
- Pre-validation: invalid cron, `cron` + `run_at`/`run_in` exclusivity, `depends_on` unsupported, blank description (`recurring_name_required`)
- Name uniqueness: duplicate description returns `blocked`; distinct descriptions both succeed
- Command path: missing command/action, env without action
- Action path: unknown action, env allowlist, action cwd resolution
- DB state: recurring task persisted, `next_run_at` populated
- Retry field inheritance (action defaults, task overrides)
- `scheduled_at_local` reflects the requested timezone (not UTC)

### Intent API — `depends_on` (`test_api_depends_on.py`) — 8 tests
Covers the dependency scheduling outcomes via `POST /api/tasks/intent`:
- Nonexistent dep ID → `blocked`
- Already-failed/cancelled dep → `failed` (immediate)
- In-flight dep → `waiting`
- All deps succeeded → `scheduled`
- `cron` + `depends_on` → 400
- Duplicate dep IDs are deduplicated
- Dep IDs persisted for `waiting` tasks

### Intent API — `replace_existing` (`test_intent_replace_existing.py`) — 13 tests
Covers the `replace_existing: true` behaviour on `POST /api/tasks/intent`:
- Cancels matching `scheduled` and `waiting` tasks before creating the new one
- Cancels multiple matches; new task is always created
- Terminal states (`succeeded`, `failed`, `cancelled`, `blocked`) and `running` tasks are not affected
- Only matches on description — other tasks are not touched
- `replace_existing: false` (default, explicit, and omitted) leaves existing tasks untouched
- `replaced_task_ids` is null when no tasks were replaced

### Intent utilities (`test_intent_utilities.py`) — 63 tests
Direct unit tests for private helpers in `api.py`:
- `_parse_run_in` — valid durations (`30m`, `2h`, `1d`, `90s`), invalid inputs
- `_normalize_intent_version` — aliasing, unsupported versions
- `_intent_error` / `_raise_intent_validation` — error construction and 400 raising
- `_parse_allowed_dirs` / `_parse_allowed_env` — parsing and edge cases
- `_is_path_allowed` — prefix matching against allowlists
- `_get_settings` — default and persisted settings retrieval

### Dependency validation (`test_validate_depends_on.py`) — 17 tests
Direct unit tests for `_validate_depends_on` and `_cascade_fail_dependents`:
- Empty dep list → `immediate_schedule`
- Nonexistent IDs → `invalid` error
- Terminal bad statuses (`failed`, `cancelled`, `blocked`) → `immediate_fail`
- All succeeded → `immediate_schedule`
- Mixed in-flight → `waiting`
- `_cascade_fail_dependents`: no-op with no dependents, fails waiting dependents, ignores non-waiting

### Dependency runtime (`test_dependency_runtime.py`) — 20 tests
Unit tests for the Celery dependency task helpers:
- `_trigger_dependents` — schedules newly-unblocked tasks, skips non-waiting
- `_try_unblock_task` — all deps succeeded, partial success, any dep failed
- `_schedule_waiting_task` — Celery dispatch, DB status update

### Beat task (`test_beat_task.py`) — 14 tests
Unit tests for `check_waiting_tasks` (the Celery beat task):
- Picks up waiting tasks whose deps have all succeeded
- Ignores non-waiting tasks
- Multiple tasks processed in one beat

### Recurring beat task (`test_recurring_beat_task.py`) — 18 tests
Unit tests for the recurring Celery beat task:
- `_compute_next_run` — timezone-aware cron computation
- `compute_initial_next_run` — returns a future UTC datetime
- `_spawn_task` — creates `TaskRequest`, dispatches to Celery, advances `next_run_at`, resolves action command, skips on missing action/command; verifies task row is committed before `apply_async` (guards against task_request_not_found race condition)
- `check_recurring_tasks` — fires due tasks, ignores future/disabled tasks, handles multiple due

### Notification task (`test_notification_task.py`) — 21 tests
Unit tests for `run_command_at` (the Celery execution task):
- Retry logic on non-zero exit codes
- Completion notification via `ask_assistant` when `notify_on_complete` is set
- Notification suppressed when `action_name == "ask_assistant"` (the action script sends its own message; a second notification would double-fire the endpoint)
- Environment variable injection
- Notification content: task ID, status, exit code, output

### Cleanup (`test_cleanup.py`) — 25 tests
Unit tests for the auto-cleanup beat task and `POST /api/tasks/cleanup`:
- `_do_cleanup`: no-op when disabled, deletes terminal tasks past retention cutoff
- Respects `retain_result` flag
- Manual cleanup endpoint deletes all terminal tasks regardless of retention

### Natural language parser (`test_nl_parser.py`) — 26 tests
Unit tests for `nl_parser.py` and `POST /api/parse`:
- `_parse_in_duration` — `"in 30 minutes"`, `"in 2 hours"`, edge cases
- `_parse_at_delimiter` — `"at 9am"`, `"tomorrow at noon"`, ambiguous inputs
- `parse_request` — end-to-end command + time extraction, confidence scoring
- `POST /api/parse` — happy path and error handling

---

## Design notes

**No external services.** All tests run fully offline. Celery `apply_async` is patched in fixtures; no broker connection is made.

**StaticPool for multi-module tests.** When multiple modules (e.g. `api` and `tasks.task_manager`) must share a single in-memory SQLite DB, the `api_client` fixture uses SQLAlchemy's `StaticPool` so all connections see the same in-memory state.

**Private function testing.** Internal helpers are imported directly (e.g. `from api import _validate_depends_on`) and tested in isolation. This keeps unit tests fast and makes failure attribution obvious.

**Fixture vs. `make_*` helpers.** DB fixtures (`api_client`, `dep_mem_db`, etc.) handle setup/teardown and monkeypatching. `make_task`, `make_action`, and `make_recurring` are plain functions that create rows inside a caller-provided session — they don't manage transactions or commits.
