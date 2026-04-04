"""
Data export endpoints.

Allows users to export price data in various formats.
Rate-limited to prevent bulk scraping.
"""

import csv
import io
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.response import success_response
from src.db.session import get_db
from src.models.bottle import Bottle, SpiritCategory
from src.models.price import Price
from src.models.user import User

router = APIRouter()


@router.get("/prices/csv")
async def export_prices_csv(
    request: Request,
    bottle_id: int | None = Query(None, description="Filter by bottle ID"),
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    min_price: float | None = Query(None, ge=0, description="Minimum price USD"),
    max_price: float | None = Query(None, ge=0, description="Maximum price USD"),
    days: int = Query(365, ge=1, le=1825, description="Days of history"),
    db: AsyncSession = Depends(get_db),
):
    """Export price data as CSV."""
    # Rate limit: 5 exports per hour per IP
    from src.main import limiter
    await limiter.check("5/hour", request)

    # Build query
    query = (
        select(
            Price.id,
            Price.transaction_date,
            Bottle.name.label("bottle_name"),
            Bottle.category,
            Bottle.distillery,
            Price.price,
            Price.currency,
            Price.price_usd,
            Price.source,
            Price.source_name,
            Price.auction_house,
            Price.is_sold,
            Price.source_url,
        )
        .join(Bottle, Price.bottle_id == Bottle.id)
        .order_by(Price.transaction_date.desc())
    )

    # Apply filters
    if bottle_id:
        query = query.where(Price.bottle_id == bottle_id)
    if category:
        query = query.where(Bottle.category == category)
    if min_price is not None:
        query = query.where(Price.price_usd >= min_price)
    if max_price is not None:
        query = query.where(Price.price_usd <= max_price)

    # Date filter
    cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)
    query = query.where(Price.transaction_date >= cutoff)

    # Limit to prevent huge exports
    query = query.limit(10000)

    result = await db.execute(query)
    rows = result.fetchall()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Price ID", "Date", "Bottle Name", "Category", "Distillery",
        "Price", "Currency", "Price USD", "Source", "Source Name",
        "Auction House", "Sold", "URL",
    ])

    for row in rows:
        writer.writerow([
            row.id,
            row.transaction_date.strftime("%Y-%m-%d") if row.transaction_date else "",
            row.bottle_name,
            row.category.value if row.category else "",
            row.distillery or "",
            float(row.price) if row.price else "",
            row.currency,
            float(row.price_usd) if row.price_usd else "",
            row.source.value if row.source else "",
            row.source_name or "",
            row.auction_house.value if row.auction_house else "",
            "Yes" if row.is_sold else "No",
            row.source_url or "",
        ])

    output.seek(0)
    filename = f"wtracker_prices_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/prices/json")
async def export_prices_json(
    request: Request,
    bottle_id: int | None = Query(None, description="Filter by bottle ID"),
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    min_price: float | None = Query(None, ge=0, description="Minimum price USD"),
    max_price: float | None = Query(None, ge=0, description="Maximum price USD"),
    days: int = Query(365, ge=1, le=1825, description="Days of history"),
    db: AsyncSession = Depends(get_db),
):
    """Export price data as JSON."""
    from src.main import limiter
    await limiter.check("5/hour", request)

    query = (
        select(
            Price.id,
            Price.transaction_date,
            Price.bottle_id,
            Bottle.name.label("bottle_name"),
            Bottle.category,
            Bottle.distillery,
            Price.price,
            Price.currency,
            Price.price_usd,
            Price.source,
            Price.source_name,
            Price.auction_house,
            Price.is_sold,
            Price.source_url,
        )
        .join(Bottle, Price.bottle_id == Bottle.id)
        .order_by(Price.transaction_date.desc())
    )

    if bottle_id:
        query = query.where(Price.bottle_id == bottle_id)
    if category:
        query = query.where(Bottle.category == category)
    if min_price is not None:
        query = query.where(Price.price_usd >= min_price)
    if max_price is not None:
        query = query.where(Price.price_usd <= max_price)

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = query.where(Price.transaction_date >= cutoff)
    query = query.limit(10000)

    result = await db.execute(query)
    rows = result.fetchall()

    data = {
        "exported_at": datetime.utcnow().isoformat(),
        "filters": {
            "bottle_id": bottle_id,
            "category": category.value if category else None,
            "min_price": min_price,
            "max_price": max_price,
            "days": days,
        },
        "count": len(rows),
        "prices": [
            {
                "id": row.id,
                "date": row.transaction_date.isoformat() if row.transaction_date else None,
                "bottle_id": row.bottle_id,
                "bottle_name": row.bottle_name,
                "category": row.category.value if row.category else None,
                "distillery": row.distillery,
                "price": float(row.price) if row.price else None,
                "currency": row.currency,
                "price_usd": float(row.price_usd) if row.price_usd else None,
                "source": row.source.value if row.source else None,
                "source_name": row.source_name,
                "auction_house": row.auction_house.value if row.auction_house else None,
                "sold": row.is_sold,
                "url": row.source_url,
            }
            for row in rows
        ],
    }

    filename = f"wtracker_prices_{datetime.utcnow().strftime('%Y%m%d')}.json"

    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/bottles/csv")
async def export_bottles_csv(
    request: Request,
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    has_prices: bool = Query(True, description="Only bottles with prices"),
    db: AsyncSession = Depends(get_db),
):
    """Export bottle catalog as CSV with price statistics."""
    from src.main import limiter
    await limiter.check("5/hour", request)

    query = (
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            Bottle.age_statement,
            Bottle.size_ml,
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price"),
            func.min(Price.price_usd).label("min_price"),
            func.max(Price.price_usd).label("max_price"),
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

    query = query.limit(5000)

    result = await db.execute(query)
    rows = result.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Bottle ID", "Name", "Category", "Distillery", "Age",
        "Size (ml)", "Price Count", "Avg Price USD", "Min Price USD",
        "Max Price USD", "Last Sale",
    ])

    for row in rows:
        writer.writerow([
            row.id,
            row.name,
            row.category.value if row.category else "",
            row.distillery or "",
            row.age_statement or "",
            row.size_ml or "",
            row.price_count or 0,
            round(float(row.avg_price), 2) if row.avg_price else "",
            round(float(row.min_price), 2) if row.min_price else "",
            round(float(row.max_price), 2) if row.max_price else "",
            row.last_sale.strftime("%Y-%m-%d") if row.last_sale else "",
        ])

    output.seek(0)
    filename = f"wtracker_bottles_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/collection/{collection_id}/csv")
async def export_collection_csv(
    collection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export a user's collection with current valuations.
    Requires authentication and ownership.
    """
    from src.models.collection import Collection, CollectionItem

    # Get collection and verify ownership
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    # Get items with valuations
    query = (
        select(
            CollectionItem.id,
            CollectionItem.quantity,
            CollectionItem.purchase_price,
            CollectionItem.purchase_date,
            CollectionItem.notes,
            Bottle.id.label("bottle_id"),
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            func.avg(Price.price_usd).label("current_value"),
            func.count(Price.id).label("price_count"),
        )
        .join(Bottle, CollectionItem.bottle_id == Bottle.id)
        .join(Price, Price.bottle_id == Bottle.id, isouter=True)
        .where(CollectionItem.collection_id == collection_id)
        .group_by(CollectionItem.id, Bottle.id)
        .order_by(Bottle.name)
    )

    result = await db.execute(query)
    rows = result.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Item ID", "Bottle ID", "Name", "Category", "Distillery",
        "Quantity", "Purchase Price", "Purchase Date",
        "Current Value (avg)", "Gain/Loss", "Price Data Points", "Notes",
    ])

    for row in rows:
        current_val = float(row.current_value) if row.current_value else None
        purchase = float(row.purchase_price) if row.purchase_price else None
        gain_loss = None
        if current_val and purchase:
            gain_loss = round(current_val - purchase, 2)

        writer.writerow([
            row.id,
            row.bottle_id,
            row.name,
            row.category.value if row.category else "",
            row.distillery or "",
            row.quantity or 1,
            purchase or "",
            row.purchase_date.strftime("%Y-%m-%d") if row.purchase_date else "",
            round(current_val, 2) if current_val else "",
            gain_loss if gain_loss is not None else "",
            row.price_count or 0,
            row.notes or "",
        ])

    output.seek(0)
    filename = f"wtracker_collection_{collection_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
