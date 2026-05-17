#!/bin/bash
# DramValue Full Deployment Script
# Run with: sudo bash scripts/deploy.sh
# Or without sudo for just Docker (skips nginx/certbot)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOMAIN="dramvalue.com"

cd "$PROJECT_DIR"
echo "=== DramValue Deployment ==="
echo "Project: $PROJECT_DIR"
echo ""

# -------------------------------------------------------------------------
# 1. Docker Compose - Build and start all services
# -------------------------------------------------------------------------
echo "[1/6] Building and starting Docker containers..."
docker compose up -d --build

echo "  Waiting for database to be healthy..."
for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U wtracker -d wtracker >/dev/null 2>&1; then
        echo "  Database ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ERROR: Database not ready after 30s. Check: docker compose logs db"
        exit 1
    fi
    sleep 1
done

# -------------------------------------------------------------------------
# 2. Run database migrations
# -------------------------------------------------------------------------
echo "[2/6] Running database migrations..."
docker compose exec -T api alembic upgrade head
echo "  Migrations complete."

# -------------------------------------------------------------------------
# 3. Reimport CSV data
# -------------------------------------------------------------------------
echo "[3/6] Reimporting CSV data into database..."
docker compose exec -T api python scripts/reimport_csv_data.py
echo "  Data import complete."

# -------------------------------------------------------------------------
# 4. Nginx + Certbot SSL (requires sudo)
# -------------------------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
    echo "[4/6] Setting up Nginx and SSL for $DOMAIN..."

    apt-get update -qq
    apt-get install -y -qq nginx certbot python3-certbot-nginx

    NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"
    NGINX_ENABLED="/etc/nginx/sites-enabled/$DOMAIN"
    CERTBOT_WEBROOT="/var/www/certbot"
    mkdir -p "$CERTBOT_WEBROOT"

    # Check if SSL cert already exists
    if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
        echo "  SSL certificate already exists, installing full config..."
        cp "$PROJECT_DIR/deploy/nginx/$DOMAIN" "$NGINX_CONF"
    else
        echo "  Installing HTTP-only config for certbot challenge..."
        cat > "$NGINX_CONF" <<'HTTPCONF'
server {
    listen 80;
    listen [::]:80;
    server_name dramvalue.com www.dramvalue.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'Setting up SSL...';
        add_header Content-Type text/plain;
    }
}
HTTPCONF

        ln -sf "$NGINX_CONF" "$NGINX_ENABLED"
        rm -f /etc/nginx/sites-enabled/default
        nginx -t && systemctl reload nginx

        echo "  Obtaining SSL certificate..."
        certbot certonly \
            --webroot \
            --webroot-path "$CERTBOT_WEBROOT" \
            -d "$DOMAIN" \
            -d "www.$DOMAIN" \
            --non-interactive \
            --agree-tos \
            --email admin@dramvalue.com

        echo "  Installing full SSL nginx config..."
        cp "$PROJECT_DIR/deploy/nginx/$DOMAIN" "$NGINX_CONF"
    fi

    ln -sf "$NGINX_CONF" "$NGINX_ENABLED"
    nginx -t && systemctl reload nginx

    # Auto-renewal hook
    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/bin/bash
systemctl reload nginx
HOOK
    chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    systemctl enable certbot.timer 2>/dev/null || true
    systemctl start certbot.timer 2>/dev/null || true

    echo "  Nginx + SSL configured."
else
    echo "[4/6] Skipping Nginx/SSL setup (not running as root). Run with sudo to include."
fi

# -------------------------------------------------------------------------
# 5. Set up weekly backup cron
# -------------------------------------------------------------------------
echo "[5/6] Setting up weekly backup cron..."
CRON_LINE="0 0 * * 0 cd $PROJECT_DIR && bash scripts/weekly_backup.sh >> /dev/null 2>&1"
(crontab -l 2>/dev/null | grep -v "weekly_backup.sh"; echo "$CRON_LINE") | crontab -
echo "  Weekly backup cron installed (Sundays at midnight)."

# -------------------------------------------------------------------------
# 6. Verify
# -------------------------------------------------------------------------
echo "[6/6] Verifying deployment..."
echo ""
docker compose ps
echo ""

# Wait a moment for the API to fully start
sleep 3
HEALTH=$(curl -s http://localhost:8002/health 2>/dev/null || echo "NOT REACHABLE")
echo "API Health: $HEALTH"
echo ""

echo "=== Deployment Complete ==="
echo ""
echo "Services:"
echo "  API:        http://localhost:8002"
echo "  Database:   PostgreSQL on port 5434"
echo "  pgAdmin:    docker compose --profile tools up pgadmin (port 5050)"
echo ""
if [ "$(id -u)" -eq 0 ]; then
    echo "  Website:    https://$DOMAIN"
fi
echo ""
echo "Useful commands:"
echo "  docker compose logs -f api        # API logs"
echo "  docker compose logs -f worker     # Scraper logs"
echo "  docker compose logs -f beat       # Scheduler logs"
echo "  docker compose exec api python scripts/reimport_csv_data.py  # Re-import data"
echo ""
