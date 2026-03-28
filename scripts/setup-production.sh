#!/bin/bash
# =============================================================================
# DramValue (WTracker) Production Setup Script
# =============================================================================
#
# Sets up the full application stack on a fresh server:
#   - System dependencies (Docker, Docker Compose, Git)
#   - Application code (clone from GitHub)
#   - Environment configuration
#   - Database initialization & Kaggle data imports
#   - Docker containers (API, Worker, Beat, DB, Redis, Tor)
#   - Cron jobs (weekly git backup)
#   - Firewall (UFW)
#
# Usage:
#   chmod +x scripts/setup-production.sh
#   sudo ./scripts/setup-production.sh
#
# Run from any directory - it will set up in /var/www/wtracker
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INSTALL_DIR="/var/www/wtracker"
REPO_URL="https://github.com/tedrubin80/tracker.git"
BRANCH="main"
API_PORT="8001"
DB_PORT="5434"
LOG_DIR="$INSTALL_DIR/logs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    err "Please run as root: sudo ./setup-production.sh"
    exit 1
fi

log "Starting DramValue production setup..."
echo ""

# ---------------------------------------------------------------------------
# Step 1: System dependencies
# ---------------------------------------------------------------------------
log "Step 1/8: Installing system dependencies..."

apt-get update -qq

# Git
if ! command -v git &>/dev/null; then
    apt-get install -y -qq git
    log "Git installed"
else
    info "Git already installed"
fi

# Docker
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log "Docker installed and started"
else
    info "Docker already installed ($(docker --version | cut -d' ' -f3))"
fi

# Docker Compose (v2 plugin)
if ! docker compose version &>/dev/null; then
    log "Installing Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
    log "Docker Compose installed"
else
    info "Docker Compose already installed"
fi

# pip & kagglehub (for data imports)
if ! command -v pip3 &>/dev/null; then
    apt-get install -y -qq python3-pip
fi
pip3 install --break-system-packages kagglehub pandas 2>/dev/null || pip3 install kagglehub pandas

echo ""

# ---------------------------------------------------------------------------
# Step 2: Clone or update repository
# ---------------------------------------------------------------------------
log "Step 2/8: Setting up application code..."

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Repository exists at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git pull origin "$BRANCH" || warn "Git pull failed - continuing with existing code"
else
    log "Cloning repository..."
    mkdir -p "$(dirname $INSTALL_DIR)"
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    git checkout "$BRANCH"
    log "Repository cloned to $INSTALL_DIR"
fi

mkdir -p "$LOG_DIR"
echo ""

# ---------------------------------------------------------------------------
# Step 3: Environment configuration
# ---------------------------------------------------------------------------
log "Step 3/8: Configuring environment..."

if [ -f "$INSTALL_DIR/.env" ]; then
    info ".env file already exists"
    warn "Review .env and update passwords for production!"
else
    # Generate secure random values
    SECRET_KEY=$(openssl rand -base64 32)
    JWT_SECRET=$(openssl rand -base64 32)
    DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')

    cat > "$INSTALL_DIR/.env" << ENVEOF
# =============================================================================
# DramValue Production Configuration
# Generated on $(date '+%Y-%m-%d %H:%M:%S')
# =============================================================================

# Application
APP_NAME=DramValue
APP_ENV=production
DEBUG=false
SECRET_KEY=${SECRET_KEY}
CORS_ORIGINS=https://dramvalue.com,https://www.dramvalue.com

# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=wtracker
POSTGRES_USER=wtracker
POSTGRES_PASSWORD=${DB_PASSWORD}
DATABASE_URL=postgresql+asyncpg://wtracker:${DB_PASSWORD}@db:5432/wtracker

# Authentication
JWT_SECRET_KEY=${JWT_SECRET}
JWT_ALGORITHM=HS256

# Trust & Fraud Detection
TRUST_BASE_SCORE=50
TRUST_VERIFIED_BONUS=25
TRUST_SUBMISSION_INCREMENT=1
FRAUD_STDDEV_THRESHOLD=2.0
FRAUD_NEW_ACCOUNT_SUBMISSION_LIMIT=5
FRAUD_BURST_WINDOW_MINUTES=10
FRAUD_BURST_LIMIT=3
FRAUD_SINGLE_USER_INFLUENCE_CAP=0.25

# Forecasting
FORECAST_MIN_DATAPOINTS=10
FORECAST_CONFIDENCE_THRESHOLD=0.6
FORECAST_RECALCULATE_ON_NEW_DATA=true

# Redis
REDIS_URL=redis://redis:6379/0

# Logging
LOG_LEVEL=INFO
ENVEOF

    chmod 600 "$INSTALL_DIR/.env"
    log ".env file created with secure random keys"
    warn "IMPORTANT: Edit .env to add any API keys (PERPLEXITY_API_KEY, etc.)"
fi

echo ""

# ---------------------------------------------------------------------------
# Step 4: Create production docker-compose override
# ---------------------------------------------------------------------------
log "Step 4/8: Creating production Docker Compose config..."

cat > "$INSTALL_DIR/docker-compose.prod.yml" << 'PRODEOF'
# Production overrides for docker-compose.yml
services:
  api:
    build:
      context: .
      target: production
    volumes: []  # No source mounting in production
    restart: always
    deploy:
      resources:
        limits:
          memory: 512M

  worker:
    build:
      context: .
      target: production
    volumes: []
    command: celery -A src.tasks.celery_app worker --loglevel=info --concurrency=2 -Q scraping,maintenance,celery
    restart: always
    deploy:
      resources:
        limits:
          memory: 1G

  beat:
    build:
      context: .
      target: production
    volumes: []
    command: celery -A src.tasks.celery_app beat --loglevel=info
    restart: always
    deploy:
      resources:
        limits:
          memory: 256M

  db:
    restart: always
    deploy:
      resources:
        limits:
          memory: 512M

  redis:
    restart: always
    deploy:
      resources:
        limits:
          memory: 256M

  tor:
    restart: always
PRODEOF

log "docker-compose.prod.yml created"
echo ""

# ---------------------------------------------------------------------------
# Step 5: Create Docker network if needed
# ---------------------------------------------------------------------------
log "Step 5/8: Setting up Docker networks..."

docker network create yarntrack_default 2>/dev/null || info "yarntrack_default network already exists"
echo ""

# ---------------------------------------------------------------------------
# Step 6: Build and start containers
# ---------------------------------------------------------------------------
log "Step 6/8: Building and starting containers..."

cd "$INSTALL_DIR"

# Build all images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Start the database first and wait for it
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db redis
log "Waiting for database to be healthy..."
sleep 10

# Check DB health
RETRIES=30
until docker compose exec -T db pg_isready -U wtracker -d wtracker &>/dev/null || [ $RETRIES -eq 0 ]; do
    RETRIES=$((RETRIES - 1))
    sleep 2
done

if [ $RETRIES -eq 0 ]; then
    err "Database failed to start"
    exit 1
fi

log "Database is healthy"

# Create the market_stats table if it doesn't exist
docker compose exec -T db psql -U wtracker -d wtracker -c "
CREATE TABLE IF NOT EXISTS market_stats (
    id SERIAL PRIMARY KEY,
    auction_name VARCHAR(255) NOT NULL,
    auction_slug VARCHAR(255) NOT NULL,
    period_date TIMESTAMP WITH TIME ZONE NOT NULL,
    winning_bid_max FLOAT NOT NULL,
    winning_bid_min FLOAT NOT NULL,
    winning_bid_mean FLOAT NOT NULL,
    trading_volume FLOAT NOT NULL,
    lots_count INTEGER NOT NULL,
    all_auctions_lots_count INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_market_stat_slug_date UNIQUE (auction_slug, period_date)
);
CREATE INDEX IF NOT EXISTS ix_market_stats_auction_name ON market_stats (auction_name);
CREATE INDEX IF NOT EXISTS ix_market_stats_auction_slug ON market_stats (auction_slug);
CREATE INDEX IF NOT EXISTS ix_market_stats_period_date ON market_stats (period_date);
" 2>/dev/null || info "market_stats table already exists"

# Start all remaining services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

log "All containers started"

# Show status
docker compose ps
echo ""

# ---------------------------------------------------------------------------
# Step 7: Import Kaggle datasets
# ---------------------------------------------------------------------------
log "Step 7/8: Importing Kaggle datasets..."

# Download datasets
python3 -c "
import kagglehub
print('Downloading cask auction data...')
p1 = kagglehub.dataset_download('joaopaivaa/whisky-casks-auction-database')
print(f'  -> {p1}')

print('Downloading market data...')
p2 = kagglehub.dataset_download('shivd24coder/wiskey-price-dataset')
print(f'  -> {p2}')

print('Downloading brand data...')
p3 = kagglehub.dataset_download('koki25ando/world-whisky-distilleries-brands-dataset')
print(f'  -> {p3}')
" 2>&1 | grep -v "Warning:"

# Copy data and scripts into API container, then run imports
CASK_CSV=$(find /root/.cache/kagglehub -name "casks_database.csv" 2>/dev/null | head -1)
MARKET_CSV=$(find /root/.cache/kagglehub -name "auction_data.csv" 2>/dev/null | head -1)
BRAND_DIR=$(find /root/.cache/kagglehub -path "*/world-whisky*" -name "Whisky_Brand.csv" 2>/dev/null | head -1 | xargs dirname)

API_CONTAINER=$(docker compose ps -q api)

if [ -n "$CASK_CSV" ]; then
    docker cp "$CASK_CSV" "$API_CONTAINER:/tmp/casks_database.csv"
    docker cp "$INSTALL_DIR/scripts/import_kaggle_casks.py" "$API_CONTAINER:/app/scripts/import_kaggle_casks.py"
    log "Importing cask auction data..."
    docker compose exec -T api python scripts/import_kaggle_casks.py --csv /tmp/casks_database.csv 2>&1 | grep -E "(Import complete|Loaded|DRY RUN)" || warn "Cask import had issues"
fi

if [ -n "$MARKET_CSV" ]; then
    docker cp "$MARKET_CSV" "$API_CONTAINER:/tmp/auction_data.csv"
    docker cp "$INSTALL_DIR/scripts/import_kaggle_market.py" "$API_CONTAINER:/app/scripts/import_kaggle_market.py"
    docker cp "$INSTALL_DIR/src/models/market_stat.py" "$API_CONTAINER:/app/src/models/market_stat.py"
    docker cp "$INSTALL_DIR/src/models/__init__.py" "$API_CONTAINER:/app/src/models/__init__.py"
    log "Importing market data..."
    docker compose exec -T api python scripts/import_kaggle_market.py --csv /tmp/auction_data.csv 2>&1 | grep -E "(Import complete|Loaded|DRY RUN)" || warn "Market import had issues"
fi

if [ -n "$BRAND_DIR" ]; then
    docker cp "$BRAND_DIR/Whisky_Brand.csv" "$API_CONTAINER:/tmp/Whisky_Brand.csv"
    docker cp "$BRAND_DIR/Distillery.csv" "$API_CONTAINER:/tmp/Distillery.csv"
    docker cp "$INSTALL_DIR/scripts/import_kaggle_brands.py" "$API_CONTAINER:/app/scripts/import_kaggle_brands.py"
    log "Importing brand data..."
    docker compose exec -T api python scripts/import_kaggle_brands.py --path /tmp 2>&1 | grep -E "(Import complete|Loaded|DRY RUN)" || warn "Brand import had issues"
fi

echo ""

# ---------------------------------------------------------------------------
# Step 8: Set up cron jobs
# ---------------------------------------------------------------------------
log "Step 8/8: Setting up cron jobs..."

# Make scripts executable
chmod +x "$INSTALL_DIR/scripts/weekly_backup.sh"

# Add cron jobs (without duplicating)
CRON_MARKER="# DramValue automated tasks"
if crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
    info "Cron jobs already configured"
else
    (crontab -l 2>/dev/null; cat << CRONEOF

$CRON_MARKER
# Weekly git backup - Sunday at midnight
0 0 * * 0 $INSTALL_DIR/scripts/weekly_backup.sh

# Daily database backup - 3 AM
0 3 * * * docker compose -f $INSTALL_DIR/docker-compose.yml exec -T db pg_dump -U wtracker wtracker | gzip > $INSTALL_DIR/backups/db_\$(date +\%Y\%m\%d).sql.gz 2>> $LOG_DIR/db_backup.log

# Clean old DB backups (keep 30 days)
0 4 * * * find $INSTALL_DIR/backups -name "db_*.sql.gz" -mtime +30 -delete

# Clean old logs (keep 90 days)
0 4 1 * * find $LOG_DIR -name "*.log" -mtime +90 -delete

# Health check every 5 minutes - restart API if down
*/5 * * * * curl -sf http://localhost:${API_PORT}/health > /dev/null || (echo "[\$(date)] API health check failed, restarting..." >> $LOG_DIR/health.log && cd $INSTALL_DIR && docker compose restart api)
CRONEOF
    ) | crontab -

    # Create backups directory
    mkdir -p "$INSTALL_DIR/backups"

    log "Cron jobs installed:"
    info "  - Weekly git backup (Sun midnight)"
    info "  - Daily DB backup (3 AM)"
    info "  - Old backup cleanup (30 days)"
    info "  - Old log cleanup (90 days)"
    info "  - API health check (every 5 min)"
fi

echo ""

# ---------------------------------------------------------------------------
# Optional: UFW Firewall
# ---------------------------------------------------------------------------
if command -v ufw &>/dev/null; then
    log "Configuring firewall..."
    ufw allow 22/tcp   comment "SSH"        2>/dev/null || true
    ufw allow 80/tcp   comment "HTTP"       2>/dev/null || true
    ufw allow 443/tcp  comment "HTTPS"      2>/dev/null || true
    ufw allow ${API_PORT}/tcp comment "DramValue API" 2>/dev/null || true
    ufw --force enable 2>/dev/null || true
    info "Firewall configured (SSH, HTTP, HTTPS, API:${API_PORT})"
fi

echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "============================================================================="
echo -e "${GREEN}  DramValue Production Setup Complete${NC}"
echo "============================================================================="
echo ""
echo "  Application:  http://$(hostname -I | awk '{print $1}'):${API_PORT}"
echo "  Database:      PostgreSQL on port ${DB_PORT} (internal)"
echo "  Install dir:   ${INSTALL_DIR}"
echo "  Logs:          ${LOG_DIR}/"
echo "  Backups:       ${INSTALL_DIR}/backups/"
echo ""
echo "  Services running:"
docker compose ps --format "    {{.Name}}: {{.Status}}" 2>/dev/null
echo ""
echo "  Scrapers (managed by Celery Beat):"
echo "    Auction:  Whisky Auctioneer, Scotch Whisky Auctions,"
echo "              Whisky Hunter, Whisky.Auction UK, WhiskyAuction.com,"
echo "              WhiskyStats, Rare Whisky 101"
echo "    Retail:   Dekanta, Whisky Barrel, Whiskybase, Wine-Searcher,"
echo "              BoozApp, WhiskyFindr, Bottle Blue Book"
echo ""
echo "  Cron jobs:"
echo "    Sun 00:00  Weekly git backup + push"
echo "    Daily 03:00  Database backup (pg_dump)"
echo "    Daily 04:00  Old backup cleanup (>30 days)"
echo "    Monthly     Old log cleanup (>90 days)"
echo "    Every 5min  API health check + auto-restart"
echo ""
echo "  Next steps:"
echo "    1. Edit .env to add any API keys"
echo "    2. Set up a reverse proxy (nginx) for HTTPS"
echo "    3. Point your domain DNS to this server"
echo "    4. Monitor logs: tail -f ${LOG_DIR}/*.log"
echo ""
echo "============================================================================="
