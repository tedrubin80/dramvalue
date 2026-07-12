#!/bin/bash
# =============================================================================
# DramValue Production Permissions Fix
# =============================================================================
# Sets secure, consistent permissions across the project tree.
#
# Usage:
#   sudo ./scripts/fix-permissions.sh
#
# Run after deploys or when files are created with overly permissive modes.
# =============================================================================

set -euo pipefail

INSTALL_DIR="/var/www/wtracker"
OWNER="${SUDO_USER:-$(whoami)}"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./scripts/fix-permissions.sh"
    exit 1
fi

echo "[+] Fixing permissions in $INSTALL_DIR (owner: $OWNER)"

# Directories: owner rwx, group/others rx (no group write)
find "$INSTALL_DIR" -type d \
    ! -path "$INSTALL_DIR/.git/*" \
    ! -path "$INSTALL_DIR/.git.broken/*" \
    -exec chmod 755 {} +

# Regular files: owner rw, group/others r (no group write)
find "$INSTALL_DIR" -type f \
    ! -path "$INSTALL_DIR/.git/*" \
    ! -path "$INSTALL_DIR/.git.broken/*" \
    ! -name "*.sh" \
    -exec chmod 644 {} +

# Executable scripts
find "$INSTALL_DIR/scripts" -maxdepth 1 -type f -name "*.sh" -exec chmod 755 {} +
chmod 755 "$INSTALL_DIR/scripts/fix-permissions.sh" 2>/dev/null || true

# Secrets and sensitive data — owner only
if [ -f "$INSTALL_DIR/.env" ]; then
    chmod 600 "$INSTALL_DIR/.env"
    chown "$OWNER:$OWNER" "$INSTALL_DIR/.env"
fi

# Database backups contain full dumps — restrict access
if [ -d "$INSTALL_DIR/backups" ]; then
    chmod 700 "$INSTALL_DIR/backups"
    find "$INSTALL_DIR/backups" -type f -exec chmod 600 {} +
    chown -R "$OWNER:$OWNER" "$INSTALL_DIR/backups"
fi

# Deploy configs (nginx, SSL references)
if [ -d "$INSTALL_DIR/deploy" ]; then
    chmod 700 "$INSTALL_DIR/deploy"
    find "$INSTALL_DIR/deploy" -type f -exec chmod 600 {} +
fi

# Local tool caches — owner only
for dir in .claude .cursor .impeccable .remember; do
    if [ -d "$INSTALL_DIR/$dir" ]; then
        chmod 700 "$INSTALL_DIR/$dir"
        find "$INSTALL_DIR/$dir" -type f -exec chmod 600 {} + 2>/dev/null || true
        find "$INSTALL_DIR/$dir" -type d -exec chmod 700 {} + 2>/dev/null || true
    fi
done

# Logs: writable by owner, readable by group (for monitoring)
if [ -d "$INSTALL_DIR/logs" ]; then
    chmod 750 "$INSTALL_DIR/logs"
    find "$INSTALL_DIR/logs" -type f -exec chmod 640 {} + 2>/dev/null || true
fi

# Static files served directly by nginx (www-data needs read)
if [ -d "$INSTALL_DIR/static" ]; then
    chmod -R 755 "$INSTALL_DIR/static"
    find "$INSTALL_DIR/static" -type f -exec chmod 644 {} +
    chown -R "$OWNER:www-data" "$INSTALL_DIR/static"
fi

# Project ownership
chown -R "$OWNER:$OWNER" "$INSTALL_DIR" \
    --exclude="$INSTALL_DIR/static" \
    --exclude="$INSTALL_DIR/.git" 2>/dev/null || \
    chown -R "$OWNER:$OWNER" "$INSTALL_DIR"

echo "[+] Permissions applied:"
echo "    Files:       644"
echo "    Directories: 755"
echo "    Scripts:     755"
echo "    .env:        600"
echo "    backups/:    700 (files 600)"
echo "    deploy/:     700 (files 600)"
echo "    static/:     755 (nginx-readable)"
