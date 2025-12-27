"""
Price submission endpoints for crowdsourced data.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.db.session import get_db
from src.models.bottle import Bottle
from src.models.submission import Submission, SubmissionStatus
from src.models.user import User

router = APIRouter()


# =============================================================================
# Request/Response Schemas
# =============================================================================


class SubmissionCreate(BaseModel):
    """Create a new price submission."""
    bottle_id: int
    price: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=3)
    transaction_date: datetime
    source_description: str | None = Field(None, max_length=500)
    notes: str | None = None


class SubmissionResponse(BaseModel):
    """Submission response."""
    id: int
    bottle_id: int
    price: float
    currency: str
    transaction_date: datetime
    status: SubmissionStatus
    confidence_score: float
    created_at: datetime

    class Config:
        from_attributes = True


class SubmissionListResponse(BaseModel):
    """List of user's submissions."""
    items: list[SubmissionResponse]
    total: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(
    data: SubmissionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a price report.

    - Requires email verification
    - Subject to fraud detection
    - May be queued for moderation
    """
    # Check submission privileges
    if not current_user.can_submit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required to submit prices",
        )

    # Verify bottle exists
    bottle_result = await db.execute(
        select(Bottle).where(Bottle.id == data.bottle_id, Bottle.is_active == True)
    )
    bottle = bottle_result.scalar_one_or_none()
    if not bottle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # TODO: Run fraud detection
    # - Check for price outliers
    # - Check submission velocity
    # - Check for duplicate submissions

    # Create submission
    submission = Submission(
        user_id=current_user.id,
        bottle_id=data.bottle_id,
        price=data.price,
        currency=data.currency,
        transaction_date=data.transaction_date,
        source_description=data.source_description,
        notes=data.notes,
        confidence_score=current_user.trust_score / 100,  # Normalize to 0-1
    )

    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return submission


@router.get("/me", response_model=SubmissionListResponse)
async def get_my_submissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user's submissions.
    """
    result = await db.execute(
        select(Submission)
        .where(Submission.user_id == current_user.id)
        .order_by(Submission.created_at.desc())
    )
    submissions = result.scalars().all()

    return SubmissionListResponse(
        items=[SubmissionResponse.model_validate(s) for s in submissions],
        total=len(submissions),
    )


@router.get("/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific submission (own submissions only for regular users).
    """
    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )

    # Only allow viewing own submissions (or moderator access)
    if submission.user_id != current_user.id and not current_user.is_moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return submission
