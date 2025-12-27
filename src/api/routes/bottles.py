"""
Bottle search and detail endpoints.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.models.bottle import Bottle, BottleAlias, BottleSize, SpiritCategory

router = APIRouter()


# =============================================================================
# Response Schemas
# =============================================================================


class BottleListItem(BaseModel):
    """Bottle in search results."""
    id: int
    name: str
    distillery: str | None
    category: SpiritCategory
    age_statement: int | None
    release_year: int | None
    avg_price: float | None
    price_count: int
    price_trend: float | None
    confidence_score: float | None

    class Config:
        from_attributes = True


class BottleDetail(BaseModel):
    """Full bottle details."""
    id: int
    name: str
    normalized_name: str
    distillery: str | None
    brand: str | None
    category: SpiritCategory
    age_statement: int | None
    proof: float | None
    size: BottleSize
    size_ml: int | None
    release_year: int | None
    batch_number: str | None
    is_limited_release: bool
    is_allocated: bool
    msrp: float | None
    description: str | None
    tasting_notes: str | None

    # Statistics
    price_count: int
    avg_price: float | None
    min_price: float | None
    max_price: float | None
    last_price: float | None
    last_price_date: datetime | None
    price_trend: float | None
    confidence_score: float | None

    # Aliases
    aliases: list[str]

    class Config:
        from_attributes = True


class PaginatedBottles(BaseModel):
    """Paginated bottle list."""
    items: list[BottleListItem]
    total: int
    page: int
    page_size: int
    pages: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=PaginatedBottles)
async def search_bottles(
    q: str | None = Query(None, description="Search query"),
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    distillery: str | None = Query(None, description="Filter by distillery"),
    min_price: float | None = Query(None, ge=0, description="Minimum average price"),
    max_price: float | None = Query(None, ge=0, description="Maximum average price"),
    sort: Literal["name", "price", "trend", "recent"] = Query("name", description="Sort by"),
    order: Literal["asc", "desc"] = Query("asc", description="Sort order"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search and browse bottles.

    - Free text search matches name, distillery, and aliases
    - Filter by category, distillery, price range
    - Sort by name, price, trend, or recency
    """
    # Build base query
    query = select(Bottle).where(Bottle.is_active == True)

    # Text search
    if q:
        search_term = f"%{q}%"
        # Include alias search via subquery
        alias_bottle_ids = (
            select(BottleAlias.bottle_id)
            .where(BottleAlias.alias.ilike(search_term))
            .scalar_subquery()
        )
        query = query.where(
            or_(
                Bottle.name.ilike(search_term),
                Bottle.distillery.ilike(search_term),
                Bottle.brand.ilike(search_term),
                Bottle.id.in_(alias_bottle_ids),
            )
        )

    # Filters
    if category:
        query = query.where(Bottle.category == category)
    if distillery:
        query = query.where(Bottle.distillery.ilike(f"%{distillery}%"))
    if min_price is not None:
        query = query.where(Bottle.avg_price >= min_price)
    if max_price is not None:
        query = query.where(Bottle.avg_price <= max_price)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Sorting
    sort_column = {
        "name": Bottle.name,
        "price": Bottle.avg_price,
        "trend": Bottle.price_trend,
        "recent": Bottle.last_price_date,
    }.get(sort, Bottle.name)

    if order == "desc":
        query = query.order_by(sort_column.desc().nullslast())
    else:
        query = query.order_by(sort_column.asc().nullsfirst())

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    bottles = result.scalars().all()

    return PaginatedBottles(
        items=[BottleListItem.model_validate(b) for b in bottles],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/{bottle_id}", response_model=BottleDetail)
async def get_bottle(bottle_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get full details for a specific bottle.
    """
    query = (
        select(Bottle)
        .options(selectinload(Bottle.aliases))
        .where(Bottle.id == bottle_id, Bottle.is_active == True)
    )
    result = await db.execute(query)
    bottle = result.scalar_one_or_none()

    if not bottle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Convert to response with aliases
    response_data = {
        **{k: getattr(bottle, k) for k in BottleDetail.model_fields if k != "aliases"},
        "aliases": [a.alias for a in bottle.aliases],
    }

    return BottleDetail(**response_data)
