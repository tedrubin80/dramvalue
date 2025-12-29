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
    "whisky_auctioneer": "src.scrapers.spiders.whisky_auctioneer.WhiskyAuctioneerSpider",
    "scotch_whisky_auctions": "src.scrapers.spiders.scotch_whisky_auctions.ScotchWhiskyAuctionsSpider",
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
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    logger.info(f"Starting scrape task for: {source_name}")

    if source_name not in SPIDER_REGISTRY:
        raise ValueError(f"Unknown spider: {source_name}. Available: {list(SPIDER_REGISTRY.keys())}")

    # Create scrape run record
    scrape_run_id = _create_scrape_run(source_name, triggered_by, self.request.id)

    try:
        # Update status to running
        _update_scrape_run(scrape_run_id, status=ScrapeStatus.RUNNING)

        # Import spider class
        spider_class = _import_spider(source_name)

        # Configure Scrapy settings
        settings = get_project_settings()
        settings.setmodule("src.scrapers.settings")

        # Create crawler process
        process = CrawlerProcess(settings)

        # Results collector
        results = {
            "items_scraped": 0,
            "items_new": 0,
            "items_updated": 0,
            "items_skipped": 0,
            "items_errored": 0,
            "errors": [],
        }

        def collect_stats(spider, reason):
            """Collect stats from spider when it closes."""
            results["items_scraped"] = spider.items_scraped
            results["items_new"] = spider.items_new
            results["items_updated"] = spider.items_updated
            results["items_skipped"] = spider.items_skipped
            results["items_errored"] = spider.items_errored
            results["errors"] = spider.errors

        # Connect signal to collect stats
        from scrapy import signals
        crawler = process.create_crawler(spider_class)
        crawler.signals.connect(collect_stats, signal=signals.spider_closed)

        # Run spider
        process.crawl(crawler, scrape_run_id=scrape_run_id)
        process.start()  # Blocks until spider finishes

        # Update scrape run with results
        _update_scrape_run(
            scrape_run_id,
            status=ScrapeStatus.COMPLETED,
            items_scraped=results["items_scraped"],
            items_new=results["items_new"],
            items_updated=results["items_updated"],
            items_skipped=results["items_skipped"],
            items_errored=results["items_errored"],
            errors=results["errors"],
        )

        logger.info(f"Scrape completed for {source_name}: {results}")
        return results

    except Exception as e:
        logger.error(f"Scrape failed for {source_name}: {e}")

        # Update scrape run with error
        _update_scrape_run(
            scrape_run_id,
            status=ScrapeStatus.FAILED,
            errors=[{"error": str(e), "timestamp": datetime.utcnow().isoformat()}],
        )

        # Retry with exponential backoff
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
