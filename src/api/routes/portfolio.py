"""
Portfolio valuation endpoints.

Provides detailed portfolio analysis and valuation for user collections.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.response import success_response
from src.db.session import get_db
from src.models.bottle import Bottle, SpiritCategory
from src.models.collection import Collection, CollectionItem
from src.models.price import Price
from src.models.user import User

router = APIRouter()


@router.get("/summary")
async def get_portfolio_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get comprehensive portfolio summary.

    Returns:
    - Total portfolio value (based on current market prices)
    - Total cost basis (what you paid)
    - Overall gain/loss
    - Number of unique bottles and total quantity
    """
    user_id = current_user.id

    # Get all collection items with current market prices
    price_subq = (
        select(
            Price.bottle_id,
            func.avg(Price.price_usd).label("avg_price"),
            func.count(Price.id).label("price_count"),
            func.max(Price.transaction_date).label("last_sale"),
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    result = await db.execute(
        select(
            func.count(CollectionItem.id).label("unique_items"),
            func.sum(CollectionItem.quantity).label("total_bottles"),
            func.sum(CollectionItem.purchase_price * CollectionItem.quantity).label("total_cost"),
            func.sum(
                func.coalesce(price_subq.c.avg_price, CollectionItem.purchase_price, 0)
                * CollectionItem.quantity
            ).label("market_value"),
        )
        .select_from(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .join(price_subq, price_subq.c.bottle_id == CollectionItem.bottle_id, isouter=True)
        .where(Collection.user_id == user_id)
    )
    row = result.fetchone()

    total_cost = float(row.total_cost or 0)
    market_value = float(row.market_value or 0)
    gain_loss = market_value - total_cost
    gain_loss_pct = (gain_loss / total_cost * 100) if total_cost > 0 else 0

    return success_response(
        data={
            "unique_items": row.unique_items or 0,
            "total_bottles": int(row.total_bottles or 0),
            "total_cost_usd": round(total_cost, 2),
            "market_value_usd": round(market_value, 2),
            "gain_loss_usd": round(gain_loss, 2),
            "gain_loss_pct": round(gain_loss_pct, 2),
            "is_profitable": gain_loss > 0,
        }
    )


@router.get("/by-category")
async def get_portfolio_by_category(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get portfolio breakdown by spirit category.

    Shows value distribution across different categories.
    """
    user_id = current_user.id

    price_subq = (
        select(
            Price.bottle_id,
            func.avg(Price.price_usd).label("avg_price"),
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Bottle.category,
            func.count(CollectionItem.id).label("item_count"),
            func.sum(CollectionItem.quantity).label("bottle_count"),
            func.sum(CollectionItem.purchase_price * CollectionItem.quantity).label("cost"),
            func.sum(
                func.coalesce(price_subq.c.avg_price, CollectionItem.purchase_price, 0)
                * CollectionItem.quantity
            ).label("value"),
        )
        .select_from(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .join(Bottle, CollectionItem.bottle_id == Bottle.id)
        .join(price_subq, price_subq.c.bottle_id == CollectionItem.bottle_id, isouter=True)
        .where(Collection.user_id == user_id)
        .group_by(Bottle.category)
        .order_by(func.sum(
            func.coalesce(price_subq.c.avg_price, CollectionItem.purchase_price, 0)
            * CollectionItem.quantity
        ).desc())
    )
    rows = result.fetchall()

    total_value = sum(float(r.value or 0) for r in rows)

    categories = []
    for row in rows:
        cost = float(row.cost or 0)
        value = float(row.value or 0)
        gain_loss = value - cost

        categories.append({
            "category": row.category.value if row.category else "unknown",
            "item_count": row.item_count,
            "bottle_count": int(row.bottle_count or 0),
            "cost_usd": round(cost, 2),
            "value_usd": round(value, 2),
            "gain_loss_usd": round(gain_loss, 2),
            "portfolio_pct": round(value / total_value * 100, 1) if total_value > 0 else 0,
        })

    return success_response(
        data={
            "total_value_usd": round(total_value, 2),
            "categories": categories,
        },
        meta={"category_count": len(categories)},
    )


@router.get("/top-performers")
async def get_top_performers(
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get top performing bottles in portfolio.

    Returns bottles with highest ROI (return on investment).
    """
    user_id = current_user.id

    price_subq = (
        select(
            Price.bottle_id,
            func.avg(Price.price_usd).label("avg_price"),
            func.count(Price.id).label("price_count"),
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    result = await db.execute(
        select(
            CollectionItem.id,
            CollectionItem.quantity,
            CollectionItem.purchase_price,
            CollectionItem.purchase_date,
            Bottle.id.label("bottle_id"),
            Bottle.name,
            Bottle.category,
            price_subq.c.avg_price.label("current_price"),
            price_subq.c.price_count,
        )
        .select_from(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .join(Bottle, CollectionItem.bottle_id == Bottle.id)
        .join(price_subq, price_subq.c.bottle_id == CollectionItem.bottle_id)
        .where(
            Collection.user_id == user_id,
            CollectionItem.purchase_price.isnot(None),
            CollectionItem.purchase_price > 0,
            price_subq.c.avg_price.isnot(None),
        )
        .order_by(
            ((price_subq.c.avg_price - CollectionItem.purchase_price) / CollectionItem.purchase_price).desc()
        )
        .limit(limit)
    )
    rows = result.fetchall()

    gainers = []
    for row in rows:
        purchase = float(row.purchase_price)
        current = float(row.current_price)
        gain = current - purchase
        roi = (gain / purchase * 100) if purchase > 0 else 0

        gainers.append({
            "item_id": row.id,
            "bottle_id": row.bottle_id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "quantity": row.quantity,
            "purchase_price_usd": round(purchase, 2),
            "current_price_usd": round(current, 2),
            "gain_loss_usd": round(gain, 2),
            "roi_pct": round(roi, 1),
            "purchase_date": row.purchase_date.isoformat() if row.purchase_date else None,
            "price_data_points": row.price_count,
        })

    return success_response(
        data={"top_gainers": gainers},
        meta={"count": len(gainers)},
    )


@router.get("/underperformers")
async def get_underperformers(
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get underperforming bottles in portfolio.

    Returns bottles with lowest/negative ROI.
    """
    user_id = current_user.id

    price_subq = (
        select(
            Price.bottle_id,
            func.avg(Price.price_usd).label("avg_price"),
            func.count(Price.id).label("price_count"),
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    result = await db.execute(
        select(
            CollectionItem.id,
            CollectionItem.quantity,
            CollectionItem.purchase_price,
            CollectionItem.purchase_date,
            Bottle.id.label("bottle_id"),
            Bottle.name,
            Bottle.category,
            price_subq.c.avg_price.label("current_price"),
            price_subq.c.price_count,
        )
        .select_from(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .join(Bottle, CollectionItem.bottle_id == Bottle.id)
        .join(price_subq, price_subq.c.bottle_id == CollectionItem.bottle_id)
        .where(
            Collection.user_id == user_id,
            CollectionItem.purchase_price.isnot(None),
            CollectionItem.purchase_price > 0,
            price_subq.c.avg_price.isnot(None),
        )
        .order_by(
            ((price_subq.c.avg_price - CollectionItem.purchase_price) / CollectionItem.purchase_price).asc()
        )
        .limit(limit)
    )
    rows = result.fetchall()

    losers = []
    for row in rows:
        purchase = float(row.purchase_price)
        current = float(row.current_price)
        loss = current - purchase
        roi = (loss / purchase * 100) if purchase > 0 else 0

        losers.append({
            "item_id": row.id,
            "bottle_id": row.bottle_id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "quantity": row.quantity,
            "purchase_price_usd": round(purchase, 2),
            "current_price_usd": round(current, 2),
            "gain_loss_usd": round(loss, 2),
            "roi_pct": round(roi, 1),
            "purchase_date": row.purchase_date.isoformat() if row.purchase_date else None,
            "price_data_points": row.price_count,
        })

    return success_response(
        data={"underperformers": losers},
        meta={"count": len(losers)},
    )


@router.get("/recent-activity")
async def get_portfolio_activity(
    days: int = Query(30, ge=7, le=90, description="Days of activity"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get recent market activity for portfolio bottles.

    Shows which portfolio bottles have recent sales/prices.
    """
    user_id = current_user.id
    cutoff = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            func.count(Price.id).label("recent_sales"),
            func.avg(Price.price_usd).label("avg_price"),
            func.min(Price.price_usd).label("min_price"),
            func.max(Price.price_usd).label("max_price"),
            func.max(Price.transaction_date).label("last_sale"),
        )
        .select_from(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .join(Bottle, CollectionItem.bottle_id == Bottle.id)
        .join(Price, Price.bottle_id == Bottle.id)
        .where(
            Collection.user_id == user_id,
            Price.transaction_date >= cutoff,
        )
        .group_by(Bottle.id)
        .having(func.count(Price.id) > 0)
        .order_by(func.count(Price.id).desc())
        .limit(20)
    )
    rows = result.fetchall()

    activity = [
        {
            "bottle_id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "recent_sales": row.recent_sales,
            "avg_price_usd": round(float(row.avg_price), 2) if row.avg_price else None,
            "price_range": {
                "min": round(float(row.min_price), 2) if row.min_price else None,
                "max": round(float(row.max_price), 2) if row.max_price else None,
            },
            "last_sale": row.last_sale.isoformat() if row.last_sale else None,
        }
        for row in rows
    ]

    return success_response(
        data={
            "period_days": days,
            "bottles_with_activity": activity,
        },
        meta={"count": len(activity)},
    )


@router.get("/valuation-details")
async def get_valuation_details(
    collection_id: int | None = Query(None, description="Filter by collection ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed valuation for all portfolio items.

    Includes purchase price, current market value, and confidence score.
    """
    user_id = current_user.id

    price_subq = (
        select(
            Price.bottle_id,
            func.avg(Price.price_usd).label("avg_price"),
            func.count(Price.id).label("price_count"),
            func.stddev(Price.price_usd).label("price_stddev"),
            func.max(Price.transaction_date).label("last_sale"),
        )
        .group_by(Price.bottle_id)
        .subquery()
    )

    query = (
        select(
            CollectionItem.id,
            CollectionItem.quantity,
            CollectionItem.purchase_price,
            CollectionItem.purchase_date,
            CollectionItem.notes,
            Collection.id.label("collection_id"),
            Collection.name.label("collection_name"),
            Bottle.id.label("bottle_id"),
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            price_subq.c.avg_price,
            price_subq.c.price_count,
            price_subq.c.price_stddev,
            price_subq.c.last_sale,
        )
        .select_from(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .join(Bottle, CollectionItem.bottle_id == Bottle.id)
        .join(price_subq, price_subq.c.bottle_id == CollectionItem.bottle_id, isouter=True)
        .where(Collection.user_id == user_id)
        .order_by(Collection.name, Bottle.name)
    )

    if collection_id:
        query = query.where(Collection.id == collection_id)

    result = await db.execute(query)
    rows = result.fetchall()

    items = []
    total_cost = 0
    total_value = 0

    for row in rows:
        purchase = float(row.purchase_price) if row.purchase_price else None
        current = float(row.avg_price) if row.avg_price else None
        quantity = row.quantity or 1

        # Calculate confidence score based on price data
        confidence = "low"
        if row.price_count and row.price_count >= 10:
            confidence = "high"
        elif row.price_count and row.price_count >= 3:
            confidence = "medium"

        item_cost = (purchase * quantity) if purchase else 0
        item_value = (current * quantity) if current else item_cost
        gain_loss = item_value - item_cost if item_cost > 0 else None

        total_cost += item_cost
        total_value += item_value

        items.append({
            "item_id": row.id,
            "collection_id": row.collection_id,
            "collection_name": row.collection_name,
            "bottle_id": row.bottle_id,
            "name": row.name,
            "category": row.category.value if row.category else None,
            "distillery": row.distillery,
            "quantity": quantity,
            "purchase_price_usd": round(purchase, 2) if purchase else None,
            "current_price_usd": round(current, 2) if current else None,
            "total_cost_usd": round(item_cost, 2),
            "total_value_usd": round(item_value, 2),
            "gain_loss_usd": round(gain_loss, 2) if gain_loss is not None else None,
            "price_data_points": row.price_count or 0,
            "valuation_confidence": confidence,
            "last_market_sale": row.last_sale.isoformat() if row.last_sale else None,
            "purchase_date": row.purchase_date.isoformat() if row.purchase_date else None,
            "notes": row.notes,
        })

    return success_response(
        data={
            "items": items,
            "totals": {
                "total_cost_usd": round(total_cost, 2),
                "total_value_usd": round(total_value, 2),
                "total_gain_loss_usd": round(total_value - total_cost, 2),
            },
        },
        meta={"count": len(items)},
    )
