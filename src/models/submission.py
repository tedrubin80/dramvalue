"""
Submission model for crowdsourced price data.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.models.price import Price
    from src.models.user import User


class SubmissionStatus(str, enum.Enum):
    """Status of a crowdsourced submission."""
    PENDING = "pending"       # Awaiting review
    APPROVED = "approved"     # Accepted into dataset
    REJECTED = "rejected"     # Rejected by moderator
    AUTO_FLAGGED = "auto_flagged"  # Flagged by fraud detection


class SubmissionFlag(str, enum.Enum):
    """Fraud detection flags."""
    PRICE_OUTLIER = "price_outlier"           # >2 std dev from mean
    DUPLICATE_EXACT = "duplicate_exact"        # Same price submitted multiple times
    NEW_ACCOUNT_VOLUME = "new_account_volume"  # Too many submissions too fast
    BURST_SUBMISSION = "burst_submission"      # Many in short window
    ROUND_NUMBER = "round_number"              # Always round numbers
    USER_DOMINANCE = "user_dominance"          # Single user dominates bottle data


class Submission(Base):
    """
    User-submitted price data before verification.

    Submissions go through fraud detection and may require
    moderator approval before affecting price averages.
    """

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Reference
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bottle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bottles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Submitted Data
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_description: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    # Status & Review
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.PENDING, index=True
    )

    # Fraud Detection
    flags: Mapped[str | None] = mapped_column(String(500))  # comma-separated flags
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    fraud_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Trust Weight (computed from user trust + submission quality)
    computed_weight: Mapped[float] = mapped_column(Float, default=1.0)

    # Moderation
    reviewed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="submissions", foreign_keys=[user_id])
    price: Mapped["Price | None"] = relationship("Price", back_populates="submission", uselist=False)

    def __repr__(self) -> str:
        return f"<Submission ${self.price:.2f} by User#{self.user_id} ({self.status.value})>"

    def add_flag(self, flag: SubmissionFlag) -> None:
        """Add a fraud detection flag."""
        current_flags = set(self.flags.split(",")) if self.flags else set()
        current_flags.add(flag.value)
        current_flags.discard("")  # remove empty strings
        self.flags = ",".join(sorted(current_flags))

    def has_flag(self, flag: SubmissionFlag) -> bool:
        """Check if submission has a specific flag."""
        if not self.flags:
            return False
        return flag.value in self.flags.split(",")

    @property
    def flag_list(self) -> list[str]:
        """Get list of all flags."""
        if not self.flags:
            return []
        return [f for f in self.flags.split(",") if f]
