"""
Price service - business logic for price operations.
"""

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bottle import Bottle
from src.models.price import Price, PriceSource
from src.services.base import BaseService, NotFoundError


class PriceService(BaseService[Price]):
    """
    Service for price-related operations.

    Handles:
    - Price history retrieval
    - Statistical calculations
    - Chart data formatting
    - Trend analysis
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db, Price)

    async def get_bottle_or_raise(self, bottle_id: int) -> Bottle:
        """Get bottle by ID or raise NotFoundError."""
        result = await self.db.execute(
            select(Bottle).where(Bottle.id == bottle_id, Bottle.is_active == True)
        )
        bottle = result.scalar_one_or_none()
        if not bottle:
            raise NotFoundError("Bottle", bottle_id)
        return bottle

    async def get_history(
        self,
        bottle_id: int,
        *,
        days: int = 365,
        source: PriceSource | None = None,
        verified_only: bool = False,
        limit: int | None = None,
    ) -> tuple[Bottle, list[Price]]:
        """
        Get price history for a bottle.

        Returns:
            Tuple of (bottle, prices)
        """
        bottle = await self.get_bottle_or_raise(bottle_id)

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        query = (
            select(Price)
            .where(
                Price.bottle_id == bottle_id,
                Price.transaction_date >= cutoff_date,
                Price.is_excluded == False,
            )
            .order_by(Price.transaction_date.desc())
        )

        if source:
            query = query.where(Price.source == source)
        if verified_only:
            query = query.where(Price.is_verified == True)
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        prices = list(result.scalars().all())

        return bottle, prices

    async def get_stats(self, bottle_id: int) -> dict:
        """
        Get comprehensive price statistics for a bottle.

        Returns dict with:
        - count, avg, median, min, max, std_dev
        - trends (30d, 90d)
        - source breakdown
        """
        bottle = await self.get_bottle_or_raise(bottle_id)

        # Get all non-excluded prices
        result = await self.db.execute(
            select(Price).where(
                Price.bottle_id == bottle_id,
                Price.is_excluded == False,
            )
        )
        all_prices = list(result.scalars().all())

        if not all_prices:
            return {
                "bottle_id": bottle_id,
                "bottle_name": bottle.name,
                "count": 0,
                "avg_price": None,
                "median_price": None,
                "min_price": None,
                "max_price": None,
                "std_dev": None,
                "trend_30d": None,
                "trend_90d": None,
                "sources": [],
                "last_updated": None,
            }

        # Calculate statistics
        price_values = sorted([p.price_usd for p in all_prices])
        n = len(price_values)
        avg = sum(price_values) / n
        median = (
            price_values[n // 2]
            if n % 2
            else (price_values[n // 2 - 1] + price_values[n // 2]) / 2
        )
        variance = sum((x - avg) ** 2 for x in price_values) / n
        std_dev = variance ** 0.5

        # Source breakdown
        source_data = {}
        for price in all_prices:
            if price.source not in source_data:
                source_data[price.source] = []
            source_data[price.source].append(price.price_usd)

        sources = [
            {
                "source": source.value,
                "count": len(prices),
                "avg_price": round(sum(prices) / len(prices), 2),
                "min_price": round(min(prices), 2),
                "max_price": round(max(prices), 2),
            }
            for source, prices in source_data.items()
        ]

        # Trend calculations
        now = datetime.utcnow()
        trend_30d = await self._calculate_trend(all_prices, now, 30)
        trend_90d = await self._calculate_trend(all_prices, now, 90)

        return {
            "bottle_id": bottle_id,
            "bottle_name": bottle.name,
            "count": n,
            "avg_price": round(avg, 2),
            "median_price": round(median, 2),
            "min_price": round(min(price_values), 2),
            "max_price": round(max(price_values), 2),
            "std_dev": round(std_dev, 2),
            "trend_30d": round(trend_30d, 2) if trend_30d else None,
            "trend_90d": round(trend_90d, 2) if trend_90d else None,
            "sources": sources,
            "last_updated": bottle.stats_updated_at,
        }

    async def _calculate_trend(
        self,
        prices: list[Price],
        now: datetime,
        days: int,
    ) -> float | None:
        """Calculate price trend as percentage change."""
        recent = [
            p for p in prices
            if p.transaction_date >= now - timedelta(days=days)
        ]
        older = [
            p for p in prices
            if now - timedelta(days=days * 2) <= p.transaction_date < now - timedelta(days=days)
        ]

        if not recent or not older:
            return None

        recent_avg = sum(p.price_usd for p in recent) / len(recent)
        older_avg = sum(p.price_usd for p in older) / len(older)

        if older_avg <= 0:
            return None

        return ((recent_avg - older_avg) / older_avg) * 100

    async def get_chart_data(
        self,
        bottle_id: int,
        *,
        days: int = 365,
        aggregation: Literal["daily", "weekly", "monthly"] | None = None,
    ) -> dict:
        """
        Get price data formatted for charting.

        Auto-selects aggregation based on time range if not specified:
        - <= 90 days: daily
        - <= 365 days: weekly
        - > 365 days: monthly

        Returns Chart.js compatible format.
        """
        bottle = await self.get_bottle_or_raise(bottle_id)

        # Auto-select aggregation
        if aggregation is None:
            if days <= 90:
                aggregation = "daily"
            elif days <= 365:
                aggregation = "weekly"
            else:
                aggregation = "monthly"

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get raw prices
        result = await self.db.execute(
            select(Price)
            .where(
                Price.bottle_id == bottle_id,
                Price.transaction_date >= cutoff_date,
                Price.is_excluded == False,
            )
            .order_by(Price.transaction_date.asc())
        )
        prices = list(result.scalars().all())

        if not prices:
            return {
                "bottle_id": bottle_id,
                "bottle_name": bottle.name,
                "labels": [],
                "datasets": [],
                "aggregation": aggregation,
                "period_days": days,
            }

        # Aggregate by period
        aggregated = self._aggregate_prices(prices, aggregation)

        # Format for Chart.js
        labels = list(aggregated.keys())
        avg_values = [d["avg"] for d in aggregated.values()]
        min_values = [d["min"] for d in aggregated.values()]
        max_values = [d["max"] for d in aggregated.values()]
        counts = [d["count"] for d in aggregated.values()]

        return {
            "bottle_id": bottle_id,
            "bottle_name": bottle.name,
            "labels": labels,
            "datasets": [
                {
                    "label": "Average Price",
                    "data": avg_values,
                    "type": "line",
                    "borderColor": "#3b82f6",
                    "backgroundColor": "rgba(59, 130, 246, 0.1)",
                    "fill": True,
                },
                {
                    "label": "Price Range",
                    "data": [
                        {"min": min_val, "max": max_val}
                        for min_val, max_val in zip(min_values, max_values)
                    ],
                    "type": "bar",
                    "backgroundColor": "rgba(156, 163, 175, 0.3)",
                    "hidden": True,
                },
            ],
            "counts": counts,
            "aggregation": aggregation,
            "period_days": days,
        }

    def _aggregate_prices(
        self,
        prices: list[Price],
        aggregation: Literal["daily", "weekly", "monthly"],
    ) -> dict:
        """Aggregate prices by time period."""
        buckets = {}

        for price in prices:
            dt = price.transaction_date

            if aggregation == "daily":
                key = dt.strftime("%Y-%m-%d")
            elif aggregation == "weekly":
                # Start of week (Monday)
                week_start = dt - timedelta(days=dt.weekday())
                key = week_start.strftime("%Y-%m-%d")
            else:  # monthly
                key = dt.strftime("%Y-%m")

            if key not in buckets:
                buckets[key] = []
            buckets[key].append(price.price_usd)

        # Calculate stats for each bucket
        result = {}
        for key, values in buckets.items():
            result[key] = {
                "avg": round(sum(values) / len(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "count": len(values),
            }

        return result

    async def get_recent_prices(
        self,
        limit: int = 20,
        source: PriceSource | None = None,
    ) -> list[dict]:
        """
        Get most recent prices across all bottles.

        Useful for activity feeds.
        """
        query = (
            select(Price, Bottle.name.label("bottle_name"))
            .join(Bottle, Price.bottle_id == Bottle.id)
            .where(
                Price.is_excluded == False,
                Bottle.is_active == True,
            )
            .order_by(Price.created_at.desc())
            .limit(limit)
        )

        if source:
            query = query.where(Price.source == source)

        result = await self.db.execute(query)

        return [
            {
                "id": row.Price.id,
                "bottle_id": row.Price.bottle_id,
                "bottle_name": row.bottle_name,
                "price_usd": row.Price.price_usd,
                "source": row.Price.source.value,
                "transaction_date": row.Price.transaction_date.isoformat(),
                "created_at": row.Price.created_at.isoformat(),
            }
            for row in result.all()
        ]

    async def get_price_distribution(
        self,
        bottle_id: int,
        bucket_count: int = 10,
    ) -> dict:
        """
        Get price distribution for histogram display.

        Divides price range into buckets and counts occurrences.
        """
        bottle = await self.get_bottle_or_raise(bottle_id)

        result = await self.db.execute(
            select(Price.price_usd)
            .where(
                Price.bottle_id == bottle_id,
                Price.is_excluded == False,
            )
        )
        prices = [row[0] for row in result.all()]

        if not prices:
            return {
                "bottle_id": bottle_id,
                "bottle_name": bottle.name,
                "buckets": [],
                "min_price": None,
                "max_price": None,
            }

        min_price = min(prices)
        max_price = max(prices)
        bucket_size = (max_price - min_price) / bucket_count if max_price > min_price else 1

        buckets = []
        for i in range(bucket_count):
            bucket_min = min_price + (i * bucket_size)
            bucket_max = min_price + ((i + 1) * bucket_size)
            count = sum(1 for p in prices if bucket_min <= p < bucket_max)
            if i == bucket_count - 1:  # Include max in last bucket
                count += sum(1 for p in prices if p == bucket_max)

            buckets.append({
                "range_min": round(bucket_min, 2),
                "range_max": round(bucket_max, 2),
                "count": count,
                "label": f"${int(bucket_min)}-${int(bucket_max)}",
            })

        return {
            "bottle_id": bottle_id,
            "bottle_name": bottle.name,
            "buckets": buckets,
            "min_price": round(min_price, 2),
            "max_price": round(max_price, 2),
            "total_count": len(prices),
        }
