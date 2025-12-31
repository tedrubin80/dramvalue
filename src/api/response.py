"""
Standardized API response envelope.

All API responses follow this format for consistency:
{
    "success": true,
    "data": { ... },
    "meta": { "page": 1, "total": 100, ... },
    "error": null
}
"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_items: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there's a next page")
    has_prev: bool = Field(..., description="Whether there's a previous page")


class ErrorDetail(BaseModel):
    """Error information."""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    field: str | None = Field(None, description="Field that caused the error")
    details: dict[str, Any] | None = Field(None, description="Additional error details")


class ApiResponse(BaseModel, Generic[T]):
    """
    Standard API response envelope.

    All endpoints return this format for consistency.
    """
    success: bool = Field(..., description="Whether the request succeeded")
    data: T | None = Field(None, description="Response data")
    meta: dict[str, Any] | None = Field(None, description="Response metadata")
    error: ErrorDetail | None = Field(None, description="Error details if failed")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


def success_response(
    data: Any,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a successful response.

    Usage:
        return success_response({"bottles": bottles})
        return success_response(bottle, meta={"cached": True})
    """
    return {
        "success": True,
        "data": data,
        "meta": meta,
        "error": None,
        "timestamp": datetime.utcnow().isoformat(),
    }


def paginated_response(
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
    item_key: str = "items",
) -> dict[str, Any]:
    """
    Create a paginated response with metadata.

    Usage:
        return paginated_response(
            items=bottles,
            total=100,
            page=1,
            page_size=20,
            item_key="bottles"
        )
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    return {
        "success": True,
        "data": {item_key: items},
        "meta": {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            }
        },
        "error": None,
        "timestamp": datetime.utcnow().isoformat(),
    }


def error_response(
    code: str,
    message: str,
    field: str | None = None,
    details: dict[str, Any] | None = None,
    status_code: int = 400,
) -> dict[str, Any]:
    """
    Create an error response.

    Usage:
        return error_response("NOT_FOUND", "Bottle not found")
        return error_response("VALIDATION_ERROR", "Invalid price", field="price")
    """
    return {
        "success": False,
        "data": None,
        "meta": None,
        "error": {
            "code": code,
            "message": message,
            "field": field,
            "details": details,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
