"""
User model for authentication and trust scoring.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.models.collection import Collection
    from src.models.submission import Submission


class UserRole(str, enum.Enum):
    """User role enumeration."""
    USER = "user"
    VERIFIED = "verified"
    MODERATOR = "moderator"
    ADMIN = "admin"


class User(Base):
    """
    User model for pseudonymous authentication.

    Privacy-first design:
    - Display name is public, email is admin-only
    - Trust score tracks submission reliability
    - No real identity required
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Authentication
    display_name: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Verification & Role
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.USER, nullable=False
    )

    # Trust System
    trust_score: Mapped[float] = mapped_column(Float, default=50.0)
    total_submissions: Mapped[int] = mapped_column(Integer, default=0)
    approved_submissions: Mapped[int] = mapped_column(Integer, default=0)
    rejected_submissions: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    submissions: Mapped[list["Submission"]] = relationship(
        "Submission", back_populates="user", lazy="dynamic",
        foreign_keys="[Submission.user_id]"
    )
    collections: Mapped[list["Collection"]] = relationship(
        "Collection", back_populates="user", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<User {self.display_name} (trust: {self.trust_score:.1f})>"

    @property
    def is_verified(self) -> bool:
        """Check if user has verified email."""
        return self.email_verified

    @property
    def can_submit(self) -> bool:
        """Check if user can submit price data."""
        return self.email_verified and self.is_active and not self.is_banned

    @property
    def is_moderator(self) -> bool:
        """Check if user has moderation privileges."""
        return self.role in (UserRole.MODERATOR, UserRole.ADMIN)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.role == UserRole.ADMIN
