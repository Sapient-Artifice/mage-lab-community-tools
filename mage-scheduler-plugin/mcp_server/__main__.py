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

import sys

from mcp_server.backend import (  # noqa: E402
    DATA_DIR,
    _is_ready,
    _start_backend,
    _wait_for_ready,
)


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
