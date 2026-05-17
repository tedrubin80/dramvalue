"""
Celery tasks for web scraping.

Handles spider execution, error handling, and run tracking.
"""

import logging
from datetime import datetime
from typing import Optional

from src.tasks.celery_app import celery_app
from src.models.scrape_run import ScrapeRun, ScrapeStatus

logger = logging.getLogger(__name__)

# Spider registry - maps source names to spider classes
SPIDER_REGISTRY = {
    # Auction scrapers (hammer prices)
    "whisky_auctioneer": "src.scrapers.spiders.whisky_auctioneer.WhiskyAuctioneerSpider",
    "scotch_whisky_auctions": "src.scrapers.spiders.scotch_whisky_auctions.ScotchWhiskyAuctionsSpider",
    "whisky_hunter": "src.scrapers.spiders.whisky_hunter.WhiskyHunterSpider",
    "whisky_auction_uk": "src.scrapers.spiders.whisky_auction_uk.WhiskyAuctionUKSpider",
    "whiskyauction_com": "src.scrapers.spiders.whiskyauction_com.WhiskyAuctionComSpider",
    "whiskystats": "src.scrapers.spiders.whiskystats.WhiskyStatsSpider",
    "rare_whisky_101": "src.scrapers.spiders.rare_whisky_101.RareWhisky101Spider",

    # Retail/marketplace scrapers (listing prices)
    "dekanta": "src.scrapers.spiders.dekanta.DekantaSpider",
    "whisky_barrel": "src.scrapers.spiders.whisky_barrel.WhiskyBarrelSpider",
    "whiskybase": "src.scrapers.spiders.whiskybase.WhiskybaseSpider",
    "wine_searcher": "src.scrapers.spiders.wine_searcher.WineSearcherSpider",
    "boozapp": "src.scrapers.spiders.boozapp.BoozAppSpider",
    "whiskyfindr": "src.scrapers.spiders.whiskyfindr.WhiskyFindrSpider",
    "bottle_blue_book": "src.scrapers.spiders.bottle_blue_book.BottleBlueBookSpider",
    "whisky_hammer": "src.scrapers.spiders.whisky_hammer.WhiskyHammerSpider",
    "cask_cartel": "src.scrapers.spiders.cask_cartel.CaskCartelSpider",
}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=600)
def scrape_source(
    self,
    source_name: str,
    full_scrape: bool = False,
    triggered_by: str = "schedule",
) -> dict:
    """
    Run scraper for a specific source.

    Args:
        source_name: Name of spider to run (e.g., 'whisky_auctioneer')
        full_scrape: If True, scrape all available data; otherwise incremental
        triggered_by: How the scrape was triggered ('schedule', 'manual', 'api')

    Returns:
        dict with scrape results
    """
    import subprocess
    import json

    logger.info(f"Starting scrape task for: {source_name}")

    if source_name not in SPIDER_REGISTRY:
        raise ValueError(f"Unknown spider: {source_name}. Available: {list(SPIDER_REGISTRY.keys())}")

    # Create scrape run record
    scrape_run_id = _create_scrape_run(source_name, triggered_by, self.request.id)

    try:
        # Update status to running
        _update_scrape_run(scrape_run_id, status=ScrapeStatus.RUNNING)

        # Run Scrapy in subprocess to avoid Twisted reactor issues
        spider_module = SPIDER_REGISTRY[source_name]

        # Create a Python script to run the spider
        # This avoids needing scrapy.cfg and allows us to run in subprocess
        script = f"""
import sys
sys.path.insert(0, '/app')

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from importlib import import_module

# Import our custom settings module
settings_module = import_module('src.scrapers.settings')
settings = Settings()
settings.setmodule(settings_module)
settings.set('LOG_LEVEL', 'INFO')

# Import spider class
module_path, class_name = '{spider_module}'.rsplit('.', 1)
module = import_module(module_path)
spider_class = getattr(module, class_name)

# Run crawler
process = CrawlerProcess(settings)
process.crawl(spider_class, scrape_run_id={scrape_run_id})
process.start()
"""

        logger.info(f"Running spider {source_name} in subprocess")

        result = subprocess.run(
            ["python3", "-c", script],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            raise RuntimeError(f"Spider exited with code {result.returncode}: {error_msg}")

        # Get updated scrape run from database to see results
        stats = _get_scrape_run_stats(scrape_run_id)

        # Update status to completed (spider should have updated stats)
        _update_scrape_run(scrape_run_id, status=ScrapeStatus.COMPLETED)

        logger.info(f"Scrape completed for {source_name}: {stats}")
        return stats

    except subprocess.TimeoutExpired:
        logger.error(f"Scrape timed out for {source_name}")
        _update_scrape_run(
            scrape_run_id,
            status=ScrapeStatus.FAILED,
            errors=[{"error": "Scrape timed out after 1 hour", "timestamp": datetime.utcnow().isoformat()}],
        )
        raise self.retry(exc=Exception("Timeout"))

    except Exception as e:
        logger.error(f"Scrape failed for {source_name}: {e}")

        _update_scrape_run(
            scrape_run_id,
            status=ScrapeStatus.FAILED,
            errors=[{"error": str(e), "timestamp": datetime.utcnow().isoformat()}],
        )

        # Notify admin when all retries are exhausted
        if self.request.retries >= self.max_retries:
            try:
                from src.services.email_service import send_admin_notification
                send_admin_notification(
                    subject=f"[DramValue] Scraper failed: {source_name}",
                    body_text=(
                        f"Spider '{source_name}' has failed all {self.max_retries + 1} attempts.\n\n"
                        f"Last error: {e}\n\n"
                        f"Scrape run ID: {scrape_run_id}\n"
                        f"Time: {datetime.utcnow().isoformat()}"
                    ),
                )
            except Exception as notify_err:
                logger.error(f"Failed to send admin notification: {notify_err}")

        raise self.retry(exc=e)


@celery_app.task
def scrape_all_sources() -> dict:
    """
    Queue scraping tasks for all active sources.

    Returns:
        dict mapping source names to task IDs
    """
    results = {}
    for source_name in SPIDER_REGISTRY:
        task = scrape_source.delay(source_name, triggered_by="batch")
        results[source_name] = task.id
        logger.info(f"Queued scrape for {source_name}: {task.id}")
    return results


def _import_spider(source_name: str):
    """Dynamically import spider class."""
    module_path = SPIDER_REGISTRY[source_name]
    module_name, class_name = module_path.rsplit(".", 1)

    import importlib
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _create_scrape_run(
    source_name: str,
    triggered_by: str,
    task_id: Optional[str] = None,
) -> int:
    """Create scrape run database record."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.scrapers.settings import DATABASE_URL

    # Use sync connection for Celery
    db_url = DATABASE_URL
    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        run = ScrapeRun(
            source_name=source_name,
            spider_name=source_name,
            started_at=datetime.utcnow(),
            status=ScrapeStatus.PENDING,
            triggered_by=triggered_by,
            celery_task_id=task_id,
        )
        session.add(run)
        session.commit()
        run_id = run.id
        return run_id
    finally:
        session.close()
        engine.dispose()


def _update_scrape_run(
    run_id: int,
    status: Optional[ScrapeStatus] = None,
    items_scraped: int = 0,
    items_new: int = 0,
    items_updated: int = 0,
    items_skipped: int = 0,
    items_errored: int = 0,
    errors: Optional[list] = None,
):
    """Update scrape run record."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.scrapers.settings import DATABASE_URL

    db_url = DATABASE_URL
    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        run = session.query(ScrapeRun).get(run_id)
        if run:
            if status:
                run.status = status
            if status in (ScrapeStatus.COMPLETED, ScrapeStatus.FAILED, ScrapeStatus.CANCELLED):
                run.completed_at = datetime.utcnow()
            run.items_scraped = items_scraped
            run.items_new = items_new
            run.items_updated = items_updated
            run.items_skipped = items_skipped
            run.items_errored = items_errored
            if errors:
                run.errors = errors
            session.commit()
    finally:
        session.close()
        engine.dispose()


def _get_scrape_run_stats(run_id: int) -> dict:
    """Get stats from scrape run record."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.scrapers.settings import DATABASE_URL

    db_url = DATABASE_URL
    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        run = session.query(ScrapeRun).get(run_id)
        if run:
            return {
                "items_scraped": run.items_scraped,
                "items_new": run.items_new,
                "items_updated": run.items_updated,
                "items_skipped": run.items_skipped,
                "items_errored": run.items_errored,
                "errors": run.errors or [],
            }
        return {}
    finally:
        session.close()
        engine.dispose()
