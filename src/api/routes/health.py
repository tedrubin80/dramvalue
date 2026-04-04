"""
Health check endpoints.

Basic /health is public (for load balancer).
Detailed endpoints (/db, /scraper, /data-quality) require admin auth.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_admin
from src.db.session import get_db
from src.models.scrape_run import ScrapeRun, ScrapeStatus
from src.models.price import Price
from src.models.bottle import Bottle
from src.models.moderation import ModerationQueue, ModerationFlag
from src.models.user import User

router = APIRouter()


@router.get("")
async def health():
    """Basic health check — public, no details."""
    return {"status": "healthy"}


@router.get("/db")
async def health_db(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Database connectivity health check (admin only)."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return {"status": "unhealthy", "database": "disconnected"}


@router.get("/scraper")
async def health_scraper(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Scraper health status (admin only)."""
    cutoff = datetime.utcnow() - timedelta(hours=48)
    query = (
        select(ScrapeRun)
        .where(ScrapeRun.started_at >= cutoff)
        .order_by(ScrapeRun.started_at.desc())
    )
    result = await db.execute(query)
    runs = result.scalars().all()

    sources = {}
    for run in runs:
        if run.source_name not in sources:
            sources[run.source_name] = {
                "last_run": run.started_at.isoformat() if run.started_at else None,
                "last_status": run.status.value,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "items_last_48h": 0,
                "errors_last_48h": 0,
                "runs_last_48h": 0,
            }
        sources[run.source_name]["items_last_48h"] += run.items_new
        sources[run.source_name]["errors_last_48h"] += run.items_errored
        sources[run.source_name]["runs_last_48h"] += 1

    alerts = []
    all_healthy = True

    for source_name, stats in sources.items():
        if stats["last_status"] == "failed":
            alerts.append(f"{source_name}: Last scrape failed")
            all_healthy = False

        if stats.get("last_run"):
            last_run = datetime.fromisoformat(stats["last_run"])
            if datetime.utcnow() - last_run > timedelta(hours=12):
                alerts.append(f"{source_name}: No scrapes in last 12 hours")
                all_healthy = False

    expected_sources = {"whisky_auctioneer", "scotch_whisky_auctions"}
    missing_sources = expected_sources - set(sources.keys())
    if missing_sources:
        for source in missing_sources:
            alerts.append(f"{source}: Never scraped")
        all_healthy = False

    return {
        "status": "healthy" if all_healthy else "degraded",
        "sources": sources,
        "alerts": alerts,
        "checked_at": datetime.utcnow().isoformat(),
    }


@router.get("/data-quality")
async def health_data_quality(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Data quality metrics (admin only)."""
    bottle_count = await db.scalar(
        select(func.count(Bottle.id)).where(Bottle.is_active == True)
    )
    price_count = await db.scalar(
        select(func.count(Price.id)).where(Price.is_excluded == False)
    )

    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_prices = await db.scalar(
        select(func.count(Price.id)).where(
            Price.created_at >= week_ago,
            Price.is_excluded == False,
        )
    )

    month_ago = datetime.utcnow() - timedelta(days=30)
    monthly_prices = await db.scalar(
        select(func.count(Price.id)).where(
            Price.created_at >= month_ago,
            Price.is_excluded == False,
        )
    )

    review_backlog = await db.scalar(
        select(func.count(ModerationQueue.id)).where(
            ModerationQueue.flag_type == ModerationFlag.MANUAL_REVIEW,
            ModerationQueue.is_resolved == 0,
        )
    )

    phase2_target = 1000
    progress_percent = min(100, ((bottle_count or 0) / phase2_target) * 100)

    return {
        "bottles_total": bottle_count or 0,
        "prices_total": price_count or 0,
        "prices_last_7_days": recent_prices or 0,
        "prices_last_30_days": monthly_prices or 0,
        "normalization_backlog": review_backlog or 0,
        "phase2_target": phase2_target,
        "progress_percent": round(progress_percent, 1),
        "status": "on_track" if progress_percent >= 10 else "needs_attention",
        "checked_at": datetime.utcnow().isoformat(),
    }
