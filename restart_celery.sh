#!/bin/bash
pkill -f "celery" 2>/dev/null
sleep 1
RSENTRY_ROOT="$(cd "$(dirname "$0")" && pwd)"
set -a && source "$RSENTRY_ROOT/.env" && set +a
PYTHONPATH="$RSENTRY_ROOT" \
  "$RSENTRY_ROOT/venv/bin/celery" \
  -A backend.workers.tasks:celery_app worker \
  --loglevel=info \
  >> /tmp/rsentry-celery.log 2>&1 &
echo "Celery PID: $!"
