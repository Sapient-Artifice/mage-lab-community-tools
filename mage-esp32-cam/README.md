# mage-esp32-cam

Capture JPEG snapshots from ESP32-CAM modules over WiFi, save them to disk, and open them in a tab — all from a Mage Lab conversation.

## Files

- `esp32_cam_tool.py` — tool functions

## Setup

1. Copy `esp32_cam_tool.py` into `~/Mage/Tools` (or a subfolder).
2. Optionally set environment variables in your Mage env file (see below).
3. Approve the tool in the Mage Lab UI.

No env vars are required to get started — run `esp32_cam_scan_network()` first to discover cameras on your network.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ESP32_CAM_<NAME>` | No | — | Named camera URL, e.g. `ESP32_CAM_FRONT_DOOR=http://192.168.1.101/capture` |
| `ESP32_CAM_DEFAULT` | No | — | Default camera URL when no `camera` or `url` arg is given |
| `ESP32_CAM_TIMEOUT` | No | `10` | HTTP request timeout in seconds for captures |
| `ESP32_CAM_SAVE_DIR` | No | workspace path | Directory to save captured images |

### Named camera example (env file)

```
ESP32_CAM_FRONT_DOOR=http://192.168.1.42/capture
ESP32_CAM_GARAGE=http://192.168.1.43/capture
ESP32_CAM_DEFAULT=http://192.168.1.42/capture
```

Any `ESP32_CAM_<NAME>` entry becomes addressable by its `<NAME>` (case-insensitive, spaces/hyphens normalized to underscores).

## Functions

### `esp32_cam_scan_network(subnet, timeout)`

Scans the local /24 subnet in parallel for hosts that serve JPEG images on known ESP32-CAM paths (`/capture`, `/jpg`, `/photo`). Takes a few seconds.

Works on any RFC-1918 subnet — 10.x.x.x, 172.16.x.x, 192.168.x.x, or any other. The subnet is auto-detected from your machine's outbound network interface; no configuration needed.

| Arg | Required | Description |
|---|---|---|
| `subnet` | No | Network prefix to scan, e.g. `"192.168.1"` (default: auto-detected from local IP) |
| `timeout` | No | Per-host timeout in seconds (default: `1.0`) |

Uses 64 parallel workers; scanning a full /24 takes roughly 2–4 seconds.

**Returns JSON:**

```json
{
  "subnet": "192.168.1.0/24",
  "found": [
    { "ip": "192.168.1.101", "url": "http://192.168.1.101/capture", "content_type": "image/jpeg" }
  ],
  "hint": "To name a camera, add ESP32_CAM_<NAME>=<url> to your env file..."
}
```

### `esp32_cam_capture(camera, url, filename, save_dir, open_after)`

Fetches a snapshot, saves it to disk, and opens it in a tab.

| Arg | Required | Description |
|---|---|---|
| `camera` | No | Named camera (looks up `ESP32_CAM_<NAME>`) |
| `url` | No | Direct capture URL — overrides `camera` lookup |
| `filename` | No | Output filename (default: `esp32cam_<camera>_<timestamp>.jpg`) |
| `save_dir` | No | Override save directory for this capture |
| `open_after` | No | Open in tab after saving (`"true"` / `"false"`, default `"true"`) |

**URL resolution order:** `url` arg → `camera` name env lookup → `ESP32_CAM_DEFAULT`

**Returns JSON:**

```json
{
  "saved": "/home/user/workspace/esp32cam_front_door_20260309_143022.jpg",
  "size_kb": 42.3,
  "url": "http://192.168.1.101/capture",
  "source": "front_door",
  "timestamp": "2026-03-09T14:30:22",
  "opened": true
}
```

### `esp32_cam_list_cameras()`

Lists all named cameras configured via env vars. Does not probe the network — use `esp32_cam_scan_network()` for discovery.

```json
{
  "cameras": [
    { "name": "DEFAULT", "url": "http://192.168.1.101/capture" },
    { "name": "FRONT_DOOR", "url": "http://192.168.1.101/capture" },
    { "name": "GARAGE", "url": "http://192.168.1.102/capture" }
  ]
}
```

## Typical workflow

1. **Discover:** _"Scan the network for cameras"_ → finds `192.168.1.101`
2. **Capture directly:** _"Capture http://192.168.1.101/capture"_ → saves JPEG, opens in tab
3. **Name it (optional):** add `ESP32_CAM_LAB=http://192.168.1.101/capture` to env file
4. **Use by name:** _"Take a snapshot from the lab camera"_

## Notes

- The `/capture` endpoint returns a single JPEG. MJPEG stream URLs (e.g. `/stream`) are not supported — point to `/capture`.
- If the camera returns an unexpected `Content-Type`, the tool reports it rather than saving the response.
- Images are saved with a timestamp in the filename so repeated captures don't overwrite each other.
- The Pylance warnings about `config`, `utils.functions_metadata`, and `ws_manager` are expected — these are Mage Lab internal modules resolved at runtime, not available in local dev environments.
