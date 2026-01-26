import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, urlparse

import requests

from config import config
from utils.functions_metadata import function_schema
from ws_manager import open_tab

try:
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
except ImportError:
    WebClient = None
    SocketModeClient = None
    SocketModeRequest = None
    SocketModeResponse = None


logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_MAGE_API_TOKEN = os.getenv("SLACK_MAGE_API_TOKEN")
ASK_ASSISTANT_URL = os.getenv("MAGE_ASK_ASSISTANT_URL", "http://127.0.0.1:11115/ask_assistant")

WORKSPACE_DIR = Path(config.workspace_path).expanduser().resolve()
DATA_DIR = WORKSPACE_DIR / ".slack_mage"
CONFIG_PATH = DATA_DIR / "slack_mage_config.json"
STATE_PATH = DATA_DIR / "slack_mage_state.json"

DEFAULT_CONFIG = {
    "version": 1,
    "rules": [],
    "notification_settings": {
        "throttle_seconds": 30
    }
}

DEFAULT_STATE = {
    "event_counts": {},
    "recent_events": [],
    "last_notified": {}
}

STATE_LOCK = threading.RLock()

LISTENER_LOCK = threading.Lock()
LISTENER_STATE: Dict[str, Any] = {
    "client": None,
    "thread": None,
    "running": False
}

SERVER_LOCK = threading.Lock()
SERVER_STATE: Dict[str, Any] = {
    "httpd": None,
    "thread": None,
    "port": None
}

LOOKUP_CACHE_LOCK = threading.Lock()
LOOKUP_CACHE: Dict[str, Any] = {
    "users": {"ts": 0, "data": []},
    "channels": {"ts": 0, "data": []}
}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return json.loads(json.dumps(default))


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _load_config() -> Dict[str, Any]:
    _ensure_data_dir()
    with STATE_LOCK:
        config_data = _load_json(CONFIG_PATH, DEFAULT_CONFIG)
        if "notification_settings" not in config_data:
            config_data["notification_settings"] = DEFAULT_CONFIG["notification_settings"].copy()
        if "rules" not in config_data:
            config_data["rules"] = []
        return config_data


def _save_config(config_data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with STATE_LOCK:
        _atomic_write(CONFIG_PATH, config_data)


def _load_state() -> Dict[str, Any]:
    _ensure_data_dir()
    with STATE_LOCK:
        state = _load_json(STATE_PATH, DEFAULT_STATE)
        state.setdefault("event_counts", {})
        state.setdefault("recent_events", [])
        state.setdefault("last_notified", {})
        return state


def _save_state(state: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with STATE_LOCK:
        _atomic_write(STATE_PATH, state)


def _get_slack_client() -> Optional[Any]:
    if WebClient is None:
        return None
    if not SLACK_BOT_TOKEN:
        return None
    return WebClient(token=SLACK_BOT_TOKEN)


def _lookup_users(query: str) -> List[Dict[str, Any]]:
    client = _get_slack_client()
    if not client:
        return []
    now = time.time()
    try:
        with LOOKUP_CACHE_LOCK:
            if now - LOOKUP_CACHE["users"]["ts"] < 300:
                users = LOOKUP_CACHE["users"]["data"]
            else:
                users = []
                cursor = None
                while True:
                    response = client.users_list(limit=200, cursor=cursor)
                    users.extend(response.get("members", []))
                    cursor = response.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
                LOOKUP_CACHE["users"] = {"ts": now, "data": users}
    except Exception as exc:
        logger.warning("User lookup failed: %s", exc)
        return []
    q = query.lower()
    results = []
    for user in users:
        profile = user.get("profile", {})
        hay = " ".join(
            [
                user.get("name", ""),
                profile.get("real_name", ""),
                profile.get("display_name", "")
            ]
        ).lower()
        if q in hay:
            results.append(
                {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "real_name": profile.get("real_name"),
                    "display_name": profile.get("display_name")
                }
            )
    return results[:50]


def _lookup_channels(query: str) -> List[Dict[str, Any]]:
    client = _get_slack_client()
    if not client:
        return []
    now = time.time()
    try:
        with LOOKUP_CACHE_LOCK:
            if now - LOOKUP_CACHE["channels"]["ts"] < 300:
                channels = LOOKUP_CACHE["channels"]["data"]
            else:
                channels = []
                cursor = None
                while True:
                    response = client.conversations_list(
                        limit=200,
                        cursor=cursor,
                        types="public_channel,private_channel,im,mpim"
                    )
                    channels.extend(response.get("channels", []))
                    cursor = response.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
                LOOKUP_CACHE["channels"] = {"ts": now, "data": channels}
    except Exception as exc:
        logger.warning("Channel lookup failed: %s", exc)
        return []
    q = query.lower()
    results = []
    for channel in channels:
        name = channel.get("name") or channel.get("user") or ""
        if q in name.lower():
            results.append(
                {
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "user": channel.get("user"),
                    "is_private": channel.get("is_private", False),
                    "is_im": channel.get("is_im", False),
                    "is_mpim": channel.get("is_mpim", False),
                }
            )
    return results[:50]


def _notify_assistant(rule: Dict[str, Any], event_info: Dict[str, Any]) -> None:
    include_message = bool(rule.get("notify_include_message"))
    if include_message and event_info.get("text"):
        message = (
            "Slack event notification (message content included): "
            f"rule='{rule.get('name')}', "
            f"event_type={event_info.get('event_type')}, "
            f"user_id={event_info.get('user_id')}, "
            f"channel_id={event_info.get('channel_id')}, "
            f"timestamp={event_info.get('timestamp')}, "
            f"message={event_info.get('text')!r}. "
            "If needed, call notify_me."
        )
    else:
        message = (
            "Slack event notification (no message content): "
            f"rule='{rule.get('name')}', "
            f"event_type={event_info.get('event_type')}, "
            f"user_id={event_info.get('user_id')}, "
            f"channel_id={event_info.get('channel_id')}, "
            f"timestamp={event_info.get('timestamp')}. "
            "Please do not read the message content. "
            "If needed, call notify_me."
        )
    try:
        requests.post(ASK_ASSISTANT_URL, json={"message": message}, timeout=5)
    except Exception as exc:
        logger.warning("ask_assistant failed: %s", exc)


def _handle_message_event(event: Dict[str, Any]) -> None:
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")
    message_text = event.get("text") or ""
    if len(message_text) > 2000:
        message_text = message_text[:2000] + "..."
    if not user_id or not channel_id:
        return

    config_data = _load_config()
    rules = config_data.get("rules", [])
    notification_settings = config_data.get("notification_settings", {})
    throttle_seconds = int(notification_settings.get("throttle_seconds", 30))

    matched = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if rule.get("event_type") != "message_posted":
            continue
        if rule.get("channel_id") and rule.get("channel_id") != channel_id:
            continue
        if rule.get("user_id") and rule.get("user_id") != user_id:
            continue
        matched.append(rule)

    if not matched:
        return

    notify_queue = []
    with STATE_LOCK:
        state = _load_state()
        recent_events = state.get("recent_events", [])
        event_counts = state.get("event_counts", {})
        last_notified = state.get("last_notified", {})

        for rule in matched:
            rule_id = rule.get("id")
            if not rule_id:
                continue
            event_info = {
                "rule_id": rule_id,
                "rule_name": rule.get("name"),
                "event_type": "message_posted",
                "channel_id": channel_id,
                "user_id": user_id,
                "timestamp": timestamp,
                "text": message_text
            }
            if rule.get("surface", True):
                event_counts[rule_id] = event_counts.get(rule_id, 0) + 1
                recent_events.append(event_info)
            if rule.get("notify_assistant"):
                last_ts = float(last_notified.get(rule_id, 0))
                now = time.time()
                if now - last_ts >= throttle_seconds:
                    last_notified[rule_id] = now
                    notify_queue.append((rule, event_info))

        state["recent_events"] = recent_events[-200:]
        state["event_counts"] = event_counts
        state["last_notified"] = last_notified
        _save_state(state)

    for rule, event_info in notify_queue:
        _notify_assistant(rule, event_info)


def _process_socket_mode(client: Any, req: Any) -> None:
    if SocketModeRequest is None:
        return
    if req.type == "events_api":
        response = SocketModeResponse(envelope_id=req.envelope_id)
        client.send_socket_mode_response(response)
        payload = req.payload or {}
        event = payload.get("event", {})
        if event.get("type") != "message":
            return
        if event.get("subtype") is not None:
            return
        if event.get("bot_id") or event.get("user") is None:
            return
        _handle_message_event(event)


def _start_listener() -> str:
    if SocketModeClient is None:
        return "Error: slack_sdk is not installed. Install slack_sdk in the mage lab environment."
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        return "Error: SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set in .env."

    with LISTENER_LOCK:
        if LISTENER_STATE["running"]:
            return "Slack listener is already running."

        web_client = WebClient(token=SLACK_BOT_TOKEN)
        client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)
        client.socket_mode_request_listeners.append(_process_socket_mode)

        def _run():
            try:
                client.connect()
                if hasattr(client, "wait"):
                    client.wait()
                else:
                    while _listener_status():
                        time.sleep(1)
            except Exception as exc:
                logger.error("Socket Mode client failed: %s", exc)
            finally:
                with LISTENER_LOCK:
                    LISTENER_STATE["running"] = False

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        LISTENER_STATE["client"] = client
        LISTENER_STATE["thread"] = thread
        LISTENER_STATE["running"] = True

    return "Slack listener started."


def _stop_listener() -> str:
    with LISTENER_LOCK:
        client = LISTENER_STATE.get("client")
        if not LISTENER_STATE.get("running") or client is None:
            return "Slack listener is not running."

        LISTENER_STATE["running"] = False
        if hasattr(client, "disconnect"):
            client.disconnect()
        elif hasattr(client, "close"):
            client.close()
        LISTENER_STATE["client"] = None
        LISTENER_STATE["thread"] = None
        LISTENER_STATE["running"] = False
    return "Slack listener stopped."


def _listener_status() -> bool:
    with LISTENER_LOCK:
        return bool(LISTENER_STATE.get("running"))


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _SlackMageHandler(BaseHTTPRequestHandler):
    server_version = "SlackMage/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("SlackMage server: %s", format % args)

    def _set_cors(self) -> None:
        origin = self.headers.get("Origin")
        if not origin:
            return
        allowed = {
            "http://127.0.0.1:11115",
            "http://localhost:11115",
        }
        if origin in allowed or origin.startswith("http://127.0.0.1:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Token, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _is_authorized(self) -> bool:
        if not SLACK_MAGE_API_TOKEN:
            return False
        token = self.headers.get("X-API-Token")
        if not token:
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "", 1).strip()
        if not token:
            query = parse_qs(urlparse(self.path).query)
            token = query.get("token", [None])[0]
        return bool(token and token == SLACK_MAGE_API_TOKEN)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, payload: str, status: int = 200, content_type: str = "text/plain") -> None:
        data = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return None
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return None

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            if not self._is_authorized():
                self._send_text("Unauthorized. Provide SLACK_MAGE_API_TOKEN.", status=401)
                return
            html_path = Path(__file__).parent / "slack_mage_dashboard.html"
            if not html_path.exists():
                self._send_text("Dashboard HTML not found.", status=404)
                return
            html = html_path.read_text(encoding="utf-8")
            api_base = f"http://127.0.0.1:{self.server.server_address[1]}"
            html = _inject_dashboard_context(html, SLACK_MAGE_API_TOKEN, api_base)
            self._send_text(html, content_type="text/html")
            return

        if not self._is_authorized():
            self._send_json({"error": "unauthorized"}, status=401)
            return

        if parsed.path == "/config":
            self._send_json(_load_config())
            return
        if parsed.path == "/state":
            self._send_json(_load_state())
            return
        if parsed.path == "/status":
            self._send_json({"listener_running": _listener_status()})
            return
        if parsed.path == "/lookup/users":
            query = parse_qs(parsed.query).get("query", [""])[0]
            self._send_json({"results": _lookup_users(query)})
            return
        if parsed.path == "/lookup/channels":
            query = parse_qs(parsed.query).get("query", [""])[0]
            self._send_json({"results": _lookup_channels(query)})
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._is_authorized():
            self._send_json({"error": "unauthorized"}, status=401)
            return

        if parsed.path == "/config":
            payload = self._read_json_body()
            if not payload:
                self._send_json({"error": "invalid_json"}, status=400)
                return
            payload.setdefault("rules", [])
            payload.setdefault("notification_settings", DEFAULT_CONFIG["notification_settings"].copy())
            _save_config(payload)
            self._send_json({"status": "ok"})
            return
        if parsed.path == "/state/reset":
            _save_state(json.loads(json.dumps(DEFAULT_STATE)))
            self._send_json({"status": "ok"})
            return
        if parsed.path == "/listener/start":
            self._send_json({"status": _start_listener()})
            return
        if parsed.path == "/listener/stop":
            self._send_json({"status": _stop_listener()})
            return
        self._send_json({"error": "not_found"}, status=404)


def _start_server() -> str:
    if not SLACK_MAGE_API_TOKEN:
        return "Error: SLACK_MAGE_API_TOKEN must be set in .env."
    with SERVER_LOCK:
        if SERVER_STATE["httpd"] is not None:
            return "Server already running."
        httpd = _ThreadingHTTPServer(("127.0.0.1", 0), _SlackMageHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        SERVER_STATE["httpd"] = httpd
        SERVER_STATE["thread"] = thread
        SERVER_STATE["port"] = port
    return "Server started."


def _server_url() -> Optional[str]:
    with SERVER_LOCK:
        port = SERVER_STATE.get("port")
    if not port:
        return None
    return f"http://127.0.0.1:{port}/"


def _inject_dashboard_context(html: str, token: str, api_base: str) -> str:
    payload = (
        "<script>"
        f"window.__SLACK_MAGE_TOKEN = {json.dumps(token)};"
        f"window.__SLACK_MAGE_API_BASE = {json.dumps(api_base)};"
        "</script>"
    )
    if "</head>" in html:
        return html.replace("</head>", f"{payload}</head>", 1)
    return f"{html}{payload}"


@function_schema(
    name="open_slack_mage_dashboard",
    description="Open the Slack Mage dashboard.",
    required_params=[],
    optional_params=[],
)
def open_slack_mage_dashboard() -> str:
    """
    Opens the Slack Mage dashboard in a new tab.
    """
    start_status = _start_server()
    if start_status.startswith("Error"):
        return start_status
    url = _server_url()
    if not url:
        return "Error: Dashboard server failed to start."
    token_param = quote_plus(SLACK_MAGE_API_TOKEN)
    url_with_token = f"{url}?token={token_param}"
    open_tab(url_with_token)
    return "Slack Mage dashboard opened."


@function_schema(
    name="slack_mage_start_listener",
    description="Start the Slack Socket Mode listener.",
    required_params=[],
    optional_params=[],
)
def slack_mage_start_listener() -> str:
    """
    Start the Slack Socket Mode listener.
    """
    return _start_listener()


@function_schema(
    name="slack_mage_stop_listener",
    description="Stop the Slack Socket Mode listener.",
    required_params=[],
    optional_params=[],
)
def slack_mage_stop_listener() -> str:
    """
    Stop the Slack Socket Mode listener.
    """
    return _stop_listener()


@function_schema(
    name="slack_mage_status",
    description="Get Slack Mage listener status.",
    required_params=[],
    optional_params=[],
)
def slack_mage_status() -> str:
    """
    Get status of the Slack Mage listener.
    """
    running = _listener_status()
    return f"Slack listener running: {running}."
