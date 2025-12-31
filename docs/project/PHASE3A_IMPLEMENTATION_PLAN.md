# Phase 3A Implementation Plan: Bottle Database & Search

**Created:** 2025-12-31
**Author:** Tech Lead (Jordan)
**Status:** Active
**Target Completion:** 2026-01-10 (Week 6)

---

## Overview

Phase 3A delivers the core bottle browsing and price history experience. Users will be able to search for bottles, view detailed information and price history, and discover trending bottles on the homepage.

### Scope
- Bottle API enhancements with consistent response format
- Price history API with chart-optimized aggregation
- Search with autocomplete and suggestions
- Homepage data endpoint (trending, active, featured)

### Dependencies
- Phase 2 Complete: Scraping infrastructure operational
- Existing models: Bottle, Price, BottleAlias
- Existing routes: Basic bottle/price endpoints

---

## Implementation Tasks

### Task 1: Service Layer Foundation

**File:** `src/services/__init__.py`, `src/services/base.py`

**Objective:** Establish service layer pattern for business logic separation.

**Implementation:**

```python
# src/services/base.py
from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """Base class for all services."""

    def __init__(self, db: AsyncSession):
        self.db = db
```

**Tests Required:**
- None (infrastructure code)

**Estimated Time:** 0.5 hours

---

### Task 2: Response Envelope Wrapper

**Files:** `src/api/response.py`, `src/schemas/response.py`

**Objective:** Standardize API responses per ARCHITECTURE.md spec.

**Implementation:**

```python
# src/schemas/response.py
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    page: int
    limit: int
    total: int
    pages: int
    has_more: bool


class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""
    status: str = "success"
    data: T
    meta: PaginationMeta | None = None


class ErrorDetail(BaseModel):
    """Error details."""
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    status: str = "error"
    error: ErrorDetail
```

**Usage Pattern:**
```python
# In route handlers
return APIResponse(
    data=BottleListSchema(bottles=bottles),
    meta=PaginationMeta(page=page, limit=limit, total=total, pages=pages, has_more=has_more)
)
```

**Tests Required:**
- Test response envelope serialization
- Test error response format

**Estimated Time:** 1 hour

---

### Task 3: Bottle Service Implementation

**File:** `src/services/bottle_service.py`

**Objective:** Centralize bottle business logic.

**Methods:**

| Method | Description | Returns |
|--------|-------------|---------|
| `get_bottle(id)` | Get single bottle with aliases | `Bottle \| None` |
| `search_bottles(params)` | Search with filters/pagination | `(list[Bottle], int)` |
| `get_trending_bottles(limit)` | Top bottles by price trend | `list[Bottle]` |
| `get_active_bottles(days, limit)` | Most prices in time window | `list[Bottle]` |
| `get_featured_bottles(limit)` | Allocated/limited release | `list[Bottle]` |
| `get_recent_bottles(limit)` | Newly added bottles | `list[Bottle]` |
| `get_bottle_stats(id)` | Detailed statistics | `BottleStats` |

**Implementation Details:**

```python
# src/services/bottle_service.py
from datetime import datetime, timedelta
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.bottle import Bottle, BottleAlias
from src.models.price import Price
from src.services.base import BaseService


class BottleService(BaseService):
    """Service for bottle-related business logic."""

    async def get_bottle(self, bottle_id: int) -> Bottle | None:
        """Get a single bottle by ID with aliases loaded."""
        query = (
            select(Bottle)
            .options(selectinload(Bottle.aliases))
            .where(Bottle.id == bottle_id, Bottle.is_active == True)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def search_bottles(
        self,
        query_text: str | None = None,
        category: str | None = None,
        distillery: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_age: int | None = None,
        max_age: int | None = None,
        allocated_only: bool = False,
        sort_by: str = "name",
        sort_order: str = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Bottle], int]:
        """
        Search bottles with comprehensive filtering.

        Returns tuple of (bottles, total_count).
        """
        query = select(Bottle).where(Bottle.is_active == True)

        # Text search across name, distillery, brand, and aliases
        if query_text:
            search_term = f"%{query_text}%"
            alias_ids = (
                select(BottleAlias.bottle_id)
                .where(BottleAlias.alias.ilike(search_term))
                .scalar_subquery()
            )
            query = query.where(
                or_(
                    Bottle.name.ilike(search_term),
                    Bottle.distillery.ilike(search_term),
                    Bottle.brand.ilike(search_term),
                    Bottle.id.in_(alias_ids),
                )
            )

        # Apply filters
        if category:
            query = query.where(Bottle.category == category)
        if distillery:
            query = query.where(Bottle.distillery.ilike(f"%{distillery}%"))
        if min_price is not None:
            query = query.where(Bottle.avg_price >= min_price)
        if max_price is not None:
            query = query.where(Bottle.avg_price <= max_price)
        if min_age is not None:
            query = query.where(Bottle.age_statement >= min_age)
        if max_age is not None:
            query = query.where(Bottle.age_statement <= max_age)
        if allocated_only:
            query = query.where(Bottle.is_allocated == True)

        # Count total before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Sorting
        sort_columns = {
            "name": Bottle.name,
            "price": Bottle.avg_price,
            "trend": Bottle.price_trend,
            "recent": Bottle.last_price_date,
            "age": Bottle.age_statement,
        }
        sort_col = sort_columns.get(sort_by, Bottle.name)

        if sort_order == "desc":
            query = query.order_by(sort_col.desc().nullslast())
        else:
            query = query.order_by(sort_col.asc().nullsfirst())

        # Pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        bottles = list(result.scalars().all())

        return bottles, total

    async def get_trending_bottles(self, limit: int = 10) -> list[Bottle]:
        """Get bottles with highest positive price trends."""
        query = (
            select(Bottle)
            .where(
                Bottle.is_active == True,
                Bottle.price_trend.isnot(None),
                Bottle.price_count >= 3,  # Need some data points
            )
            .order_by(Bottle.price_trend.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active_bottles(
        self, days: int = 30, limit: int = 10
    ) -> list[Bottle]:
        """Get bottles with most price activity in recent days."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Subquery to count recent prices
        price_count_subq = (
            select(
                Price.bottle_id,
                func.count(Price.id).label("recent_count")
            )
            .where(
                Price.transaction_date >= cutoff,
                Price.is_excluded == False,
            )
            .group_by(Price.bottle_id)
            .subquery()
        )

        query = (
            select(Bottle)
            .join(price_count_subq, Bottle.id == price_count_subq.c.bottle_id)
            .where(Bottle.is_active == True)
            .order_by(price_count_subq.c.recent_count.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_featured_bottles(self, limit: int = 10) -> list[Bottle]:
        """Get allocated or limited release bottles with good data."""
        query = (
            select(Bottle)
            .where(
                Bottle.is_active == True,
                or_(Bottle.is_allocated == True, Bottle.is_limited_release == True),
                Bottle.price_count >= 3,
            )
            .order_by(Bottle.avg_price.desc().nullslast())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recent_bottles(self, limit: int = 10) -> list[Bottle]:
        """Get most recently added bottles."""
        query = (
            select(Bottle)
            .where(Bottle.is_active == True)
            .order_by(Bottle.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def autocomplete(
        self, query_text: str, limit: int = 10
    ) -> list[dict]:
        """
        Get autocomplete suggestions.

        Returns list of {id, name, type} where type is 'bottle' or 'alias'.
        """
        if len(query_text) < 2:
            return []

        search_term = f"{query_text}%"  # Prefix match for autocomplete

        # Search bottles
        bottle_query = (
            select(Bottle.id, Bottle.name, Bottle.distillery)
            .where(
                Bottle.is_active == True,
                or_(
                    Bottle.name.ilike(search_term),
                    Bottle.distillery.ilike(search_term),
                )
            )
            .limit(limit)
        )
        bottle_result = await self.db.execute(bottle_query)

        suggestions = []
        for row in bottle_result:
            suggestions.append({
                "id": row.id,
                "name": row.name,
                "distillery": row.distillery,
                "type": "bottle",
            })

        # If not enough results, also search aliases
        if len(suggestions) < limit:
            remaining = limit - len(suggestions)
            alias_query = (
                select(BottleAlias.bottle_id, BottleAlias.alias, Bottle.name)
                .join(Bottle, BottleAlias.bottle_id == Bottle.id)
                .where(
                    Bottle.is_active == True,
                    BottleAlias.alias.ilike(search_term),
                )
                .limit(remaining)
            )
            alias_result = await self.db.execute(alias_query)

            for row in alias_result:
                suggestions.append({
                    "id": row.bottle_id,
                    "name": row.name,
                    "matched_alias": row.alias,
                    "type": "alias",
                })

        return suggestions
```

**Tests Required:**
- `test_get_bottle_found`
- `test_get_bottle_not_found`
- `test_search_bottles_no_filters`
- `test_search_bottles_with_query`
- `test_search_bottles_with_filters`
- `test_search_bottles_pagination`
- `test_get_trending_bottles`
- `test_get_active_bottles`
- `test_autocomplete`

**Estimated Time:** 4 hours

---

### Task 4: Price Service Implementation

**File:** `src/services/price_service.py`

**Objective:** Centralize price history and aggregation logic.

**Methods:**

| Method | Description | Returns |
|--------|-------------|---------|
| `get_price_history(bottle_id, params)` | Raw price points | `list[Price]` |
| `get_aggregated_history(bottle_id, params)` | Chart-optimized data | `list[AggregatedPrice]` |
| `get_price_stats(bottle_id)` | Statistical summary | `PriceStatistics` |
| `get_source_breakdown(bottle_id)` | Prices by source | `list[SourceStats]` |

**Chart Aggregation Strategy:**
- 0-30 days: Daily averages
- 31-365 days: Weekly averages
- 366+ days: Monthly averages

**Implementation Details:**

```python
# src/services/price_service.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, median, stdev
from typing import Literal

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bottle import Bottle
from src.models.price import Price, PriceSource
from src.services.base import BaseService


@dataclass
class AggregatedPrice:
    """Aggregated price point for charts."""
    period_start: datetime
    period_end: datetime
    period_label: str
    avg_price: float
    min_price: float
    max_price: float
    count: int


@dataclass
class PriceStatistics:
    """Comprehensive price statistics."""
    bottle_id: int
    total_count: int
    avg_price: float | None
    median_price: float | None
    min_price: float | None
    max_price: float | None
    std_dev: float | None
    trend_30d: float | None
    trend_90d: float | None
    last_price: float | None
    last_price_date: datetime | None
    data_quality: Literal["excellent", "good", "limited", "insufficient"]


@dataclass
class SourceStats:
    """Price statistics by source."""
    source: PriceSource
    count: int
    avg_price: float
    min_price: float
    max_price: float
    percentage: float


class PriceService(BaseService):
    """Service for price-related business logic."""

    async def get_price_history(
        self,
        bottle_id: int,
        days: int = 365,
        source: PriceSource | None = None,
        verified_only: bool = False,
        exclude_outliers: bool = True,
        limit: int = 500,
    ) -> list[Price]:
        """Get raw price history for a bottle."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        query = select(Price).where(
            and_(
                Price.bottle_id == bottle_id,
                Price.transaction_date >= cutoff,
                Price.is_excluded == False,
            )
        )

        if source:
            query = query.where(Price.source == source)
        if verified_only:
            query = query.where(Price.is_verified == True)
        if exclude_outliers:
            query = query.where(Price.is_outlier == False)

        query = query.order_by(Price.transaction_date.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_aggregated_history(
        self,
        bottle_id: int,
        days: int = 365,
        source: PriceSource | None = None,
    ) -> list[AggregatedPrice]:
        """
        Get aggregated price history optimized for charts.

        Aggregation strategy:
        - 0-30 days: Daily
        - 31-365 days: Weekly
        - 366+ days: Monthly
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)

        # Get all prices in range
        query = select(Price).where(
            and_(
                Price.bottle_id == bottle_id,
                Price.transaction_date >= cutoff,
                Price.is_excluded == False,
                Price.is_outlier == False,
            )
        )

        if source:
            query = query.where(Price.source == source)

        query = query.order_by(Price.transaction_date.asc())

        result = await self.db.execute(query)
        prices = list(result.scalars().all())

        if not prices:
            return []

        # Group by appropriate period
        aggregated = []

        # Determine aggregation level based on data age
        for price in prices:
            age_days = (now - price.transaction_date).days

            if age_days <= 30:
                # Daily aggregation
                period_start = price.transaction_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                period_label = period_start.strftime("%Y-%m-%d")
            elif age_days <= 365:
                # Weekly aggregation (start of week)
                period_start = price.transaction_date - timedelta(
                    days=price.transaction_date.weekday()
                )
                period_start = period_start.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                period_label = f"Week of {period_start.strftime('%Y-%m-%d')}"
            else:
                # Monthly aggregation
                period_start = price.transaction_date.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
                period_label = period_start.strftime("%Y-%m")

        # Actual aggregation (group by period)
        periods: dict[str, list[float]] = {}
        period_dates: dict[str, datetime] = {}

        for price in prices:
            age_days = (now - price.transaction_date).days

            if age_days <= 30:
                period_key = price.transaction_date.strftime("%Y-%m-%d")
                period_start = price.transaction_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            elif age_days <= 365:
                week_start = price.transaction_date - timedelta(
                    days=price.transaction_date.weekday()
                )
                period_key = week_start.strftime("%Y-W%W")
                period_start = week_start.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            else:
                period_key = price.transaction_date.strftime("%Y-%m")
                period_start = price.transaction_date.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )

            if period_key not in periods:
                periods[period_key] = []
                period_dates[period_key] = period_start
            periods[period_key].append(price.price_usd)

        # Convert to AggregatedPrice objects
        for period_key in sorted(periods.keys()):
            prices_in_period = periods[period_key]
            period_start = period_dates[period_key]

            aggregated.append(AggregatedPrice(
                period_start=period_start,
                period_end=period_start + timedelta(days=1),  # Approximate
                period_label=period_key,
                avg_price=mean(prices_in_period),
                min_price=min(prices_in_period),
                max_price=max(prices_in_period),
                count=len(prices_in_period),
            ))

        return aggregated

    async def get_price_stats(self, bottle_id: int) -> PriceStatistics | None:
        """Get comprehensive statistics for a bottle's prices."""
        # Verify bottle exists
        bottle_result = await self.db.execute(
            select(Bottle).where(Bottle.id == bottle_id)
        )
        bottle = bottle_result.scalar_one_or_none()
        if not bottle:
            return None

        # Get all valid prices
        prices_result = await self.db.execute(
            select(Price).where(
                and_(
                    Price.bottle_id == bottle_id,
                    Price.is_excluded == False,
                    Price.is_outlier == False,
                )
            ).order_by(Price.transaction_date.desc())
        )
        prices = list(prices_result.scalars().all())

        if not prices:
            return PriceStatistics(
                bottle_id=bottle_id,
                total_count=0,
                avg_price=None,
                median_price=None,
                min_price=None,
                max_price=None,
                std_dev=None,
                trend_30d=None,
                trend_90d=None,
                last_price=None,
                last_price_date=None,
                data_quality="insufficient",
            )

        price_values = [p.price_usd for p in prices]

        # Calculate basic stats
        avg = mean(price_values)
        med = median(price_values)
        std = stdev(price_values) if len(price_values) > 1 else 0

        # Calculate trends
        now = datetime.utcnow()
        trend_30d = self._calculate_trend(prices, now, 30)
        trend_90d = self._calculate_trend(prices, now, 90)

        # Determine data quality
        count = len(prices)
        if count >= 20:
            quality = "excellent"
        elif count >= 10:
            quality = "good"
        elif count >= 3:
            quality = "limited"
        else:
            quality = "insufficient"

        return PriceStatistics(
            bottle_id=bottle_id,
            total_count=count,
            avg_price=avg,
            median_price=med,
            min_price=min(price_values),
            max_price=max(price_values),
            std_dev=std,
            trend_30d=trend_30d,
            trend_90d=trend_90d,
            last_price=prices[0].price_usd if prices else None,
            last_price_date=prices[0].transaction_date if prices else None,
            data_quality=quality,
        )

    def _calculate_trend(
        self,
        prices: list[Price],
        now: datetime,
        days: int,
    ) -> float | None:
        """Calculate price trend as percentage change."""
        half_period = days // 2

        recent = [
            p.price_usd for p in prices
            if (now - p.transaction_date).days <= half_period
        ]
        older = [
            p.price_usd for p in prices
            if half_period < (now - p.transaction_date).days <= days
        ]

        if not recent or not older:
            return None

        recent_avg = mean(recent)
        older_avg = mean(older)

        if older_avg == 0:
            return None

        return ((recent_avg - older_avg) / older_avg) * 100

    async def get_source_breakdown(self, bottle_id: int) -> list[SourceStats]:
        """Get price breakdown by source."""
        # Get all prices grouped by source
        prices_result = await self.db.execute(
            select(Price).where(
                and_(
                    Price.bottle_id == bottle_id,
                    Price.is_excluded == False,
                )
            )
        )
        prices = list(prices_result.scalars().all())

        if not prices:
            return []

        # Group by source
        by_source: dict[PriceSource, list[float]] = {}
        for price in prices:
            if price.source not in by_source:
                by_source[price.source] = []
            by_source[price.source].append(price.price_usd)

        total_count = len(prices)

        return [
            SourceStats(
                source=source,
                count=len(values),
                avg_price=mean(values),
                min_price=min(values),
                max_price=max(values),
                percentage=(len(values) / total_count) * 100,
            )
            for source, values in by_source.items()
        ]
```

**Tests Required:**
- `test_get_price_history_basic`
- `test_get_price_history_with_filters`
- `test_get_aggregated_history_daily`
- `test_get_aggregated_history_weekly`
- `test_get_aggregated_history_monthly`
- `test_get_price_stats_with_data`
- `test_get_price_stats_no_data`
- `test_get_source_breakdown`
- `test_calculate_trend`

**Estimated Time:** 4 hours

---

### Task 5: Pydantic Schemas for Phase 3A

**File:** `src/schemas/bottle.py`, `src/schemas/price.py`

**Objective:** Define request/response schemas.

**Key Schemas:**

```python
# src/schemas/bottle.py
from datetime import datetime
from pydantic import BaseModel, Field
from src.models.bottle import SpiritCategory, BottleSize


class BottleListItem(BaseModel):
    """Bottle in list/search results."""
    id: int
    name: str
    distillery: str | None
    category: SpiritCategory
    age_statement: int | None
    release_year: int | None
    is_allocated: bool
    avg_price: float | None
    price_count: int
    price_trend: float | None
    confidence_score: float | None
    data_quality: str | None = None

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
    aliases: list[str] = []

    # Statistics
    price_count: int
    avg_price: float | None
    min_price: float | None
    max_price: float | None
    last_price: float | None
    last_price_date: datetime | None
    price_trend: float | None
    confidence_score: float | None
    data_quality: str | None = None

    class Config:
        from_attributes = True


class BottleSearchParams(BaseModel):
    """Search query parameters."""
    q: str | None = Field(None, description="Search query")
    category: SpiritCategory | None = None
    distillery: str | None = None
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(None, ge=0)
    min_age: int | None = Field(None, ge=0)
    max_age: int | None = Field(None, le=100)
    allocated_only: bool = False
    sort_by: str = Field("name", pattern="^(name|price|trend|recent|age)$")
    sort_order: str = Field("asc", pattern="^(asc|desc)$")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class AutocompleteSuggestion(BaseModel):
    """Autocomplete suggestion."""
    id: int
    name: str
    distillery: str | None = None
    matched_alias: str | None = None
    type: str  # 'bottle' or 'alias'


class HomepageData(BaseModel):
    """Homepage aggregated data."""
    trending: list[BottleListItem]
    most_active: list[BottleListItem]
    featured: list[BottleListItem]
    recently_added: list[BottleListItem]
    total_bottles: int
    total_prices: int


# src/schemas/price.py
from datetime import datetime
from pydantic import BaseModel
from src.models.price import PriceSource


class PricePoint(BaseModel):
    """Single price data point."""
    id: int
    price_usd: float
    transaction_date: datetime
    source: PriceSource
    source_name: str | None
    is_verified: bool
    confidence_weight: float

    class Config:
        from_attributes = True


class AggregatedPricePoint(BaseModel):
    """Aggregated price for charts."""
    period_label: str
    period_start: datetime
    avg_price: float
    min_price: float
    max_price: float
    count: int


class ChartData(BaseModel):
    """Chart.js compatible data format."""
    labels: list[str]
    datasets: list[dict]


class PriceHistoryResponse(BaseModel):
    """Price history response."""
    bottle_id: int
    bottle_name: str
    prices: list[PricePoint] | None = None
    aggregated: list[AggregatedPricePoint] | None = None
    chart_data: ChartData | None = None
    total_count: int


class PriceStatisticsResponse(BaseModel):
    """Detailed price statistics."""
    bottle_id: int
    bottle_name: str
    total_count: int
    avg_price: float | None
    median_price: float | None
    min_price: float | None
    max_price: float | None
    std_dev: float | None
    trend_30d: float | None
    trend_90d: float | None
    last_price: float | None
    last_price_date: datetime | None
    data_quality: str
    sources: list[dict]


class SourceBreakdownItem(BaseModel):
    """Price breakdown by source."""
    source: PriceSource
    count: int
    avg_price: float
    min_price: float
    max_price: float
    percentage: float
```

**Estimated Time:** 2 hours

---

### Task 6: Updated Route Handlers

**Files:** `src/api/routes/bottles.py`, `src/api/routes/prices.py`

**Objective:** Refactor routes to use services and response envelope.

**New/Enhanced Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /bottles` | Enhanced | Search with new filters, envelope response |
| `GET /bottles/{id}` | Enhanced | Full details with data quality |
| `GET /bottles/search/autocomplete` | New | Autocomplete suggestions |
| `GET /bottles/homepage` | New | Homepage aggregated data |
| `GET /bottles/trending` | New | Trending bottles |
| `GET /prices/bottle/{id}/history` | Enhanced | Raw + aggregated options |
| `GET /prices/bottle/{id}/chart` | New | Chart.js formatted data |
| `GET /prices/bottle/{id}/stats` | Enhanced | With data quality |

**Implementation Pattern:**

```python
# src/api/routes/bottles.py (updated)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.bottle import (
    BottleDetail,
    BottleListItem,
    BottleSearchParams,
    AutocompleteSuggestion,
    HomepageData,
)
from src.schemas.response import APIResponse, PaginationMeta
from src.services.bottle_service import BottleService

router = APIRouter()


@router.get("", response_model=APIResponse[dict])
async def search_bottles(
    q: str | None = Query(None, description="Search query"),
    category: str | None = Query(None),
    distillery: str | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    min_age: int | None = Query(None, ge=0),
    max_age: int | None = Query(None, le=100),
    allocated_only: bool = Query(False),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search and browse bottles."""
    service = BottleService(db)

    bottles, total = await service.search_bottles(
        query_text=q,
        category=category,
        distillery=distillery,
        min_price=min_price,
        max_price=max_price,
        min_age=min_age,
        max_age=max_age,
        allocated_only=allocated_only,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    pages = (total + page_size - 1) // page_size

    return APIResponse(
        data={"bottles": [BottleListItem.model_validate(b) for b in bottles]},
        meta=PaginationMeta(
            page=page,
            limit=page_size,
            total=total,
            pages=pages,
            has_more=page < pages,
        ),
    )


@router.get("/search/autocomplete", response_model=APIResponse[dict])
async def autocomplete(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Get autocomplete suggestions for bottle search."""
    service = BottleService(db)
    suggestions = await service.autocomplete(q, limit)

    return APIResponse(
        data={
            "suggestions": [AutocompleteSuggestion(**s) for s in suggestions],
            "query": q,
        }
    )


@router.get("/homepage", response_model=APIResponse[HomepageData])
async def get_homepage_data(
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated data for homepage."""
    service = BottleService(db)

    trending = await service.get_trending_bottles(limit=8)
    active = await service.get_active_bottles(days=30, limit=8)
    featured = await service.get_featured_bottles(limit=8)
    recent = await service.get_recent_bottles(limit=8)

    # Get totals
    from sqlalchemy import func, select
    from src.models.bottle import Bottle
    from src.models.price import Price

    total_bottles = await db.scalar(
        select(func.count()).where(Bottle.is_active == True)
    ) or 0
    total_prices = await db.scalar(
        select(func.count()).where(Price.is_excluded == False)
    ) or 0

    return APIResponse(
        data=HomepageData(
            trending=[BottleListItem.model_validate(b) for b in trending],
            most_active=[BottleListItem.model_validate(b) for b in active],
            featured=[BottleListItem.model_validate(b) for b in featured],
            recently_added=[BottleListItem.model_validate(b) for b in recent],
            total_bottles=total_bottles,
            total_prices=total_prices,
        )
    )


@router.get("/trending", response_model=APIResponse[dict])
async def get_trending_bottles(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get trending bottles by price movement."""
    service = BottleService(db)
    bottles = await service.get_trending_bottles(limit)

    return APIResponse(
        data={"bottles": [BottleListItem.model_validate(b) for b in bottles]}
    )


@router.get("/{bottle_id}", response_model=APIResponse[BottleDetail])
async def get_bottle(
    bottle_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get full details for a specific bottle."""
    service = BottleService(db)
    bottle = await service.get_bottle(bottle_id)

    if not bottle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Determine data quality
    if bottle.price_count >= 20:
        data_quality = "excellent"
    elif bottle.price_count >= 10:
        data_quality = "good"
    elif bottle.price_count >= 3:
        data_quality = "limited"
    else:
        data_quality = "insufficient"

    response_data = {
        **{k: getattr(bottle, k) for k in BottleDetail.model_fields
           if k not in ("aliases", "data_quality")},
        "aliases": [a.alias for a in bottle.aliases],
        "data_quality": data_quality,
    }

    return APIResponse(data=BottleDetail(**response_data))
```

**Estimated Time:** 4 hours

---

### Task 7: Chart Data Formatting

**File:** `src/services/price_service.py` (addition)

**Objective:** Add Chart.js compatible data formatting.

```python
# Add to PriceService class

def format_for_chartjs(
    self,
    aggregated: list[AggregatedPrice],
    show_range: bool = True,
) -> dict:
    """
    Format aggregated data for Chart.js.

    Returns structure compatible with Chart.js line chart.
    """
    if not aggregated:
        return {
            "labels": [],
            "datasets": [],
        }

    labels = [ap.period_label for ap in aggregated]
    avg_data = [round(ap.avg_price, 2) for ap in aggregated]

    datasets = [
        {
            "label": "Average Price",
            "data": avg_data,
            "borderColor": "rgb(59, 130, 246)",
            "backgroundColor": "rgba(59, 130, 246, 0.1)",
            "fill": False,
            "tension": 0.1,
        }
    ]

    if show_range:
        min_data = [round(ap.min_price, 2) for ap in aggregated]
        max_data = [round(ap.max_price, 2) for ap in aggregated]

        datasets.extend([
            {
                "label": "Min Price",
                "data": min_data,
                "borderColor": "rgb(156, 163, 175)",
                "borderDash": [5, 5],
                "fill": False,
                "tension": 0.1,
            },
            {
                "label": "Max Price",
                "data": max_data,
                "borderColor": "rgb(156, 163, 175)",
                "borderDash": [5, 5],
                "fill": False,
                "tension": 0.1,
            },
        ])

    return {
        "labels": labels,
        "datasets": datasets,
    }
```

**New Endpoint:**

```python
# src/api/routes/prices.py

@router.get("/bottle/{bottle_id}/chart", response_model=APIResponse[dict])
async def get_chart_data(
    bottle_id: int,
    days: int = Query(365, ge=7, le=1825),
    source: PriceSource | None = Query(None),
    show_range: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """
    Get price history formatted for Chart.js.

    Returns data structure ready to use with Chart.js line chart.
    """
    # Verify bottle exists
    from src.services.bottle_service import BottleService
    bottle_service = BottleService(db)
    bottle = await bottle_service.get_bottle(bottle_id)

    if not bottle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    price_service = PriceService(db)
    aggregated = await price_service.get_aggregated_history(
        bottle_id, days=days, source=source
    )

    chart_data = price_service.format_for_chartjs(aggregated, show_range)

    return APIResponse(
        data={
            "bottle_id": bottle_id,
            "bottle_name": bottle.name,
            "chart_data": chart_data,
            "data_points": len(aggregated),
            "period_days": days,
        }
    )
```

**Estimated Time:** 2 hours

---

### Task 8: Tests

**Files:** `tests/services/test_bottle_service.py`, `tests/services/test_price_service.py`, `tests/api/test_bottles.py`, `tests/api/test_prices.py`

**Test Coverage Requirements:**

| Component | Min Coverage |
|-----------|--------------|
| BottleService | 90% |
| PriceService | 90% |
| Bottle Routes | 85% |
| Price Routes | 85% |

**Key Test Scenarios:**

1. **Search Tests**
   - Empty query returns all bottles (paginated)
   - Text query matches name, distillery, aliases
   - Multiple filters combine correctly
   - Pagination works correctly
   - Sort orders work correctly

2. **Price History Tests**
   - Returns correct date range
   - Aggregation levels are correct
   - Empty results handled gracefully
   - Source filtering works

3. **Chart Data Tests**
   - Chart.js format is valid
   - Labels match data points
   - Range data included when requested

4. **Edge Cases**
   - Bottle with no prices
   - Bottle not found (404)
   - Invalid parameters (400)
   - Empty search results

**Estimated Time:** 4 hours

---

## File Summary

### New Files

| File | Purpose |
|------|---------|
| `src/services/base.py` | Base service class |
| `src/services/bottle_service.py` | Bottle business logic |
| `src/services/price_service.py` | Price business logic |
| `src/schemas/bottle.py` | Bottle schemas |
| `src/schemas/price.py` | Price schemas |
| `src/schemas/response.py` | Response envelope schemas |
| `tests/services/test_bottle_service.py` | Bottle service tests |
| `tests/services/test_price_service.py` | Price service tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/api/routes/bottles.py` | Use service layer, add endpoints |
| `src/api/routes/prices.py` | Use service layer, add chart endpoint |
| `src/services/__init__.py` | Export services |
| `src/schemas/__init__.py` | Export schemas |

---

## Timeline

| Day | Tasks | Hours |
|-----|-------|-------|
| 1 | Service layer setup, response envelope, schemas | 4 |
| 2 | BottleService implementation | 4 |
| 3 | PriceService implementation | 4 |
| 4 | Route handler updates | 4 |
| 5 | Chart data, homepage endpoint | 3 |
| 6 | Testing and refinement | 4 |
| **Total** | | **23 hours** |

---

## Quality Gates

Before marking Phase 3A complete:

- [ ] All new endpoints respond with envelope format
- [ ] Search returns relevant results within 500ms
- [ ] Autocomplete responds within 200ms
- [ ] Chart data validates in Chart.js
- [ ] Test coverage meets minimums
- [ ] No regressions in existing endpoints
- [ ] Empty states handled gracefully
- [ ] Error responses follow standard format

---

## Dependencies on Other Work

- **Required before starting:** Phase 2 complete (DONE)
- **Enables:** Phase 3B (Authentication), Phase 3C (Collections)
- **Integration point:** Homepage template will consume `/bottles/homepage`

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Performance with large datasets | Use cached stats on Bottle model |
| Chart data too large | Aggregation reduces data points |
| Search relevance poor | Can add pg_trgm extension later |
| Breaking existing API consumers | Version in URL (/api/v1/) |

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-31 | Jordan | Initial implementation plan |
