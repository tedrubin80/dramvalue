#!/bin/bash
# Weekly git backup for wtracker
# Runs every Sunday at midnight via cron

REPO_DIR="/var/www/wtracker"
LOG_FILE="$REPO_DIR/logs/git_backup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$REPO_DIR/logs"

echo "[$DATE] Starting weekly backup..." >> "$LOG_FILE"

cd "$REPO_DIR" || { echo "[$DATE] ERROR: Cannot cd to $REPO_DIR" >> "$LOG_FILE"; exit 1; }

# Check if there are any changes to commit
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "[$DATE] No changes to commit." >> "$LOG_FILE"
    exit 0
fi

# Stage all tracked file changes and new files (exclude data, logs, backups, secrets)
git add -A -- ':!data/' ':!logs/' ':!backups/' ':!*.log' ':!*.pyc' ':!__pycache__/' ':!.env'

# Check if staging resulted in anything
if git diff --cached --quiet; then
    echo "[$DATE] No meaningful changes to commit after staging." >> "$LOG_FILE"
    exit 0
fi

# Count what's being committed
CHANGED=$(git diff --cached --stat | tail -1)

# Commit
git commit -m "Weekly backup: $(date '+%b %d, %Y')

Auto-committed changes: $CHANGED

Co-Authored-By: cron <noreply@dramvalue.com>"

if [ $? -eq 0 ]; then
    echo "[$DATE] Commit successful: $CHANGED" >> "$LOG_FILE"

    # Push to remote
    git push origin main >> "$LOG_FILE" 2>&1

    if [ $? -eq 0 ]; then
        echo "[$DATE] Push to origin/main successful." >> "$LOG_FILE"
    else
        echo "[$DATE] ERROR: Push failed." >> "$LOG_FILE"
    fi
else
    echo "[$DATE] ERROR: Commit failed." >> "$LOG_FILE"
fi

echo "[$DATE] Backup complete." >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"
