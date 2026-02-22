"""
Celery application configuration for WTracker.

Provides background task processing for:
- Scheduled scraping of auction sources
- Statistics refresh and maintenance
- Report generation
"""

import os
from celery import Celery
from celery.schedules import crontab

# Redis URL from environment or default
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Create Celery app
celery_app = Celery(
    "wtracker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.tasks.scraping",
        "src.tasks.maintenance",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task tracking
    task_track_started=True,
    task_time_limit=3600,       # 1 hour max per task
    task_soft_time_limit=3000,  # Soft limit at 50 minutes

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time for scrapers
    worker_concurrency=2,
    task_acks_late=True,

    # Result backend settings
    result_expires=86400,  # Results expire after 24 hours

    # Retry settings
    task_default_retry_delay=300,  # 5 minutes
    task_max_retries=3,

    # Task routing (optional - for future scaling)
    task_routes={
        "src.tasks.scraping.*": {"queue": "scraping"},
        "src.tasks.maintenance.*": {"queue": "maintenance"},
    },
)

# Scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    # ==========================================================================
    # AUCTION SCRAPERS (hammer prices)
    # ==========================================================================

    # Scrape Whisky Auctioneer every 6 hours
    "scrape-whisky-auctioneer": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="*/6", minute="15"),
        "args": ["whisky_auctioneer"],
        "options": {"queue": "scraping"},
    },

    # Scrape Scotch Whisky Auctions every 6 hours (offset by 3 hours)
    "scrape-scotch-whisky-auctions": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="3,9,15,21", minute="15"),
        "args": ["scotch_whisky_auctions"],
        "options": {"queue": "scraping"},
    },

    # Whisky Hunter API - daily (aggregated data)
    "scrape-whisky-hunter": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="5", minute="0"),
        "args": ["whisky_hunter"],
        "options": {"queue": "scraping"},
    },

    # Whisky.Auction (UK) every 8 hours
    "scrape-whisky-auction-uk": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="2,10,18", minute="45"),
        "args": ["whisky_auction_uk"],
        "options": {"queue": "scraping"},
    },

    # WhiskyAuction.com every 8 hours
    "scrape-whiskyauction-com": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="1,9,17", minute="45"),
        "args": ["whiskyauction_com"],
        "options": {"queue": "scraping"},
    },

    # WhiskyStats - daily
    "scrape-whiskystats": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="6", minute="0"),
        "args": ["whiskystats"],
        "options": {"queue": "scraping"},
    },

    # Rare Whisky 101 - daily
    "scrape-rare-whisky-101": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="7", minute="0"),
        "args": ["rare_whisky_101"],
        "options": {"queue": "scraping"},
    },

    # ==========================================================================
    # RETAIL/MARKETPLACE SCRAPERS (listing prices)
    # ==========================================================================

    # Scrape Dekanta every 12 hours
    "scrape-dekanta": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="1,13", minute="30"),
        "args": ["dekanta"],
        "options": {"queue": "scraping"},
    },

    # Scrape The Whisky Barrel every 12 hours
    "scrape-whisky-barrel": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="4,16", minute="30"),
        "args": ["whisky_barrel"],
        "options": {"queue": "scraping"},
    },

    # Whiskybase Market - every 12 hours
    "scrape-whiskybase": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="3,15", minute="0"),
        "args": ["whiskybase"],
        "options": {"queue": "scraping"},
    },

    # Wine-Searcher - daily (large site, be respectful)
    "scrape-wine-searcher": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="8", minute="0"),
        "args": ["wine_searcher"],
        "options": {"queue": "scraping"},
    },

    # BoozApp - daily
    "scrape-boozapp": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="9", minute="0"),
        "args": ["boozapp"],
        "options": {"queue": "scraping"},
    },

    # WhiskyFindr - daily (US bourbon focus)
    "scrape-whiskyfindr": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="10", minute="0"),
        "args": ["whiskyfindr"],
        "options": {"queue": "scraping"},
    },

    # Bottle Blue Book - daily (auction valuations)
    "scrape-bottle-blue-book": {
        "task": "src.tasks.scraping.scrape_source",
        "schedule": crontab(hour="11", minute="0"),
        "args": ["bottle_blue_book"],
        "options": {"queue": "scraping"},
    },

    # ==========================================================================
    # MAINTENANCE TASKS
    # ==========================================================================

    # Refresh bottle statistics every 15 minutes
    "refresh-bottle-stats": {
        "task": "src.tasks.maintenance.refresh_bottle_stats",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "maintenance"},
    },

    # Clean up old scrape run records daily at 2:30 AM UTC
    "cleanup-scrape-runs": {
        "task": "src.tasks.maintenance.cleanup_old_scrape_runs",
        "schedule": crontab(hour="2", minute="30"),
        "options": {"queue": "maintenance"},
    },
}
