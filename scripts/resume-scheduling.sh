#!/usr/bin/env bash
# Resume DramValue scheduled tasks (host crons + Celery beat/worker).
#
# Usage: ./scripts/resume-scheduling.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRON_MARKER="# DramValue automated tasks"
DISABLED_MARKER="# DramValue automated tasks (DISABLED)"

cd "$REPO_DIR"

if crontab -l 2>/dev/null | grep -q "^${DISABLED_MARKER}$"; then
  echo "==> Re-enabling host crons..."
  crontab -l 2>/dev/null | sed \
    -e "s/^${DISABLED_MARKER}$/${CRON_MARKER}/" \
    -e "/^${CRON_MARKER}$/,/^# ===/ s/^# \\(.*wtracker.*\\)/\\1/" \
    -e "/^${CRON_MARKER}$/,/^# MOVIETWIRL/ s/^# \\(.*wtracker.*\\)/\\1/" \
    | crontab -
else
  echo "==> Host crons already active (or not installed)"
fi

echo "==> Starting Celery beat and worker..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d beat worker 2>/dev/null \
  || docker compose -f docker-compose.yml up -d beat worker

echo ""
echo "DramValue scheduling resumed."
