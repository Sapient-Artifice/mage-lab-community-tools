"""Tests for _send_completion_notification and run_command_at retry logic.

Covers:
  - _send_completion_notification: urlopen called, message content,
    output/error truncation, silent failure on exception
  - run_command_at: success/fail/retry state transitions, celery_id update,
    notify gating, task-not-found guard, env injection
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import select

from tests.conftest import make_task


def _session(factory):
    return factory()


def _make_subprocess(monkeypatch, *, returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Patch tasks.notification_task.subprocess so run() returns the given values."""
    import tasks.notification_task as nt
    fake = MagicMock()
    fake.returncode = returncode
    fake.stdout = stdout
    fake.stderr = stderr
    monkeypatch.setattr(nt, "subprocess", MagicMock(run=MagicMock(return_value=fake)))
    return fake


def _mock_apply_async(monkeypatch, celery_id: str = "new-celery-id"):
    import tasks.notification_task as nt
    fake = MagicMock()
    fake.id = celery_id
    monkeypatch.setattr(nt.run_command_at, "apply_async", lambda *a, **kw: fake)
    return fake


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
        import tasks.notification_task as nt
        mock_urlopen = MagicMock()
        monkeypatch.setattr(nt.urllib.request, "urlopen", mock_urlopen)

        nt._send_completion_notification(self._task(), returncode=0)
        mock_urlopen.assert_called_once()

    def test_message_contains_task_id(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        def fake_urlopen(req, timeout=None):
            captured.append(req.data)
        monkeypatch.setattr(nt.urllib.request, "urlopen", fake_urlopen)

        nt._send_completion_notification(self._task(), returncode=0)
        assert b"42" in captured[0]

    def test_message_labeled_success_on_zero_returncode(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))

        nt._send_completion_notification(self._task(), returncode=0)
        assert b"SUCCESS" in captured[0]

    def test_message_labeled_failed_on_nonzero_returncode(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))

        nt._send_completion_notification(self._task(), returncode=1)
        assert b"FAILED" in captured[0]

    def test_output_included_when_result_set(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))

        nt._send_completion_notification(self._task(result="hello output"), returncode=0)
        assert b"hello output" in captured[0]

    def test_output_truncated_when_over_limit(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))

        long_output = "x" * (nt.NOTIFICATION_OUTPUT_MAX + 50)
        nt._send_completion_notification(self._task(result=long_output), returncode=0)
        assert b"..." in captured[0]

    def test_error_included_on_failure(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))

        nt._send_completion_notification(self._task(error="something broke"), returncode=1)
        assert b"something broke" in captured[0]

    def test_error_truncated_when_over_limit(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))

        long_error = "e" * (nt.NOTIFICATION_ERROR_MAX + 50)
        nt._send_completion_notification(self._task(error=long_error), returncode=1)
        assert b"..." in captured[0]

    def test_no_error_section_on_success(self, monkeypatch):
        import tasks.notification_task as nt
        captured = []
        monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout=None: captured.append(req.data))

        nt._send_completion_notification(self._task(error="leftover"), returncode=0)
        # Error section only appears when returncode != 0
        assert b"leftover" not in captured[0]

    def test_urlopen_exception_does_not_raise(self, monkeypatch):
        import tasks.notification_task as nt
        monkeypatch.setattr(nt.urllib.request, "urlopen", MagicMock(side_effect=OSError("network down")))
        # Must not raise
        nt._send_completion_notification(self._task(), returncode=0)


# ---------------------------------------------------------------------------
# run_command_at — state transitions and retry logic
# ---------------------------------------------------------------------------

class TestRunCommandAt:
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
        import tasks.notification_task as nt
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory)
        _make_subprocess(monkeypatch, returncode=0, stdout="done")
        _mock_apply_async(monkeypatch)

        nt.run_command_at(task_id, "echo ok")

        s = _session(factory)
        assert s.get(TaskRequest, task_id).status == "success"
        s.close()

    def test_failure_no_retries_sets_status_to_failed(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=0)
        _make_subprocess(monkeypatch, returncode=1, stderr="oops")
        _mock_apply_async(monkeypatch)

        nt.run_command_at(task_id, "echo ok")

        s = _session(factory)
        assert s.get(TaskRequest, task_id).status == "failed"
        s.close()

    def test_failure_with_retries_sets_status_to_scheduled(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=2)
        _make_subprocess(monkeypatch, returncode=1)
        _mock_apply_async(monkeypatch)

        nt.run_command_at(task_id, "echo ok")

        s = _session(factory)
        t = s.get(TaskRequest, task_id)
        assert t.status == "scheduled"
        assert t.retry_count == 1
        s.close()

    def test_retry_updates_celery_task_id(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt
        from models import TaskRequest

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=1)
        _make_subprocess(monkeypatch, returncode=1)
        _mock_apply_async(monkeypatch, celery_id="updated-celery-id")

        nt.run_command_at(task_id, "echo ok")

        s = _session(factory)
        assert s.get(TaskRequest, task_id).celery_task_id == "updated-celery-id"
        s.close()

    def test_retries_exhausted_sets_status_to_failed(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt
        from models import TaskRequest

        factory = nt_mem_db
        # Already at max retries
        s = _session(factory)
        from models import TaskRequest as TR
        task = TR(
            description="t", command="echo ok", run_at=datetime.utcnow(),
            status="scheduled", max_retries=2, retry_count=2, retry_delay=60,
        )
        s.add(task)
        s.commit()
        task_id = task.id
        s.close()

        _make_subprocess(monkeypatch, returncode=1)
        _mock_apply_async(monkeypatch)

        nt.run_command_at(task_id, "echo ok")

        s2 = _session(factory)
        assert s2.get(TaskRequest, task_id).status == "failed"
        s2.close()

    def test_notify_called_on_success_when_enabled(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt

        factory = nt_mem_db
        task_id = self._setup_task(factory, notify=True)
        _make_subprocess(monkeypatch, returncode=0)
        _mock_apply_async(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(nt, "_send_completion_notification", mock_notify)

        nt.run_command_at(task_id, "echo ok")
        mock_notify.assert_called_once()

    def test_notify_not_called_when_disabled(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt

        factory = nt_mem_db
        task_id = self._setup_task(factory, notify=False)
        _make_subprocess(monkeypatch, returncode=0)
        _mock_apply_async(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(nt, "_send_completion_notification", mock_notify)

        nt.run_command_at(task_id, "echo ok")
        mock_notify.assert_not_called()

    def test_notify_not_called_mid_retry(self, nt_mem_db, monkeypatch):
        """Notification must only fire on final run, not during a retry."""
        import tasks.notification_task as nt

        factory = nt_mem_db
        task_id = self._setup_task(factory, max_retries=1, notify=True)
        _make_subprocess(monkeypatch, returncode=1)
        _mock_apply_async(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(nt, "_send_completion_notification", mock_notify)

        nt.run_command_at(task_id, "echo ok")
        mock_notify.assert_not_called()

    def test_notify_suppressed_for_ask_assistant_action(self, nt_mem_db, monkeypatch):
        """_send_completion_notification must not fire for ask_assistant tasks.

        The action script itself sends the message; a second automated notification
        would double-fire the ask_assistant endpoint.
        """
        import tasks.notification_task as nt
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
        _mock_apply_async(monkeypatch)

        mock_notify = MagicMock()
        monkeypatch.setattr(nt, "_send_completion_notification", mock_notify)

        nt.run_command_at(task_id, "python3 ask_assistant.py")
        mock_notify.assert_not_called()

    def test_task_not_found_returns_error_dict(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt
        _make_subprocess(monkeypatch)
        result = nt.run_command_at(9999, "echo ok")
        assert result == {"error": "task_request_not_found"}

    def test_scheduler_env_vars_injected(self, nt_mem_db, monkeypatch):
        import tasks.notification_task as nt

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
        monkeypatch.setattr(nt.subprocess, "run", fake_run)
        _mock_apply_async(monkeypatch)

        nt.run_command_at(task_id, "echo ok")

        assert "SCHEDULER_TASK_ID" in captured_env
        assert captured_env["SCHEDULER_TASK_ID"] == str(task_id)
        assert "SCHEDULER_TRIGGERED_AT" in captured_env
        assert "SCHEDULER_ACTION_NAME" in captured_env
