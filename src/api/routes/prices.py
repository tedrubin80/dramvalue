"""
Price history and trend endpoints.
"""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.bottle import Bottle
from src.models.price import Price, PriceSource

router = APIRouter()


# =============================================================================
# Response Schemas
# =============================================================================


class PricePoint(BaseModel):
    """Single price data point."""
    id: int
    price_usd: float
    transaction_date: datetime
    source: PriceSource
    source_name: str | None
    is_verified: bool
    confidence_weight: float

    class Config:
        from_attributes = True


class PriceHistory(BaseModel):
    """Price history for a bottle."""
    bottle_id: int
    bottle_name: str
    prices: list[PricePoint]
    stats: dict


class SourceBreakdown(BaseModel):
    """Price breakdown by source."""
    source: PriceSource
    count: int
    avg_price: float
    min_price: float
    max_price: float


class PriceStats(BaseModel):
    """Detailed price statistics."""
    bottle_id: int
    bottle_name: str
    total_prices: int
    avg_price: float | None
    median_price: float | None
    min_price: float | None
    max_price: float | None
    std_dev: float | None
    price_trend_30d: float | None
    price_trend_90d: float | None
    sources: list[SourceBreakdown]
    last_updated: datetime | None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/bottle/{bottle_id}/history", response_model=PriceHistory)
async def get_price_history(
    bottle_id: int,
    days: int = Query(365, ge=7, le=1825, description="Days of history"),
    source: PriceSource | None = Query(None, description="Filter by source"),
    verified_only: bool = Query(False, description="Only verified prices"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get price history for a bottle.

    - Returns individual price points
    - Filter by source type or verification status
    - Includes basic statistics
    """
    # Verify bottle exists
    bottle_result = await db.execute(
        select(Bottle).where(Bottle.id == bottle_id, Bottle.is_active == True)
    )
    bottle = bottle_result.scalar_one_or_none()
    if not bottle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Build price query
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    query = select(Price).where(
        and_(
            Price.bottle_id == bottle_id,
            Price.transaction_date >= cutoff_date,
            Price.is_excluded == False,
        )
    )

    if source:
        query = query.where(Price.source == source)
    if verified_only:
        query = query.where(Price.is_verified == True)

    query = query.order_by(Price.transaction_date.desc())

    result = await db.execute(query)
    prices = result.scalars().all()

    # Calculate stats
    price_values = [p.price_usd for p in prices]
    stats = {
        "count": len(prices),
        "avg": sum(price_values) / len(price_values) if price_values else None,
        "min": min(price_values) if price_values else None,
        "max": max(price_values) if price_values else None,
    }

    return PriceHistory(
        bottle_id=bottle_id,
        bottle_name=bottle.name,
        prices=[PricePoint.model_validate(p) for p in prices],
        stats=stats,
    )


@router.get("/bottle/{bottle_id}/stats", response_model=PriceStats)
async def get_price_stats(
    bottle_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed price statistics for a bottle.

    - Includes breakdown by source
    - 30-day and 90-day trends
    - Statistical measures (mean, median, std dev)
    """
    # Verify bottle exists
    bottle_result = await db.execute(
        select(Bottle).where(Bottle.id == bottle_id, Bottle.is_active == True)
    )
    bottle = bottle_result.scalar_one_or_none()
    if not bottle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Get all prices
    prices_result = await db.execute(
        select(Price).where(
            Price.bottle_id == bottle_id,
            Price.is_excluded == False,
        )
    )
    all_prices = prices_result.scalars().all()

    if not all_prices:
        return PriceStats(
            bottle_id=bottle_id,
            bottle_name=bottle.name,
            total_prices=0,
            avg_price=None,
            median_price=None,
            min_price=None,
            max_price=None,
            std_dev=None,
            price_trend_30d=None,
            price_trend_90d=None,
            sources=[],
            last_updated=None,
        )

    # Calculate overall stats
    price_values = sorted([p.price_usd for p in all_prices])
    n = len(price_values)
    avg = sum(price_values) / n
    median = price_values[n // 2] if n % 2 else (price_values[n // 2 - 1] + price_values[n // 2]) / 2

    # Standard deviation
    variance = sum((x - avg) ** 2 for x in price_values) / n
    std_dev = variance ** 0.5

    # Source breakdown
    source_stats = {}
    for price in all_prices:
        if price.source not in source_stats:
            source_stats[price.source] = []
        source_stats[price.source].append(price.price_usd)

    sources = [
        SourceBreakdown(
            source=source,
            count=len(prices),
            avg_price=sum(prices) / len(prices),
            min_price=min(prices),
            max_price=max(prices),
        )
        for source, prices in source_stats.items()
    ]

    # Trend calculations (simplified)
    now = datetime.utcnow()
    recent_30 = [p for p in all_prices if p.transaction_date >= now - timedelta(days=30)]
    older_30 = [p for p in all_prices if now - timedelta(days=60) <= p.transaction_date < now - timedelta(days=30)]

    trend_30d = None
    if recent_30 and older_30:
        recent_avg = sum(p.price_usd for p in recent_30) / len(recent_30)
        older_avg = sum(p.price_usd for p in older_30) / len(older_30)
        if older_avg > 0:
            trend_30d = ((recent_avg - older_avg) / older_avg) * 100

    return PriceStats(
        bottle_id=bottle_id,
        bottle_name=bottle.name,
        total_prices=n,
        avg_price=avg,
        median_price=median,
        min_price=min(price_values),
        max_price=max(price_values),
        std_dev=std_dev,
        price_trend_30d=trend_30d,
        price_trend_90d=bottle.price_trend,
        sources=sources,
        last_updated=bottle.stats_updated_at,
    )
