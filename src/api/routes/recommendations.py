"""
Bottle recommendation endpoints.

Provides similar bottles and personalized recommendations.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.db.session import get_db
from src.models.bottle import Bottle, SpiritCategory
from src.models.price import Price

router = APIRouter()


@router.get("/similar/{bottle_id}")
async def get_similar_bottles(
    bottle_id: int,
    limit: int = Query(10, ge=1, le=20, description="Number of recommendations"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get bottles similar to the specified bottle.

    Similarity is based on:
    - Same category
    - Similar price range (within 30%)
    - Similar age statement (if available)
    - Same distillery (if available)

    Returns bottles ranked by similarity score.
    """
    # Get the target bottle
    target = await db.get(Bottle, bottle_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Get target's average price
    target_price_result = await db.execute(
        select(func.avg(Price.price_usd)).where(Price.bottle_id == bottle_id)
    )
    target_avg_price = target_price_result.scalar() or 0

    # Price range for similarity (30% above and below)
    price_low = float(target_avg_price) * 0.7 if target_avg_price else 0
    price_high = float(target_avg_price) * 1.3 if target_avg_price else 10000

    # Build query for similar bottles
    # Subquery for average price per bottle
    price_subq = (
        select(
            Price.bottle_id,
            func.avg(Price.price_usd).label("avg_price"),
            func.count(Price.id).label("price_count"),
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    query = (
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            Bottle.age_statement,
            price_subq.c.avg_price,
            price_subq.c.price_count,
        )
        .join(price_subq, price_subq.c.bottle_id == Bottle.id)
        .where(Bottle.id != bottle_id)  # Exclude the target bottle
        .where(price_subq.c.price_count >= 1)  # Must have at least 1 price
    )

    # Calculate similarity factors
    similarity_conditions = []
    order_factors = []

    # Same category is important
    if target.category:
        query = query.where(Bottle.category == target.category)

    # Similar price range
    if target_avg_price and target_avg_price > 0:
        query = query.where(
            price_subq.c.avg_price.between(price_low, price_high)
        )
        # Order by price proximity
        price_diff = func.abs(price_subq.c.avg_price - target_avg_price)
        order_factors.append(price_diff)

    # Same distillery gets priority
    if target.distillery:
        query = query.order_by(
            (Bottle.distillery == target.distillery).desc(),
        )

    # Similar age statement
    if target.age_statement:
        age_low = max(0, target.age_statement - 5)
        age_high = target.age_statement + 5
        query = query.order_by(
            and_(
                Bottle.age_statement.isnot(None),
                Bottle.age_statement.between(age_low, age_high)
            ).desc(),
        )

    # Order by price proximity and price count (more data = more reliable)
    query = query.order_by(
        func.abs(price_subq.c.avg_price - target_avg_price) if target_avg_price else price_subq.c.avg_price,
        price_subq.c.price_count.desc(),
    ).limit(limit)

    result = await db.execute(query)
    rows = result.fetchall()

    similar_bottles = []
    for row in rows:
        # Calculate simple similarity score
        score = 100  # Start with base score

        # Price similarity (max 30 points)
        if target_avg_price and row.avg_price:
            price_diff_pct = abs(float(row.avg_price) - float(target_avg_price)) / float(target_avg_price) * 100
            price_score = max(0, 30 - price_diff_pct)
            score += price_score

        # Same distillery (20 points)
        if target.distillery and row.distillery == target.distillery:
            score += 20

        # Similar age (15 points)
        if target.age_statement and row.age_statement:
            age_diff = abs(target.age_statement - row.age_statement)
            if age_diff <= 2:
                score += 15
            elif age_diff <= 5:
                score += 10

        # More price data (5 points)
        if row.price_count >= 5:
            score += 5

        similar_bottles.append({
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "distillery": row.distillery,
            "age_statement": row.age_statement,
            "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
            "price_count": row.price_count,
            "similarity_score": round(score, 1),
        })

    # Sort by similarity score
    similar_bottles.sort(key=lambda x: x["similarity_score"], reverse=True)

    return success_response(
        data={
            "target_bottle": {
                "id": target.id,
                "name": target.name,
                "category": target.category.value if target.category else None,
                "distillery": target.distillery,
                "age_statement": target.age_statement,
                "avg_price_usd": round(float(target_avg_price), 2) if target_avg_price else None,
            },
            "similar_bottles": similar_bottles,
        },
        meta={"count": len(similar_bottles)},
    )


@router.get("/price-alternatives/{bottle_id}")
async def get_price_alternatives(
    bottle_id: int,
    budget_pct: int = Query(50, ge=10, le=90, description="Budget as percentage of target price"),
    limit: int = Query(10, ge=1, le=20, description="Number of results"),
    db: AsyncSession = Depends(get_db),
):
    """
    Find similar bottles at a lower price point.

    Good for finding budget-friendly alternatives.
    """
    # Get target bottle and price
    target = await db.get(Bottle, bottle_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    target_price_result = await db.execute(
        select(func.avg(Price.price_usd)).where(Price.bottle_id == bottle_id)
    )
    target_avg_price = target_price_result.scalar()

    if not target_avg_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target bottle has no price data",
        )

    # Calculate budget
    budget = float(target_avg_price) * (budget_pct / 100)

    # Find alternatives in same category under budget
    price_subq = (
        select(
            Price.bottle_id,
            func.avg(Price.price_usd).label("avg_price"),
            func.count(Price.id).label("price_count"),
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    query = (
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            Bottle.age_statement,
            price_subq.c.avg_price,
            price_subq.c.price_count,
        )
        .join(price_subq, price_subq.c.bottle_id == Bottle.id)
        .where(
            Bottle.id != bottle_id,
            Bottle.category == target.category,
            price_subq.c.avg_price <= budget,
            price_subq.c.price_count >= 2,
        )
        .order_by(
            price_subq.c.avg_price.desc(),  # Get the best within budget
            price_subq.c.price_count.desc(),
        )
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.fetchall()

    alternatives = [
        {
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "distillery": row.distillery,
            "age_statement": row.age_statement,
            "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
            "price_count": row.price_count,
            "savings_usd": round(float(target_avg_price) - float(row.avg_price), 2),
            "savings_pct": round((1 - float(row.avg_price) / float(target_avg_price)) * 100, 1),
        }
        for row in rows
    ]

    return success_response(
        data={
            "target_bottle": {
                "id": target.id,
                "name": target.name,
                "avg_price_usd": round(float(target_avg_price), 2),
            },
            "budget_usd": round(budget, 2),
            "alternatives": alternatives,
        },
        meta={"count": len(alternatives)},
    )


@router.get("/trending-in-category/{category}")
async def get_trending_in_category(
    category: SpiritCategory,
    days: int = Query(30, ge=7, le=90, description="Days to analyze"),
    limit: int = Query(10, ge=1, le=20, description="Number of results"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get trending bottles in a specific category.

    Trending = high recent sales volume + price movement.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Find bottles with recent activity
    query = (
        select(
            Bottle.id,
            Bottle.name,
            Bottle.distillery,
            Bottle.age_statement,
            func.count(Price.id).label("recent_sales"),
            func.avg(Price.price_usd).label("avg_price"),
            func.min(Price.price_usd).label("min_price"),
            func.max(Price.price_usd).label("max_price"),
        )
        .join(Price, Price.bottle_id == Bottle.id)
        .where(
            Bottle.category == category,
            Price.transaction_date >= cutoff,
        )
        .group_by(Bottle.id)
        .having(func.count(Price.id) >= 2)
        .order_by(func.count(Price.id).desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.fetchall()

    trending = [
        {
            "id": row.id,
            "name": row.name,
            "distillery": row.distillery,
            "age_statement": row.age_statement,
            "recent_sales": row.recent_sales,
            "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
            "price_range": {
                "min": round(float(row.min_price), 2) if row.min_price else None,
                "max": round(float(row.max_price), 2) if row.max_price else None,
            },
        }
        for row in rows
    ]

    return success_response(
        data={
            "category": category.value,
            "period_days": days,
            "trending_bottles": trending,
        },
        meta={"count": len(trending)},
    )
