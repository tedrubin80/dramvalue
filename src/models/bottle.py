"""
Bottle model for the spirits database.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.models.alert import PriceAlert
    from src.models.price import Price


class SpiritCategory(str, enum.Enum):
    """Spirit category enumeration."""
    BOURBON = "bourbon"
    RYE = "rye"
    SCOTCH_SINGLE_MALT = "scotch_single_malt"
    SCOTCH_BLENDED = "scotch_blended"
    IRISH = "irish"
    JAPANESE = "japanese"
    AMERICAN_SINGLE_MALT = "american_single_malt"
    OTHER = "other"


class BottleSize(str, enum.Enum):
    """Standard bottle sizes."""
    ML_50 = "50ml"
    ML_200 = "200ml"
    ML_375 = "375ml"
    ML_700 = "700ml"
    ML_750 = "750ml"
    ML_1000 = "1000ml"
    ML_1750 = "1750ml"
    OTHER = "other"


class Bottle(Base):
    """
    Bottle model representing a specific spirit release.

    Normalized naming with alias support for variations like
    "BT Stagg" vs "George T. Stagg".
    """

    __tablename__ = "bottles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, unique=True
    )
    distillery: Mapped[str | None] = mapped_column(String(255), index=True)
    brand: Mapped[str | None] = mapped_column(String(255), index=True)

    # Classification
    category: Mapped[SpiritCategory] = mapped_column(
        Enum(SpiritCategory), default=SpiritCategory.OTHER, index=True
    )

    # Details
    age_statement: Mapped[int | None] = mapped_column(Integer)  # in years, null = NAS
    proof: Mapped[float | None] = mapped_column(Float)
    size: Mapped[BottleSize] = mapped_column(
        Enum(BottleSize), default=BottleSize.ML_750
    )
    size_ml: Mapped[int | None] = mapped_column(Integer)  # actual ml for "other" sizes

    # Release Information
    release_year: Mapped[int | None] = mapped_column(Integer, index=True)
    batch_number: Mapped[str | None] = mapped_column(String(100))
    is_limited_release: Mapped[bool] = mapped_column(Boolean, default=False)
    is_allocated: Mapped[bool] = mapped_column(Boolean, default=False)

    # Retail reference
    msrp: Mapped[float | None] = mapped_column(Float)  # manufacturer suggested retail

    # Description
    description: Mapped[str | None] = mapped_column(Text)
    tasting_notes: Mapped[str | None] = mapped_column(Text)

    # Computed/Cached Statistics (updated by background jobs)
    price_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[float | None] = mapped_column(Float)
    min_price: Mapped[float | None] = mapped_column(Float)
    max_price: Mapped[float | None] = mapped_column(Float)
    last_price: Mapped[float | None] = mapped_column(Float)
    last_price_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_trend: Mapped[float | None] = mapped_column(Float)  # % change over 90 days
    confidence_score: Mapped[float | None] = mapped_column(Float)  # 0-1, based on data

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    stats_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    prices: Mapped[list["Price"]] = relationship(
        "Price", back_populates="bottle", lazy="dynamic"
    )
    aliases: Mapped[list["BottleAlias"]] = relationship(
        "BottleAlias", back_populates="bottle", lazy="selectin"
    )
    price_alerts: Mapped[list["PriceAlert"]] = relationship(
        "PriceAlert", back_populates="bottle", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Bottle {self.name} ({self.category.value})>"


class BottleAlias(Base):
    """
    Alias names for bottles to handle naming variations.

    Examples:
    - "BT Stagg" -> "George T. Stagg"
    - "BTAC Stagg" -> "George T. Stagg"
    - "Pappy 15" -> "Pappy Van Winkle 15 Year"
    """

    __tablename__ = "bottle_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    bottle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bottles.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_alias: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, unique=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    bottle: Mapped["Bottle"] = relationship("Bottle", back_populates="aliases")

    def __repr__(self) -> str:
        return f"<BottleAlias {self.alias} -> Bottle#{self.bottle_id}>"
