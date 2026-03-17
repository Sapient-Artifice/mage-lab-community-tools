import json
import os
from typing import Any, Dict, Optional

import requests

from utils.functions_metadata import function_schema


DEFAULT_BASE_URL = "http://127.0.0.1:8123"
DEFAULT_TIMEOUT = 10
DEFAULT_ALLOWED_DOMAINS = {"light", "switch"}
DEFAULT_ALLOWED_SERVICES = {"turn_on", "turn_off", "toggle"}
KASA_NAME_HINTS = {"kasa", "tp-link", "tplink", "tp link"}
KASA_PLUG_HINTS = {"plug", "outlet"}


def _get_base_url() -> str:
    return os.getenv("HA_URL", DEFAULT_BASE_URL).rstrip("/")


def _get_timeout() -> int:
    raw = os.getenv("HA_TIMEOUT", str(DEFAULT_TIMEOUT))
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT


def _get_token() -> Optional[str]:
    token = os.getenv("HA_TOKEN", "").strip()
    return token or None


def _parse_json_arg(value: Optional[str], arg_name: str) -> Dict[str, Any]:
    if value is None or value == "":
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {arg_name}: {exc}")
    if not isinstance(parsed, dict):
        raise ValueError(f"{arg_name} must be a JSON object")
    return parsed


def _allowed_domains() -> set[str]:
    raw = os.getenv("HA_ALLOWED_DOMAINS", "")
    if not raw:
        return set(DEFAULT_ALLOWED_DOMAINS)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _allowed_services() -> set[str]:
    raw = os.getenv("HA_ALLOWED_SERVICES", "")
    if not raw:
        return set(DEFAULT_ALLOWED_SERVICES)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _check_allowed(domain: str, service: str) -> Optional[str]:
    domain_allowed = _allowed_domains()
    service_allowed = _allowed_services()
    if domain not in domain_allowed:
        return f"Domain '{domain}' not allowed. Allowed: {sorted(domain_allowed)}"
    if service not in service_allowed:
        return f"Service '{service}' not allowed. Allowed: {sorted(service_allowed)}"
    return None


def _request(method: str, path: str, params: Dict[str, Any] = None, json_data: Dict[str, Any] = None) -> Any:
    token = _get_token()
    if not token:
        raise RuntimeError("HA_TOKEN is not set")

    url = f"{_get_base_url()}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=json_data,
        timeout=_get_timeout(),
    )
    response.raise_for_status()

    if response.content:
        return response.json()
    return None


@function_schema(
    name="ha_health_check",
    description="Verify Home Assistant API connectivity and auth.",
    required_params=[],
    optional_params=[],
)
def ha_health_check() -> str:
    """Check whether Home Assistant is reachable with current credentials."""
    try:
        data = _request("GET", "/api/config")
    except Exception as exc:
        return f"Health check failed: {exc}"

    result = {
        "base_url": _get_base_url(),
        "location_name": data.get("location_name"),
        "version": data.get("version"),
        "state": data.get("state"),
    }
    return json.dumps(result, indent=2)


@function_schema(
    name="ha_list_entities",
    description="List Home Assistant entities with optional filters.",
    required_params=[],
    optional_params=["domain", "name", "area"],
)
def ha_list_entities(domain: Optional[str] = None, name: Optional[str] = None, area: Optional[str] = None) -> str:
    """
    List entities from Home Assistant.

    Args:
        domain: Filter by domain (e.g., switch, light)
        name: Substring match against entity_id or friendly_name
        area: Best-effort match against area fields if present
    """
    try:
        data = _request("GET", "/api/states")
    except Exception as exc:
        return f"Failed to list entities: {exc}"

    domain_filter = domain.lower().strip() if domain else None
    name_filter = name.lower().strip() if name else None
    area_filter = area.lower().strip() if area else None

    results = []
    for item in data:
        entity_id = item.get("entity_id", "")
        attributes = item.get("attributes", {}) or {}
        friendly_name = attributes.get("friendly_name", "")
        entity_domain = entity_id.split(".")[0] if "." in entity_id else ""

        if domain_filter and entity_domain != domain_filter:
            continue

        if name_filter:
            haystack = f"{entity_id} {friendly_name}".lower()
            if name_filter not in haystack:
                continue

        if area_filter:
            area_fields = [
                str(attributes.get("area", "")),
                str(attributes.get("area_id", "")),
                str(attributes.get("room", "")),
            ]
            area_match = any(area_filter in field.lower() for field in area_fields if field)
            if not area_match:
                continue

        results.append(
            {
                "entity_id": entity_id,
                "state": item.get("state"),
                "domain": entity_domain,
                "friendly_name": friendly_name,
            }
        )

    return json.dumps(results, indent=2)


@function_schema(
    name="kasa_list_plugs",
    description="List likely Kasa smart plugs from Home Assistant entities.",
    required_params=[],
    optional_params=["name", "area"],
)
def kasa_list_plugs(name: Optional[str] = None, area: Optional[str] = None) -> str:
    """
    Best-effort listing of Kasa smart plugs.

    Args:
        name: Substring match against entity_id or friendly_name
        area: Best-effort match against area fields if present
    """
    try:
        data = _request("GET", "/api/states")
    except Exception as exc:
        return f"Failed to list Kasa plugs: {exc}"

    name_filter = name.lower().strip() if name else None
    area_filter = area.lower().strip() if area else None

    results = []
    for item in data:
        entity_id = item.get("entity_id", "")
        attributes = item.get("attributes", {}) or {}
        friendly_name = attributes.get("friendly_name", "")
        entity_domain = entity_id.split(".")[0] if "." in entity_id else ""

        if entity_domain != "switch":
            continue

        haystack = f"{entity_id} {friendly_name}".lower()
        if not any(hint in haystack for hint in KASA_NAME_HINTS):
            continue
        if not any(hint in haystack for hint in KASA_PLUG_HINTS):
            continue

        if name_filter and name_filter not in haystack:
            continue

        if area_filter:
            area_fields = [
                str(attributes.get("area", "")),
                str(attributes.get("area_id", "")),
                str(attributes.get("room", "")),
            ]
            area_match = any(area_filter in field.lower() for field in area_fields if field)
            if not area_match:
                continue

        results.append(
            {
                "entity_id": entity_id,
                "state": item.get("state"),
                "domain": entity_domain,
                "friendly_name": friendly_name,
            }
        )

    return json.dumps(results, indent=2)


@function_schema(
    name="ha_get_state",
    description="Get the state of a specific Home Assistant entity.",
    required_params=["entity_id"],
    optional_params=[],
)
def ha_get_state(entity_id: str) -> str:
    """Fetch a specific entity state by entity_id."""
    if not entity_id:
        return "entity_id is required"

    try:
        data = _request("GET", f"/api/states/{entity_id}")
    except Exception as exc:
        return f"Failed to get state for {entity_id}: {exc}"

    return json.dumps(data, indent=2)


@function_schema(
    name="ha_call_service",
    description="Call a Home Assistant service for an entity or area.",
    required_params=["domain", "service"],
    optional_params=["entity_id", "area", "service_data"],
)
def ha_call_service(
    domain: str,
    service: str,
    entity_id: Optional[str] = None,
    area: Optional[str] = None,
    service_data: Optional[str] = None,
) -> str:
    """
    Call a Home Assistant service.

    Args:
        domain: Service domain (e.g., switch, light)
        service: Service name (e.g., turn_on, turn_off)
        entity_id: Target entity_id
        area: Target area_id or area name (best effort)
        service_data: JSON object string with service fields
    """
    if not domain or not service:
        return "domain and service are required"

    domain = domain.lower().strip()
    service = service.lower().strip()

    not_allowed = _check_allowed(domain, service)
    if not_allowed:
        return f"Denied: {not_allowed}"

    try:
        data = _parse_json_arg(service_data, "service_data")
    except ValueError as exc:
        return str(exc)

    payload: Dict[str, Any] = {}
    if data:
        payload.update(data)

    if entity_id:
        payload["entity_id"] = entity_id
    if area:
        payload["area_id"] = area

    try:
        result = _request("POST", f"/api/services/{domain}/{service}", json_data=payload)
    except Exception as exc:
        return f"Service call failed: {exc}"

    return json.dumps(result, indent=2)
