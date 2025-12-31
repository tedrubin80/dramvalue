"""
Bottle search and detail endpoints.

Uses BottleService for business logic and standardized response envelope.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import paginated_response, success_response
from src.db.session import get_db
from src.models.bottle import SpiritCategory
from src.schemas.bottle import (
    BottleAutocomplete,
    BottleDetail,
    BottleListItem,
    BottleTrending,
    CategoryStats,
    DistilleryInfo,
    HomepageData,
)
from src.services import BottleService, NotFoundError

router = APIRouter()


# =============================================================================
# Dependency
# =============================================================================


def get_bottle_service(db: AsyncSession = Depends(get_db)) -> BottleService:
    """Dependency to get BottleService instance."""
    return BottleService(db)


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
async def search_bottles(
    q: str | None = Query(None, description="Search query"),
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    distillery: str | None = Query(None, description="Filter by distillery"),
    min_price: float | None = Query(None, ge=0, description="Minimum average price"),
    max_price: float | None = Query(None, ge=0, description="Maximum average price"),
    min_age: int | None = Query(None, ge=0, description="Minimum age statement"),
    max_age: int | None = Query(None, description="Maximum age statement"),
    has_prices: bool | None = Query(None, description="Filter bottles with/without prices"),
    sort: Literal["name", "price", "trend", "recent", "popularity"] = Query(
        "name", description="Sort by field"
    ),
    order: Literal["asc", "desc"] = Query("asc", description="Sort order"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: BottleService = Depends(get_bottle_service),
):
    """
    Search and browse bottles.

    - Free text search matches name, distillery, brand, and aliases
    - Filter by category, distillery, price range, age
    - Sort by name, price, trend, recency, or popularity
    - Paginated results with metadata
    """
    bottles, total = await service.search(
        query=q,
        category=category,
        distillery=distillery,
        min_price=min_price,
        max_price=max_price,
        min_age=min_age,
        max_age=max_age,
        has_prices=has_prices,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )

    items = [BottleListItem.model_validate(b).model_dump() for b in bottles]

    return paginated_response(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        item_key="bottles",
    )


@router.get("/autocomplete")
async def autocomplete_bottles(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=20, description="Max suggestions"),
    service: BottleService = Depends(get_bottle_service),
):
    """
    Get autocomplete suggestions for bottle search.

    Returns lightweight results optimized for dropdown display.
    """
    suggestions = await service.autocomplete(q, limit=limit)

    return success_response(
        data={"suggestions": suggestions},
        meta={"query": q, "count": len(suggestions)},
    )


@router.get("/trending")
async def get_trending_bottles(
    days: int = Query(30, ge=7, le=90, description="Days to analyze"),
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
    category: SpiritCategory | None = Query(None, description="Filter by category"),
    service: BottleService = Depends(get_bottle_service),
):
    """
    Get trending bottles based on recent activity and price movement.

    Trending = high recent activity + price momentum.
    """
    bottles = await service.get_trending(
        days=days,
        limit=limit,
        category=category,
    )

    items = [BottleTrending.model_validate(b).model_dump() for b in bottles]

    return success_response(
        data={"bottles": items},
        meta={"days": days, "count": len(items)},
    )


@router.get("/homepage")
async def get_homepage_data(
    service: BottleService = Depends(get_bottle_service),
):
    """
    Get aggregated data for the homepage.

    Returns:
    - Recently updated bottles
    - Trending up/down bottles
    - Category statistics
    - Total counts
    """
    data = await service.get_homepage_data()

    return success_response(
        data={
            "recently_updated": [
                BottleListItem.model_validate(b).model_dump()
                for b in data["recently_updated"]
            ],
            "trending_up": [
                BottleTrending.model_validate(b).model_dump()
                for b in data["trending_up"]
            ],
            "trending_down": [
                BottleTrending.model_validate(b).model_dump()
                for b in data["trending_down"]
            ],
            "category_stats": data["category_stats"],
            "total_bottles": data["total_bottles"],
            "total_prices": data["total_prices"],
        }
    )


@router.get("/categories")
async def get_categories():
    """
    Get all available spirit categories.
    """
    categories = [
        {"value": cat.value, "label": cat.value.replace("_", " ").title()}
        for cat in SpiritCategory
    ]

    return success_response(data={"categories": categories})


@router.get("/distilleries")
async def get_distilleries(
    service: BottleService = Depends(get_bottle_service),
):
    """
    Get list of all distilleries with bottle counts.
    """
    distilleries = await service.get_distilleries()

    return success_response(
        data={"distilleries": distilleries},
        meta={"count": len(distilleries)},
    )


@router.get("/category/{category}")
async def get_bottles_by_category(
    category: SpiritCategory,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: BottleService = Depends(get_bottle_service),
):
    """
    Get bottles in a specific category.
    """
    bottles, total = await service.get_by_category(
        category=category,
        page=page,
        page_size=page_size,
    )

    items = [BottleListItem.model_validate(b).model_dump() for b in bottles]

    return paginated_response(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        item_key="bottles",
    )


@router.get("/{bottle_id}")
async def get_bottle(
    bottle_id: int,
    service: BottleService = Depends(get_bottle_service),
):
    """
    Get full details for a specific bottle.

    Includes aliases and all statistics.
    """
    try:
        bottle = await service.get_by_id_with_aliases(bottle_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Build response with aliases
    response_data = BottleDetail.model_validate(bottle).model_dump()
    response_data["aliases"] = [a.alias for a in bottle.aliases]

    return success_response(data={"bottle": response_data})
