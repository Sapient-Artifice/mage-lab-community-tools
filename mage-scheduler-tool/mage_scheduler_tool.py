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


def _service_ready(url: str) -> bool:
    try:
        resp = requests.get(f"{url}/health", timeout=1.5)
        return resp.ok
    except requests.RequestException:
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


@function_schema(
    name="mage_scheduler_start",
    description="Start the mage scheduler API and worker services",
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
    description="Stop the mage scheduler API and worker services",
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
    description="Check scheduler status",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_status() -> str:
    state = _load_state()
    base_url = state.get("base_url", BASE_URL)
    api_pid = state.get("api_pid")
    worker_pid = state.get("worker_pid")

    status = {
        "base_url": base_url,
        "api_pid": api_pid,
        "worker_pid": worker_pid,
        "api_alive": _pid_alive(api_pid),
        "worker_alive": _pid_alive(worker_pid),
        "ready": _service_ready(base_url),
    }
    return json.dumps(status, indent=2)


@function_schema(
    name="mage_scheduler_open_dashboard",
    description="Open the scheduler dashboard",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_open_dashboard() -> str:
    open_url(f"{BASE_URL}/")
    return f"Opened {BASE_URL}/"


@function_schema(
    name="mage_scheduler_open_actions",
    description="Open the scheduler actions page",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_open_actions() -> str:
    open_url(f"{BASE_URL}/actions")
    return f"Opened {BASE_URL}/actions"


@function_schema(
    name="mage_scheduler_open_settings",
    description="Open the scheduler settings page",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_open_settings() -> str:
    open_url(f"{BASE_URL}/settings")
    return f"Opened {BASE_URL}/settings"


def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = requests.post(f"{BASE_URL}{path}", json=payload, timeout=10)
    if not resp.ok:
        return {"error": resp.text, "status_code": resp.status_code}
    return resp.json()


def _get_json(path: str) -> Dict[str, Any]:
    resp = requests.get(f"{BASE_URL}{path}", timeout=10)
    if not resp.ok:
        return {"error": resp.text, "status_code": resp.status_code}
    return resp.json()


@function_schema(
    name="mage_scheduler_preview_intent",
    description="Preview a scheduling intent without creating a task",
    required_params=["intent_json"],
    optional_params=[],
)
def mage_scheduler_preview_intent(intent_json: str) -> str:
    payload = json.loads(intent_json)
    result = _post_json("/api/tasks/intent/preview", payload)
    return json.dumps(result, indent=2)


@function_schema(
    name="mage_scheduler_schedule_intent",
    description="Schedule a task using the LLM intent schema",
    required_params=["intent_json"],
    optional_params=[],
)
def mage_scheduler_schedule_intent(intent_json: str) -> str:
    payload = json.loads(intent_json)
    result = _post_json("/api/tasks/intent", payload)
    return json.dumps(result, indent=2)


@function_schema(
    name="mage_scheduler_run_now",
    description="Run a command immediately via the scheduler",
    required_params=["task_json"],
    optional_params=[],
)
def mage_scheduler_run_now(task_json: str) -> str:
    payload = json.loads(task_json)
    result = _post_json("/api/tasks/run_now", payload)
    return json.dumps(result, indent=2)


@function_schema(
    name="mage_scheduler_list_tasks",
    description="List recent scheduler tasks",
    required_params=[],
    optional_params=["limit"],
)
def mage_scheduler_list_tasks(limit: Optional[str] = "20") -> str:
    data = _get_json("/api/tasks")
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
        }
        for task in tasks
    ]
    return json.dumps(summary, indent=2)


@function_schema(
    name="mage_scheduler_list_actions",
    description="List available scheduler actions",
    required_params=[],
    optional_params=[],
)
def mage_scheduler_list_actions() -> str:
    data = _get_json("/api/actions")
    return json.dumps(data, indent=2)


@function_schema(
    name="mage_scheduler_create_action",
    description="Create a scheduler action",
    required_params=["action_json"],
    optional_params=[],
)
def mage_scheduler_create_action(action_json: str) -> str:
    payload = json.loads(action_json)
    result = _post_json("/api/actions", payload)
    return json.dumps(result, indent=2)


@function_schema(
    name="mage_scheduler_update_action",
    description="Update a scheduler action",
    required_params=["action_id", "action_json"],
    optional_params=[],
)
def mage_scheduler_update_action(action_id: str, action_json: str) -> str:
    payload = json.loads(action_json)
    try:
        action_id_value = int(action_id)
    except ValueError:
        return json.dumps({"error": "invalid_action_id"}, indent=2)
    resp = requests.put(f"{BASE_URL}/api/actions/{action_id_value}", json=payload, timeout=10)
    if not resp.ok:
        return json.dumps({"error": resp.text, "status_code": resp.status_code}, indent=2)
    return json.dumps(resp.json(), indent=2)


@function_schema(
    name="mage_scheduler_delete_action",
    description="Delete a scheduler action",
    required_params=["action_id"],
    optional_params=[],
)
def mage_scheduler_delete_action(action_id: str) -> str:
    try:
        action_id_value = int(action_id)
    except ValueError:
        return json.dumps({"error": "invalid_action_id"}, indent=2)
    resp = requests.delete(f"{BASE_URL}/api/actions/{action_id_value}", timeout=10)
    if not resp.ok:
        return json.dumps({"error": resp.text, "status_code": resp.status_code}, indent=2)
    return json.dumps(resp.json(), indent=2)
