# DramValue.com - Whisky Price Intelligence Platform
# Nginx configuration for WTracker application

# HTTP Server (redirect to HTTPS)
server {
    listen 80;
    listen [::]:80;
    server_name dramvalue.com www.dramvalue.com;

    # ACME challenge for Let's Encrypt renewals
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all HTTP requests to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name dramvalue.com www.dramvalue.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/dramvalue.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dramvalue.com/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:dramvalue_ssl:10m;
    ssl_session_tickets off;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json image/svg+xml;

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        access_log off;
    }

    # OpenAPI docs
    location /docs {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location /redoc {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # Static landing page
    location = / {
        root /var/www/wtracker/static;
        try_files /index.html =404;
        expires 1h;
        add_header Cache-Control "public";
    }

    # Static assets
    location /static/ {
        alias /var/www/wtracker/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Block access to sensitive files
    location ~ /\.(env|git|svn|htaccess|htpasswd) {
        deny all;
        return 404;
    }

    # Logging
    access_log /var/log/nginx/dramvalue.com.access.log;
    error_log /var/log/nginx/dramvalue.com.error.log warn;
}
