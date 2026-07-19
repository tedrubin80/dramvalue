"""
Private JSON feed API for personal integrations (OpenClaw, promo automation).

All endpoints require FEED_API_KEY via X-API-Key or Authorization: Bearer headers.
Designed for polling price data, looking up specific bottles, and spotting trends.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import verify_feed_api_key
from src.api.response import paginated_response, success_response
from src.core.rate_limit import limiter
from src.db.session import get_db
from src.models.bottle import Bottle, SpiritCategory
from src.models.market_stat import MarketStat
from src.models.price import Price, PriceSource

router = APIRouter(dependencies=[Depends(verify_feed_api_key)])

SITE_BASE = "https://dramvalue.com"


def _bottle_url(bottle_id: int) -> str:
    return f"{SITE_BASE}/bottles/{bottle_id}"


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
        "page_url": _bottle_url(row.bottle_id) if row.bottle_id else None,
    }


def _serialize_bottle_promo(bottle: Bottle, *, recent_count: int | None = None) -> dict:
    """Compact bottle payload with pricing, trend, and shareable page URL."""
    data = {
        "id": bottle.id,
        "name": bottle.name,
        "distillery": bottle.distillery,
        "brand": bottle.brand,
        "category": bottle.category.value if bottle.category else None,
        "age_statement": bottle.age_statement,
        "size_ml": bottle.size_ml,
        "price_count": bottle.price_count or 0,
        "avg_price_usd": round(float(bottle.avg_price), 2) if bottle.avg_price is not None else None,
        "min_price_usd": round(float(bottle.min_price), 2) if bottle.min_price is not None else None,
        "max_price_usd": round(float(bottle.max_price), 2) if bottle.max_price is not None else None,
        "last_price_usd": round(float(bottle.last_price), 2) if bottle.last_price is not None else None,
        "last_price_date": bottle.last_price_date.isoformat() if bottle.last_price_date else None,
        "price_trend_90d_pct": round(float(bottle.price_trend), 2) if bottle.price_trend is not None else None,
        "page_url": _bottle_url(bottle.id),
    }
    if recent_count is not None:
        data["recent_price_count"] = recent_count
    return data


@router.get("")
@limiter.limit("120/hour")
async def feed_info(request: Request):
    """Feed API index — lists available endpoints."""
    return success_response(
        data={
            "name": "DramValue Private Feed API",
            "version": "1.1",
            "purpose": "Private bottle pricing & trends for site promotion (OpenClaw)",
            "endpoints": {
                "stats": "/api/v1/feed/stats",
                "search": "/api/v1/feed/search?q=",
                "bottle": "/api/v1/feed/bottles/{id}",
                "bottle_prices": "/api/v1/feed/bottles/{id}/prices",
                "bottles": "/api/v1/feed/bottles",
                "trending": "/api/v1/feed/trending",
                "movers": "/api/v1/feed/movers",
                "prices": "/api/v1/feed/prices",
                "prices_recent": "/api/v1/feed/prices/recent",
                "market": "/api/v1/feed/market",
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


@router.get("/search")
@limiter.limit("120/hour")
async def feed_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=200, description="Bottle / distillery / brand search"),
    limit: int = Query(20, ge=1, le=50),
    category: SpiritCategory | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Search bottles by name, distillery, or brand — for promo lookups."""
    pattern = f"%{q.strip()}%"
    query = (
        select(Bottle)
        .where(
            Bottle.is_active == True,  # noqa: E712
            or_(
                Bottle.name.ilike(pattern),
                Bottle.distillery.ilike(pattern),
                Bottle.brand.ilike(pattern),
                Bottle.normalized_name.ilike(pattern),
            ),
        )
        .order_by(Bottle.price_count.desc().nullslast(), Bottle.name)
        .limit(limit)
    )
    if category:
        query = query.where(Bottle.category == category)

    result = await db.execute(query)
    bottles = list(result.scalars().all())

    return success_response(
        data=[_serialize_bottle_promo(b) for b in bottles],
        meta={"q": q, "count": len(bottles), "limit": limit},
    )


@router.get("/trending")
@limiter.limit("120/hour")
async def feed_trending(
    request: Request,
    days: int = Query(30, ge=7, le=90),
    limit: int = Query(15, ge=1, le=50),
    category: SpiritCategory | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Trending bottles by recent price activity + 90d trend.

    Ideal for OpenClaw promo posts: hottest bottles with shareable page_url.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    activity = (
        select(
            Price.bottle_id,
            func.count(Price.id).label("recent_count"),
        )
        .where(
            Price.transaction_date >= cutoff,
            Price.is_excluded == False,  # noqa: E712
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    query = (
        select(Bottle, activity.c.recent_count)
        .join(activity, Bottle.id == activity.c.bottle_id)
        .where(
            Bottle.is_active == True,  # noqa: E712
            Bottle.price_count >= 3,
        )
        .order_by(
            activity.c.recent_count.desc(),
            Bottle.price_trend.desc().nullslast(),
        )
        .limit(limit)
    )
    if category:
        query = query.where(Bottle.category == category)

    result = await db.execute(query)
    rows = result.all()

    return success_response(
        data=[
            _serialize_bottle_promo(bottle, recent_count=recent_count)
            for bottle, recent_count in rows
        ],
        meta={"days": days, "count": len(rows), "limit": limit},
    )


@router.get("/movers")
@limiter.limit("120/hour")
async def feed_movers(
    request: Request,
    direction: Literal["up", "down", "both"] = Query("both"),
    limit: int = Query(10, ge=1, le=30),
    min_prices: int = Query(5, ge=2, le=50, description="Minimum price points required"),
    category: SpiritCategory | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Biggest 90-day price movers — gainers and/or losers for promo headlines."""
    base = (
        select(Bottle)
        .where(
            Bottle.is_active == True,  # noqa: E712
            Bottle.price_count >= min_prices,
            Bottle.price_trend.isnot(None),
        )
    )
    if category:
        base = base.where(Bottle.category == category)

    movers: dict = {}

    if direction in ("up", "both"):
        up_result = await db.execute(
            base.where(Bottle.price_trend > 0)
            .order_by(Bottle.price_trend.desc())
            .limit(limit)
        )
        movers["gainers"] = [
            _serialize_bottle_promo(b) for b in up_result.scalars().all()
        ]

    if direction in ("down", "both"):
        down_result = await db.execute(
            base.where(Bottle.price_trend < 0)
            .order_by(Bottle.price_trend.asc())
            .limit(limit)
        )
        movers["losers"] = [
            _serialize_bottle_promo(b) for b in down_result.scalars().all()
        ]

    return success_response(
        data=movers,
        meta={"direction": direction, "limit": limit, "min_prices": min_prices},
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
            "page_url": _bottle_url(row.id),
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


@router.get("/bottles/{bottle_id}")
@limiter.limit("120/hour")
async def feed_bottle_detail(
    request: Request,
    bottle_id: int,
    recent_limit: int = Query(10, ge=1, le=50, description="Recent prices to include"),
    db: AsyncSession = Depends(get_db),
):
    """
    Single bottle with pricing summary, 90d trend, and recent sales.

    Primary endpoint for OpenClaw when promoting a specific bottle.
    """
    result = await db.execute(
        select(Bottle).where(Bottle.id == bottle_id, Bottle.is_active == True)  # noqa: E712
    )
    bottle = result.scalar_one_or_none()
    if not bottle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bottle not found")

    prices_result = await db.execute(
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
        .where(
            Price.bottle_id == bottle_id,
            Price.is_excluded == False,  # noqa: E712
        )
        .order_by(Price.transaction_date.desc().nullslast(), Price.id.desc())
        .limit(recent_limit)
    )
    recent_prices = [_serialize_price(row) for row in prices_result.fetchall()]

    trend_label = None
    if bottle.price_trend is not None:
        if bottle.price_trend >= 5:
            trend_label = "rising"
        elif bottle.price_trend <= -5:
            trend_label = "falling"
        else:
            trend_label = "stable"

    data = _serialize_bottle_promo(bottle)
    data.update(
        {
            "confidence_score": (
                round(float(bottle.confidence_score), 3)
                if bottle.confidence_score is not None
                else None
            ),
            "trend_label": trend_label,
            "stats_updated_at": (
                bottle.stats_updated_at.isoformat() if bottle.stats_updated_at else None
            ),
            "recent_prices": recent_prices,
            "promo": {
                "headline_hint": (
                    f"{bottle.name} — avg ${bottle.avg_price:,.0f}"
                    if bottle.avg_price
                    else bottle.name
                ),
                "trend_hint": (
                    f"{bottle.price_trend:+.1f}% over 90 days"
                    if bottle.price_trend is not None
                    else None
                ),
                "cta_url": _bottle_url(bottle.id),
            },
        }
    )

    return success_response(data=data)


@router.get("/bottles/{bottle_id}/prices")
@limiter.limit("120/hour")
async def feed_bottle_prices(
    request: Request,
    bottle_id: int,
    days: int = Query(365, ge=1, le=1825),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Full price history for one bottle."""
    exists = await db.scalar(select(Bottle.id).where(Bottle.id == bottle_id))
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bottle not found")

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
        .where(
            Price.bottle_id == bottle_id,
            Price.transaction_date >= cutoff,
            Price.is_excluded == False,  # noqa: E712
        )
        .order_by(Price.transaction_date.desc(), Price.id.desc())
    )

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
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
