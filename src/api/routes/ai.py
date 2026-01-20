"""
AI-powered endpoints using Perplexity.

Provides intelligent search, bottle research, and market insights.
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from src.api.response import success_response
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


@router.get("/search")
async def ai_search(
    q: str = Query(..., min_length=2, description="Search query"),
):
    """
    AI-enhanced whisky search.

    Uses Perplexity AI to understand your query and provide intelligent
    results with context about matching bottles.
    """
    try:
        service = get_ai_service()
        result = await service.search_whisky(q)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "AI search failed"),
            )

        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.get("/bottle-info")
async def get_bottle_info(
    name: str = Query(..., min_length=2, description="Bottle name"),
):
    """
    Get AI-researched information about a specific bottle.

    Returns detailed information including tasting notes, history,
    and market context.
    """
    try:
        service = get_ai_service()
        result = await service.get_bottle_info(name)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to get bottle info"),
            )

        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.get("/market-analysis")
async def get_market_analysis(
    category: str = Query("scotch whisky", description="Category to analyze"),
):
    """
    Get AI-powered market analysis.

    Provides current trends, hot bottles, and investment insights
    for the specified category.
    """
    try:
        service = get_ai_service()
        result = await service.analyze_market(category)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Market analysis failed"),
            )

        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.post("/estimate-value")
async def estimate_value(request: ValueRequest):
    """
    Get AI-assisted value estimation for a bottle.

    Provides estimated price range, confidence level, and market context.
    """
    try:
        service = get_ai_service()
        result = await service.estimate_value(
            bottle_name=request.bottle_name,
            condition=request.condition,
            has_box=request.has_box,
        )

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Value estimation failed"),
            )

        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.get("/research")
async def research_topic(
    topic: str = Query(..., min_length=5, description="Topic to research"),
):
    """
    Research any whisky-related topic.

    General-purpose research endpoint for flexible queries about
    distilleries, regions, trends, retailers, etc.
    """
    try:
        service = get_ai_service()
        result = await service.research_topic(topic)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Research failed"),
            )

        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )


@router.post("/compare")
async def compare_bottles(request: CompareRequest):
    """
    Compare multiple bottles using AI.

    Provides side-by-side comparison of value, investment potential,
    and drinking quality.
    """
    if len(request.bottles) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 bottles required for comparison",
        )

    if len(request.bottles) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 bottles can be compared at once",
        )

    try:
        service = get_ai_service()
        result = await service.compare_bottles(request.bottles)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Comparison failed"),
            )

        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )
