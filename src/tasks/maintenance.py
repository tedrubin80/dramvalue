"""
Celery tasks for maintenance and statistics.

Handles:
- Bottle statistics refresh
- Scrape run cleanup
- Data quality checks
"""

import logging
from datetime import datetime, timedelta

from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def refresh_bottle_stats() -> dict:
    """
    Refresh cached statistics for all bottles.

    Updates:
    - price_count
    - avg_price, min_price, max_price
    - last_price, last_price_date
    - price_trend (90-day change)

    Returns:
        dict with update statistics
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from src.scrapers.settings import DATABASE_URL

    logger.info("Starting bottle statistics refresh")

    db_url = DATABASE_URL
    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Update bottle statistics using a single efficient query
        update_query = text("""
            UPDATE bottles b
            SET
                price_count = stats.price_count,
                avg_price = stats.avg_price,
                min_price = stats.min_price,
                max_price = stats.max_price,
                last_price = stats.last_price,
                last_price_date = stats.last_price_date,
                stats_updated_at = NOW()
            FROM (
                SELECT
                    p.bottle_id,
                    COUNT(*) as price_count,
                    AVG(p.price_usd) as avg_price,
                    MIN(p.price_usd) as min_price,
                    MAX(p.price_usd) as max_price,
                    (
                        SELECT price_usd
                        FROM prices
                        WHERE bottle_id = p.bottle_id
                        AND is_excluded = false
                        ORDER BY transaction_date DESC
                        LIMIT 1
                    ) as last_price,
                    MAX(p.transaction_date) as last_price_date
                FROM prices p
                WHERE p.is_excluded = false
                GROUP BY p.bottle_id
            ) stats
            WHERE b.id = stats.bottle_id
        """)

        result = session.execute(update_query)
        bottles_updated = result.rowcount

        # Calculate price trends (90-day change)
        trend_query = text("""
            UPDATE bottles b
            SET price_trend = trend.pct_change
            FROM (
                SELECT
                    bottle_id,
                    CASE
                        WHEN old_avg IS NULL OR old_avg = 0 THEN NULL
                        ELSE ((new_avg - old_avg) / old_avg) * 100
                    END as pct_change
                FROM (
                    SELECT
                        p.bottle_id,
                        AVG(CASE WHEN p.transaction_date >= NOW() - INTERVAL '30 days' THEN p.price_usd END) as new_avg,
                        AVG(CASE WHEN p.transaction_date < NOW() - INTERVAL '60 days'
                                  AND p.transaction_date >= NOW() - INTERVAL '90 days' THEN p.price_usd END) as old_avg
                    FROM prices p
                    WHERE p.is_excluded = false
                    GROUP BY p.bottle_id
                ) avgs
            ) trend
            WHERE b.id = trend.bottle_id
        """)

        session.execute(trend_query)
        session.commit()

        logger.info(f"Refreshed statistics for {bottles_updated} bottles")
        return {
            "bottles_updated": bottles_updated,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error refreshing bottle stats: {e}")
        raise

    finally:
        session.close()
        engine.dispose()


@celery_app.task
def cleanup_old_scrape_runs(days_to_keep: int = 30) -> dict:
    """
    Clean up old scrape run records.

    Keeps the last N days of records and removes older ones.

    Args:
        days_to_keep: Number of days of records to retain

    Returns:
        dict with deletion statistics
    """
    from sqlalchemy import create_engine, delete
    from sqlalchemy.orm import sessionmaker
    from src.scrapers.settings import DATABASE_URL
    from src.models.scrape_run import ScrapeRun

    logger.info(f"Cleaning up scrape runs older than {days_to_keep} days")

    db_url = DATABASE_URL
    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        # Delete old records
        stmt = delete(ScrapeRun).where(ScrapeRun.started_at < cutoff_date)
        result = session.execute(stmt)
        deleted_count = result.rowcount

        session.commit()

        logger.info(f"Deleted {deleted_count} old scrape run records")
        return {
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error cleaning up scrape runs: {e}")
        raise

    finally:
        session.close()
        engine.dispose()


@celery_app.task
def check_data_quality() -> dict:
    """
    Check data quality metrics and generate report.

    Returns:
        dict with quality metrics
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from src.scrapers.settings import DATABASE_URL

    logger.info("Running data quality check")

    db_url = DATABASE_URL
    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get various quality metrics
        metrics = {}

        # Total counts
        counts_query = text("""
            SELECT
                (SELECT COUNT(*) FROM bottles WHERE is_active = true) as bottles,
                (SELECT COUNT(*) FROM prices WHERE is_excluded = false) as prices,
                (SELECT COUNT(*) FROM prices WHERE transaction_date >= NOW() - INTERVAL '7 days') as prices_7d,
                (SELECT COUNT(*) FROM prices WHERE transaction_date >= NOW() - INTERVAL '30 days') as prices_30d
        """)
        result = session.execute(counts_query).fetchone()
        metrics["bottles"] = result[0]
        metrics["prices"] = result[1]
        metrics["prices_last_7_days"] = result[2]
        metrics["prices_last_30_days"] = result[3]

        # Bottles without prices
        orphan_query = text("""
            SELECT COUNT(*)
            FROM bottles b
            LEFT JOIN prices p ON b.id = p.bottle_id
            WHERE p.id IS NULL AND b.is_active = true
        """)
        metrics["bottles_without_prices"] = session.execute(orphan_query).scalar()

        # Prices marked as outliers
        outlier_query = text("""
            SELECT COUNT(*) FROM prices WHERE is_outlier = true
        """)
        metrics["outlier_prices"] = session.execute(outlier_query).scalar()

        # Recent scrape runs
        scrape_query = text("""
            SELECT
                source_name,
                status,
                started_at,
                items_new
            FROM scrape_runs
            WHERE started_at >= NOW() - INTERVAL '24 hours'
            ORDER BY started_at DESC
        """)
        runs = session.execute(scrape_query).fetchall()
        metrics["recent_scrape_runs"] = [
            {
                "source": row[0],
                "status": row[1],
                "started_at": row[2].isoformat() if row[2] else None,
                "items_new": row[3],
            }
            for row in runs
        ]

        logger.info(f"Data quality check complete: {metrics}")
        return metrics

    finally:
        session.close()
        engine.dispose()
