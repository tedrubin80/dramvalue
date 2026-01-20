"""
Frontend template routes.

Serves HTML templates using Jinja2 for server-side rendering.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.bottle import Bottle
from src.models.price import Price

# Configure templates
templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter()


# =============================================================================
# Template Context Helpers
# =============================================================================

async def get_template_context(request: Request) -> dict:
    """
    Get common context for all templates.

    TODO: Add current_user from JWT token when authentication middleware is added.
    """
    return {
        "request": request,
        "current_user": None,  # Will be populated by auth middleware
    }


# =============================================================================
# Homepage Routes
# =============================================================================

@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """Homepage with search and trending bottles."""
    context = await get_template_context(request)

    # Get real stats from database
    stats_result = await db.execute(
        select(
            func.count(Bottle.id).label("bottle_count"),
        )
    )
    bottle_count = stats_result.scalar() or 0

    price_stats = await db.execute(
        select(
            func.count(Price.id).label("price_count"),
            func.count(func.distinct(Price.bottle_id)).label("bottles_with_prices"),
        )
    )
    price_row = price_stats.fetchone()

    context["stats"] = {
        "bottle_count": bottle_count,
        "price_count": price_row.price_count if price_row else 0,
        "bottles_with_prices": price_row.bottles_with_prices if price_row else 0,
    }

    # Get trending bottles (most price data in last 30 days)
    cutoff = datetime.utcnow() - timedelta(days=30)
    trending_result = await db.execute(
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            func.count(Price.id).label("recent_sales"),
            func.avg(Price.price_usd).label("avg_price"),
        )
        .join(Price, Price.bottle_id == Bottle.id)
        .where(Price.transaction_date >= cutoff)
        .group_by(Bottle.id)
        .order_by(func.count(Price.id).desc())
        .limit(6)
    )
    trending_rows = trending_result.fetchall()

    context["trending_bottles"] = [
        {
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else "spirits",
            "recent_sales": row.recent_sales,
            "avg_price": round(float(row.avg_price), 2) if row.avg_price else None,
        }
        for row in trending_rows
    ]

    return templates.TemplateResponse("home.html", context)


# =============================================================================
# Authentication Routes
# =============================================================================

@router.get("/auth/login", response_class=HTMLResponse, name="login")
async def login_page(request: Request):
    """Login page."""
    context = await get_template_context(request)

    # Check for registration success message
    if request.query_params.get("registered"):
        context["messages"] = [("success", "Account created successfully! Please sign in.")]

    return templates.TemplateResponse("auth/login.html", context)


@router.get("/auth/register", response_class=HTMLResponse, name="register")
async def register_page(request: Request):
    """Registration page."""
    context = await get_template_context(request)
    return templates.TemplateResponse("auth/register.html", context)


# =============================================================================
# Bottle Routes
# =============================================================================

@router.get("/bottles", response_class=HTMLResponse, name="bottles_list")
async def bottles_list(request: Request):
    """Bottle search and browse page."""
    context = await get_template_context(request)
    # TODO: Implement bottle list template
    return templates.TemplateResponse("bottles/list.html", context)


@router.get("/bottles/{bottle_id}", response_class=HTMLResponse, name="bottle_detail")
async def bottle_detail(request: Request, bottle_id: int):
    """Bottle detail page with price chart."""
    context = await get_template_context(request)
    context["bottle_id"] = bottle_id
    # TODO: Implement bottle detail template
    return templates.TemplateResponse("bottles/detail.html", context)


# =============================================================================
# Collection Routes (Protected)
# =============================================================================

@router.get("/collections", response_class=HTMLResponse, name="collections_list")
async def collections_list(request: Request):
    """User's collections page."""
    context = await get_template_context(request)
    # TODO: Add authentication check
    # TODO: Implement collections list template
    return templates.TemplateResponse("collections/list.html", context)


@router.get("/collections/{collection_id}", response_class=HTMLResponse, name="collection_detail")
async def collection_detail(request: Request, collection_id: int):
    """Collection detail page."""
    context = await get_template_context(request)
    context["collection_id"] = collection_id
    # TODO: Add authentication check
    # TODO: Implement collection detail template
    return templates.TemplateResponse("collections/detail.html", context)


# =============================================================================
# User Profile Routes (Protected)
# =============================================================================

@router.get("/profile", response_class=HTMLResponse, name="profile")
async def profile_page(request: Request):
    """User profile page."""
    context = await get_template_context(request)
    # TODO: Add authentication check
    # TODO: Implement profile template
    return templates.TemplateResponse("profile.html", context)


# =============================================================================
# Static Pages
# =============================================================================

@router.get("/about", response_class=HTMLResponse, name="about")
async def about_page(request: Request):
    """About page."""
    context = await get_template_context(request)
    # TODO: Implement about template
    return {"message": "About page - coming soon"}


@router.get("/terms", response_class=HTMLResponse, name="terms")
async def terms_page(request: Request):
    """Terms of service page."""
    context = await get_template_context(request)
    # TODO: Implement terms template
    return {"message": "Terms page - coming soon"}


@router.get("/privacy", response_class=HTMLResponse, name="privacy")
async def privacy_page(request: Request):
    """Privacy policy page."""
    context = await get_template_context(request)
    # TODO: Implement privacy template
    return {"message": "Privacy page - coming soon"}
