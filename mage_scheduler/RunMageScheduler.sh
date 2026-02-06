#!/bin/bash

set -euo pipefail

cd /home/bard/Desktop/mage-lab-community-tools/mage_scheduler

uv run celery -A celery_app worker --beat --loglevel=info &
uv run uvicorn api:app --reload --port 8012 &
