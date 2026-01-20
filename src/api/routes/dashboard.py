"""
User dashboard endpoint.

Provides personalized stats and activity for authenticated users.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.response import success_response
from src.db.session import get_db
from src.models.alert import AlertStatus, PriceAlert
from src.models.bottle import Bottle
from src.models.collection import Collection, CollectionItem
from src.models.price import Price
from src.models.submission import Submission
from src.models.user import User

router = APIRouter()


@router.get("")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get personalized dashboard data for the current user.

    Returns:
    - User stats (submissions, trust score)
    - Collection summary with valuations
    - Active alerts
    - Recent activity
    - Watchlist bottles with price changes
    """
    user_id = current_user.id

    # User stats
    user_stats = {
        "display_name": current_user.display_name,
        "trust_score": current_user.trust_score,
        "total_submissions": current_user.total_submissions,
        "approved_submissions": current_user.approved_submissions,
        "member_since": current_user.created_at.isoformat(),
    }

    # Collections summary
    collections_result = await db.execute(
        select(
            func.count(Collection.id).label("collection_count"),
        ).where(Collection.user_id == user_id)
    )
    collection_count = collections_result.scalar() or 0

    # Collection items count and value
    items_result = await db.execute(
        select(
            func.count(CollectionItem.id).label("item_count"),
            func.sum(CollectionItem.quantity).label("total_bottles"),
            func.sum(CollectionItem.purchase_price * CollectionItem.quantity).label("total_cost"),
        )
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user_id)
    )
    items_row = items_result.fetchone()

    # Get current market value of collection
    value_result = await db.execute(
        select(
            func.sum(
                func.coalesce(
                    select(func.avg(Price.price_usd))
                    .where(Price.bottle_id == CollectionItem.bottle_id)
                    .correlate(CollectionItem)
                    .scalar_subquery(),
                    0
                ) * CollectionItem.quantity
            ).label("market_value")
        )
        .select_from(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user_id)
    )
    market_value = value_result.scalar() or 0

    collection_stats = {
        "collection_count": collection_count,
        "total_items": items_row.item_count or 0 if items_row else 0,
        "total_bottles": int(items_row.total_bottles or 0) if items_row else 0,
        "total_cost": round(float(items_row.total_cost or 0), 2) if items_row else 0,
        "market_value": round(float(market_value), 2),
        "gain_loss": round(float(market_value) - float(items_row.total_cost or 0), 2) if items_row and items_row.total_cost else 0,
    }

    # Active alerts
    alerts_result = await db.execute(
        select(
            PriceAlert.id,
            PriceAlert.alert_type,
            PriceAlert.target_price,
            PriceAlert.status,
            PriceAlert.times_triggered,
            Bottle.id.label("bottle_id"),
            Bottle.name.label("bottle_name"),
        )
        .join(Bottle, PriceAlert.bottle_id == Bottle.id)
        .where(
            PriceAlert.user_id == user_id,
            PriceAlert.status == AlertStatus.ACTIVE,
        )
        .order_by(PriceAlert.created_at.desc())
        .limit(10)
    )

    active_alerts = [
        {
            "id": row.id,
            "bottle_id": row.bottle_id,
            "bottle_name": row.bottle_name,
            "alert_type": row.alert_type.value,
            "target_price": float(row.target_price) if row.target_price else None,
            "times_triggered": row.times_triggered,
        }
        for row in alerts_result
    ]

    # Alert counts
    alert_counts = await db.execute(
        select(
            func.count(PriceAlert.id).filter(PriceAlert.status == AlertStatus.ACTIVE).label("active"),
            func.count(PriceAlert.id).filter(PriceAlert.status == AlertStatus.TRIGGERED).label("triggered"),
            func.count(PriceAlert.id).filter(PriceAlert.status == AlertStatus.PAUSED).label("paused"),
        ).where(PriceAlert.user_id == user_id)
    )
    alert_count_row = alert_counts.fetchone()

    alert_stats = {
        "active": alert_count_row.active or 0,
        "triggered": alert_count_row.triggered or 0,
        "paused": alert_count_row.paused or 0,
    }

    # Recent submissions
    submissions_result = await db.execute(
        select(
            Submission.id,
            Submission.status,
            Submission.submitted_price,
            Submission.created_at,
            Bottle.name.label("bottle_name"),
        )
        .join(Bottle, Submission.bottle_id == Bottle.id, isouter=True)
        .where(Submission.user_id == user_id)
        .order_by(Submission.created_at.desc())
        .limit(5)
    )

    recent_submissions = [
        {
            "id": row.id,
            "bottle_name": row.bottle_name or "Unknown",
            "price": float(row.submitted_price) if row.submitted_price else None,
            "status": row.status.value if row.status else None,
            "date": row.created_at.isoformat() if row.created_at else None,
        }
        for row in submissions_result
    ]

    # Watchlist (bottles from collections with recent price changes)
    week_ago = datetime.utcnow() - timedelta(days=7)
    watchlist_result = await db.execute(
        select(
            Bottle.id,
            Bottle.name,
            func.avg(Price.price_usd).label("avg_price"),
            func.count(Price.id).filter(Price.created_at >= week_ago).label("recent_sales"),
        )
        .join(CollectionItem, CollectionItem.bottle_id == Bottle.id)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .join(Price, Price.bottle_id == Bottle.id, isouter=True)
        .where(Collection.user_id == user_id)
        .group_by(Bottle.id)
        .having(func.count(Price.id).filter(Price.created_at >= week_ago) > 0)
        .order_by(func.count(Price.id).filter(Price.created_at >= week_ago).desc())
        .limit(5)
    )

    watchlist_activity = [
        {
            "bottle_id": row.id,
            "name": row.name,
            "avg_price": round(float(row.avg_price), 2) if row.avg_price else None,
            "recent_sales": row.recent_sales,
        }
        for row in watchlist_result
    ]

    return success_response(
        data={
            "user": user_stats,
            "collections": collection_stats,
            "alerts": {
                "counts": alert_stats,
                "active_alerts": active_alerts,
            },
            "recent_submissions": recent_submissions,
            "watchlist_activity": watchlist_activity,
        }
    )


@router.get("/activity")
async def get_user_activity(
    days: int = Query(30, ge=7, le=90, description="Days of activity"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed user activity over time.
    """
    user_id = current_user.id
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Submissions over time
    submissions_result = await db.execute(
        select(
            func.date(Submission.created_at).label("date"),
            func.count(Submission.id).label("count"),
        )
        .where(
            Submission.user_id == user_id,
            Submission.created_at >= cutoff,
        )
        .group_by(func.date(Submission.created_at))
        .order_by(func.date(Submission.created_at))
    )

    submissions_by_date = [
        {"date": str(row.date), "count": row.count}
        for row in submissions_result
    ]

    # Alerts triggered over time
    alerts_result = await db.execute(
        select(
            func.date(PriceAlert.last_triggered_at).label("date"),
            func.count(PriceAlert.id).label("count"),
        )
        .where(
            PriceAlert.user_id == user_id,
            PriceAlert.last_triggered_at >= cutoff,
        )
        .group_by(func.date(PriceAlert.last_triggered_at))
        .order_by(func.date(PriceAlert.last_triggered_at))
    )

    alerts_by_date = [
        {"date": str(row.date), "count": row.count}
        for row in alerts_result
    ]

    return success_response(
        data={
            "period_days": days,
            "submissions_by_date": submissions_by_date,
            "alerts_triggered_by_date": alerts_by_date,
        }
    )
