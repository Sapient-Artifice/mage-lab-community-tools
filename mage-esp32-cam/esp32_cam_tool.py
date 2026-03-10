import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import requests

from config import config
from utils.functions_metadata import function_schema
from ws_manager import open_tab

DEFAULT_TIMEOUT = 10
SCAN_TIMEOUT = 1.0
SCAN_WORKERS = 64
_CAM_PREFIX = "ESP32_CAM_"
_RESERVED_SUFFIXES = {"DEFAULT", "TIMEOUT", "SAVE_DIR"}
_CAPTURE_PATHS = ["/capture", "/jpg", "/photo"]


def _get_timeout() -> int:
    raw = os.getenv("ESP32_CAM_TIMEOUT", str(DEFAULT_TIMEOUT))
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT


def _get_save_dir() -> Path:
    raw = os.getenv("ESP32_CAM_SAVE_DIR", "")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(config.workspace_path).expanduser().resolve()


def _resolve_url(camera: Optional[str], url: Optional[str]) -> tuple[str, str]:
    """
    Returns (resolved_url, source_label).

    Priority: url arg > camera name env lookup > ESP32_CAM_DEFAULT.
    """
    if url:
        return url.strip(), "direct"

    if camera:
        key = f"{_CAM_PREFIX}{camera.upper().replace(' ', '_').replace('-', '_')}"
        val = os.getenv(key, "").strip()
        if val:
            return val, camera
        raise ValueError(
            f"Camera '{camera}' not found. Set {key} in your env file, "
            f"or pass url directly."
        )

    default = os.getenv("ESP32_CAM_DEFAULT", "").strip()
    if default:
        return default, "default"

    raise ValueError(
        "No camera URL resolved. Pass url=, camera=, or set ESP32_CAM_DEFAULT."
    )


def _derive_stream_url(capture_url: str) -> str:
    """
    Derive the MJPEG stream URL from a capture URL.

    The Espressif CameraWebServer firmware runs two HTTP servers:
      - Port 80 (or user-configured): capture endpoint (/capture)
      - Port 81 (capture_port + 1):   stream endpoint (/stream)

    This function replaces the path with /stream and increments the port by 1
    to match that convention. Pass stream_url= directly to esp32_cam_stream()
    to override if your firmware uses a different layout.
    """
    parsed = urlparse(capture_url)
    capture_port = parsed.port or 80
    stream_port = capture_port + 1
    netloc = f"{parsed.hostname}:{stream_port}"
    return urlunparse(parsed._replace(netloc=netloc, path="/stream"))


def _named_cameras() -> dict[str, str]:
    """Return all named cameras from env (excludes reserved suffixes)."""
    cameras = {}
    for key, val in os.environ.items():
        if not key.startswith(_CAM_PREFIX):
            continue
        suffix = key[len(_CAM_PREFIX):]
        if suffix in _RESERVED_SUFFIXES or not val.strip():
            continue
        cameras[suffix] = val.strip()
    return cameras


def _local_subnet() -> Optional[str]:
    """Best-effort: return the /24 subnet of the default outbound interface (e.g. '192.168.1')."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3])
    except Exception:
        pass
    return None


def _probe_host(host: str, timeout: float) -> Optional[dict]:
    """Try known ESP32-CAM capture paths on host:80. Return dict if found, else None."""
    for path in _CAPTURE_PATHS:
        url = f"http://{host}{path}"
        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            ct = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and ("image" in ct or "jpeg" in ct):
                resp.close()
                return {"ip": host, "url": url, "content_type": ct}
        except Exception:
            pass
    return None


def _render_stream_html(stream_url: str, label: str) -> str:
    """Generate a minimal HTML page that displays an MJPEG stream via <img>."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ESP32-CAM — {label}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #111;
      color: #ccc;
      font-family: monospace;
      display: flex;
      flex-direction: column;
      align-items: center;
      height: 100vh;
      overflow: hidden;
    }}
    header {{
      width: 100%;
      padding: 6px 12px;
      background: #1a1a1a;
      border-bottom: 1px solid #333;
      display: flex;
      align-items: center;
      gap: 12px;
      flex-shrink: 0;
    }}
    .dot {{
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #e53;
      animation: pulse 1.2s ease-in-out infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.3; }}
    }}
    .label {{ font-size: 13px; color: #aaa; }}
    .url {{ font-size: 11px; color: #555; margin-left: auto; }}
    .stream-wrap {{
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      min-height: 0;
    }}
    img {{
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      display: block;
    }}
    .error {{
      display: none;
      color: #e53;
      font-size: 13px;
      text-align: center;
      padding: 16px;
    }}
  </style>
</head>
<body>
  <header>
    <div class="dot"></div>
    <span class="label">ESP32-CAM &mdash; {label}</span>
    <span class="url">{stream_url}</span>
  </header>
  <div class="stream-wrap">
    <img id="stream" src="{stream_url}" alt="MJPEG stream"
         onerror="document.getElementById('err').style.display='block';
                  document.getElementById('stream').style.display='none';">
    <p class="error" id="err">
      Stream unavailable.<br>
      Check that the camera is reachable at {stream_url}
    </p>
  </div>
</body>
</html>
"""


@function_schema(
    name="esp32_cam_capture",
    description=(
        "Capture a JPEG snapshot from an ESP32-CAM over WiFi, save it to disk, "
        "and open it in a tab. Resolve camera URL from: url arg > camera name "
        "(ESP32_CAM_<NAME> env var) > ESP32_CAM_DEFAULT env var."
    ),
    required_params=[],
    optional_params=["camera", "url", "filename", "save_dir", "open_after"],
)
def esp32_cam_capture(
    camera: Optional[str] = None,
    url: Optional[str] = None,
    filename: Optional[str] = None,
    save_dir: Optional[str] = None,
    open_after: Optional[str] = "true",
) -> str:
    """
    Capture a snapshot from an ESP32-CAM.

    Args:
        camera:   Named camera (matches ESP32_CAM_<NAME> env var, e.g. "front_door")
        url:      Direct capture URL (overrides camera name lookup)
        filename: Output filename (default: esp32cam_<camera>_<timestamp>.jpg)
        save_dir: Directory to save into (default: ESP32_CAM_SAVE_DIR or workspace)
        open_after: Open the saved image in a tab ("true"/"false", default "true")
    """
    try:
        cam_url, source = _resolve_url(camera, url)
    except ValueError as exc:
        return str(exc)

    dest_dir = Path(save_dir).expanduser().resolve() if save_dir else _get_save_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = source.lower().replace(" ", "_").replace("-", "_")
        filename = f"esp32cam_{label}_{ts}.jpg"

    dest = dest_dir / filename

    try:
        resp = requests.get(cam_url, timeout=_get_timeout())
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        return f"Connection failed: could not reach {cam_url}"
    except requests.exceptions.Timeout:
        return f"Timeout after {_get_timeout()}s connecting to {cam_url}"
    except requests.exceptions.HTTPError as exc:
        return f"HTTP error from camera: {exc}"
    except Exception as exc:
        return f"Capture failed: {exc}"

    content_type = resp.headers.get("Content-Type", "")
    if content_type and "image" not in content_type and "jpeg" not in content_type:
        return (
            f"Unexpected Content-Type '{content_type}' from {cam_url}. "
            f"Expected an image response."
        )

    try:
        dest.write_bytes(resp.content)
    except OSError as exc:
        return f"Failed to save image: {exc}"

    size_kb = round(len(resp.content) / 1024, 1)
    result = {
        "saved": str(dest),
        "size_kb": size_kb,
        "url": cam_url,
        "source": source,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    should_open = (open_after or "true").strip().lower() not in ("false", "0", "no")
    if should_open:
        open_tab(str(dest))
        result["opened"] = True

    return json.dumps(result, indent=2)


@function_schema(
    name="esp32_cam_stream",
    description=(
        "Open a live MJPEG stream from an ESP32-CAM in a tab. "
        "Generates an HTML viewer and opens it. The stream URL is derived from the "
        "capture URL by replacing the path with /stream, or can be provided directly. "
        "Resolve camera from: stream_url arg > url arg > camera name "
        "(ESP32_CAM_<NAME> env var) > ESP32_CAM_DEFAULT env var."
    ),
    required_params=[],
    optional_params=["camera", "url", "stream_url"],
)
def esp32_cam_stream(
    camera: Optional[str] = None,
    url: Optional[str] = None,
    stream_url: Optional[str] = None,
) -> str:
    """
    Open a live MJPEG stream from an ESP32-CAM in a viewer tab.

    Args:
        camera:     Named camera (matches ESP32_CAM_<NAME> env var)
        url:        Capture URL to derive stream URL from (e.g. http://192.168.1.101/capture)
        stream_url: Direct MJPEG stream URL — skips derivation (e.g. http://192.168.1.101/stream)
    """
    # Resolve the base (capture) URL first, then derive stream URL unless given directly
    if stream_url:
        resolved_stream = stream_url.strip()
        source = "direct"
    else:
        try:
            capture_url, source = _resolve_url(camera, url)
        except ValueError as exc:
            return str(exc)
        resolved_stream = _derive_stream_url(capture_url)

    label = source if source != "direct" else urlparse(resolved_stream).hostname or "camera"
    label_display = label.replace("_", " ").title()

    # Write the HTML viewer to the save dir; overwrite per camera so tabs don't accumulate
    save_dir = _get_save_dir()
    save_dir.mkdir(parents=True, exist_ok=True)
    slug = label.lower().replace(" ", "_").replace("-", "_")
    html_path = save_dir / f"esp32cam_stream_{slug}.html"

    try:
        html_path.write_text(_render_stream_html(resolved_stream, label_display), encoding="utf-8")
    except OSError as exc:
        return f"Failed to write stream viewer: {exc}"

    open_tab(str(html_path))

    return json.dumps(
        {
            "stream_url": resolved_stream,
            "viewer": str(html_path),
            "source": source,
            "opened": True,
        },
        indent=2,
    )


@function_schema(
    name="esp32_cam_list_cameras",
    description=(
        "List all named ESP32-CAM cameras configured via ESP32_CAM_<NAME> env vars, "
        "plus the default camera if set."
    ),
    required_params=[],
    optional_params=[],
)
def esp32_cam_list_cameras() -> str:
    """List all configured ESP32-CAM cameras from env vars."""
    cameras = _named_cameras()
    default = os.getenv("ESP32_CAM_DEFAULT", "").strip()

    result: dict = {}
    if default:
        result["DEFAULT"] = default
    result.update(cameras)

    if not result:
        return json.dumps(
            {
                "cameras": [],
                "hint": (
                    "No cameras configured. Add ESP32_CAM_<NAME>=<url> entries "
                    "to your env file, e.g. ESP32_CAM_FRONT_DOOR=http://192.168.1.101/capture. "
                    "Use esp32_cam_scan_network() to discover cameras on your local network."
                ),
            },
            indent=2,
        )

    return json.dumps(
        {"cameras": [{"name": k, "url": v} for k, v in result.items()]},
        indent=2,
    )


@function_schema(
    name="esp32_cam_scan_network",
    description=(
        "Scan the local network for ESP32-CAM devices by probing each host on the /24 "
        "subnet for a JPEG capture endpoint. Returns discovered camera IPs and URLs. "
        "Optionally specify a different subnet (e.g. '192.168.1'). "
        "Takes a few seconds to complete."
    ),
    required_params=[],
    optional_params=["subnet", "timeout"],
)
def esp32_cam_scan_network(
    subnet: Optional[str] = None,
    timeout: Optional[str] = None,
) -> str:
    """
    Scan the local /24 subnet for hosts that serve JPEG images on known ESP32-CAM paths.

    Args:
        subnet:  Network prefix to scan, e.g. "192.168.1" (default: auto-detected /24)
        timeout: Per-host HTTP timeout in seconds (default: 1.0)
    """
    if subnet:
        net = subnet.rstrip(".")
    else:
        net = _local_subnet()
        if not net:
            return "Could not determine local subnet. Pass subnet= explicitly (e.g. '192.168.1')."

    try:
        probe_timeout = float(timeout) if timeout else SCAN_TIMEOUT
    except ValueError:
        probe_timeout = SCAN_TIMEOUT

    hosts = [f"{net}.{i}" for i in range(1, 255)]
    found = []

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        futures = {pool.submit(_probe_host, h, probe_timeout): h for h in hosts}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                found.append(result)

    found.sort(key=lambda x: [int(p) for p in x["ip"].split(".")])

    if not found:
        return json.dumps(
            {
                "subnet": f"{net}.0/24",
                "found": [],
                "hint": (
                    "No ESP32-CAM devices found. Check that the camera is powered on "
                    "and connected to the same network."
                ),
            },
            indent=2,
        )

    return json.dumps(
        {
            "subnet": f"{net}.0/24",
            "found": found,
            "hint": (
                "To name a camera, add ESP32_CAM_<NAME>=<url> to your env file, "
                "e.g. ESP32_CAM_FRONT_DOOR=http://192.168.1.101/capture"
            ),
        },
        indent=2,
    )
