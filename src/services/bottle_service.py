"""
Bottle service - business logic for bottle operations.
"""

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.bottle import Bottle, BottleAlias, SpiritCategory
from src.models.price import Price
from src.services.base import BaseService, NotFoundError


class BottleService(BaseService[Bottle]):
    """
    Service for bottle-related operations.

    Handles:
    - Search with filters and sorting
    - Autocomplete suggestions
    - Trending bottles
    - Homepage aggregations
    - Bottle details with aliases
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db, Bottle)

    async def search(
        self,
        *,
        query: str | None = None,
        category: SpiritCategory | None = None,
        distillery: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_age: int | None = None,
        max_age: int | None = None,
        has_prices: bool | None = None,
        sort: Literal["name", "price", "trend", "recent", "popularity"] = "name",
        order: Literal["asc", "desc"] = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Bottle], int]:
        """
        Search bottles with filters, sorting, and pagination.

        Returns:
            Tuple of (bottles, total_count)
        """
        # Build base query for active bottles
        base_query = select(Bottle).where(Bottle.is_active == True)

        # Text search across name, distillery, brand, and aliases
        if query:
            search_term = f"%{query}%"
            alias_subquery = (
                select(BottleAlias.bottle_id)
                .where(BottleAlias.alias.ilike(search_term))
                .scalar_subquery()
            )
            base_query = base_query.where(
                or_(
                    Bottle.name.ilike(search_term),
                    Bottle.distillery.ilike(search_term),
                    Bottle.brand.ilike(search_term),
                    Bottle.normalized_name.ilike(search_term),
                    Bottle.id.in_(alias_subquery),
                )
            )

        # Apply filters
        if category:
            base_query = base_query.where(Bottle.category == category)
        if distillery:
            base_query = base_query.where(Bottle.distillery.ilike(f"%{distillery}%"))
        if min_price is not None:
            base_query = base_query.where(Bottle.avg_price >= min_price)
        if max_price is not None:
            base_query = base_query.where(Bottle.avg_price <= max_price)
        if min_age is not None:
            base_query = base_query.where(Bottle.age_statement >= min_age)
        if max_age is not None:
            base_query = base_query.where(Bottle.age_statement <= max_age)
        if has_prices is True:
            base_query = base_query.where(Bottle.price_count > 0)
        elif has_prices is False:
            base_query = base_query.where(Bottle.price_count == 0)

        # Get total count
        total = await self.count(base_query)

        # Apply sorting
        sort_mapping = {
            "name": Bottle.name,
            "price": Bottle.avg_price,
            "trend": Bottle.price_trend,
            "recent": Bottle.last_price_date,
            "popularity": Bottle.price_count,
        }
        sort_column = sort_mapping.get(sort, Bottle.name)

        if order == "desc":
            base_query = base_query.order_by(sort_column.desc().nullslast())
        else:
            base_query = base_query.order_by(sort_column.asc().nullsfirst())

        # Apply pagination
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)

        result = await self.db.execute(base_query)
        bottles = list(result.scalars().all())

        return bottles, total

    async def autocomplete(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Get autocomplete suggestions for bottle search.

        Returns lightweight suggestions with id, name, and category.
        """
        if len(query) < 2:
            return []

        search_term = f"%{query}%"

        # Search bottles
        result = await self.db.execute(
            select(Bottle.id, Bottle.name, Bottle.distillery, Bottle.category)
            .where(
                Bottle.is_active == True,
                or_(
                    Bottle.name.ilike(search_term),
                    Bottle.distillery.ilike(search_term),
                )
            )
            .order_by(Bottle.price_count.desc())
            .limit(limit)
        )

        suggestions = [
            {
                "id": row.id,
                "name": row.name,
                "distillery": row.distillery,
                "category": row.category.value if row.category else None,
            }
            for row in result.all()
        ]

        return suggestions

    async def get_by_id_with_aliases(self, bottle_id: int) -> Bottle:
        """
        Get bottle by ID with aliases loaded.

        Raises NotFoundError if not found.
        """
        result = await self.db.execute(
            select(Bottle)
            .options(selectinload(Bottle.aliases))
            .where(Bottle.id == bottle_id, Bottle.is_active == True)
        )
        bottle = result.scalar_one_or_none()

        if not bottle:
            raise NotFoundError("Bottle", bottle_id)

        return bottle

    async def get_trending(
        self,
        days: int = 30,
        limit: int = 10,
        category: SpiritCategory | None = None,
    ) -> list[Bottle]:
        """
        Get trending bottles based on price activity and trend.

        Trending = high recent activity + positive price movement.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Subquery for recent price activity
        activity_subquery = (
            select(
                Price.bottle_id,
                func.count(Price.id).label("recent_count"),
            )
            .where(
                Price.transaction_date >= cutoff_date,
                Price.is_excluded == False,
            )
            .group_by(Price.bottle_id)
            .subquery()
        )

        query = (
            select(Bottle)
            .join(activity_subquery, Bottle.id == activity_subquery.c.bottle_id)
            .where(
                Bottle.is_active == True,
                Bottle.price_count >= 5,  # Minimum data points
            )
            .order_by(
                activity_subquery.c.recent_count.desc(),
                Bottle.price_trend.desc().nullslast(),
            )
            .limit(limit)
        )

        if category:
            query = query.where(Bottle.category == category)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_homepage_data(self) -> dict:
        """
        Get aggregated data for the homepage.

        Returns:
            - recently_updated: Bottles with recent price updates
            - trending_up: Bottles with positive trend
            - trending_down: Bottles with negative trend
            - category_stats: Price stats by category
            - total_bottles: Total active bottles
            - total_prices: Total price records
        """
        # Recently updated bottles
        recently_updated_result = await self.db.execute(
            select(Bottle)
            .where(
                Bottle.is_active == True,
                Bottle.last_price_date.isnot(None),
            )
            .order_by(Bottle.last_price_date.desc())
            .limit(10)
        )
        recently_updated = list(recently_updated_result.scalars().all())

        # Trending up (positive price_trend)
        trending_up_result = await self.db.execute(
            select(Bottle)
            .where(
                Bottle.is_active == True,
                Bottle.price_trend > 0,
                Bottle.price_count >= 5,
            )
            .order_by(Bottle.price_trend.desc())
            .limit(5)
        )
        trending_up = list(trending_up_result.scalars().all())

        # Trending down (negative price_trend)
        trending_down_result = await self.db.execute(
            select(Bottle)
            .where(
                Bottle.is_active == True,
                Bottle.price_trend < 0,
                Bottle.price_count >= 5,
            )
            .order_by(Bottle.price_trend.asc())
            .limit(5)
        )
        trending_down = list(trending_down_result.scalars().all())

        # Category statistics
        category_stats_result = await self.db.execute(
            select(
                Bottle.category,
                func.count(Bottle.id).label("count"),
                func.avg(Bottle.avg_price).label("avg_price"),
            )
            .where(Bottle.is_active == True)
            .group_by(Bottle.category)
        )
        category_stats = [
            {
                "category": row.category.value if row.category else "other",
                "count": row.count,
                "avg_price": round(row.avg_price, 2) if row.avg_price else None,
            }
            for row in category_stats_result.all()
        ]

        # Totals
        total_bottles = await self.db.scalar(
            select(func.count(Bottle.id)).where(Bottle.is_active == True)
        ) or 0

        total_prices = await self.db.scalar(
            select(func.count(Price.id)).where(Price.is_excluded == False)
        ) or 0

        return {
            "recently_updated": recently_updated,
            "trending_up": trending_up,
            "trending_down": trending_down,
            "category_stats": category_stats,
            "total_bottles": total_bottles,
            "total_prices": total_prices,
        }

    async def get_by_category(
        self,
        category: SpiritCategory,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Bottle], int]:
        """Get bottles by category with pagination."""
        return await self.search(
            category=category,
            page=page,
            page_size=page_size,
            sort="popularity",
            order="desc",
        )

    async def get_distilleries(self) -> list[dict]:
        """Get list of all distilleries with bottle counts."""
        result = await self.db.execute(
            select(
                Bottle.distillery,
                func.count(Bottle.id).label("count"),
            )
            .where(
                Bottle.is_active == True,
                Bottle.distillery.isnot(None),
            )
            .group_by(Bottle.distillery)
            .order_by(func.count(Bottle.id).desc())
        )

        return [
            {"name": row.distillery, "count": row.count}
            for row in result.all()
        ]
