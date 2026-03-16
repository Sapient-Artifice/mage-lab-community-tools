"""Tests for _send_completion_notification and run_command retry logic.

Adapted from test_notification_task.py — Celery apply_async replaced with
dispatch.schedule_command mocking.

Covers:
  - _send_completion_notification: urlopen called, message content,
    output/error truncation, silent failure on exception
  - run_command: success/fail/retry state transitions, job_id update,
    notify gating, task-not-found guard, env injection, cancelled guard
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from tests.conftest import make_task


def _session(factory):
    return factory()


def _make_subprocess(monkeypatch, *, returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Patch jobs.run_command.subprocess so run() returns the given values."""
    import jobs.run_command as rc
    fake = MagicMock()
    fake.returncode = returncode
    fake.stdout = stdout
    fake.stderr = stderr
    monkeypatch.setattr(rc, "subprocess", MagicMock(run=MagicMock(return_value=fake)))
    return fake


def _mock_schedule(monkeypatch, job_id: str = "new-job-id"):
    """Patch dispatch.schedule_command to return a fake job_id string."""
    import dispatch
    monkeypatch.setattr(dispatch, "schedule_command", lambda *a, **kw: job_id)
    return job_id


# ---------------------------------------------------------------------------
# _send_completion_notification
# ---------------------------------------------------------------------------

class TestSendCompletionNotification:
    def _task(self, **kwargs):
        t = MagicMock()
        t.id = 42
        t.action_name = "my_action"
        t.description = "do the thing"
        t.result = kwargs.get("result", None)
        t.error = kwargs.get("error", None)
        return t

    def test_urlopen_called_once(self, monkeypatch):
        import jobs.run_command as rc
        mock_urlopen = MagicMock()
        monkeypatch.setattr(rc.urllib.request, "urlopen", mock_urlopen)
        rc._send_completion_notification(self._task(), returncode=0)
        mock_urlopen.assert_called_once()

    def test_message_contains_task_id(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        rc._send_completion_notification(self._task(), returncode=0)
        assert b"42" in captured[0]

    def test_message_labeled_success_on_zero_returncode(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        rc._send_completion_notification(self._task(), returncode=0)
        assert b"SUCCESS" in captured[0]

    def test_message_labeled_failed_on_nonzero_returncode(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        rc._send_completion_notification(self._task(), returncode=1)
        assert b"FAILED" in captured[0]

    def test_output_included_when_result_set(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        rc._send_completion_notification(self._task(result="hello output"), returncode=0)
        assert b"hello output" in captured[0]

    def test_output_truncated_when_over_limit(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        long_output = "x" * (rc.NOTIFICATION_OUTPUT_MAX + 50)
        rc._send_completion_notification(self._task(result=long_output), returncode=0)
        assert b"..." in captured[0]

    def test_error_included_on_failure(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        rc._send_completion_notification(self._task(error="something broke"), returncode=1)
        assert b"something broke" in captured[0]

    def test_error_truncated_when_over_limit(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        long_error = "e" * (rc.NOTIFICATION_ERROR_MAX + 50)
        rc._send_completion_notification(self._task(error=long_error), returncode=1)
        assert b"..." in captured[0]

    def test_no_error_section_on_success(self, monkeypatch):
        import jobs.run_command as rc
        captured = []
        monkeypatch.setattr(rc.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))
        rc._send_completion_notification(self._task(error="leftover"), returncode=0)
        assert b"leftover" not in captured[0]

    def test_urlopen_exception_does_not_raise(self, monkeypatch):
        import jobs.run_command as rc
        monkeypatch.setattr(rc.urllib.request, "urlopen", MagicMock(side_effect=OSError("network down")))
        rc._send_completion_notification(self._task(), returncode=0)


# ---------------------------------------------------------------------------
# run_command — state transitions and retry logic
# ---------------------------------------------------------------------------

class TestRunCommand:
    def _setup_task(self, factory, *, max_retries=0, retry_delay=60, notify=False):
        from models import TaskRequest
        s = _session(factory)
        task = TaskRequest(
            description="test",
            command="echo ok",
            run_at=datetime.utcnow(),
            status="scheduled",
            max_retries=max_retries,
            retry_delay=retry_delay,
            retry_count=0,
            notify_on_complete=1 if notify else 0,
        )
        s.add(task)
        s.commit()
        task_id = task.id
        s.close()
        return task_id

    def test_success_sets_status_to_success(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory)
        _make_subprocess(monkeypatch, returncode=0, stdout="done")
        _mock_schedule(monkeypatch)

        rc.run_command(task_id, "echo ok")

        s = _session(factory)
        assert s.get(TaskRequest, task_id).status == "success"
        s.close()

    def test_failure_no_retries_sets_status_to_failed(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=0)
        _make_subprocess(monkeypatch, returncode=1, stderr="oops")
        _mock_schedule(monkeypatch)

        rc.run_command(task_id, "echo ok")

        s = _session(factory)
        assert s.get(TaskRequest, task_id).status == "failed"
        s.close()

    def test_failure_with_retries_sets_status_to_scheduled(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=2)
        _make_subprocess(monkeypatch, returncode=1)
        _mock_schedule(monkeypatch)

        rc.run_command(task_id, "echo ok")

        s = _session(factory)
        t = s.get(TaskRequest, task_id)
        assert t.status == "scheduled"
        assert t.retry_count == 1
        s.close()

    def test_retry_updates_job_id(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=1)
        _make_subprocess(monkeypatch, returncode=1)
        _mock_schedule(monkeypatch, job_id="updated-job-id")

        rc.run_command(task_id, "echo ok")

        s = _session(factory)
        assert s.get(TaskRequest, task_id).job_id == "updated-job-id"
        s.close()

    def test_retries_exhausted_sets_status_to_failed(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc
        from models import TaskRequest

        factory = nt_mem_db
        s = _session(factory)
        task = TaskRequest(
            description="t", command="echo ok", run_at=datetime.utcnow(),
            status="scheduled", max_retries=2, retry_count=2, retry_delay=60,
        )
        s.add(task)
        s.commit()
        task_id = task.id
        s.close()

        _make_subprocess(monkeypatch, returncode=1)
        _mock_schedule(monkeypatch)

        rc.run_command(task_id, "echo ok")

        s2 = _session(factory)
        assert s2.get(TaskRequest, task_id).status == "failed"
        s2.close()

    def test_cancelled_task_is_skipped_before_running(self, nt_mem_db, monkeypatch):
        """If the task was cancelled before the job fired, run_command returns early."""
        import jobs.run_command as rc
        from models import TaskRequest

        factory = nt_mem_db
        s = _session(factory)
        task = TaskRequest(
            description="t", command="echo ok", run_at=datetime.utcnow(),
            status="cancelled",
        )
        s.add(task)
        s.commit()
        task_id = task.id
        s.close()

        fake_subprocess = MagicMock()
        monkeypatch.setattr(rc, "subprocess", fake_subprocess)

        result = rc.run_command(task_id, "echo ok")

        assert result == {"skipped": "task_was_cancelled"}
        fake_subprocess.run.assert_not_called()

    def test_notify_called_on_success_when_enabled(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc

        factory = nt_mem_db
        task_id = self._setup_task(factory, notify=True)
        _make_subprocess(monkeypatch, returncode=0)
        _mock_schedule(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(rc, "_send_completion_notification", mock_notify)

        rc.run_command(task_id, "echo ok")
        mock_notify.assert_called_once()

    def test_notify_not_called_when_disabled(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc

        factory = nt_mem_db
        task_id = self._setup_task(factory, notify=False)
        _make_subprocess(monkeypatch, returncode=0)
        _mock_schedule(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(rc, "_send_completion_notification", mock_notify)

        rc.run_command(task_id, "echo ok")
        mock_notify.assert_not_called()

    def test_notify_not_called_mid_retry(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=1, notify=True)
        _make_subprocess(monkeypatch, returncode=1)
        _mock_schedule(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(rc, "_send_completion_notification", mock_notify)

        rc.run_command(task_id, "echo ok")
        mock_notify.assert_not_called()

    def test_notify_suppressed_for_ask_assistant_action(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc
        from models import TaskRequest

        factory = nt_mem_db
        s = _session(factory)
        task = TaskRequest(
            description="ping assistant",
            command="python3 ask_assistant.py",
            run_at=datetime.utcnow(),
            status="scheduled",
            max_retries=0,
            retry_count=0,
            notify_on_complete=1,
            action_name="ask_assistant",
        )
        s.add(task)
        s.commit()
        task_id = task.id
        s.close()

        _make_subprocess(monkeypatch, returncode=0)
        _mock_schedule(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(rc, "_send_completion_notification", mock_notify)

        rc.run_command(task_id, "python3 ask_assistant.py")
        mock_notify.assert_not_called()

    def test_task_not_found_returns_error_dict(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc
        _make_subprocess(monkeypatch)
        result = rc.run_command(9999, "echo ok")
        assert result == {"error": "task_request_not_found"}

    def test_scheduler_env_vars_injected(self, nt_mem_db, monkeypatch):
        import jobs.run_command as rc

        factory = nt_mem_db
        task_id = self._setup_task(factory)

        captured_env = {}
        def fake_run(cmd, *, shell, capture_output, text, cwd, env):
            captured_env.update(env)
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r
        monkeypatch.setattr(rc.subprocess, "run", fake_run)
        _mock_schedule(monkeypatch)

        rc.run_command(task_id, "echo ok")

        assert "SCHEDULER_TASK_ID" in captured_env
        assert captured_env["SCHEDULER_TASK_ID"] == str(task_id)
        assert "SCHEDULER_TRIGGERED_AT" in captured_env
        assert "SCHEDULER_ACTION_NAME" in captured_env
