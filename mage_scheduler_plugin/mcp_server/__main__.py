"""
Mage Scheduler MCP Server — entry point
=========================================
Launched by the Mage Lab plugin system when the mage-scheduler plugin is
activated (via the mcpServers entry in .claude-plugin/plugin.json).

Startup sequence:
  1. Check if the FastAPI backend is already running on SCHEDULER_PORT.
  2. If not, spawn a uvicorn subprocess pointing at mage_scheduler/api.py.
  3. Wait up to 15 seconds for the backend to become ready.
  4. Import tool definitions and start the FastMCP stdio server (blocks until
     the plugin session ends).

The uvicorn process runs independently and is NOT killed when this process
exits — scheduled tasks continue to fire in the background. On the next
plugin activation, step 1 detects the running backend and skips startup.

Environment variables (set in plugin.json mcpServers.env):
  SCHEDULER_DATA_DIR   Where the SQLite DB and logs live (default ~/.mage_scheduler)
  SCHEDULER_PORT       Port for the FastAPI backend (default 8012)
  SCHEDULER_HOST       Bind host for the FastAPI backend (default 127.0.0.1)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = PLUGIN_DIR / "mage_scheduler"

PORT = int(os.environ.get("SCHEDULER_PORT", "8012"))
HOST = os.environ.get("SCHEDULER_HOST", "127.0.0.1")
BASE_URL = f"http://{HOST}:{PORT}"

DATA_DIR = Path(os.environ.get("SCHEDULER_DATA_DIR", Path.home() / ".mage_scheduler"))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def _is_ready(timeout: float = 1.5) -> bool:
    try:
        req = urllib.request.Request(f"{BASE_URL}/health")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Backend startup
# ---------------------------------------------------------------------------

def _start_backend() -> subprocess.Popen:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "scheduler.log"
    log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115

    # Resolve the python interpreter inside our own venv so the subprocess
    # picks up apscheduler, sqlalchemy, fastapi etc.
    python = Path(sys.executable)

    env = {**os.environ, "SCHEDULER_DATA_DIR": str(DATA_DIR)}

    proc = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "api:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        stdout=log_file,
        stderr=log_file,
        env=env,
        # Detach from this process's session so the backend survives past the
        # MCP server's lifetime (tasks continue firing between sessions).
        start_new_session=True,
    )
    return proc


def _wait_for_ready(timeout_secs: int = 15) -> bool:
    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        if _is_ready():
            return True
        time.sleep(0.4)
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not _is_ready():
        _start_backend()
        if not _wait_for_ready(timeout_secs=5):
            # Backend did not come up in time — serve MCP anyway so the LLM
            # gets a meaningful error from the tool calls rather than silence.
            _warn("Mage Scheduler backend did not become ready in 5s. "
                  f"Check logs at {DATA_DIR / 'scheduler.log'}")

    # Import tool registry — this registers all @mcp.tool() decorators
    from mcp_server.tools import mcp  # noqa: PLC0415

    # Serve MCP tools over stdio (blocks until the session ends)
    mcp.run(transport="stdio")


def _warn(msg: str) -> None:
    print(f"[mage-scheduler] WARNING: {msg}", file=sys.stderr)


if __name__ == "__main__":
    main()
