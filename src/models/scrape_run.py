"""
ScrapeRun model for tracking scraping operations.

Records the history and statistics of each spider run for
monitoring, debugging, and auditing purposes.
"""

import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class ScrapeStatus(str, enum.Enum):
    """Status of a scrape run."""
    PENDING = "pending"       # Queued but not started
    RUNNING = "running"       # Currently executing
    COMPLETED = "completed"   # Finished successfully
    FAILED = "failed"         # Finished with errors
    CANCELLED = "cancelled"   # Manually stopped


class ScrapeRun(Base):
    """
    Record of a scraping operation.

    Tracks each spider run for monitoring, debugging, and auditing.
    Used by health checks to determine scraper status.
    """

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Source identification
    source_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    spider_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Status
    status: Mapped[ScrapeStatus] = mapped_column(
        Enum(ScrapeStatus), default=ScrapeStatus.PENDING, index=True
    )

    # Item statistics
    items_scraped: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, default=0)
    items_errored: Mapped[int] = mapped_column(Integer, default=0)

    # Error tracking
    errors: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    # Request statistics
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(Integer, default=0)

    # Trigger information
    triggered_by: Mapped[str] = mapped_column(
        String(50), default="schedule"
    )  # 'schedule', 'manual', 'api'
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self) -> str:
        return f"<ScrapeRun {self.source_name} ({self.status.value})>"

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate run duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_running(self) -> bool:
        """Check if run is still in progress."""
        return self.status in (ScrapeStatus.PENDING, ScrapeStatus.RUNNING)

    @property
    def is_finished(self) -> bool:
        """Check if run has finished (success or failure)."""
        return self.status in (ScrapeStatus.COMPLETED, ScrapeStatus.FAILED, ScrapeStatus.CANCELLED)

    @property
    def success_rate(self) -> Optional[float]:
        """Calculate success rate as percentage."""
        total = self.items_scraped + self.items_errored
        if total > 0:
            return (self.items_scraped / total) * 100
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "source_name": self.source_name,
            "spider_name": self.spider_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "items_scraped": self.items_scraped,
            "items_new": self.items_new,
            "items_updated": self.items_updated,
            "items_skipped": self.items_skipped,
            "items_errored": self.items_errored,
            "success_rate": self.success_rate,
            "triggered_by": self.triggered_by,
            "errors": self.errors or [],
        }
