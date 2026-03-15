"""Unit tests for mcp_server/backend.py — process management helpers.

Covers:
  - _is_ready: returns True on HTTP 200, False on error or non-200
  - _find_backend_pid: parses ss output, returns None on no match or error
  - restart_backend: success with no existing process, success after killing
    existing process, failure when backend never becomes ready,
    ProcessLookupError suppressed on SIGTERM
"""
from __future__ import annotations

import signal
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.backend import _find_backend_pid, _is_ready, restart_backend


# ---------------------------------------------------------------------------
# _is_ready
# ---------------------------------------------------------------------------

class TestIsReady:
    def _mock_urlopen(self, status: int):
        resp = MagicMock()
        resp.status = status
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_returns_true_on_200(self):
        with patch("mcp_server.backend.urllib.request.urlopen",
                   return_value=self._mock_urlopen(200)):
            assert _is_ready() is True

    def test_returns_false_on_connection_error(self):
        with patch("mcp_server.backend.urllib.request.urlopen",
                   side_effect=OSError("connection refused")):
            assert _is_ready() is False

    def test_returns_false_on_non_200(self):
        with patch("mcp_server.backend.urllib.request.urlopen",
                   return_value=self._mock_urlopen(503)):
            assert _is_ready() is False


# ---------------------------------------------------------------------------
# _find_backend_pid
# ---------------------------------------------------------------------------

class TestFindBackendPid:
    def _ss_result(self, stdout: str) -> MagicMock:
        r = MagicMock()
        r.stdout = stdout
        return r

    def test_returns_pid_when_port_and_pid_present(self):
        output = (
            'LISTEN 0 4096 127.0.0.1:8012 0.0.0.0:* '
            'users:(("uvicorn",pid=12345,fd=6))\n'
        )
        with patch("mcp_server.backend.subprocess.run",
                   return_value=self._ss_result(output)):
            assert _find_backend_pid() == 12345

    def test_returns_none_when_port_not_in_output(self):
        output = "LISTEN 0 4096 0.0.0.0:9999 0.0.0.0:*\n"
        with patch("mcp_server.backend.subprocess.run",
                   return_value=self._ss_result(output)):
            assert _find_backend_pid() is None

    def test_returns_none_on_subprocess_error(self):
        with patch("mcp_server.backend.subprocess.run",
                   side_effect=OSError("ss not found")):
            assert _find_backend_pid() is None


# ---------------------------------------------------------------------------
# restart_backend
# ---------------------------------------------------------------------------

class TestRestartBackend:
    def test_starts_fresh_when_no_existing_backend(self):
        with patch("mcp_server.backend._find_backend_pid", return_value=None), \
             patch("mcp_server.backend._start_backend") as mock_start, \
             patch("mcp_server.backend._wait_for_ready", return_value=True):
            success, msg = restart_backend(timeout_secs=1)

        assert success is True
        assert "restarted" in msg.lower()
        mock_start.assert_called_once()

    def test_sends_sigterm_to_existing_pid(self):
        with patch("mcp_server.backend._find_backend_pid", return_value=9999), \
             patch("mcp_server.backend.os.kill") as mock_kill, \
             patch("mcp_server.backend._is_ready", return_value=False), \
             patch("mcp_server.backend.time.sleep"), \
             patch("mcp_server.backend.time.monotonic", side_effect=[0.0, 10.0]), \
             patch("mcp_server.backend._start_backend"), \
             patch("mcp_server.backend._wait_for_ready", return_value=True):
            success, msg = restart_backend(timeout_secs=1)

        mock_kill.assert_any_call(9999, signal.SIGTERM)
        assert success is True

    def test_returns_false_when_backend_never_ready(self):
        with patch("mcp_server.backend._find_backend_pid", return_value=None), \
             patch("mcp_server.backend._start_backend"), \
             patch("mcp_server.backend._wait_for_ready", return_value=False):
            success, msg = restart_backend(timeout_secs=1)

        assert success is False
        assert "did not become ready" in msg

    def test_process_lookup_error_on_sigterm_is_suppressed(self):
        with patch("mcp_server.backend._find_backend_pid", return_value=1234), \
             patch("mcp_server.backend.os.kill", side_effect=ProcessLookupError), \
             patch("mcp_server.backend._is_ready", return_value=False), \
             patch("mcp_server.backend.time.sleep"), \
             patch("mcp_server.backend.time.monotonic", side_effect=[0.0, 10.0]), \
             patch("mcp_server.backend._start_backend"), \
             patch("mcp_server.backend._wait_for_ready", return_value=True):
            # Must not raise
            success, _ = restart_backend(timeout_secs=1)

        assert success is True
