"""
Personal collection management endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_current_user
from src.db.session import get_db
from src.models.bottle import Bottle
from src.models.collection import Collection, CollectionItem
from src.models.user import User

router = APIRouter()


# =============================================================================
# Request/Response Schemas
# =============================================================================


class CollectionCreate(BaseModel):
    """Create a new collection."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class CollectionItemCreate(BaseModel):
    """Add a bottle to collection."""
    bottle_id: int
    quantity: int = Field(default=1, ge=1)
    purchase_price: float | None = Field(None, ge=0)
    purchase_date: datetime | None = None
    purchase_location: str | None = Field(None, max_length=255)
    notes: str | None = None


class CollectionItemResponse(BaseModel):
    """Collection item response."""
    id: int
    bottle_id: int
    bottle_name: str
    quantity: int
    purchase_price: float | None
    purchase_date: datetime | None
    current_value: float | None
    roi: float | None

    class Config:
        from_attributes = True


class CollectionResponse(BaseModel):
    """Collection response."""
    id: int
    name: str
    description: str | None
    total_bottles: int
    total_value: float | None
    created_at: datetime

    class Config:
        from_attributes = True


class CollectionDetailResponse(BaseModel):
    """Collection with items."""
    id: int
    name: str
    description: str | None
    total_bottles: int
    total_value: float | None
    items: list[CollectionItemResponse]

    class Config:
        from_attributes = True


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all collections for current user."""
    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == current_user.id)
        .order_by(Collection.created_at.desc())
    )
    collections = result.scalars().all()
    return [CollectionResponse.model_validate(c) for c in collections]


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    data: CollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new collection."""
    collection = Collection(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
async def get_collection(
    collection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get collection details with items."""
    result = await db.execute(
        select(Collection)
        .options(selectinload(Collection.items).selectinload(CollectionItem.bottle))
        .where(Collection.id == collection_id, Collection.user_id == current_user.id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    items = [
        CollectionItemResponse(
            id=item.id,
            bottle_id=item.bottle_id,
            bottle_name=item.bottle.name,
            quantity=item.quantity,
            purchase_price=item.purchase_price,
            purchase_date=item.purchase_date,
            current_value=item.current_value,
            roi=item.roi,
        )
        for item in collection.items
    ]

    return CollectionDetailResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        total_bottles=collection.total_bottles,
        total_value=collection.total_value,
        items=items,
    )


@router.post("/{collection_id}/items", response_model=CollectionItemResponse, status_code=status.HTTP_201_CREATED)
async def add_item_to_collection(
    collection_id: int,
    data: CollectionItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a bottle to a collection."""
    collection_result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id,
        )
    )
    collection = collection_result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    bottle_result = await db.execute(
        select(Bottle).where(Bottle.id == data.bottle_id, Bottle.is_active == True)
    )
    bottle = bottle_result.scalar_one_or_none()
    if not bottle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bottle not found")

    item = CollectionItem(
        collection_id=collection_id,
        bottle_id=data.bottle_id,
        quantity=data.quantity,
        purchase_price=data.purchase_price,
        purchase_date=data.purchase_date,
        purchase_location=data.purchase_location,
        notes=data.notes,
        current_value=bottle.avg_price,
    )
    db.add(item)

    collection.total_bottles += data.quantity
    if bottle.avg_price and data.quantity:
        collection.total_value = (collection.total_value or 0) + (bottle.avg_price * data.quantity)

    await db.commit()
    await db.refresh(item)

    return CollectionItemResponse(
        id=item.id,
        bottle_id=item.bottle_id,
        bottle_name=bottle.name,
        quantity=item.quantity,
        purchase_price=item.purchase_price,
        purchase_date=item.purchase_date,
        current_value=item.current_value,
        roi=item.roi,
    )


@router.delete("/{collection_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_collection(
    collection_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a bottle from a collection."""
    result = await db.execute(
        select(CollectionItem)
        .join(Collection)
        .where(
            CollectionItem.id == item_id,
            CollectionItem.collection_id == collection_id,
            Collection.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    await db.delete(item)
    await db.commit()
