"""
Collection model for personal bottle tracking.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.models.bottle import Bottle
    from src.models.user import User


class Collection(Base):
    """
    User's personal bottle collection.

    Users can have multiple collections (e.g., "Cellar", "Daily Drinkers").
    """

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Cached Statistics (updated when items change)
    total_bottles: Mapped[int] = mapped_column(Integer, default=0)
    total_value: Mapped[float | None] = mapped_column(Float)
    value_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="collections")
    items: Mapped[list["CollectionItem"]] = relationship(
        "CollectionItem", back_populates="collection", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Collection '{self.name}' by User#{self.user_id}>"


class CollectionItem(Base):
    """
    Individual bottle in a user's collection.

    Tracks purchase price for ROI calculation and quantity for duplicates.
    """

    __tablename__ = "collection_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    collection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bottle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bottles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Ownership Details
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    purchase_price: Mapped[float | None] = mapped_column(Float)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchase_location: Mapped[str | None] = mapped_column(String(255))

    # Current Valuation (updated periodically)
    current_value: Mapped[float | None] = mapped_column(Float)
    value_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    collection: Mapped["Collection"] = relationship("Collection", back_populates="items")
    bottle: Mapped["Bottle"] = relationship("Bottle")

    def __repr__(self) -> str:
        return f"<CollectionItem Bottle#{self.bottle_id} x{self.quantity}>"

    @property
    def roi(self) -> float | None:
        """Calculate return on investment."""
        if self.purchase_price and self.current_value:
            return ((self.current_value - self.purchase_price) / self.purchase_price) * 100
        return None

    @property
    def total_purchase_value(self) -> float | None:
        """Total purchase value including quantity."""
        if self.purchase_price:
            return self.purchase_price * self.quantity
        return None

    @property
    def total_current_value(self) -> float | None:
        """Total current value including quantity."""
        if self.current_value:
            return self.current_value * self.quantity
        return None
