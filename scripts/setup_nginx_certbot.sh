#!/bin/bash
# Setup Nginx and Certbot SSL for dramvalue.com
# Run with: sudo bash scripts/setup_nginx_certbot.sh

set -e

DOMAIN="dramvalue.com"
NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"
NGINX_ENABLED="/etc/nginx/sites-enabled/$DOMAIN"
APP_CONF="/var/www/wtracker/deploy/nginx/$DOMAIN"
CERTBOT_WEBROOT="/var/www/certbot"

echo "=== Setting up Nginx and SSL for $DOMAIN ==="

# 1. Install nginx and certbot if not present
echo "[1/6] Installing nginx and certbot..."
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx

# 2. Create certbot webroot
echo "[2/6] Creating certbot webroot..."
mkdir -p "$CERTBOT_WEBROOT"

# 3. Install initial HTTP-only nginx config (for certbot challenge)
echo "[3/6] Installing initial nginx config (HTTP only)..."
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
echo "    Nginx running with HTTP config."

# 4. Obtain SSL certificate
echo "[4/6] Obtaining SSL certificate from Let's Encrypt..."
certbot certonly \
    --webroot \
    --webroot-path "$CERTBOT_WEBROOT" \
    -d "$DOMAIN" \
    -d "www.$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email admin@dramvalue.com

# 5. Install full nginx config with SSL
echo "[5/6] Installing full nginx config with SSL..."
cp "$APP_CONF" "$NGINX_CONF"
nginx -t && systemctl reload nginx
echo "    Nginx running with full SSL config."

# 6. Set up auto-renewal cron
echo "[6/6] Setting up certbot auto-renewal..."
# certbot installs a systemd timer by default, but ensure it's active
systemctl enable certbot.timer 2>/dev/null || true
systemctl start certbot.timer 2>/dev/null || true

# Also add a renewal hook to reload nginx
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/bin/bash
systemctl reload nginx
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

echo ""
echo "=== Setup complete! ==="
echo "  - $DOMAIN is now served over HTTPS"
echo "  - SSL auto-renewal is configured"
echo "  - Nginx proxies to FastAPI on port 8001"
echo ""
echo "Next steps:"
echo "  1. Start the app: cd /var/www/wtracker && docker-compose up -d"
echo "  2. Or run directly: uvicorn src.main:app --host 127.0.0.1 --port 8001"
