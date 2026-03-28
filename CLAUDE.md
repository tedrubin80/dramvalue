# DramValue (WTracker) — AI Setup & Operations Guide

## What This Project Is

DramValue is a whisky price intelligence platform. It scrapes auction houses and retail sites for whisky prices, stores them in PostgreSQL, and serves a web frontend for browsing bottles, brands, market trends, and price history.

**Tech stack**: Python 3.11, FastAPI, SQLAlchemy (async), Scrapy, Celery, PostgreSQL 16, Redis 7, Docker Compose, Jinja2/Tailwind templates.

**Live URL**: http://localhost:8001 (or whatever port `API_PORT` is set to)

---

## Quick Start (Fresh Server)

```bash
# 1. Clone the repo
git clone https://github.com/tedrubin80/tracker.git /var/www/wtracker
cd /var/www/wtracker

# 2. Run the setup script (installs everything)
sudo ./scripts/setup-production.sh

# 3. Edit .env with any API keys
nano .env

# 4. Verify it's working
curl http://localhost:8001/
```

The setup script handles: Docker, Docker Compose, git, pip, kagglehub, .env generation, container builds, database creation, Kaggle data imports, cron jobs, and firewall.

---

## Project Structure

```
/var/www/wtracker/
├── src/
│   ├── api/routes/          # FastAPI route handlers
│   │   ├── frontend.py      # All HTML page routes (/, /brands, /market, etc.)
│   │   ├── export.py        # CSV/JSON data export endpoints
│   │   └── ...              # Other API routes
│   ├── core/                # Config, security, settings
│   ├── db/session.py        # SQLAlchemy async engine & session
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── bottle.py        # Bottle, BottleAlias, SpiritCategory
│   │   ├── price.py         # Price, PriceSource, AuctionHouse
│   │   ├── market_stat.py   # MarketStat (Kaggle market data)
│   │   ├── user.py          # User accounts
│   │   ├── collection.py    # User collections
│   │   ├── alert.py         # Price alerts
│   │   └── ...
│   ├── scrapers/
│   │   ├── items.py         # AuctionLotItem, RetailPriceItem (Scrapy items)
│   │   ├── pipelines/       # validation.py, normalization.py, deduplication.py, database.py
│   │   └── spiders/         # 14 scraper spiders (dekanta, whisky_barrel, etc.)
│   └── tasks/
│       ├── celery_app.py    # Celery config + beat_schedule (all scraper schedules)
│       ├── scraping.py      # scrape_source() task
│       └── maintenance.py   # refresh_bottle_stats(), cleanup tasks
├── templates/               # Jinja2 HTML templates (Tailwind CSS)
├── scripts/
│   ├── setup-production.sh  # Full server setup script
│   ├── weekly_backup.sh     # Git commit + push (cron)
│   ├── import_kaggle_*.py   # Kaggle dataset importers
│   └── init-db/             # Database initialization
├── docker-compose.yml       # Development compose config
├── docker-compose.prod.yml  # Production overrides (created by setup script)
├── Dockerfile               # Multi-stage: base → builder → development → production
├── .env                     # Environment variables (DO NOT COMMIT)
└── pyproject.toml           # Python dependencies
```

---

## Docker Services

| Container | Service | Purpose |
|-----------|---------|---------|
| `wtracker-api` | FastAPI app | Web frontend + API (port 8001→8000) |
| `wtracker-worker` | Celery worker | Runs scraper spiders and maintenance tasks |
| `wtracker-beat` | Celery beat | Schedules all periodic tasks |
| `wtracker-db` | PostgreSQL 16 | Primary database (port 5434→5432) |
| `wtracker-redis` | Redis 7 | Celery message broker |
| `wtracker-tor` | Tor proxy | SOCKS5 proxy for scraper anonymity |

### Common Docker Commands

```bash
cd /var/www/wtracker

# Start all services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# View logs
docker compose logs -f api          # API logs
docker compose logs -f worker       # Scraper/task logs
docker compose logs -f beat         # Scheduler logs

# Restart a service
docker compose restart api
docker compose restart worker

# Rebuild after code changes
docker compose -f docker-compose.yml -f docker-compose.prod.yml build api worker beat
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Run a scraper manually
docker compose exec -T worker python -c "
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from src.scrapers.spiders.dekanta import DekantaSpider
settings = get_project_settings()
process = CrawlerProcess(settings)
process.crawl(DekantaSpider)
process.start()
"

# Database shell
docker compose exec -T db psql -U wtracker -d wtracker

# Check database stats
docker compose exec -T db psql -U wtracker -d wtracker -c "
SELECT source_name, COUNT(*) as count, MAX(created_at)::date as latest
FROM prices GROUP BY source_name ORDER BY count DESC;
"
```

---

## Database Schema (Key Tables)

- **bottles** — 9,600+ whisky bottles/brands. Key fields: `name`, `normalized_name`, `distillery`, `category`, `brand`, `price_count`, `avg_price`.
- **prices** — 16,000+ price records. Key fields: `bottle_id`, `price`, `price_usd`, `source` (AUCTION/RETAIL/IMPORT), `source_name`, `transaction_date`.
- **market_stats** — 1,700 monthly auction aggregate records. Key fields: `auction_name`, `period_date`, `trading_volume`, `winning_bid_mean`, `lots_count`.
- **users** — User accounts with JWT auth.
- **collections** — User bottle collections.
- **price_alerts** — User price alert subscriptions.

---

## Scraper Pipeline

Items flow through 4 pipeline stages:

1. **ValidationPipeline** — Checks required fields. Supports both `AuctionLotItem` and `RetailPriceItem`.
2. **NormalizationPipeline** — Matches/creates bottle records, detects category.
3. **DeduplicationPipeline** — In-memory dedup within a scrape run.
4. **DatabasePipeline** — Persists to PostgreSQL.

**Important fields on items**: Both item types MUST have `validation_errors`, `is_duplicate`, and `_dedup_key` fields defined (these are set by pipelines).

### Active Scrapers

| Spider | Type | Schedule | Source |
|--------|------|----------|--------|
| dekanta | Retail (Shopify JSON) | Every 12h | dekanta.com |
| whisky_barrel | Retail (Shopify JSON) | Every 12h | thewhiskybarrel.com |
| scotch_whisky_auctions | Auction | Every 6h | scotchwhiskyauctions.com |
| whisky_auctioneer | Auction | Every 6h | whiskyauctioneer.com |
| whisky_auction_uk | Auction | Every 8h | whisky.auction |
| whiskyauction_com | Auction | Every 8h | whiskyauction.com |
| whisky_hunter | Auction API | Daily | whiskyhunter.net |
| whiskystats | Market data | Daily | whiskystats.net |
| rare_whisky_101 | Market data | Daily | rarewhisky101.com |
| whiskybase | Marketplace | Every 12h | whiskybase.com |
| wine_searcher | Retail | Daily | wine-searcher.com |
| boozapp | Retail | Daily | boozapp.com |
| whiskyfindr | Retail | Daily | whiskyfindr.com |
| bottle_blue_book | Valuations | Daily | bottlebluebook.com |

Schedules are defined in `src/tasks/celery_app.py` → `beat_schedule`.

---

## Cron Jobs (Host Level)

| Schedule | Script | Purpose |
|----------|--------|---------|
| Sun 00:00 | `scripts/weekly_backup.sh` | Git commit + push all changes |
| Daily 03:00 | inline pg_dump | Database backup to `backups/` |
| Daily 04:00 | find + delete | Clean DB backups older than 30 days |
| Monthly | find + delete | Clean logs older than 90 days |
| Every 5min | curl health check | Auto-restart API if unresponsive |

---

## Web Pages

| Route | Template | Description |
|-------|----------|-------------|
| `/` | home.html | Homepage with search, stats, trending |
| `/brands` | brands.html | Browse 4,800+ brands with category filters |
| `/bottles` | bottles/list.html | Browse all bottles with pagination |
| `/bottles/{id}` | bottles/detail.html | Bottle detail with price chart |
| `/market` | market.html | Market overview with trading volume charts |
| `/trending` | trending.html | Trending bottles by recent activity |
| `/about` | about.html | About page with site stats |
| `/search?q=` | search.html | Search results |
| `/auth/login` | auth/login.html | Login page |
| `/auth/register` | auth/register.html | Registration page |
| `/profile` | profile.html | User profile (requires auth) |
| `/collections` | collections/list.html | User collections (requires auth) |
| `/alerts` | alerts/list.html | Price alerts (requires auth) |

---

## Kaggle Data Imports

Three Kaggle datasets have been imported. Re-run safely (they skip duplicates):

```bash
# Cask auction prices (562 records → bottles + prices)
docker compose exec -T api python scripts/import_kaggle_casks.py --csv /tmp/casks_database.csv

# Market aggregate stats (1,719 records → market_stats table)
docker compose exec -T api python scripts/import_kaggle_market.py --csv /tmp/auction_data.csv

# Brand catalog (4,800+ brands → bottles table)
docker compose exec -T api python scripts/import_kaggle_brands.py --path /tmp
```

The setup script handles downloading these datasets and running the imports automatically.

---

## Troubleshooting

### Scrapers returning 0 items
1. Check spider logs: `docker compose logs -f worker`
2. Ensure `RetailPriceItem` has `validation_errors`, `is_duplicate`, `_dedup_key` fields in `src/scrapers/items.py`
3. Check if site structure changed (common with Shopify stores)

### API not responding
1. Check: `docker compose ps` — all containers should show "Up"
2. Logs: `docker compose logs -f api`
3. Health: `curl http://localhost:8001/health`
4. Restart: `docker compose restart api`

### Database connection issues
1. Check DB health: `docker compose exec -T db pg_isready -U wtracker`
2. Verify .env has correct `POSTGRES_*` variables
3. Check `DATABASE_URL` uses `postgresql+asyncpg://` scheme

### Missing market_stats table
```sql
-- Run in psql or via docker compose exec
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
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | App secret for session signing |
| `JWT_SECRET_KEY` | Yes | JWT token signing key |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `DATABASE_URL` | Yes | Full async database URL |
| `REDIS_URL` | Yes | Redis connection URL |
| `CORS_ORIGINS` | Yes | Comma-separated allowed origins |
| `PERPLEXITY_API_KEY` | No | For AI-powered features |
| `DEBUG` | No | Set `false` in production |
| `LOG_LEVEL` | No | INFO for production, DEBUG for dev |
