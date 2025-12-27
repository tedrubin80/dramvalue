"""
Moderation models for submission review and user management.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.models.submission import Submission
    from src.models.user import User


class ModerationFlag(str, enum.Enum):
    """Types of moderation flags."""
    PRICE_OUTLIER = "price_outlier"
    DUPLICATE_SUBMISSION = "duplicate_submission"
    SUSPICIOUS_ACCOUNT = "suspicious_account"
    BURST_ACTIVITY = "burst_activity"
    USER_DOMINANCE = "user_dominance"
    MANUAL_REVIEW = "manual_review"
    REPORTED_BY_USER = "reported_by_user"


class ModerationAction(str, enum.Enum):
    """Actions taken by moderators."""
    APPROVE = "approve"
    REJECT = "reject"
    ADJUST_WEIGHT = "adjust_weight"
    BAN_USER = "ban_user"
    WARN_USER = "warn_user"
    ESCALATE = "escalate"


class ModerationQueue(Base):
    """
    Queue of items requiring moderator review.

    Items are added automatically by fraud detection or manually flagged.
    """

    __tablename__ = "moderation_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # What's being reviewed
    submission_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Flag Information
    flag_type: Mapped[ModerationFlag] = mapped_column(
        Enum(ModerationFlag), nullable=False, index=True
    )
    flag_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    flag_details: Mapped[str | None] = mapped_column(Text)

    # Priority (higher = more urgent)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # Status
    is_resolved: Mapped[bool] = mapped_column(Integer, default=False, index=True)
    action_taken: Mapped[ModerationAction | None] = mapped_column(Enum(ModerationAction))
    resolution_notes: Mapped[str | None] = mapped_column(Text)

    # Assignment
    assigned_to_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Review
    reviewed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    submission: Mapped["Submission | None"] = relationship("Submission")
    flagged_user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])

    def __repr__(self) -> str:
        target = f"Submission#{self.submission_id}" if self.submission_id else f"User#{self.user_id}"
        return f"<ModerationQueue {self.flag_type.value} on {target}>"
