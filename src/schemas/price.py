"""
Pydantic schemas for price-related API endpoints.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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


class PriceHistory(BaseModel):
    """Price history for a bottle."""
    bottle_id: int
    bottle_name: str
    prices: list[PricePoint]
    stats: dict[str, Any]


class SourceBreakdown(BaseModel):
    """Price statistics by source."""
    source: str
    count: int
    avg_price: float
    min_price: float
    max_price: float


class PriceStats(BaseModel):
    """Comprehensive price statistics."""
    bottle_id: int
    bottle_name: str
    count: int
    avg_price: float | None
    median_price: float | None
    min_price: float | None
    max_price: float | None
    std_dev: float | None
    trend_30d: float | None
    trend_90d: float | None
    sources: list[SourceBreakdown]
    last_updated: datetime | None


class ChartDataset(BaseModel):
    """Single dataset for Chart.js."""
    label: str
    data: list[Any]
    type: str = "line"
    borderColor: str | None = None
    backgroundColor: str | None = None
    fill: bool = False
    hidden: bool = False


class ChartData(BaseModel):
    """Chart.js compatible data format."""
    bottle_id: int
    bottle_name: str
    labels: list[str]
    datasets: list[ChartDataset]
    counts: list[int] = Field(default_factory=list)
    aggregation: str
    period_days: int


class DistributionBucket(BaseModel):
    """Price distribution bucket for histogram."""
    range_min: float
    range_max: float
    count: int
    label: str


class PriceDistribution(BaseModel):
    """Price distribution data."""
    bottle_id: int
    bottle_name: str
    buckets: list[DistributionBucket]
    min_price: float | None
    max_price: float | None
    total_count: int = 0


class RecentPrice(BaseModel):
    """Recent price activity item."""
    id: int
    bottle_id: int
    bottle_name: str
    price_usd: float
    source: str
    transaction_date: str
    created_at: str
