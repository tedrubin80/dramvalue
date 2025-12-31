"""
Pydantic schemas for bottle-related API endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.bottle import BottleSize, SpiritCategory


class BottleBase(BaseModel):
    """Base bottle fields."""
    name: str
    distillery: str | None = None
    brand: str | None = None
    category: SpiritCategory = SpiritCategory.OTHER
    age_statement: int | None = None
    proof: float | None = None
    size: BottleSize = BottleSize.ML_750
    release_year: int | None = None


class BottleListItem(BaseModel):
    """Bottle summary for list views."""
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

    # Related data
    aliases: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class BottleAutocomplete(BaseModel):
    """Lightweight autocomplete suggestion."""
    id: int
    name: str
    distillery: str | None
    category: str | None


class BottleTrending(BaseModel):
    """Trending bottle with activity data."""
    id: int
    name: str
    distillery: str | None
    category: SpiritCategory
    avg_price: float | None
    price_trend: float | None
    price_count: int
    last_price_date: datetime | None

    class Config:
        from_attributes = True


class CategoryStats(BaseModel):
    """Statistics for a spirit category."""
    category: str
    count: int
    avg_price: float | None


class DistilleryInfo(BaseModel):
    """Distillery with bottle count."""
    name: str
    count: int


class HomepageData(BaseModel):
    """Aggregated homepage data."""
    recently_updated: list[BottleListItem]
    trending_up: list[BottleTrending]
    trending_down: list[BottleTrending]
    category_stats: list[CategoryStats]
    total_bottles: int
    total_prices: int
