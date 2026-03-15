"""Tests for pure utility functions in api.py.

Covers:
  - _parse_run_in
  - _normalize_intent_version
  - _intent_error
  - _raise_intent_validation
  - _parse_allowed_dirs
  - _parse_allowed_env
  - _is_path_allowed
  - _get_settings
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# _parse_run_in
# ---------------------------------------------------------------------------

class TestParseRunIn:
    def _call(self, value: str):
        from api import _parse_run_in
        return _parse_run_in(value)

    # --- seconds ---
    @pytest.mark.parametrize("unit", ["s", "sec", "secs", "second", "seconds"])
    def test_seconds_aliases(self, unit):
        assert self._call(f"30{unit}") == timedelta(seconds=30)

    # --- minutes ---
    @pytest.mark.parametrize("unit", ["m", "min", "mins", "minute", "minutes"])
    def test_minutes_aliases(self, unit):
        assert self._call(f"2{unit}") == timedelta(seconds=120)

    # --- hours ---
    @pytest.mark.parametrize("unit", ["h", "hr", "hrs", "hour", "hours"])
    def test_hours_aliases(self, unit):
        assert self._call(f"1{unit}") == timedelta(seconds=3600)

    # --- days ---
    @pytest.mark.parametrize("unit", ["d", "day", "days"])
    def test_days_aliases(self, unit):
        assert self._call(f"1{unit}") == timedelta(seconds=86400)

    def test_fractional_hours(self):
        assert self._call("1.5h") == timedelta(seconds=5400)

    def test_fractional_minutes(self):
        assert self._call("0.5m") == timedelta(seconds=30)

    def test_leading_trailing_whitespace_stripped(self):
        assert self._call("  30m  ") == timedelta(seconds=1800)

    def test_space_between_number_and_unit(self):
        assert self._call("30 m") == timedelta(seconds=1800)

    def test_case_insensitive_unit(self):
        assert self._call("30M") == timedelta(seconds=1800)
        assert self._call("2H") == timedelta(seconds=7200)

    def test_unknown_unit_returns_none(self):
        assert self._call("30x") is None

    def test_empty_string_returns_none(self):
        assert self._call("") is None

    def test_zero_value_returns_none(self):
        assert self._call("0m") is None

    def test_negative_not_matched(self):
        # Pattern anchors to digits only; "-30m" won't match
        assert self._call("-30m") is None

    def test_plain_number_without_unit_returns_none(self):
        assert self._call("30") is None


# ---------------------------------------------------------------------------
# _normalize_intent_version
# ---------------------------------------------------------------------------

class TestNormalizeIntentVersion:
    def _call(self, value: str):
        from api import _normalize_intent_version
        return _normalize_intent_version(value)

    def test_v1_exact(self):
        normalized, errors = self._call("v1")
        assert normalized == "v1"
        assert errors == []

    def test_alias_1(self):
        normalized, errors = self._call("1")
        assert normalized == "v1"
        assert errors == []

    def test_alias_1_0(self):
        normalized, errors = self._call("1.0")
        assert normalized == "v1"
        assert errors == []

    def test_unknown_version_returns_error(self):
        normalized, errors = self._call("v2")
        assert normalized is None
        assert "unsupported_intent_version" in errors

    def test_empty_string_returns_error(self):
        normalized, errors = self._call("")
        assert normalized is None
        assert "unsupported_intent_version" in errors


# ---------------------------------------------------------------------------
# _intent_error
# ---------------------------------------------------------------------------

class TestIntentError:
    def _call(self, code: str):
        from api import _intent_error
        return _intent_error(code)

    def test_known_code_has_message_and_hint(self):
        result = self._call("run_in_invalid")
        assert result["code"] == "run_in_invalid"
        assert "message" in result
        assert result["message"] != "run_in_invalid"  # resolved to human text
        assert "hint" in result

    def test_unknown_code_uses_code_as_message_no_hint(self):
        result = self._call("no_such_code")
        assert result["code"] == "no_such_code"
        assert result["message"] == "no_such_code"
        assert "hint" not in result


# ---------------------------------------------------------------------------
# _raise_intent_validation
# ---------------------------------------------------------------------------

class TestRaiseIntentValidation:
    def _call(self, errors):
        from api import _raise_intent_validation
        _raise_intent_validation(errors)

    def test_empty_list_does_not_raise(self):
        self._call([])  # should not raise

    def test_single_error_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            self._call(["run_in_invalid"])
        assert exc_info.value.status_code == 400

    def test_detail_contains_errors_list(self):
        with pytest.raises(HTTPException) as exc_info:
            self._call(["run_in_invalid"])
        detail = exc_info.value.detail
        assert "errors" in detail
        assert len(detail["errors"]) == 1

    def test_multiple_errors_all_included(self):
        with pytest.raises(HTTPException) as exc_info:
            self._call(["run_in_invalid", "invalid_timezone"])
        errors = exc_info.value.detail["errors"]
        codes = [e["code"] for e in errors]
        assert "run_in_invalid" in codes
        assert "invalid_timezone" in codes

    def test_each_error_entry_has_code_and_message(self):
        with pytest.raises(HTTPException) as exc_info:
            self._call(["run_in_invalid"])
        entry = exc_info.value.detail["errors"][0]
        assert "code" in entry
        assert "message" in entry


# ---------------------------------------------------------------------------
# _parse_allowed_dirs
# ---------------------------------------------------------------------------

class TestParseAllowedDirs:
    def _call(self, value):
        from api import _parse_allowed_dirs
        return _parse_allowed_dirs(value)

    def test_none_returns_none(self):
        assert self._call(None) is None

    def test_empty_string_returns_none(self):
        assert self._call("") is None

    def test_whitespace_only_returns_none(self):
        assert self._call("   ") is None

    def test_comma_separated(self):
        assert self._call("/a,/b") == ["/a", "/b"]

    def test_newline_separated(self):
        assert self._call("/a\n/b") == ["/a", "/b"]

    def test_mixed_separators(self):
        assert self._call("/a,/b\n/c") == ["/a", "/b", "/c"]

    def test_whitespace_around_entries_stripped(self):
        assert self._call("  /a ,  /b  ") == ["/a", "/b"]

    def test_blank_entries_filtered(self):
        assert self._call("/a,,/b") == ["/a", "/b"]

    def test_all_blank_after_filtering_returns_none(self):
        assert self._call(",,,") is None


# ---------------------------------------------------------------------------
# _parse_allowed_env
# ---------------------------------------------------------------------------

class TestParseAllowedEnv:
    """_parse_allowed_env has identical logic to _parse_allowed_dirs."""

    def _call(self, value):
        from api import _parse_allowed_env
        return _parse_allowed_env(value)

    def test_none_returns_none(self):
        assert self._call(None) is None

    def test_comma_separated_keys(self):
        assert self._call("KEY_A,KEY_B") == ["KEY_A", "KEY_B"]

    def test_newline_separated_keys(self):
        assert self._call("KEY_A\nKEY_B") == ["KEY_A", "KEY_B"]

    def test_whitespace_stripped(self):
        assert self._call("  KEY_A ,  KEY_B  ") == ["KEY_A", "KEY_B"]

    def test_blank_entries_filtered(self):
        assert self._call("KEY_A,,KEY_B") == ["KEY_A", "KEY_B"]


# ---------------------------------------------------------------------------
# _is_path_allowed
# ---------------------------------------------------------------------------

class TestIsPathAllowed:
    def _call(self, path: str, allowed_dirs: list[str]) -> bool:
        from api import _is_path_allowed
        return _is_path_allowed(path, allowed_dirs)

    def test_exact_dir_match_allowed(self, tmp_path):
        assert self._call(str(tmp_path), [str(tmp_path)]) is True

    def test_child_path_allowed(self, tmp_path):
        child = tmp_path / "sub" / "program"
        child.parent.mkdir()
        child.touch()
        assert self._call(str(child), [str(tmp_path)]) is True

    def test_path_outside_allowed_dirs_denied(self, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        assert self._call(str(other), [str(allowed)]) is False

    def test_prefix_collision_not_allowed(self, tmp_path):
        """'/usr/bin2' must NOT be allowed by allowed_dirs=['/usr/bin']."""
        base = tmp_path / "bin"
        impostor = tmp_path / "bin2"
        base.mkdir()
        impostor.mkdir()
        assert self._call(str(impostor), [str(base)]) is False

    def test_matches_second_entry_in_list(self, tmp_path):
        allowed1 = tmp_path / "a"
        allowed2 = tmp_path / "b"
        target = tmp_path / "b" / "prog"
        allowed1.mkdir()
        allowed2.mkdir()
        target.touch()
        assert self._call(str(target), [str(allowed1), str(allowed2)]) is True

    def test_empty_allowed_dirs_denies_all(self, tmp_path):
        assert self._call(str(tmp_path), []) is False


# ---------------------------------------------------------------------------
# _get_settings
# ---------------------------------------------------------------------------

class TestGetSettings:
    def _call(self, session):
        from api import _get_settings
        return _get_settings(session)

    def test_creates_settings_row_when_absent(self, db_session):
        from models import Settings
        from sqlalchemy import select
        assert db_session.execute(select(Settings)).scalar_one_or_none() is None
        settings = self._call(db_session)
        assert settings.id is not None

    def test_returns_existing_settings_on_second_call(self, db_session):
        s1 = self._call(db_session)
        s2 = self._call(db_session)
        assert s1.id == s2.id

    def test_no_duplicate_row_created(self, db_session):
        from models import Settings
        from sqlalchemy import select
        self._call(db_session)
        self._call(db_session)
        count = len(db_session.execute(select(Settings)).scalars().all())
        assert count == 1
