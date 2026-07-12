"""
Price model for tracking transaction data.
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
    from src.models.bottle import Bottle
    from src.models.submission import Submission


class PriceSource(str, enum.Enum):
    """Source of price data - affects trust weighting."""
    AUCTION = "auction"           # Highest trust - verifiable public records
    RETAIL = "retail"             # High trust - public retail listings
    CROWDSOURCED = "crowdsourced" # Variable trust - user submissions
    IMPORT = "import"             # Bulk import from verified dataset


class AuctionHouse(str, enum.Enum):
    """Known auction houses for data sourcing."""
    UNICORN = "unicorn_auctions"
    WHISKY_AUCTIONEER = "whisky_auctioneer"
    SCOTCH_WHISKY_AUCTIONS = "scotch_whisky_auctions"
    WHISKY_AUCTION_UK = "whisky_auction_uk"
    WHISKYAUCTION_COM = "whiskyauction_com"
    WHISKY_HAMMER = "whisky_hammer"
    WHISKY_HUNTER = "whisky_hunter"
    BOTTLE_BLUE_BOOK = "bottle_blue_book"
    WHISKYSTATS = "whiskystats"
    RARE_WHISKY_101 = "rare_whisky_101"
    SOTHEBYS = "sothebys"
    CHRISTIES = "christies"
    OTHER = "other"


class Price(Base):
    """
    Price record representing a single transaction or listing.

    Trust weighting:
    - Auction data: highest weight (verifiable, timestamped)
    - Retail: high weight (public, verifiable)
    - Crowdsourced: weighted by submitter trust score
    """

    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Reference
    bottle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bottles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submission_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("submissions.id", ondelete="SET NULL"), index=True
    )

    # Price Data
    price: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    price_usd: Mapped[float] = mapped_column(Float, nullable=False, index=True)  # normalized

    # Source Information
    source: Mapped[PriceSource] = mapped_column(
        Enum(PriceSource), nullable=False, index=True
    )
    source_name: Mapped[str | None] = mapped_column(String(255))  # specific source name
    auction_house: Mapped[AuctionHouse | None] = mapped_column(Enum(AuctionHouse))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_id: Mapped[str | None] = mapped_column(String(255))  # external ID for dedup

    # Transaction Details
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    is_sold: Mapped[bool] = mapped_column(Boolean, default=True)  # vs listed/asking
    includes_fees: Mapped[bool] = mapped_column(Boolean, default=True)  # buyer's premium

    # Trust & Quality
    confidence_weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(500))

    # Notes
    notes: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    bottle: Mapped["Bottle"] = relationship("Bottle", back_populates="prices")
    submission: Mapped["Submission | None"] = relationship(
        "Submission", back_populates="price"
    )

    def __repr__(self) -> str:
        return f"<Price ${self.price_usd:.2f} for Bottle#{self.bottle_id}>"
