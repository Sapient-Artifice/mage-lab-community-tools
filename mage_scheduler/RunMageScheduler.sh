#!/bin/bash

cd /home/bard/Mage/Workspace/mage_scheduler

uv run celery -A celery_app worker --beat --loglevel=info &

uv run celery --broker=redis://localhost:6379/0 flower --port=5555 &
