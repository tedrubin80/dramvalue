"""
Price history, statistics, and chart endpoints.

Uses PriceService for business logic and standardized response envelope.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.db.session import get_db
from src.models.price import PriceSource
from src.schemas.price import (
    ChartData,
    PriceDistribution,
    PriceHistory,
    PricePoint,
    PriceStats,
    RecentPrice,
)
from src.services import NotFoundError, PriceService

router = APIRouter()


# =============================================================================
# Dependency
# =============================================================================


def get_price_service(db: AsyncSession = Depends(get_db)) -> PriceService:
    """Dependency to get PriceService instance."""
    return PriceService(db)


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/bottle/{bottle_id}/history")
async def get_price_history(
    bottle_id: int,
    days: int = Query(365, ge=7, le=1825, description="Days of history"),
    source: PriceSource | None = Query(None, description="Filter by source"),
    verified_only: bool = Query(False, description="Only verified prices"),
    limit: int | None = Query(None, ge=1, le=1000, description="Max prices to return"),
    service: PriceService = Depends(get_price_service),
):
    """
    Get price history for a bottle.

    - Returns individual price points
    - Filter by source type or verification status
    - Includes basic statistics
    """
    try:
        bottle, prices = await service.get_history(
            bottle_id,
            days=days,
            source=source,
            verified_only=verified_only,
            limit=limit,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Calculate quick stats
    price_values = [p.price_usd for p in prices]
    stats = {
        "count": len(prices),
        "avg": round(sum(price_values) / len(price_values), 2) if price_values else None,
        "min": round(min(price_values), 2) if price_values else None,
        "max": round(max(price_values), 2) if price_values else None,
    }

    return success_response(
        data={
            "bottle_id": bottle_id,
            "bottle_name": bottle.name,
            "prices": [PricePoint.model_validate(p).model_dump() for p in prices],
            "stats": stats,
        },
        meta={"days": days, "source_filter": source.value if source else None},
    )


@router.get("/bottle/{bottle_id}/stats")
async def get_price_stats(
    bottle_id: int,
    service: PriceService = Depends(get_price_service),
):
    """
    Get detailed price statistics for a bottle.

    - Includes breakdown by source
    - 30-day and 90-day trends
    - Statistical measures (mean, median, std dev)
    """
    try:
        stats = await service.get_stats(bottle_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    return success_response(data={"stats": stats})


@router.get("/bottle/{bottle_id}/chart")
async def get_chart_data(
    bottle_id: int,
    days: int = Query(365, ge=7, le=1825, description="Days of history"),
    aggregation: Literal["daily", "weekly", "monthly"] | None = Query(
        None, description="Aggregation period (auto if not specified)"
    ),
    service: PriceService = Depends(get_price_service),
):
    """
    Get price data formatted for Chart.js.

    Auto-selects aggregation based on time range:
    - <= 90 days: daily
    - <= 365 days: weekly
    - > 365 days: monthly
    """
    try:
        chart_data = await service.get_chart_data(
            bottle_id,
            days=days,
            aggregation=aggregation,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    return success_response(data={"chart": chart_data})


@router.get("/bottle/{bottle_id}/distribution")
async def get_price_distribution(
    bottle_id: int,
    buckets: int = Query(10, ge=5, le=20, description="Number of histogram buckets"),
    service: PriceService = Depends(get_price_service),
):
    """
    Get price distribution for histogram display.

    Divides price range into buckets and counts occurrences.
    """
    try:
        distribution = await service.get_price_distribution(
            bottle_id,
            bucket_count=buckets,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    return success_response(data={"distribution": distribution})


@router.get("/recent")
async def get_recent_prices(
    limit: int = Query(20, ge=1, le=100, description="Number of prices"),
    source: PriceSource | None = Query(None, description="Filter by source"),
    service: PriceService = Depends(get_price_service),
):
    """
    Get most recent prices across all bottles.

    Useful for activity feeds and monitoring.
    """
    prices = await service.get_recent_prices(
        limit=limit,
        source=source,
    )

    return success_response(
        data={"prices": prices},
        meta={"count": len(prices)},
    )


@router.get("/sources")
async def get_price_sources():
    """
    Get all available price sources.
    """
    sources = [
        {
            "value": source.value,
            "label": source.value.replace("_", " ").title(),
        }
        for source in PriceSource
    ]

    return success_response(data={"sources": sources})
