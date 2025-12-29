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
