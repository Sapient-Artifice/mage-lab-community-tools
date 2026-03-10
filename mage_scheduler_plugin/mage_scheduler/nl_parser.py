from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
import re
import dateparser
from dateparser.search import search_dates


@dataclass
class ParsedRequest:
    command: str
    run_at: datetime
    confidence: str
    interpretation: str
    warnings: list[str]


def parse_request(text: str) -> ParsedRequest:
    text = text.strip()
    if not text:
        raise ValueError("empty_request")

    warnings: list[str] = []

    for parser in (_parse_in_duration, _parse_at_delimiter, _parse_search_dates):
        result = parser(text)
        if result is None:
            continue
        command_text, parsed_time, confidence = result
        interpretation = _interpret(command_text, parsed_time)
        if confidence in ("low", "medium"):
            warnings.append("confirm_time")
        return ParsedRequest(
            command=command_text,
            run_at=parsed_time,
            confidence=confidence,
            interpretation=interpretation,
            warnings=warnings,
        )

    raise ValueError("unparseable_request")


def _parse_in_duration(text: str) -> tuple[str, datetime, str] | None:
    patterns = [
        r"^\s*in\s+(?P<duration>.+?)\s+(?:do|run|execute)\s+(?P<command>.+)$",
        r"^\s*(?:do|run|execute)\s+(?P<command>.+?)\s+in\s+(?P<duration>.+)$",
        r"^\s*(?P<command>.+?)\s+in\s+(?P<duration>.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        command = match.group("command").strip()
        duration_text = f"in {match.group('duration').strip()}"
        parsed_time = _parse_time(duration_text)
        if not command:
            return None
        confidence = "medium" if "do|run|execute" in pattern else "low"
        return command, parsed_time, confidence
    return None


def _parse_at_delimiter(text: str) -> tuple[str, datetime, str] | None:
    patterns = [
        r"^\s*(?:do|run|execute)\s+(?P<command>.+?)\s+(?:at|@)\s+(?P<time>.+)$",
        r"^\s*(?:at|@)\s+(?P<time>.+?)\s+(?:do|run|execute)\s+(?P<command>.+)$",
        r"^\s*(?P<command>.+?)\s+(?:at|@)\s+(?P<time>.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        command = match.group("command").strip()
        time_text = match.group("time").strip()
        if not command or not time_text:
            return None
        parsed_time = _parse_time(time_text)
        confidence = "high" if "do|run|execute" in pattern else "medium"
        return command, parsed_time, confidence
    return None


def _parse_search_dates(text: str) -> tuple[str, datetime, str] | None:
    results = search_dates(
        text,
        settings={
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    if not results:
        return None

    time_text, parsed_time = results[-1]
    if parsed_time is None:
        return None

    command = _strip_time_phrase(text, time_text)
    if not command:
        return None
    parsed_time = _normalize_to_local(parsed_time)
    return command, parsed_time, "low"


def _parse_time(time_text: str) -> datetime:
    parsed = dateparser.parse(
        time_text,
        settings={
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    if parsed is None:
        raise ValueError("unparseable_time")

    return _normalize_to_local(parsed)


def _normalize_to_local(parsed: datetime) -> datetime:
    local_tz = datetime.now().astimezone().tzinfo
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(local_tz).replace(tzinfo=None)


def _strip_time_phrase(text: str, time_text: str) -> str:
    command = text.replace(time_text, " ")
    command = re.sub(r"\b(at|on|around|by)\b", " ", command, flags=re.IGNORECASE)
    command = re.sub(r"\s+", " ", command).strip()
    return command


def _interpret(command: str, run_at: datetime) -> str:
    timestamp = run_at.strftime("%Y-%m-%d %H:%M:%S")
    return f'Run \"{command}\" at {timestamp} (local)'
