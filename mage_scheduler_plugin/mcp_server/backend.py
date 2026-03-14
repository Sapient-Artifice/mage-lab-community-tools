"""
Mage Scheduler — backend process management
=============================================
Shared by __main__.py (startup) and tools.py (scheduler_restart_backend).
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = PLUGIN_DIR / "mage_scheduler"

PORT = int(os.environ.get("SCHEDULER_PORT", "8012"))
HOST = os.environ.get("SCHEDULER_HOST", "127.0.0.1")
BASE_URL = f"http://{HOST}:{PORT}"

DATA_DIR = Path(os.environ.get("SCHEDULER_DATA_DIR", Path.home() / ".mage_scheduler"))


def _is_ready(timeout: float = 1.5) -> bool:
    try:
        req = urllib.request.Request(f"{BASE_URL}/health")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _start_backend() -> subprocess.Popen:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "scheduler.log"
    log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115

    # Use the venv Python from this plugin's own directory — never sys.executable,
    # which may be inherited from a parent process running a different environment
    # (e.g. Mage Lab activating its own venv before spawning us).
    python = PLUGIN_DIR / ".venv" / "bin" / "python"

    # Strip Python environment vars that could cause the subprocess to load
    # packages from the parent process's venv instead of ours.
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT")}
    env["SCHEDULER_DATA_DIR"] = str(DATA_DIR)

    return subprocess.Popen(
        [str(python), "-m", "uvicorn", "api:app",
         "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND_DIR),
        stdout=log_file,
        stderr=log_file,
        env=env,
        # Detach from this process's session so the backend survives past the
        # MCP server's lifetime (tasks continue firing between sessions).
        start_new_session=True,
    )


def _wait_for_ready(timeout_secs: int = 15) -> bool:
    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        if _is_ready():
            return True
        time.sleep(0.4)
    return False


def _find_backend_pid() -> int | None:
    """Return the PID of the process listening on PORT, or None."""
    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{PORT}"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{PORT}" in line:
                m = re.search(r"pid=(\d+)", line)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return None


def restart_backend(timeout_secs: int = 15) -> tuple[bool, str]:
    """Kill the running backend (if any) and start a fresh one.

    Returns (success, message).
    """
    pid = _find_backend_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        # Wait up to 5s for graceful shutdown before forcing.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not _is_ready(timeout=0.4):
                break
            time.sleep(0.3)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            time.sleep(0.5)

    _start_backend()

    if _wait_for_ready(timeout_secs=timeout_secs):
        return True, f"Backend restarted successfully on {BASE_URL}."
    return False, (
        f"Backend process started but did not become ready within {timeout_secs}s. "
        f"Check logs at {DATA_DIR / 'scheduler.log'}."
    )
