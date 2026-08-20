#!/usr/bin/env bash
# Pause DramValue scheduled tasks (host crons + Celery beat/worker).
# The API, database, and Redis stay running so the site remains online.
#
# Usage: ./scripts/pause-scheduling.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRON_MARKER="# DramValue automated tasks"
DISABLED_MARKER="# DramValue automated tasks (DISABLED)"

cd "$REPO_DIR"

echo "==> Stopping Celery beat and worker..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop beat worker 2>/dev/null \
  || docker compose -f docker-compose.yml stop beat worker

if crontab -l 2>/dev/null | grep -q "^${DISABLED_MARKER}$"; then
  echo "==> Host crons already disabled"
else
  echo "==> Disabling host crons..."
  crontab -l 2>/dev/null | sed \
    -e "s/^${CRON_MARKER}$/${DISABLED_MARKER}/" \
    -e "/^${DISABLED_MARKER}$/,/^# ===/ s/^\\([^#]\\)/# \\1/" \
    -e "/^${DISABLED_MARKER}$/,/^# MOVIETWIRL/ s/^\\([^#]\\)/# \\1/" \
    | crontab -
fi

echo ""
echo "DramValue scheduling paused."
echo "  Stopped: Celery beat, Celery worker, host crons (backup/health check)"
echo "  Still running: API, PostgreSQL, Redis"
echo ""
echo "To resume: ./scripts/resume-scheduling.sh"
