"""
Price alert model for WTracker.

Allows users to set alerts when bottles hit target prices.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.models.bottle import Bottle
    from src.models.user import User


class AlertType(str, Enum):
    """Type of price alert."""
    PRICE_BELOW = "price_below"  # Alert when price drops below target
    PRICE_ABOVE = "price_above"  # Alert when price rises above target
    ANY_SALE = "any_sale"  # Alert on any new sale
    PRICE_CHANGE = "price_change"  # Alert on significant price change (%)


class AlertStatus(str, Enum):
    """Status of an alert."""
    ACTIVE = "active"
    TRIGGERED = "triggered"
    PAUSED = "paused"
    EXPIRED = "expired"


class PriceAlert(Base):
    """
    Price alert for a specific bottle.

    Users can create alerts to be notified when:
    - Price drops below a target
    - Price rises above a target
    - Any new sale occurs
    - Price changes by a certain percentage
    """

    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Relationships
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bottle_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bottles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Alert configuration
    alert_type: Mapped[AlertType] = mapped_column(
        SQLEnum(AlertType),
        nullable=False,
        default=AlertType.PRICE_BELOW,
    )
    target_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,  # Not required for ANY_SALE type
    )
    percentage_threshold: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,  # Only for PRICE_CHANGE type
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
    )

    # Status
    status: Mapped[AlertStatus] = mapped_column(
        SQLEnum(AlertStatus),
        nullable=False,
        default=AlertStatus.ACTIVE,
    )

    # Notification preferences
    notify_email: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    notify_push: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Optional note
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Tracking
    times_triggered: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_triggered_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="price_alerts")
    bottle: Mapped["Bottle"] = relationship("Bottle", back_populates="price_alerts")

    def __repr__(self) -> str:
        return f"<PriceAlert {self.id}: {self.alert_type.value} for bottle {self.bottle_id}>"

    def is_triggered(self, current_price: Decimal, previous_price: Decimal | None = None) -> bool:
        """Check if alert should be triggered based on current price."""
        if self.status != AlertStatus.ACTIVE:
            return False

        if self.alert_type == AlertType.PRICE_BELOW:
            return self.target_price is not None and current_price <= self.target_price

        elif self.alert_type == AlertType.PRICE_ABOVE:
            return self.target_price is not None and current_price >= self.target_price

        elif self.alert_type == AlertType.ANY_SALE:
            return True

        elif self.alert_type == AlertType.PRICE_CHANGE:
            if previous_price is None or previous_price == 0 or self.percentage_threshold is None:
                return False
            change_pct = abs((current_price - previous_price) / previous_price * 100)
            return change_pct >= self.percentage_threshold

        return False
