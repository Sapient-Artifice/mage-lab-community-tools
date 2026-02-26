#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

CELERY_PID=""
UVICORN_PID=""

cleanup() {
    echo "Stopping services..."
    [ -n "$CELERY_PID" ] && kill "$CELERY_PID" 2>/dev/null || true
    [ -n "$UVICORN_PID" ] && kill "$UVICORN_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting Celery worker+beat..."
uv run celery -A celery_app worker --beat --loglevel=info &
CELERY_PID=$!

echo "Starting Uvicorn on port 8012..."
uv run uvicorn api:app --port 8012 &
UVICORN_PID=$!

echo "Both services running. Press Ctrl+C to stop."
wait
