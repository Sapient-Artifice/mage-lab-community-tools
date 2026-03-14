"""
Mage Scheduler MCP Tool Definitions
=====================================
21 tools exposed over the MCP stdio transport via FastMCP.

All tools communicate with the local FastAPI backend (running in a sibling
uvicorn process started by __main__.py) using httpx. The backend URL is
derived from the SCHEDULER_PORT env var (default 8012).

Tool naming: function name becomes the MCP tool name.
In Claude Code, tools are addressed as mcp__scheduler__<tool_name>.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

from mcp_server.backend import restart_backend, DATA_DIR as _BACKEND_DATA_DIR

import logging

import httpx
from mcp.server.fastmcp import FastMCP

# Suppress httpx request/response logging — it would pollute the MCP stdio channel
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_PORT = int(os.environ.get("SCHEDULER_PORT", "8012"))
_HOST = os.environ.get("SCHEDULER_HOST", "127.0.0.1")
BASE_URL = f"http://{_HOST}:{_PORT}"

mcp = FastMCP("scheduler")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(path: str) -> str:
    try:
        resp = httpx.get(f"{BASE_URL}{path}", timeout=10)
        return resp.text
    except httpx.RequestError as exc:
        return json.dumps({"error": f"connection_error: {exc}"})


def _post(path: str, payload: dict) -> str:
    try:
        resp = httpx.post(f"{BASE_URL}{path}", json=payload, timeout=10)
        return resp.text
    except httpx.RequestError as exc:
        return json.dumps({"error": f"connection_error: {exc}"})


def _put(path: str, payload: dict) -> str:
    try:
        resp = httpx.put(f"{BASE_URL}{path}", json=payload, timeout=10)
        return resp.text
    except httpx.RequestError as exc:
        return json.dumps({"error": f"connection_error: {exc}"})


def _delete(path: str) -> str:
    try:
        resp = httpx.delete(f"{BASE_URL}{path}", timeout=10)
        return resp.text
    except httpx.RequestError as exc:
        return json.dumps({"error": f"connection_error: {exc}"})


_MAGE_LAB_PORT = int(os.environ.get("MAGE_LAB_PORT", os.environ.get("API_PORT", "11115")))
_MAGE_LAB_URL = os.environ.get("MAGE_LAB_URL", f"http://127.0.0.1:{_MAGE_LAB_PORT}")


_PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _open_in_app(url: str, panel: str = "panel") -> None:
    """Open a URL in the mage-lab in-app tab via a local iframe wrapper.

    Writes a small HTML file containing a full-screen <iframe src="url"> so
    that the live app loads directly — preserving its own assets, navigation,
    and AJAX calls — then asks the mage-lab backend to open that file as a tab.
    Falls back to the system browser if the backend is unreachable.
    """
    wrapper_path = _PLUGIN_DIR / f"mage_scheduler_{panel}.html"
    wrapper_path.write_text(
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Mage Scheduler</title>
<style>*{{margin:0;padding:0}}html,body,iframe{{width:100%;height:100%;border:none;display:block}}</style>
</head><body>
<iframe src="{url}" width="100%" height="100%" frameborder="0"></iframe>
</body></html>""",
        encoding="utf-8",
    )
    try:
        httpx.get(
            f"{_MAGE_LAB_URL}/api/test_open_tab",
            params={"path": str(wrapper_path)},
            timeout=3,
        )
    except httpx.RequestError:
        if platform.system() == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------

@mcp.tool()
def scheduler_status() -> str:
    """Check whether the Mage Scheduler API and worker are alive.
    Returns base_url, api_alive, worker_alive, and ready flag."""
    api_ok = False
    worker_ok = False
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=3)
        api_ok = resp.status_code == 200
    except Exception:
        pass
    if api_ok:
        try:
            resp = httpx.get(f"{BASE_URL}/health/worker", timeout=3)
            if resp.status_code == 200:
                worker_ok = bool(resp.json().get("worker_alive"))
        except Exception:
            pass
    return json.dumps(
        {
            "base_url": BASE_URL,
            "api_alive": api_ok,
            "worker_alive": worker_ok,
            "ready": api_ok and worker_ok,
        },
        indent=2,
    )


@mcp.tool()
def scheduler_context() -> str:
    """Bootstrap call to orient yourself before scheduling.

    Returns in one call: service status, all available Actions (name +
    allowed_env), recent tasks with status/error, task counts by status, and
    allowed command/cwd directories.

    Call this once at the start of a scheduling session instead of calling
    scheduler_status, scheduler_list_actions, scheduler_list_tasks, and
    scheduler_get_validation separately."""
    api_ok = False
    worker_ok = False
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=3)
        api_ok = resp.status_code == 200
    except Exception:
        pass
    if api_ok:
        try:
            resp = httpx.get(f"{BASE_URL}/health/worker", timeout=3)
            if resp.status_code == 200:
                worker_ok = bool(resp.json().get("worker_alive"))
        except Exception:
            pass

    service = {"base_url": BASE_URL, "api_ready": api_ok, "worker_ready": worker_ok}

    if not api_ok:
        return json.dumps(
            {"service": service, "hint": "Scheduler API is not responding."},
            indent=2,
        )

    actions: list = []
    try:
        resp = httpx.get(f"{BASE_URL}/api/actions", timeout=5)
        if resp.is_success:
            actions = [
                {
                    "name": a.get("name"),
                    "description": a.get("description"),
                    "allowed_env": a.get("allowed_env"),
                }
                for a in resp.json()
            ]
    except Exception:
        pass

    stats: dict = {}
    try:
        resp = httpx.get(f"{BASE_URL}/api/tasks/stats", timeout=5)
        if resp.is_success:
            stats = resp.json()
    except Exception:
        pass

    recent_tasks: list = []
    try:
        resp = httpx.get(f"{BASE_URL}/api/tasks", timeout=5)
        if resp.is_success:
            all_tasks = resp.json()
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
    except Exception:
        pass

    validation: dict = {}
    try:
        resp = httpx.get(f"{BASE_URL}/api/validation", timeout=5)
        if resp.is_success:
            v = resp.json()
            validation = {
                "allowed_command_dirs": v.get("allowed_command_dirs", []),
                "allowed_cwd_dirs": v.get("allowed_cwd_dirs", []),
            }
    except Exception:
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
# Dashboard
# ---------------------------------------------------------------------------

@mcp.tool()
def scheduler_open_dashboard() -> str:
    """Open the Mage Scheduler task dashboard in the browser."""
    url = f"{BASE_URL}/"
    _open_in_app(url, "dashboard")
    return f"Opened {url}"


@mcp.tool()
def scheduler_open_actions() -> str:
    """Open the Mage Scheduler actions management page in the browser."""
    url = f"{BASE_URL}/actions"
    _open_in_app(url, "actions")
    return f"Opened {url}"


@mcp.tool()
def scheduler_open_settings() -> str:
    """Open the Mage Scheduler settings page in the browser."""
    url = f"{BASE_URL}/settings"
    _open_in_app(url, "settings")
    return f"Opened {url}"


# ---------------------------------------------------------------------------
# Intent scheduling
# ---------------------------------------------------------------------------

@mcp.tool()
def scheduler_preview_intent(intent: dict) -> str:
    """Validate a scheduling intent and preview the resolved schedule without creating a task.

    Use before scheduler_schedule_intent when you want to confirm timing or
    catch validation errors first. Returns the same response as
    scheduler_schedule_intent but does not persist anything.

    Intent fields: intent_version, task (description, action_name or command,
    run_at or run_in, timezone, cron, depends_on, notify_on_complete, env,
    max_retries, retry_delay, retain_result), replace_existing, meta."""
    return _post("/api/tasks/intent/preview", intent)


@mcp.tool()
def scheduler_schedule_intent(intent: dict) -> str:
    """Schedule a task using the structured intent API.

    Primary tool for creating one-off, recurring (cron), and dependency-chained
    tasks. Set top-level replace_existing: true to cancel any existing
    scheduled/waiting tasks with the same description before creating the new
    one — useful for rescheduling without accumulating stale entries. Response
    includes replaced_task_ids when tasks were cancelled.

    Intent fields: intent_version (v1), task.description, task.action_name or
    task.command (absolute path), task.run_at or task.run_in, task.timezone,
    task.cron (for recurring), task.depends_on (list of task IDs),
    task.notify_on_complete, task.env (requires action_name), task.max_retries,
    task.retry_delay, task.retain_result. Top-level: replace_existing, meta."""
    return _post("/api/tasks/intent", intent)


@mcp.tool()
def scheduler_run_now(task: dict) -> str:
    """Dispatch a command for immediate execution via the scheduler.

    task must include 'command' (absolute path). Optional fields: description,
    cwd, notify_on_complete, max_retries."""
    return _post("/api/tasks/run_now", task)


# ---------------------------------------------------------------------------
# Task inspection and management
# ---------------------------------------------------------------------------

@mcp.tool()
def scheduler_list_tasks(
    limit: int = 20,
    status: Optional[str] = None,
) -> str:
    """List recent scheduler tasks.

    Each entry includes id, description, status, run_at, action_name, command
    basename, and error snippet. Use status to filter — accepts a single
    status or comma-separated list (e.g. 'scheduled', 'running', 'failed',
    'success', 'waiting', 'cancelled')."""
    path = "/api/tasks"
    if status:
        path = f"{path}?status={status}"
    raw = _get(path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict) and data.get("error"):
        return raw
    tasks = data[:limit]
    summary = [
        {
            "id": t.get("id"),
            "description": t.get("description"),
            "status": t.get("status"),
            "run_at": t.get("run_at"),
            "action_name": t.get("action_name"),
            "command": Path(t.get("command") or "").name or t.get("command"),
            "error": ((t.get("error") or "")[:100]) or None,
        }
        for t in tasks
    ]
    return json.dumps(summary, indent=2)


@mcp.tool()
def scheduler_get_task(task_id: int) -> str:
    """Get full detail for a task by ID.

    Returns command, result output, error message, retry count, dependency
    list, and all scheduling metadata. Use when a task has failed or has an
    unexpected status and you need to understand why."""
    return _get(f"/api/tasks/{task_id}")


@mcp.tool()
def scheduler_get_dependencies(task_id: int) -> str:
    """Get the dependency graph for a task by ID.

    Returns depends_on (upstream task IDs this task requires) and blocking
    (downstream waiting task IDs that are held by this task)."""
    return _get(f"/api/tasks/{task_id}/dependencies")


@mcp.tool()
def scheduler_cancel_task(task_id: int) -> str:
    """Cancel a scheduled, running, or waiting task by ID.

    Cascades immediately: any tasks that depend on this one are failed.
    Cancelled tasks cannot be un-cancelled; create a new task if needed."""
    return _post(f"/api/tasks/{task_id}/cancel", {})


@mcp.tool()
def scheduler_cleanup() -> str:
    """Delete all terminal tasks (succeeded, failed, cancelled, blocked).

    Tasks with retain_result=true are preserved. Use this to reduce noise
    after a session with many cancelled or duplicate tasks. Returns a count
    of deleted tasks."""
    return _post("/api/tasks/cleanup", {})


# ---------------------------------------------------------------------------
# Recurring tasks
# ---------------------------------------------------------------------------

@mcp.tool()
def scheduler_list_recurring() -> str:
    """List all recurring (cron) tasks.

    Each entry includes name, cron expression, timezone, action_name, enabled
    status, next_run_at, and last_run_at."""
    return _get("/api/recurring")


@mcp.tool()
def scheduler_toggle_recurring(recurring_id: int) -> str:
    """Enable or disable a recurring task by ID. Returns the updated task."""
    return _post(f"/api/recurring/{recurring_id}/toggle", {})


@mcp.tool()
def scheduler_delete_recurring(recurring_id: int) -> str:
    """Permanently delete a recurring task by ID.

    In-flight spawned task instances are not affected."""
    return _delete(f"/api/recurring/{recurring_id}")


# ---------------------------------------------------------------------------
# Actions management
# ---------------------------------------------------------------------------

@mcp.tool()
def scheduler_list_actions() -> str:
    """List all registered scheduler actions.

    Each entry includes name, command, allowed_env, retry policy, and allowed
    dirs. Check this before scheduling to see what action names are available."""
    return _get("/api/actions")


@mcp.tool()
def scheduler_get_validation() -> str:
    """Get allowed command and cwd directories from scheduler settings.

    Check this when a command or path is rejected to understand what
    directories are permitted."""
    return _get("/api/validation")


@mcp.tool()
def scheduler_create_action(action: dict) -> str:
    """Register a new named action in the scheduler.

    Actions are reusable vetted commands schedulable by name.
    Fields: name (required), command (required, absolute path), description,
    default_cwd, allowed_env (list of allowed env key names),
    allowed_command_dirs, allowed_cwd_dirs, max_retries, retry_delay."""
    return _post("/api/actions", action)


@mcp.tool()
def scheduler_update_action(action_id: int, action: dict) -> str:
    """Update an existing scheduler action by ID. Replaces all fields (full update)."""
    return _put(f"/api/actions/{action_id}", action)


@mcp.tool()
def scheduler_delete_action(action_id: int) -> str:
    """Delete a scheduler action by ID."""
    return _delete(f"/api/actions/{action_id}")


@mcp.tool()
def scheduler_restart_backend() -> str:
    """Restart the Mage Scheduler backend process.

    Gracefully stops the currently running backend (if any), then spawns a
    fresh one and waits up to 15 seconds for it to become ready.

    Use this when:
    - scheduler_status shows api_alive: false (backend crashed or was killed)
    - You need to pick up configuration changes that require a restart
    - The backend is unresponsive or behaving unexpectedly
    """
    success, message = restart_backend(timeout_secs=15)
    return json.dumps(
        {
            "success": success,
            "message": message,
            "log": str(_BACKEND_DATA_DIR / "scheduler.log"),
        },
        indent=2,
    )
