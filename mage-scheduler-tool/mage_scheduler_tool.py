import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from config import config
from utils.functions_metadata import function_schema
from ws_manager import open_url

DEFAULT_PORT = int(os.getenv("MAGE_SCHEDULER_PORT", "8012"))
BASE_URL = os.getenv("MAGE_SCHEDULER_URL", f"http://127.0.0.1:{DEFAULT_PORT}")
WORKSPACE_DIR = Path(config.workspace_path).expanduser().resolve()
STATE_DIR = WORKSPACE_DIR / ".mage_scheduler"
STATE_PATH = STATE_DIR / "service_state.json"
SERVICE_DIR = Path(os.getenv("MAGE_SCHEDULER_HOME", str(WORKSPACE_DIR / "mage_scheduler"))).expanduser().resolve()
PYTHON_BIN = os.getenv("MAGE_SCHEDULER_PYTHON", sys.executable)


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    _ensure_state_dir()
    tmp_path = STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(STATE_PATH)


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _resolve_base_url(state: Optional[Dict[str, Any]] = None) -> str:
    env_url = os.getenv("MAGE_SCHEDULER_URL")
    if env_url:
        return env_url
    env_port = os.getenv("MAGE_SCHEDULER_PORT")
    if env_port:
        return f"http://127.0.0.1:{int(env_port)}"
    if state:
        if state.get("base_url"):
            return str(state["base_url"])
        if state.get("port"):
            return f"http://127.0.0.1:{int(state['port'])}"
    return f"http://127.0.0.1:{DEFAULT_PORT}"


def _current_base_url() -> str:
    return _resolve_base_url(_load_state())


def _service_ready(url: str) -> bool:
    try:
        resp = requests.get(f"{url}/health", timeout=1.5)
        return resp.ok
    except requests.RequestException:
        return False


def _worker_ready(url: str) -> bool:
    try:
        resp = requests.get(f"{url}/health/worker", timeout=1.5)
        if not resp.ok:
            return False
        data = resp.json()
        return bool(data.get("worker_alive"))
    except (requests.RequestException, ValueError):
        return False


def _spawn_process(args: list[str], cwd: Path, log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")
    return subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )


def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    base_url = _current_base_url()
    resp = requests.post(f"{base_url}{path}", json=payload, timeout=10)
    if not resp.ok:
        return {"error": resp.text, "status_code": resp.status_code}
    return resp.json()


def _get_json(path: str) -> Dict[str, Any]:
    base_url = _current_base_url()
    resp = requests.get(f"{base_url}{path}", timeout=10)
    if not resp.ok:
        return {"error": resp.text, "status_code": resp.status_code}
    return resp.json()


# ---------------------------------------------------------------------------
# Service lifecycle
# ---------------------------------------------------------------------------

@function_schema(
    name="mage_scheduler_start",
    description=(
        "Start the Mage Scheduler API and Celery worker. "
        "Call this if any other scheduler tool returns a connection error."
    ),
    required_params=[],
    optional_params=["port"],
)
def mage_scheduler_start(port: Optional[str] = None) -> str:
    port_value = int(port) if port else DEFAULT_PORT
    base_url = os.getenv("MAGE_SCHEDULER_URL", f"http://127.0.0.1:{port_value}")

    state = _load_state()
    api_pid = state.get("api_pid")
    worker_pid = state.get("worker_pid")

    if _pid_alive(api_pid) and _pid_alive(worker_pid) and _service_ready(base_url):
        return f"Scheduler already running at {base_url}."

    if not SERVICE_DIR.exists():
        return f"Service directory not found: {SERVICE_DIR}"

    api_log = STATE_DIR / "api.log"
    worker_log = STATE_DIR / "worker.log"

    api_proc = _spawn_process(
        [PYTHON_BIN, "-m", "uvicorn", "api:app", "--port", str(port_value)],
        SERVICE_DIR,
        api_log,
    )
    worker_proc = _spawn_process(
        [PYTHON_BIN, "-m", "celery", "-A", "celery_app", "worker", "--beat", "--loglevel=info"],
        SERVICE_DIR,
        worker_log,
    )

    state.update(
        {
            "api_pid": api_proc.pid,
            "worker_pid": worker_proc.pid,
            "port": port_value,
            "base_url": base_url,
            "started_at": time.time(),
        }
    )
    _save_state(state)

    time.sleep(1.0)
    if _service_ready(base_url):
        return f"Scheduler started at {base_url}."
    return f"Scheduler started but not yet ready. Check logs in {STATE_DIR}."


@function_schema(
    name="mage_scheduler_stop",
    description="Stop the Mage Scheduler API and worker services.",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_stop() -> str:
    state = _load_state()
    api_pid = state.get("api_pid")
    worker_pid = state.get("worker_pid")

    stopped = []
    for pid, label in ((api_pid, "api"), (worker_pid, "worker")):
        if _pid_alive(pid):
            try:
                os.kill(pid, 15)
                stopped.append(label)
            except OSError:
                pass

    state.update({"api_pid": None, "worker_pid": None})
    _save_state(state)

    if stopped:
        return f"Stopped: {', '.join(stopped)}."
    return "No running scheduler processes found."


@function_schema(
    name="mage_scheduler_status",
    description=(
        "Check whether the Mage Scheduler API and worker are alive. "
        "Returns base_url, pid status, and API/worker readiness."
    ),
    required_params=[],
    optional_params=[],
)
def mage_scheduler_status() -> str:
    state = _load_state()
    base_url = _resolve_base_url(state)
    api_pid = state.get("api_pid")
    worker_pid = state.get("worker_pid")
    api_ready = _service_ready(base_url)
    worker_ready = _worker_ready(base_url)

    status = {
        "base_url": base_url,
        "api_pid": api_pid,
        "worker_pid": worker_pid,
        "api_alive": _pid_alive(api_pid) or api_ready,
        "worker_alive": _pid_alive(worker_pid) or worker_ready,
        "ready": api_ready,
    }
    return json.dumps(status, indent=2)


# ---------------------------------------------------------------------------
# Dashboard / browser shortcuts
# ---------------------------------------------------------------------------

@function_schema(
    name="mage_scheduler_open_dashboard",
    description="Open the scheduler dashboard in the browser to review tasks and results visually.",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_open_dashboard() -> str:
    base_url = _current_base_url()
    open_url(f"{base_url}/")
    return f"Opened {base_url}/"


@function_schema(
    name="mage_scheduler_open_actions",
    description="Open the scheduler actions management page in the browser.",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_open_actions() -> str:
    base_url = _current_base_url()
    open_url(f"{base_url}/actions")
    return f"Opened {base_url}/actions"


@function_schema(
    name="mage_scheduler_open_settings",
    description="Open the scheduler settings page in the browser.",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_open_settings() -> str:
    base_url = _current_base_url()
    open_url(f"{base_url}/settings")
    return f"Opened {base_url}/settings"


# ---------------------------------------------------------------------------
# Context bootstrap (Phase 3)
# ---------------------------------------------------------------------------

@function_schema(
    name="mage_scheduler_context",
    description=(
        "Single bootstrap call to orient yourself before scheduling. "
        "Returns service status, available actions (name + allowed env), "
        "recent tasks with status/error, task counts by status, and allowed "
        "command/cwd directories. Call this once at the start of a scheduling "
        "session instead of calling status, list_actions, list_tasks, and "
        "get_validation separately."
    ),
    required_params=[],
    optional_params=[],
)
def mage_scheduler_context() -> str:
    state = _load_state()
    base_url = _resolve_base_url(state)
    api_ready = _service_ready(base_url)
    worker_ready = _worker_ready(base_url)

    service = {
        "base_url": base_url,
        "api_ready": api_ready,
        "worker_ready": worker_ready,
    }

    if not api_ready:
        return json.dumps(
            {
                "service": service,
                "hint": "Scheduler is not running. Call mage_scheduler_start() to start it.",
            },
            indent=2,
        )

    # Available actions
    actions: list = []
    try:
        resp = requests.get(f"{base_url}/api/actions", timeout=5)
        if resp.ok:
            actions = [
                {
                    "name": a.get("name"),
                    "description": a.get("description"),
                    "allowed_env": a.get("allowed_env"),
                }
                for a in resp.json()
            ]
    except requests.RequestException:
        pass

    # Task counts by status
    stats: dict = {}
    try:
        resp = requests.get(f"{base_url}/api/tasks/stats", timeout=5)
        if resp.ok:
            stats = resp.json()
    except requests.RequestException:
        pass

    # Recent tasks — prefer active/terminal over noise; skip bulk cancelled clutter
    recent_tasks: list = []
    try:
        resp = requests.get(f"{base_url}/api/tasks", timeout=5)
        if resp.ok:
            all_tasks = resp.json()
            # Show active + recently completed first; suppress cancelled unless nothing else
            active = [t for t in all_tasks if t.get("status") not in ("cancelled", "blocked")]
            pool = active if active else all_tasks
            recent_tasks = [
                {
                    "id": t.get("id"),
                    "description": t.get("description"),
                    "status": t.get("status"),
                    "run_at": t.get("run_at"),
                    "action_name": t.get("action_name"),
                    "error": ((t.get("error") or "")[:100]) or None,
                }
                for t in pool[:10]
            ]
    except requests.RequestException:
        pass

    # Allowed dirs from settings
    validation: dict = {}
    try:
        resp = requests.get(f"{base_url}/api/validation", timeout=5)
        if resp.ok:
            v = resp.json()
            validation = {
                "allowed_command_dirs": v.get("allowed_command_dirs", []),
                "allowed_cwd_dirs": v.get("allowed_cwd_dirs", []),
            }
    except requests.RequestException:
        pass

    return json.dumps(
        {
            "service": service,
            "actions": actions,
            "stats": stats,
            "recent_tasks": recent_tasks,
            "validation": validation,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Intent scheduling
# ---------------------------------------------------------------------------

@function_schema(
    name="mage_scheduler_preview_intent",
    description=(
        "Validate a scheduling intent and preview the resolved schedule without creating a task. "
        "Use before mage_scheduler_schedule_intent when you want to confirm timing or catch errors first."
    ),
    required_params=["intent_json"],
    optional_params=[],
)
def mage_scheduler_preview_intent(intent_json: str) -> str:
    payload = json.loads(intent_json)
    result = _post_json("/api/tasks/intent/preview", payload)
    return json.dumps(result, indent=2)


@function_schema(
    name="mage_scheduler_schedule_intent",
    description=(
        "Schedule a task using the structured intent API. "
        "Primary tool for creating one-off, dependency-chained, and recurring (cron) tasks. "
        "Accepts intent_json with fields: description, action_name or command, run_at or run_in, "
        "timezone, cron, depends_on, notify_on_complete, env, max_retries. "
        "Set top-level 'replace_existing': true to cancel any existing scheduled/waiting tasks "
        "with the same description before creating the new one — useful for rescheduling without "
        "accumulating stale entries. Response includes 'replaced_task_ids' when tasks were cancelled."
    ),
    required_params=["intent_json"],
    optional_params=[],
)
def mage_scheduler_schedule_intent(intent_json: str) -> str:
    payload = json.loads(intent_json)
    result = _post_json("/api/tasks/intent", payload)
    return json.dumps(result, indent=2)


@function_schema(
    name="mage_scheduler_run_now",
    description=(
        "Dispatch a command for immediate execution via the scheduler. "
        "task_json must include 'command' (absolute path). "
        "Optional fields: description, cwd, notify_on_complete, max_retries."
    ),
    required_params=["task_json"],
    optional_params=[],
)
def mage_scheduler_run_now(task_json: str) -> str:
    payload = json.loads(task_json)
    result = _post_json("/api/tasks/run_now", payload)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Task inspection and management
# ---------------------------------------------------------------------------

@function_schema(
    name="mage_scheduler_list_tasks",
    description=(
        "List recent scheduler tasks. "
        "Each entry includes id, description, status, run_at, action_name, command (basename), and error snippet. "
        "Use the optional 'status' param to filter — accepts a single status or comma-separated list "
        "(e.g. 'scheduled', 'running', 'failed', 'succeeded', 'waiting', 'cancelled')."
    ),
    required_params=[],
    optional_params=["limit", "status"],
)
def mage_scheduler_list_tasks(
    limit: Optional[str] = "20",
    status: Optional[str] = None,
) -> str:
    path = "/api/tasks"
    if status:
        path = f"{path}?status={status}"
    data = _get_json(path)
    if isinstance(data, dict) and data.get("error"):
        return json.dumps(data, indent=2)
    try:
        limit_value = int(limit or 20)
    except ValueError:
        limit_value = 20

    tasks = data[:limit_value]
    summary = [
        {
            "id": task.get("id"),
            "description": task.get("description"),
            "status": task.get("status"),
            "run_at": task.get("run_at"),
            "action_name": task.get("action_name"),
            "command": Path(task.get("command") or "").name or task.get("command"),
            "error": ((task.get("error") or "")[:100]) or None,
        }
        for task in tasks
    ]
    return json.dumps(summary, indent=2)


@function_schema(
    name="mage_scheduler_get_task",
    description=(
        "Get full detail for a task by ID — command, result output, error message, "
        "retry count, dependency list, and all scheduling metadata. "
        "Use this when list_tasks shows a failure or unexpected status and you need to understand why."
    ),
    required_params=["task_id"],
    optional_params=[],
)
def mage_scheduler_get_task(task_id: str) -> str:
    try:
        task_id_value = int(task_id)
    except ValueError:
        return json.dumps({"error": "invalid_task_id"}, indent=2)
    data = _get_json(f"/api/tasks/{task_id_value}")
    return json.dumps(data, indent=2)


@function_schema(
    name="mage_scheduler_get_dependencies",
    description=(
        "Get the dependency graph for a task by ID. "
        "Returns 'depends_on' (upstream task IDs this task requires) and "
        "'blocking' (waiting task IDs that are held by this task)."
    ),
    required_params=["task_id"],
    optional_params=[],
)
def mage_scheduler_get_dependencies(task_id: str) -> str:
    try:
        task_id_value = int(task_id)
    except ValueError:
        return json.dumps({"error": "invalid_task_id"}, indent=2)
    data = _get_json(f"/api/tasks/{task_id_value}/dependencies")
    return json.dumps(data, indent=2)


@function_schema(
    name="mage_scheduler_cancel_task",
    description=(
        "Cancel a scheduled, running, or waiting task by ID. "
        "Cascades immediately: any tasks that depend on this one are failed. "
        "Cancelled tasks cannot be un-cancelled; create a new task if needed."
    ),
    required_params=["task_id"],
    optional_params=[],
)
def mage_scheduler_cancel_task(task_id: str) -> str:
    try:
        task_id_value = int(task_id)
    except ValueError:
        return json.dumps({"error": "invalid_task_id"}, indent=2)
    base_url = _current_base_url()
    resp = requests.post(f"{base_url}/api/tasks/{task_id_value}/cancel", timeout=10)
    if not resp.ok:
        return json.dumps({"error": resp.text, "status_code": resp.status_code}, indent=2)
    return json.dumps(resp.json(), indent=2)


@function_schema(
    name="mage_scheduler_cleanup",
    description=(
        "Delete all terminal tasks (succeeded, failed, cancelled, blocked) to clear scheduler history. "
        "Tasks with retain_result=true are preserved. "
        "Use this to reduce noise after a session with many cancelled or duplicate tasks."
    ),
    required_params=[],
    optional_params=[],
)
def mage_scheduler_cleanup() -> str:
    result = _post_json("/api/tasks/cleanup", {})
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Recurring tasks
# ---------------------------------------------------------------------------

@function_schema(
    name="mage_scheduler_list_recurring",
    description=(
        "List all recurring (cron) tasks — name, cron expression, timezone, "
        "action_name, enabled status, next_run_at, and last_run_at."
    ),
    required_params=[],
    optional_params=[],
)
def mage_scheduler_list_recurring() -> str:
    data = _get_json("/api/recurring")
    return json.dumps(data, indent=2)


@function_schema(
    name="mage_scheduler_toggle_recurring",
    description="Enable or disable a recurring task by ID. Returns the updated recurring task.",
    required_params=["recurring_id"],
    optional_params=[],
)
def mage_scheduler_toggle_recurring(recurring_id: str) -> str:
    try:
        recurring_id_value = int(recurring_id)
    except ValueError:
        return json.dumps({"error": "invalid_recurring_id"}, indent=2)
    base_url = _current_base_url()
    resp = requests.post(f"{base_url}/api/recurring/{recurring_id_value}/toggle", timeout=10)
    if not resp.ok:
        return json.dumps({"error": resp.text, "status_code": resp.status_code}, indent=2)
    return json.dumps(resp.json(), indent=2)


@function_schema(
    name="mage_scheduler_delete_recurring",
    description="Permanently delete a recurring task by ID. In-flight spawned tasks are not affected.",
    required_params=["recurring_id"],
    optional_params=[],
)
def mage_scheduler_delete_recurring(recurring_id: str) -> str:
    try:
        recurring_id_value = int(recurring_id)
    except ValueError:
        return json.dumps({"error": "invalid_recurring_id"}, indent=2)
    base_url = _current_base_url()
    resp = requests.delete(f"{base_url}/api/recurring/{recurring_id_value}", timeout=10)
    if not resp.ok:
        return json.dumps({"error": resp.text, "status_code": resp.status_code}, indent=2)
    return json.dumps(resp.json(), indent=2)


# ---------------------------------------------------------------------------
# Actions management
# ---------------------------------------------------------------------------

@function_schema(
    name="mage_scheduler_list_actions",
    description=(
        "List all registered scheduler actions — name, command, allowed_env, retry policy, and allowed dirs. "
        "Check this before scheduling to see what actions are available by name."
    ),
    required_params=[],
    optional_params=[],
)
def mage_scheduler_list_actions() -> str:
    data = _get_json("/api/actions")
    return json.dumps(data, indent=2)


@function_schema(
    name="mage_scheduler_get_validation",
    description=(
        "Get allowed command and cwd directories from scheduler settings. "
        "Check this when a command or path is rejected to understand what directories are permitted."
    ),
    required_params=[],
    optional_params=[],
)
def mage_scheduler_get_validation() -> str:
    data = _get_json("/api/validation")
    return json.dumps(data, indent=2)


@function_schema(
    name="mage_scheduler_create_action",
    description=(
        "Register a new named action in the scheduler. "
        "Actions are reusable vetted commands that can be scheduled by name. "
        "action_json fields: name, command, description, default_cwd, allowed_env, "
        "allowed_command_dirs, allowed_cwd_dirs, max_retries, retry_delay."
    ),
    required_params=["action_json"],
    optional_params=[],
)
def mage_scheduler_create_action(action_json: str) -> str:
    payload = json.loads(action_json)
    result = _post_json("/api/actions", payload)
    return json.dumps(result, indent=2)


@function_schema(
    name="mage_scheduler_update_action",
    description="Update an existing scheduler action by ID. Replaces all fields (full update).",
    required_params=["action_id", "action_json"],
    optional_params=[],
)
def mage_scheduler_update_action(action_id: str, action_json: str) -> str:
    payload = json.loads(action_json)
    try:
        action_id_value = int(action_id)
    except ValueError:
        return json.dumps({"error": "invalid_action_id"}, indent=2)
    base_url = _current_base_url()
    resp = requests.put(f"{base_url}/api/actions/{action_id_value}", json=payload, timeout=10)
    if not resp.ok:
        return json.dumps({"error": resp.text, "status_code": resp.status_code}, indent=2)
    return json.dumps(resp.json(), indent=2)


@function_schema(
    name="mage_scheduler_delete_action",
    description="Delete a scheduler action by ID.",
    required_params=["action_id"],
    optional_params=[],
)
def mage_scheduler_delete_action(action_id: str) -> str:
    try:
        action_id_value = int(action_id)
    except ValueError:
        return json.dumps({"error": "invalid_action_id"}, indent=2)
    base_url = _current_base_url()
    resp = requests.delete(f"{base_url}/api/actions/{action_id_value}", timeout=10)
    if not resp.ok:
        return json.dumps({"error": resp.text, "status_code": resp.status_code}, indent=2)
    return json.dumps(resp.json(), indent=2)
