"""Tests for nl_parser.py and POST /api/parse.

Covers:
  - _parse_in_duration: pattern matching, command extraction, confidence levels
  - _parse_at_delimiter: pattern matching, command extraction, confidence levels
  - parse_request: error cases, warnings, full ParsedRequest output
  - POST /api/parse API endpoint

Note on confidence scoring:
  Both _parse_in_duration and _parse_at_delimiter check whether the literal
  string "do|run|execute" appears in the regex pattern string. Since all
  patterns that use an explicit do/run/execute keyword embed this group as
  r"(?:do|run|execute)", the substring "do|run|execute" IS present, so the
  "high"/"medium" branch is correctly taken for those patterns.
  Only the final fallback patterns (no explicit keyword) produce lower confidence.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _parse_in_duration
# ---------------------------------------------------------------------------

class TestParseInDuration:
    def _fn(self, text):
        from nl_parser import _parse_in_duration
        return _parse_in_duration(text)

    def test_in_duration_then_run_command(self):
        """'in N minutes run CMD' → command extracted, result not None."""
        result = self._fn("in 5 minutes run echo hello")
        assert result is not None
        command, parsed_time, confidence = result
        assert "echo hello" in command

    def test_run_command_then_in_duration(self):
        """'run CMD in N minutes' → command extracted."""
        result = self._fn("run echo hello in 5 minutes")
        assert result is not None
        command, parsed_time, confidence = result
        assert "echo hello" in command

    def test_command_then_in_duration_fallback(self):
        """'CMD in N minutes' → matches fallback pattern, confidence low."""
        result = self._fn("echo hello in 5 minutes")
        assert result is not None
        command, parsed_time, confidence = result
        assert "echo hello" in command
        assert confidence == "low"

    def test_explicit_keyword_pattern_gives_medium_confidence(self):
        """Patterns with explicit do/run/execute keyword give 'medium' confidence."""
        result = self._fn("in 5 minutes run echo hello")
        assert result is not None
        _, _, confidence = result
        assert confidence == "medium"

    def test_no_match_returns_none(self):
        """Text without a parseable time-then-command structure returns None."""
        result = self._fn("just some words without time")
        assert result is None

    def test_returns_parsed_time(self):
        from datetime import datetime
        result = self._fn("run echo hello in 5 minutes")
        assert result is not None
        _, parsed_time, _ = result
        assert isinstance(parsed_time, datetime)


# ---------------------------------------------------------------------------
# _parse_at_delimiter
# ---------------------------------------------------------------------------

class TestParseAtDelimiter:
    def _fn(self, text):
        from nl_parser import _parse_at_delimiter
        return _parse_at_delimiter(text)

    def test_run_command_at_time(self):
        """'run CMD at TIME' → command extracted."""
        result = self._fn("run echo hello at noon")
        assert result is not None
        command, _, _ = result
        assert "echo hello" in command

    def test_at_time_run_command(self):
        """'at TIME run CMD' → command extracted."""
        result = self._fn("at noon run echo hello")
        assert result is not None
        command, _, _ = result
        assert "echo hello" in command

    def test_explicit_keyword_gives_high_confidence(self):
        """Patterns with do/run/execute give 'high' confidence."""
        result = self._fn("run echo hello at noon")
        assert result is not None
        _, _, confidence = result
        assert confidence == "high"

    def test_command_at_time_fallback_medium_confidence(self):
        """'CMD at TIME' fallback pattern gives 'medium' confidence."""
        result = self._fn("echo hello at noon")
        assert result is not None
        _, _, confidence = result
        assert confidence == "medium"

    def test_no_match_returns_none(self):
        result = self._fn("just some words")
        assert result is None

    def test_at_sign_also_works(self):
        """'@' is accepted as delimiter."""
        result = self._fn("run echo hello @ noon")
        assert result is not None


# ---------------------------------------------------------------------------
# parse_request
# ---------------------------------------------------------------------------

class TestParseRequest:
    def test_empty_text_raises_value_error(self):
        from nl_parser import parse_request
        with pytest.raises(ValueError, match="empty_request"):
            parse_request("")

    def test_whitespace_only_raises_value_error(self):
        from nl_parser import parse_request
        with pytest.raises(ValueError, match="empty_request"):
            parse_request("   ")

    def test_unparseable_raises_value_error(self):
        from nl_parser import parse_request
        with pytest.raises(ValueError, match="unparseable_request"):
            parse_request("xyzzy frobble wumbo")

    def test_valid_in_duration_returns_parsed_request(self):
        from nl_parser import parse_request, ParsedRequest
        result = parse_request("run echo hello in 5 minutes")
        assert isinstance(result, ParsedRequest)
        assert "echo hello" in result.command

    def test_valid_at_delimiter_returns_parsed_request(self):
        from nl_parser import parse_request, ParsedRequest
        result = parse_request("run echo hello at noon")
        assert isinstance(result, ParsedRequest)
        assert "echo hello" in result.command

    def test_low_confidence_adds_confirm_time_warning(self):
        from nl_parser import parse_request
        result = parse_request("echo hello in 5 minutes")
        assert "confirm_time" in result.warnings

    def test_medium_confidence_adds_confirm_time_warning(self):
        from nl_parser import parse_request
        result = parse_request("echo hello at noon")
        assert "confirm_time" in result.warnings

    def test_high_confidence_no_confirm_time_warning(self):
        from nl_parser import parse_request
        result = parse_request("run echo hello at noon")
        assert result.confidence == "high"
        assert "confirm_time" not in result.warnings

    def test_result_has_all_expected_fields(self):
        from nl_parser import parse_request
        from datetime import datetime
        result = parse_request("run echo hello at noon")
        assert result.command
        assert isinstance(result.run_at, datetime)
        assert result.confidence in ("low", "medium", "high")
        assert isinstance(result.interpretation, str)
        assert isinstance(result.warnings, list)

    def test_interpretation_contains_command_and_timestamp(self):
        from nl_parser import parse_request
        result = parse_request("run echo hello at noon")
        assert result.command in result.interpretation
        assert "Run" in result.interpretation


# ---------------------------------------------------------------------------
# POST /api/parse
# ---------------------------------------------------------------------------

class TestApiParseEndpoint:
    def test_valid_text_returns_200(self, api_client):
        client, _ = api_client
        resp = client.post("/api/parse", json={"text": "run echo hello at noon"})
        assert resp.status_code == 200

    def test_response_has_expected_fields(self, api_client):
        client, _ = api_client
        resp = client.post("/api/parse", json={"text": "run echo hello at noon"})
        data = resp.json()
        assert "command" in data
        assert "run_at_local" in data
        assert "run_at_iso" in data
        assert "confidence" in data
        assert "interpretation" in data
        assert "warnings" in data

    def test_empty_text_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post("/api/parse", json={"text": ""})
        assert resp.status_code == 400

    def test_unparseable_text_returns_400(self, api_client):
        client, _ = api_client
        resp = client.post("/api/parse", json={"text": "xyzzy frobble wumbo"})
        assert resp.status_code == 400
