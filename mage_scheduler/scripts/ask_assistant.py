#!/usr/bin/env python3
"""Send a scheduled message to the ask_assistant endpoint.

Reads the MESSAGE environment variable and POSTs it as JSON to
http://127.0.0.1:11115/ask_assistant. Exits non-zero on failure so
Celery marks the task as failed.

Usage (via action):
    env MESSAGE="your message here" python3 ask_assistant.py
"""
import json
import os
import sys
import urllib.request

ENDPOINT = "http://127.0.0.1:11115/ask_assistant"

message = os.environ.get("MESSAGE", "").strip()
if not message:
    print("ERROR: MESSAGE environment variable is required and must not be empty", file=sys.stderr)
    sys.exit(1)

payload = json.dumps({"message": message}).encode()
req = urllib.request.Request(
    ENDPOINT,
    data=payload,
    headers={"Content-Type": "application/json"},
)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        print(body)
except urllib.error.HTTPError as exc:
    body = exc.read().decode()
    print(f"ERROR: HTTP {exc.code} from ask_assistant: {body}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)
