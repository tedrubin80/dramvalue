"""
Market analytics and statistics endpoints.

Provides aggregated market data, trends, and insights.
"""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.db.session import get_db
from src.models.bottle import Bottle, SpiritCategory
from src.models.price import AuctionHouse, Price, PriceSource

router = APIRouter()


@router.get("/overview")
async def get_market_overview(
    db: AsyncSession = Depends(get_db),
):
    """
    Get overall market statistics.

    Returns:
    - Total bottles and prices in database
    - Price statistics (min, max, avg, median)
    - Breakdown by category and auction house
    - Recent activity stats
    """
    # Total counts
    bottles_count = await db.scalar(select(func.count(Bottle.id)))
    prices_count = await db.scalar(select(func.count(Price.id)))

    # Price statistics
    price_stats = await db.execute(
        select(
            func.min(Price.price_usd).label("min"),
            func.max(Price.price_usd).label("max"),
            func.avg(Price.price_usd).label("avg"),
            func.percentile_cont(0.5).within_group(Price.price_usd).label("median"),
        )
    )
    stats_row = price_stats.fetchone()

    # By category
    category_stats = await db.execute(
        select(
            Bottle.category,
            func.count(Bottle.id).label("bottle_count"),
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price"),
        )
        .join(Price, Price.bottle_id == Bottle.id, isouter=True)
        .group_by(Bottle.category)
        .order_by(func.count(Bottle.id).desc())
    )

    # By auction house
    auction_stats = await db.execute(
        select(
            Price.auction_house,
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price"),
            func.min(Price.transaction_date).label("first_price"),
            func.max(Price.transaction_date).label("last_price"),
        )
        .where(Price.auction_house.isnot(None))
        .group_by(Price.auction_house)
        .order_by(func.count(Price.id).desc())
    )

    # Recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_prices = await db.scalar(
        select(func.count(Price.id)).where(Price.created_at >= week_ago)
    )

    return success_response(
        data={
            "totals": {
                "bottles": bottles_count,
                "prices": prices_count,
                "recent_prices_7d": recent_prices,
            },
            "price_stats": {
                "min_usd": float(stats_row.min) if stats_row.min else 0,
                "max_usd": float(stats_row.max) if stats_row.max else 0,
                "avg_usd": round(float(stats_row.avg), 2) if stats_row.avg else 0,
                "median_usd": round(float(stats_row.median), 2) if stats_row.median else 0,
            },
            "by_category": [
                {
                    "category": row.category.value if row.category else "unknown",
                    "bottle_count": row.bottle_count,
                    "price_count": row.price_count or 0,
                    "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
                }
                for row in category_stats
            ],
            "by_auction_house": [
                {
                    "auction_house": row.auction_house.value if row.auction_house else "unknown",
                    "price_count": row.price_count,
                    "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
                    "first_price": row.first_price.isoformat() if row.first_price else None,
                    "last_price": row.last_price.isoformat() if row.last_price else None,
                }
                for row in auction_stats
            ],
        }
    )


@router.get("/top-bottles")
async def get_top_bottles(
    metric: Literal["price_count", "avg_price", "max_price", "volatility"] = Query(
        "price_count", description="Metric to rank by"
    ),
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get top bottles ranked by various metrics.

    Metrics:
    - price_count: Most frequently traded
    - avg_price: Highest average price
    - max_price: Highest single sale
    - volatility: Most price variation (std dev / avg)
    """
    base_query = (
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price"),
            func.max(Price.price_usd).label("max_price"),
            func.min(Price.price_usd).label("min_price"),
            func.stddev(Price.price_usd).label("std_dev"),
        )
        .join(Price, Price.bottle_id == Bottle.id)
        .group_by(Bottle.id)
        .having(func.count(Price.id) >= 3)  # At least 3 prices for meaningful stats
    )

    if category:
        base_query = base_query.where(Bottle.category == category)

    # Order by metric
    if metric == "price_count":
        base_query = base_query.order_by(func.count(Price.id).desc())
    elif metric == "avg_price":
        base_query = base_query.order_by(func.avg(Price.price_usd).desc())
    elif metric == "max_price":
        base_query = base_query.order_by(func.max(Price.price_usd).desc())
    elif metric == "volatility":
        # Coefficient of variation = std_dev / avg
        base_query = base_query.order_by(
            (func.stddev(Price.price_usd) / func.avg(Price.price_usd)).desc()
        )

    result = await db.execute(base_query.limit(limit))

    bottles = []
    for row in result:
        volatility = None
        if row.std_dev and row.avg_price and row.avg_price > 0:
            volatility = round(float(row.std_dev) / float(row.avg_price) * 100, 1)

        bottles.append({
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "distillery": row.distillery,
            "price_count": row.price_count,
            "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
            "max_price_usd": round(float(row.max_price), 2) if row.max_price else None,
            "min_price_usd": round(float(row.min_price), 2) if row.min_price else None,
            "volatility_pct": volatility,
        })

    return success_response(
        data={"bottles": bottles},
        meta={"metric": metric, "count": len(bottles)},
    )


@router.get("/price-ranges")
async def get_price_ranges(
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get distribution of bottles across price ranges.

    Useful for understanding market segments.
    """
    # Calculate average price per bottle, then bucket
    subquery = (
        select(
            Bottle.id,
            Bottle.category,
            func.avg(Price.price_usd).label("avg_price"),
        )
        .join(Price, Price.bottle_id == Bottle.id)
        .group_by(Bottle.id)
    )

    if category:
        subquery = subquery.where(Bottle.category == category)

    subquery = subquery.subquery()

    # Define price ranges
    ranges = [
        (0, 50, "Under $50"),
        (50, 100, "$50-100"),
        (100, 200, "$100-200"),
        (200, 500, "$200-500"),
        (500, 1000, "$500-1000"),
        (1000, 5000, "$1000-5000"),
        (5000, None, "Over $5000"),
    ]

    result_ranges = []
    for low, high, label in ranges:
        if high is None:
            count = await db.scalar(
                select(func.count()).select_from(subquery).where(subquery.c.avg_price >= low)
            )
        else:
            count = await db.scalar(
                select(func.count())
                .select_from(subquery)
                .where(subquery.c.avg_price >= low, subquery.c.avg_price < high)
            )

        result_ranges.append({
            "range": label,
            "min": low,
            "max": high,
            "count": count or 0,
        })

    return success_response(
        data={"ranges": result_ranges},
        meta={"category": category.value if category else "all"},
    )


@router.get("/compare")
async def compare_bottles(
    ids: str = Query(..., description="Comma-separated bottle IDs (max 5)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Compare multiple bottles side by side.

    Returns detailed stats for each bottle for comparison.
    """
    try:
        bottle_ids = [int(x.strip()) for x in ids.split(",")][:5]
    except ValueError:
        return success_response(data={"bottles": []}, meta={"error": "Invalid IDs"})

    if not bottle_ids:
        return success_response(data={"bottles": []})

    # Get stats for each bottle
    result = await db.execute(
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            Bottle.age_statement,
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price"),
            func.min(Price.price_usd).label("min_price"),
            func.max(Price.price_usd).label("max_price"),
            func.stddev(Price.price_usd).label("std_dev"),
            func.max(Price.transaction_date).label("last_sale"),
        )
        .join(Price, Price.bottle_id == Bottle.id, isouter=True)
        .where(Bottle.id.in_(bottle_ids))
        .group_by(Bottle.id)
    )

    bottles = []
    for row in result:
        bottles.append({
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "distillery": row.distillery,
            "age_statement": row.age_statement,
            "stats": {
                "price_count": row.price_count or 0,
                "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
                "min_price_usd": round(float(row.min_price), 2) if row.min_price else None,
                "max_price_usd": round(float(row.max_price), 2) if row.max_price else None,
                "std_dev": round(float(row.std_dev), 2) if row.std_dev else None,
                "last_sale": row.last_sale.isoformat() if row.last_sale else None,
            },
        })

    return success_response(
        data={"bottles": bottles},
        meta={"requested_ids": bottle_ids, "found": len(bottles)},
    )


@router.get("/auction-houses")
async def get_auction_house_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed statistics for each auction house.
    """
    result = await db.execute(
        select(
            Price.auction_house,
            func.count(Price.id).label("total_prices"),
            func.count(func.distinct(Price.bottle_id)).label("unique_bottles"),
            func.avg(Price.price_usd).label("avg_price"),
            func.min(Price.price_usd).label("min_price"),
            func.max(Price.price_usd).label("max_price"),
            func.sum(Price.price_usd).label("total_value"),
            func.min(Price.transaction_date).label("first_price"),
            func.max(Price.transaction_date).label("last_price"),
        )
        .where(Price.auction_house.isnot(None))
        .group_by(Price.auction_house)
        .order_by(func.count(Price.id).desc())
    )

    houses = []
    for row in result:
        houses.append({
            "auction_house": row.auction_house.value if row.auction_house else "unknown",
            "display_name": row.auction_house.value.replace("_", " ").title() if row.auction_house else "Unknown",
            "total_prices": row.total_prices,
            "unique_bottles": row.unique_bottles,
            "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
            "min_price_usd": round(float(row.min_price), 2) if row.min_price else None,
            "max_price_usd": round(float(row.max_price), 2) if row.max_price else None,
            "total_value_usd": round(float(row.total_value), 2) if row.total_value else None,
            "date_range": {
                "first": row.first_price.isoformat() if row.first_price else None,
                "last": row.last_price.isoformat() if row.last_price else None,
            },
        })

    return success_response(data={"auction_houses": houses})


@router.get("/search")
async def global_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """
    Global search across bottles with price context.

    Returns bottles matching the query with their price statistics.
    """
    search_term = f"%{q.lower()}%"

    result = await db.execute(
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            Bottle.age_statement,
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price"),
            func.max(Price.transaction_date).label("last_sale"),
        )
        .join(Price, Price.bottle_id == Bottle.id, isouter=True)
        .where(
            func.lower(Bottle.name).like(search_term)
            | func.lower(Bottle.distillery).like(search_term)
        )
        .group_by(Bottle.id)
        .order_by(func.count(Price.id).desc(), Bottle.name)
        .limit(limit)
    )

    bottles = []
    for row in result:
        bottles.append({
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "distillery": row.distillery,
            "age_statement": row.age_statement,
            "price_count": row.price_count or 0,
            "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
            "last_sale": row.last_sale.isoformat() if row.last_sale else None,
        })

    return success_response(
        data={"results": bottles},
        meta={"query": q, "count": len(bottles)},
    )
