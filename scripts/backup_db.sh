#!/bin/bash
# =============================================================================
# DramValue Database Backup Script
# Creates a compressed pg_dump and optionally pushes to GitHub
# =============================================================================
#
# Usage:
#   ./scripts/backup_db.sh              # Local backup only
#   ./scripts/backup_db.sh --push       # Backup + commit + push to GitHub
#
# Backups are saved to /var/www/wtracker/backups/
# =============================================================================

set -euo pipefail

REPO_DIR="/var/www/wtracker"
BACKUP_DIR="$REPO_DIR/backups"
LOG_FILE="$REPO_DIR/logs/db_backup.log"
DATE=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="$BACKUP_DIR/db_${DATE}.sql.gz"
LATEST_LINK="$BACKUP_DIR/db_latest.sql.gz"
PUSH_TO_GIT=false

mkdir -p "$BACKUP_DIR" "$REPO_DIR/logs"

# Parse args
if [ "${1:-}" = "--push" ]; then
    PUSH_TO_GIT=true
fi

echo "[$(date)] Starting database backup..." | tee -a "$LOG_FILE"

# Run pg_dump
docker compose -f "$REPO_DIR/docker-compose.yml" exec -T db \
    pg_dump -U wtracker -d wtracker --no-owner --no-privileges \
    | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ] && [ -s "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup successful: $BACKUP_FILE ($SIZE)" | tee -a "$LOG_FILE"

    # Update latest symlink
    ln -sf "$BACKUP_FILE" "$LATEST_LINK"

    # Clean old backups (keep last 30)
    cd "$BACKUP_DIR"
    ls -t db_*.sql.gz 2>/dev/null | tail -n +31 | xargs -r rm -f
    REMAINING=$(ls db_*.sql.gz 2>/dev/null | wc -l)
    echo "[$(date)] Keeping $REMAINING backups" | tee -a "$LOG_FILE"

    # Push to GitHub if requested
    if [ "$PUSH_TO_GIT" = true ]; then
        cd "$REPO_DIR"

        # Only commit the latest backup (not all history)
        cp "$BACKUP_FILE" "$BACKUP_DIR/db_latest_github.sql.gz"
        git add backups/db_latest_github.sql.gz
        git commit -m "Database backup: $(date '+%b %d, %Y %H:%M')

Backup size: $SIZE

Co-Authored-By: cron <noreply@dramvalue.com>" 2>/dev/null

        if git push origin main 2>>"$LOG_FILE"; then
            echo "[$(date)] Backup pushed to GitHub" | tee -a "$LOG_FILE"
        else
            echo "[$(date)] ERROR: Git push failed" | tee -a "$LOG_FILE"
        fi
    fi
else
    echo "[$(date)] ERROR: Backup failed" | tee -a "$LOG_FILE"
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "[$(date)] Backup complete" | tee -a "$LOG_FILE"
echo "---" >> "$LOG_FILE"
