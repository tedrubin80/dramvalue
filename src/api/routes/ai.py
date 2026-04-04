"""
AI-powered endpoints using Perplexity.

Provides intelligent search, bottle research, and market insights.
All endpoints require authentication and are rate-limited to prevent API cost abuse.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.api.response import success_response
from src.models.user import User
from src.services.ai_service import get_ai_service

router = APIRouter()


class CompareRequest(BaseModel):
    """Request to compare multiple bottles."""
    bottles: list[str]


class ValueRequest(BaseModel):
    """Request for value estimation."""
    bottle_name: str
    condition: str = "good"
    has_box: bool = True


async def _ai_rate_check(request: Request):
    """Check AI endpoint rate limit: 10/hour per IP."""
    from src.main import limiter
    await limiter.check("10/hour", request)


@router.get("/search")
async def ai_search(
    request: Request,
    q: str = Query(..., min_length=2, description="Search query"),
    _user: User = Depends(get_current_user),
):
    """AI-enhanced whisky search."""
    await _ai_rate_check(request)
    try:
        service = get_ai_service()
        result = await service.search_whisky(q)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI search failed",
            )

        return success_response(data=result)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.get("/bottle-info")
async def get_bottle_info(
    request: Request,
    name: str = Query(..., min_length=2, description="Bottle name"),
    _user: User = Depends(get_current_user),
):
    """Get AI-researched information about a specific bottle."""
    await _ai_rate_check(request)
    try:
        service = get_ai_service()
        result = await service.get_bottle_info(name)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get bottle info",
            )

        return success_response(data=result)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.get("/market-analysis")
async def get_market_analysis(
    request: Request,
    category: str = Query("scotch whisky", description="Category to analyze"),
    _user: User = Depends(get_current_user),
):
    """Get AI-powered market analysis."""
    await _ai_rate_check(request)
    try:
        service = get_ai_service()
        result = await service.analyze_market(category)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Market analysis failed",
            )

        return success_response(data=result)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.post("/estimate-value")
async def estimate_value(
    request: Request,
    data: ValueRequest,
    _user: User = Depends(get_current_user),
):
    """Get AI-assisted value estimation for a bottle."""
    await _ai_rate_check(request)
    try:
        service = get_ai_service()
        result = await service.estimate_value(
            bottle_name=data.bottle_name,
            condition=data.condition,
            has_box=data.has_box,
        )

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Value estimation failed",
            )

        return success_response(data=result)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.get("/research")
async def research_topic(
    request: Request,
    topic: str = Query(..., min_length=5, description="Topic to research"),
    _user: User = Depends(get_current_user),
):
    """Research any whisky-related topic."""
    await _ai_rate_check(request)
    try:
        service = get_ai_service()
        result = await service.research_topic(topic)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Research failed",
            )

        return success_response(data=result)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.post("/compare")
async def compare_bottles(
    request: Request,
    data: CompareRequest,
    _user: User = Depends(get_current_user),
):
    """Compare multiple bottles using AI."""
    await _ai_rate_check(request)

    if len(data.bottles) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 bottles required for comparison",
        )

    if len(data.bottles) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 bottles can be compared at once",
        )

    try:
        service = get_ai_service()
        result = await service.compare_bottles(data.bottles)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Comparison failed",
            )

        return success_response(data=result)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )
