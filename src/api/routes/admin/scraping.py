"""
Admin routes for scraping management.

Provides endpoints to:
- View scrape run history
- Trigger manual scrapes
- View available sources
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_admin
from src.db.session import get_db
from src.models.scrape_run import ScrapeRun, ScrapeStatus
from src.models.user import User

router = APIRouter(prefix="/scraping", tags=["Admin - Scraping"])


# Available spider sources
AVAILABLE_SOURCES = {
    "whisky_auctioneer": {
        "display_name": "Whisky Auctioneer",
        "url": "https://www.whiskyauctioneer.com",
        "schedule": "Every 6 hours",
        "description": "UK-based online whisky auction platform",
    },
    "scotch_whisky_auctions": {
        "display_name": "Scotch Whisky Auctions",
        "url": "https://www.scotchwhiskyauctions.com",
        "schedule": "Every 6 hours (offset)",
        "description": "UK-based whisky auction site",
    },
}


class ScrapeRunResponse(BaseModel):
    """Response model for scrape run."""
    id: int
    source_name: str
    spider_name: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    items_scraped: int
    items_new: int
    items_updated: int
    items_skipped: int
    items_errored: int
    triggered_by: str
    errors: Optional[list] = None

    class Config:
        from_attributes = True


class TriggerScrapeRequest(BaseModel):
    """Request to trigger a scrape."""
    source_name: str
    full_scrape: bool = False


class TriggerScrapeResponse(BaseModel):
    """Response after triggering a scrape."""
    task_id: str
    source_name: str
    message: str


class SourceInfo(BaseModel):
    """Information about a scrape source."""
    name: str
    display_name: str
    url: str
    schedule: str
    description: str
    status: str = "active"


@router.get("/runs", response_model=List[ScrapeRunResponse])
async def list_scrape_runs(
    source: Optional[str] = None,
    status_filter: Optional[ScrapeStatus] = Query(None, alias="status"),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    List recent scrape runs with optional filters.

    Args:
        source: Filter by source name
        status: Filter by status
        days: Number of days to look back
        limit: Maximum number of results
    """
    query = select(ScrapeRun).order_by(ScrapeRun.started_at.desc())

    if source:
        query = query.where(ScrapeRun.source_name == source)
    if status_filter:
        query = query.where(ScrapeRun.status == status_filter)

    cutoff = datetime.utcnow() - timedelta(days=days)
    query = query.where(ScrapeRun.started_at >= cutoff).limit(limit)

    result = await db.execute(query)
    runs = result.scalars().all()

    return [
        ScrapeRunResponse(
            id=run.id,
            source_name=run.source_name,
            spider_name=run.spider_name,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_seconds=run.duration_seconds,
            items_scraped=run.items_scraped,
            items_new=run.items_new,
            items_updated=run.items_updated,
            items_skipped=run.items_skipped,
            items_errored=run.items_errored,
            triggered_by=run.triggered_by,
            errors=run.errors,
        )
        for run in runs
    ]


@router.get("/runs/{run_id}", response_model=ScrapeRunResponse)
async def get_scrape_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Get details of a specific scrape run."""
    query = select(ScrapeRun).where(ScrapeRun.id == run_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scrape run {run_id} not found",
        )

    return ScrapeRunResponse(
        id=run.id,
        source_name=run.source_name,
        spider_name=run.spider_name,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=run.duration_seconds,
        items_scraped=run.items_scraped,
        items_new=run.items_new,
        items_updated=run.items_updated,
        items_skipped=run.items_skipped,
        items_errored=run.items_errored,
        triggered_by=run.triggered_by,
        errors=run.errors,
    )


@router.post("/trigger", response_model=TriggerScrapeResponse)
async def trigger_scrape(
    request: TriggerScrapeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Manually trigger a scrape for a specific source.

    Requires admin authentication.
    """
    if request.source_name not in AVAILABLE_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source: {request.source_name}. "
                   f"Available sources: {list(AVAILABLE_SOURCES.keys())}",
        )

    # Check for already running scrape
    running_query = select(ScrapeRun).where(
        ScrapeRun.source_name == request.source_name,
        ScrapeRun.status.in_([ScrapeStatus.PENDING, ScrapeStatus.RUNNING]),
    )
    result = await db.execute(running_query)
    running = result.scalar_one_or_none()

    if running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scrape already running for {request.source_name} (run_id: {running.id})",
        )

    # Queue the scrape task
    try:
        from src.tasks.scraping import scrape_source
        task = scrape_source.delay(
            request.source_name,
            full_scrape=request.full_scrape,
            triggered_by="manual",
        )

        return TriggerScrapeResponse(
            task_id=task.id,
            source_name=request.source_name,
            message=f"Scrape task queued for {request.source_name}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to queue task: {e}. Is Celery running?",
        )


@router.get("/sources", response_model=List[SourceInfo])
async def list_sources(
    current_user: User = Depends(get_current_admin),
):
    """List available scrape sources with their status."""
    return [
        SourceInfo(
            name=name,
            display_name=info["display_name"],
            url=info["url"],
            schedule=info["schedule"],
            description=info["description"],
            status="active",
        )
        for name, info in AVAILABLE_SOURCES.items()
    ]
