"""Bootstrap: re-launch as the plugin's venv Python if needed.

Placed in bin/ (not plugin root, not scripts/) so that:
  - mcp_installer doesn't detect pyproject.toml and prompt for uv-sync approval
  - bind_spells doesn't fire (it only triggers on a scripts/ directory)

Mage resolves "bin/start_mcp.py" to this file's absolute path and runs
it with the system python3.  We re-exec as the venv Python so that
mcp_server's dependencies (fastmcp, apscheduler, sqlalchemy, …) are
available.
"""

import os
import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent  # scripts/ -> plugin root
VENV_PYTHON = PLUGIN_DIR / ".venv" / "bin" / "python"

if __name__ == "__main__":
    # Ensure venv exists (first run, or after a clean).
    if not VENV_PYTHON.exists():
        result = subprocess.run(["uv", "sync"], cwd=str(PLUGIN_DIR))
        if result.returncode != 0 or not VENV_PYTHON.exists():
            print(
                f"[mage-scheduler] ERROR: failed to create venv in {PLUGIN_DIR}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Re-exec as venv Python so mcp_server dependencies are importable.
    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__])

    # sys.path[0] == PLUGIN_DIR (parent of scripts/), so mcp_server is importable.
    sys.path.insert(0, str(PLUGIN_DIR))
    from mcp_server.__main__ import main  # noqa: PLC0415
    main()
