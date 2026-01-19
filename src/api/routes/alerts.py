"""
Price alert endpoints.

Allows authenticated users to create, manage, and track price alerts.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.response import success_response
from src.db.session import get_db
from src.models.alert import AlertStatus, AlertType, PriceAlert
from src.models.bottle import Bottle
from src.models.user import User

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class AlertCreate(BaseModel):
    """Schema for creating a price alert."""
    bottle_id: int
    alert_type: AlertType = AlertType.PRICE_BELOW
    target_price: Decimal | None = Field(None, ge=0)
    percentage_threshold: Decimal | None = Field(None, ge=1, le=100)
    currency: str = "USD"
    notify_email: bool = True
    note: str | None = None


class AlertUpdate(BaseModel):
    """Schema for updating a price alert."""
    target_price: Decimal | None = Field(None, ge=0)
    percentage_threshold: Decimal | None = Field(None, ge=1, le=100)
    status: AlertStatus | None = None
    notify_email: bool | None = None
    note: str | None = None


class AlertResponse(BaseModel):
    """Schema for alert response."""
    id: int
    bottle_id: int
    bottle_name: str
    alert_type: str
    target_price: float | None
    percentage_threshold: float | None
    currency: str
    status: str
    notify_email: bool
    note: str | None
    times_triggered: int
    last_triggered_at: datetime | None
    created_at: datetime


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
async def list_alerts(
    status_filter: AlertStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all alerts for the current user.
    """
    query = (
        select(PriceAlert, Bottle.name)
        .join(Bottle, PriceAlert.bottle_id == Bottle.id)
        .where(PriceAlert.user_id == current_user.id)
        .order_by(PriceAlert.created_at.desc())
    )

    if status_filter:
        query = query.where(PriceAlert.status == status_filter)

    # Count total
    count_query = select(func.count(PriceAlert.id)).where(
        PriceAlert.user_id == current_user.id
    )
    if status_filter:
        count_query = count_query.where(PriceAlert.status == status_filter)
    total = await db.scalar(count_query)

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))

    alerts = []
    for alert, bottle_name in result:
        alerts.append({
            "id": alert.id,
            "bottle_id": alert.bottle_id,
            "bottle_name": bottle_name,
            "alert_type": alert.alert_type.value,
            "target_price": float(alert.target_price) if alert.target_price else None,
            "percentage_threshold": float(alert.percentage_threshold) if alert.percentage_threshold else None,
            "currency": alert.currency,
            "status": alert.status.value,
            "notify_email": alert.notify_email,
            "note": alert.note,
            "times_triggered": alert.times_triggered,
            "last_triggered_at": alert.last_triggered_at.isoformat() if alert.last_triggered_at else None,
            "created_at": alert.created_at.isoformat(),
        })

    return success_response(
        data={"alerts": alerts},
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        },
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new price alert.
    """
    # Verify bottle exists
    bottle = await db.get(Bottle, alert_data.bottle_id)
    if not bottle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bottle not found",
        )

    # Validate alert type requirements
    if alert_data.alert_type in (AlertType.PRICE_BELOW, AlertType.PRICE_ABOVE):
        if alert_data.target_price is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target price required for this alert type",
            )
    elif alert_data.alert_type == AlertType.PRICE_CHANGE:
        if alert_data.percentage_threshold is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Percentage threshold required for price change alerts",
            )

    # Check for duplicate active alert
    existing = await db.scalar(
        select(PriceAlert.id).where(
            PriceAlert.user_id == current_user.id,
            PriceAlert.bottle_id == alert_data.bottle_id,
            PriceAlert.alert_type == alert_data.alert_type,
            PriceAlert.status == AlertStatus.ACTIVE,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active alert already exists for this bottle and type",
        )

    # Create alert
    alert = PriceAlert(
        user_id=current_user.id,
        bottle_id=alert_data.bottle_id,
        alert_type=alert_data.alert_type,
        target_price=alert_data.target_price,
        percentage_threshold=alert_data.percentage_threshold,
        currency=alert_data.currency,
        notify_email=alert_data.notify_email,
        note=alert_data.note,
    )

    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    return success_response(
        data={
            "alert": {
                "id": alert.id,
                "bottle_id": alert.bottle_id,
                "bottle_name": bottle.name,
                "alert_type": alert.alert_type.value,
                "target_price": float(alert.target_price) if alert.target_price else None,
                "status": alert.status.value,
                "created_at": alert.created_at.isoformat(),
            }
        },
        meta={"message": "Alert created successfully"},
    )


@router.get("/{alert_id}")
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get details of a specific alert.
    """
    result = await db.execute(
        select(PriceAlert, Bottle.name)
        .join(Bottle, PriceAlert.bottle_id == Bottle.id)
        .where(PriceAlert.id == alert_id, PriceAlert.user_id == current_user.id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    alert, bottle_name = row

    return success_response(
        data={
            "alert": {
                "id": alert.id,
                "bottle_id": alert.bottle_id,
                "bottle_name": bottle_name,
                "alert_type": alert.alert_type.value,
                "target_price": float(alert.target_price) if alert.target_price else None,
                "percentage_threshold": float(alert.percentage_threshold) if alert.percentage_threshold else None,
                "currency": alert.currency,
                "status": alert.status.value,
                "notify_email": alert.notify_email,
                "note": alert.note,
                "times_triggered": alert.times_triggered,
                "last_triggered_at": alert.last_triggered_at.isoformat() if alert.last_triggered_at else None,
                "last_triggered_price": float(alert.last_triggered_price) if alert.last_triggered_price else None,
                "created_at": alert.created_at.isoformat(),
                "updated_at": alert.updated_at.isoformat(),
            }
        }
    )


@router.patch("/{alert_id}")
async def update_alert(
    alert_id: int,
    update_data: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing alert.
    """
    alert = await db.scalar(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == current_user.id,
        )
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    # Update fields
    if update_data.target_price is not None:
        alert.target_price = update_data.target_price
    if update_data.percentage_threshold is not None:
        alert.percentage_threshold = update_data.percentage_threshold
    if update_data.status is not None:
        alert.status = update_data.status
    if update_data.notify_email is not None:
        alert.notify_email = update_data.notify_email
    if update_data.note is not None:
        alert.note = update_data.note

    await db.commit()
    await db.refresh(alert)

    return success_response(
        data={"alert_id": alert.id, "status": alert.status.value},
        meta={"message": "Alert updated successfully"},
    )


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete an alert.
    """
    alert = await db.scalar(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == current_user.id,
        )
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    await db.delete(alert)
    await db.commit()


@router.post("/{alert_id}/pause")
async def pause_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pause an active alert.
    """
    alert = await db.scalar(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == current_user.id,
        )
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    if alert.status != AlertStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active alerts can be paused",
        )

    alert.status = AlertStatus.PAUSED
    await db.commit()

    return success_response(
        data={"alert_id": alert.id, "status": alert.status.value},
        meta={"message": "Alert paused"},
    )


@router.post("/{alert_id}/resume")
async def resume_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resume a paused alert.
    """
    alert = await db.scalar(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == current_user.id,
        )
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    if alert.status != AlertStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only paused alerts can be resumed",
        )

    alert.status = AlertStatus.ACTIVE
    await db.commit()

    return success_response(
        data={"alert_id": alert.id, "status": alert.status.value},
        meta={"message": "Alert resumed"},
    )
