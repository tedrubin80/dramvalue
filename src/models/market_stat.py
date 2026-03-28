"""
Market statistics model for tracking auction house aggregate data over time.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class MarketStat(Base):
    """
    Monthly aggregate auction market statistics per auction house.

    Used for market overview dashboards and trend analysis.
    Each row represents one auction house's performance for one month.
    """

    __tablename__ = "market_stats"
    __table_args__ = (
        UniqueConstraint("auction_slug", "period_date", name="uq_market_stat_slug_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Auction house identification
    auction_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    auction_slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Time period
    period_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Winning bid stats (in GBP)
    winning_bid_max: Mapped[float] = mapped_column(Float, nullable=False)
    winning_bid_min: Mapped[float] = mapped_column(Float, nullable=False)
    winning_bid_mean: Mapped[float] = mapped_column(Float, nullable=False)

    # Volume stats
    trading_volume: Mapped[float] = mapped_column(Float, nullable=False)
    lots_count: Mapped[int] = mapped_column(Integer, nullable=False)
    all_auctions_lots_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<MarketStat {self.auction_name} {self.period_date:%Y-%m}>"
