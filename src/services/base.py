"""
Base service class providing common functionality for all services.
"""

from typing import TypeVar, Generic, Type
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseService(Generic[ModelType]):
    """
    Base service with common CRUD operations and utilities.

    All services inherit from this to get:
    - Database session management
    - Common query helpers
    - Pagination support
    """

    def __init__(self, db: AsyncSession, model: Type[ModelType]):
        self.db = db
        self.model = model

    async def get_by_id(self, id: int) -> ModelType | None:
        """Get a single record by ID."""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        """Get all records with pagination."""
        result = await self.db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self, query=None) -> int:
        """Count records matching a query."""
        if query is None:
            query = select(self.model)
        count_query = select(func.count()).select_from(query.subquery())
        return await self.db.scalar(count_query) or 0

    async def exists(self, id: int) -> bool:
        """Check if a record exists by ID."""
        result = await self.db.execute(
            select(func.count()).where(self.model.id == id)
        )
        return (result.scalar() or 0) > 0


class ServiceError(Exception):
    """Base exception for service layer errors."""

    def __init__(self, message: str, code: str = "SERVICE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(ServiceError):
    """Resource not found."""

    def __init__(self, resource: str, id: int | str):
        super().__init__(
            message=f"{resource} with id '{id}' not found",
            code="NOT_FOUND"
        )
        self.resource = resource
        self.id = id


class ValidationError(ServiceError):
    """Validation failed."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message=message, code="VALIDATION_ERROR")
        self.field = field
