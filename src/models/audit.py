"""
Audit log for tracking all significant actions.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class AuditAction(str, enum.Enum):
    """Types of auditable actions."""
    # User actions
    USER_REGISTER = "user_register"
    USER_LOGIN = "user_login"
    USER_VERIFY_EMAIL = "user_verify_email"
    USER_UPDATE_PROFILE = "user_update_profile"
    USER_CHANGE_PASSWORD = "user_change_password"

    # Submission actions
    SUBMISSION_CREATE = "submission_create"
    SUBMISSION_APPROVE = "submission_approve"
    SUBMISSION_REJECT = "submission_reject"
    SUBMISSION_AUTO_FLAG = "submission_auto_flag"

    # Moderation actions
    MOD_APPROVE = "mod_approve"
    MOD_REJECT = "mod_reject"
    MOD_ADJUST_WEIGHT = "mod_adjust_weight"
    MOD_BAN_USER = "mod_ban_user"
    MOD_UNBAN_USER = "mod_unban_user"
    MOD_WARN_USER = "mod_warn_user"

    # Collection actions
    COLLECTION_CREATE = "collection_create"
    COLLECTION_ADD_ITEM = "collection_add_item"
    COLLECTION_REMOVE_ITEM = "collection_remove_item"

    # Admin actions
    ADMIN_CREATE_BOTTLE = "admin_create_bottle"
    ADMIN_UPDATE_BOTTLE = "admin_update_bottle"
    ADMIN_DELETE_BOTTLE = "admin_delete_bottle"
    ADMIN_IMPORT_DATA = "admin_import_data"
    ADMIN_UPDATE_USER_ROLE = "admin_update_user_role"

    # System actions
    SYSTEM_PRICE_IMPORT = "system_price_import"
    SYSTEM_STATS_UPDATE = "system_stats_update"
    SYSTEM_FORECAST_RUN = "system_forecast_run"


class AuditLog(Base):
    """
    Immutable audit log for all significant actions.

    Provides complete accountability for moderation,
    data changes, and security events.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Who
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    user_display_name: Mapped[str | None] = mapped_column(String(50))  # denormalized for history

    # What
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction), nullable=False, index=True
    )

    # Target
    target_type: Mapped[str | None] = mapped_column(String(50), index=True)  # e.g., "user", "submission"
    target_id: Mapped[int | None] = mapped_column(Integer, index=True)

    # Details
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)  # JSON for structured data
    old_value: Mapped[str | None] = mapped_column(Text)  # JSON of previous state
    new_value: Mapped[str | None] = mapped_column(Text)  # JSON of new state

    # Context
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(String(500))

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action.value} by User#{self.user_id}>"
