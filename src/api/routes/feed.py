"""
Private JSON feed API for personal integrations.

All endpoints require FEED_API_KEY via X-API-Key or Authorization: Bearer headers.
Designed for polling new price data into external systems.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import verify_feed_api_key
from src.api.response import paginated_response, success_response
from src.core.rate_limit import limiter
from src.db.session import get_db
from src.models.bottle import Bottle, SpiritCategory
from src.models.market_stat import MarketStat
from src.models.price import Price, PriceSource

router = APIRouter(dependencies=[Depends(verify_feed_api_key)])


def _serialize_price(row) -> dict:
    return {
        "id": row.id,
        "bottle_id": row.bottle_id,
        "bottle_name": row.bottle_name,
        "distillery": row.distillery,
        "category": row.category.value if row.category else None,
        "price": float(row.price) if row.price is not None else None,
        "currency": row.currency,
        "price_usd": float(row.price_usd) if row.price_usd is not None else None,
        "source": row.source.value if row.source else None,
        "source_name": row.source_name,
        "auction_house": row.auction_house.value if row.auction_house else None,
        "is_sold": row.is_sold,
        "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
        "source_url": row.source_url,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
@limiter.limit("120/hour")
async def feed_info(request: Request):
    """Feed API index — lists available endpoints."""
    return success_response(
        data={
            "name": "DramValue Private Feed API",
            "version": "1",
            "endpoints": {
                "prices": "/api/v1/feed/prices",
                "prices_recent": "/api/v1/feed/prices/recent",
                "bottles": "/api/v1/feed/bottles",
                "market": "/api/v1/feed/market",
                "stats": "/api/v1/feed/stats",
            },
        }
    )


@router.get("/stats")
@limiter.limit("120/hour")
async def feed_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """High-level database counts for monitoring."""
    bottle_count = await db.scalar(select(func.count()).select_from(Bottle))
    price_count = await db.scalar(select(func.count()).select_from(Price))
    market_count = await db.scalar(select(func.count()).select_from(MarketStat))

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_prices_7d = await db.scalar(
        select(func.count()).select_from(Price).where(Price.created_at >= week_ago)
    )

    return success_response(
        data={
            "bottles": bottle_count or 0,
            "prices": price_count or 0,
            "market_stats": market_count or 0,
            "new_prices_7d": new_prices_7d or 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/prices")
@limiter.limit("120/hour")
async def feed_prices(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    days: int = Query(30, ge=1, le=365, description="Days of history"),
    source: PriceSource | None = Query(None),
    source_name: str | None = Query(None, description="Filter by source name"),
    category: SpiritCategory | None = Query(None),
    bottle_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Paginated price feed with filters."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        select(
            Price.id,
            Price.bottle_id,
            Price.price,
            Price.currency,
            Price.price_usd,
            Price.source,
            Price.source_name,
            Price.auction_house,
            Price.is_sold,
            Price.transaction_date,
            Price.source_url,
            Price.created_at,
            Bottle.name.label("bottle_name"),
            Bottle.distillery,
            Bottle.category,
        )
        .join(Bottle, Price.bottle_id == Bottle.id)
        .where(Price.transaction_date >= cutoff)
        .order_by(Price.transaction_date.desc(), Price.id.desc())
    )

    if source:
        query = query.where(Price.source == source)
    if source_name:
        query = query.where(Price.source_name.ilike(f"%{source_name}%"))
    if category:
        query = query.where(Bottle.category == category)
    if bottle_id:
        query = query.where(Price.bottle_id == bottle_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.fetchall()

    return paginated_response(
        items=[_serialize_price(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        item_key="prices",
    )


@router.get("/prices/recent")
@limiter.limit("300/hour")
async def feed_prices_recent(
    request: Request,
    since: datetime | None = Query(
        None,
        description="ISO timestamp — return prices created after this time",
    ),
    limit: int = Query(100, ge=1, le=500),
    source_name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll for newly ingested prices.

    Use `since` from the previous response's `meta.generated_at` for incremental sync.
    """
    generated_at = datetime.now(timezone.utc)
    if since is None:
        since = generated_at - timedelta(hours=24)

    query = (
        select(
            Price.id,
            Price.bottle_id,
            Price.price,
            Price.currency,
            Price.price_usd,
            Price.source,
            Price.source_name,
            Price.auction_house,
            Price.is_sold,
            Price.transaction_date,
            Price.source_url,
            Price.created_at,
            Bottle.name.label("bottle_name"),
            Bottle.distillery,
            Bottle.category,
        )
        .join(Bottle, Price.bottle_id == Bottle.id)
        .where(Price.created_at > since)
        .order_by(Price.created_at.asc(), Price.id.asc())
        .limit(limit)
    )

    if source_name:
        query = query.where(Price.source_name.ilike(f"%{source_name}%"))

    result = await db.execute(query)
    rows = result.fetchall()

    return success_response(
        data=[_serialize_price(row) for row in rows],
        meta={
            "since": since.isoformat(),
            "generated_at": generated_at.isoformat(),
            "count": len(rows),
            "limit": limit,
        },
    )


@router.get("/bottles")
@limiter.limit("60/hour")
async def feed_bottles(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    category: SpiritCategory | None = Query(None),
    has_prices: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """Bottle catalog with price aggregates."""
    query = (
        select(
            Bottle.id,
            Bottle.name,
            Bottle.distillery,
            Bottle.category,
            Bottle.age_statement,
            Bottle.size_ml,
            Bottle.brand,
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price_usd"),
            func.max(Price.transaction_date).label("last_sale"),
        )
        .join(Price, Price.bottle_id == Bottle.id, isouter=not has_prices)
        .group_by(Bottle.id)
        .order_by(Bottle.name)
    )

    if category:
        query = query.where(Bottle.category == category)
    if has_prices:
        query = query.having(func.count(Price.id) > 0)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.fetchall()

    bottles = [
        {
            "id": row.id,
            "name": row.name,
            "distillery": row.distillery,
            "category": row.category.value if row.category else None,
            "age_statement": row.age_statement,
            "size_ml": row.size_ml,
            "brand": row.brand,
            "price_count": row.price_count or 0,
            "avg_price_usd": round(float(row.avg_price_usd), 2) if row.avg_price_usd else None,
            "last_sale": row.last_sale.isoformat() if row.last_sale else None,
        }
        for row in rows
    ]

    return paginated_response(
        items=bottles,
        total=total,
        page=page,
        page_size=page_size,
        item_key="bottles",
    )


@router.get("/market")
@limiter.limit("60/hour")
async def feed_market(
    request: Request,
    months: int = Query(12, ge=1, le=60),
    auction_slug: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Monthly auction market aggregate stats."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 31)

    query = (
        select(MarketStat)
        .where(MarketStat.period_date >= cutoff)
        .order_by(MarketStat.period_date.desc(), MarketStat.auction_name)
    )

    if auction_slug:
        query = query.where(MarketStat.auction_slug == auction_slug)

    result = await db.execute(query.limit(500))
    stats = result.scalars().all()

    return success_response(
        data=[
            {
                "auction_name": s.auction_name,
                "auction_slug": s.auction_slug,
                "period_date": s.period_date.isoformat(),
                "winning_bid_mean": s.winning_bid_mean,
                "winning_bid_min": s.winning_bid_min,
                "winning_bid_max": s.winning_bid_max,
                "trading_volume": s.trading_volume,
                "lots_count": s.lots_count,
            }
            for s in stats
        ],
        meta={"months": months, "count": len(stats)},
    )
