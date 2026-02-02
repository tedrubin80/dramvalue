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

from src.core.security import decode_token
from src.db.session import get_db
from src.models.bottle import Bottle
from src.models.price import Price
from src.models.user import User

# Configure templates
templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter()


# =============================================================================
# Template Context Helpers
# =============================================================================

async def get_current_user_from_cookie(request: Request, db: AsyncSession) -> User | None:
    """
    Get current user from JWT cookie if present and valid.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if user and user.is_active and not user.is_banned:
            return user
    except Exception:
        pass

    return None


async def get_template_context(request: Request, db: AsyncSession = None) -> dict:
    """
    Get common context for all templates.
    Includes current_user from JWT cookie if authenticated.
    """
    current_user = None
    if db:
        current_user = await get_current_user_from_cookie(request, db)

    return {
        "request": request,
        "current_user": current_user,
    }


# =============================================================================
# Homepage Routes
# =============================================================================

@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """Homepage with search and trending bottles."""
    context = await get_template_context(request, db)

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
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Login page."""
    context = await get_template_context(request, db)

    # Redirect if already logged in
    if context.get("current_user"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=302)

    # Check for registration success message
    if request.query_params.get("registered"):
        context["messages"] = [("success", "Account created successfully! Please sign in.")]

    return templates.TemplateResponse("auth/login.html", context)


@router.get("/auth/register", response_class=HTMLResponse, name="register")
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Registration page."""
    context = await get_template_context(request, db)

    # Redirect if already logged in
    if context.get("current_user"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("auth/register.html", context)


# =============================================================================
# Bottle Routes
# =============================================================================

@router.get("/search", response_class=HTMLResponse, name="search_results")
async def search_results(
    request: Request,
    db: AsyncSession = Depends(get_db),
    q: str = "",
):
    """Search results page."""
    context = await get_template_context(request, db)
    context["search_query"] = q

    if not q or len(q) < 2:
        context["bottles"] = []
        context["error"] = "Please enter at least 2 characters to search"
        return templates.TemplateResponse("search.html", context)

    # Search bottles
    search_term = f"%{q.lower()}%"
    result = await db.execute(
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            Bottle.age_statement,
            func.count(Price.id).label("price_count"),
            func.avg(Price.price_usd).label("avg_price"),
        )
        .join(Price, Price.bottle_id == Bottle.id, isouter=True)
        .where(
            func.lower(Bottle.name).like(search_term)
            | func.lower(Bottle.distillery).like(search_term)
        )
        .group_by(Bottle.id)
        .order_by(func.count(Price.id).desc(), Bottle.name)
        .limit(50)
    )

    bottles = []
    for row in result:
        bottles.append({
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else "other",
            "distillery": row.distillery,
            "age_statement": row.age_statement,
            "price_count": row.price_count or 0,
            "avg_price": round(float(row.avg_price), 2) if row.avg_price else None,
        })

    context["bottles"] = bottles
    context["result_count"] = len(bottles)

    return templates.TemplateResponse("search.html", context)


@router.get("/bottles", response_class=HTMLResponse, name="bottles_list")
async def bottles_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    q: str = None,
    category: str = None,
    page: int = 1,
):
    """Bottle search and browse page."""
    context = await get_template_context(request, db)

    # Build query
    query = select(Bottle).where(Bottle.is_active == True)

    # Search filter
    if q:
        query = query.where(Bottle.name.ilike(f"%{q}%"))
        context["search_query"] = q

    # Category filter
    if category:
        from src.models.bottle import SpiritCategory
        try:
            cat = SpiritCategory(category)
            query = query.where(Bottle.category == cat)
            context["selected_category"] = category
        except ValueError:
            pass

    # Pagination
    per_page = 24
    offset = (page - 1) * per_page

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Get bottles with price stats
    query = query.order_by(Bottle.name).offset(offset).limit(per_page)
    result = await db.execute(query)
    bottles = result.scalars().all()

    # Get categories for filter
    from src.models.bottle import SpiritCategory
    context["categories"] = [c.value for c in SpiritCategory]

    context["bottles"] = bottles
    context["page"] = page
    context["per_page"] = per_page
    context["total"] = total
    context["total_pages"] = (total + per_page - 1) // per_page

    return templates.TemplateResponse("bottles/list.html", context)


@router.get("/bottles/{bottle_id}", response_class=HTMLResponse, name="bottle_detail")
async def bottle_detail(request: Request, bottle_id: int, db: AsyncSession = Depends(get_db)):
    """Bottle detail page with price chart."""
    from fastapi import HTTPException

    context = await get_template_context(request, db)

    # Fetch bottle
    result = await db.execute(select(Bottle).where(Bottle.id == bottle_id))
    bottle = result.scalar_one_or_none()

    if not bottle:
        raise HTTPException(status_code=404, detail="Bottle not found")

    # Get price history (last 50 prices)
    prices_result = await db.execute(
        select(Price)
        .where(Price.bottle_id == bottle_id)
        .order_by(Price.transaction_date.desc())
        .limit(50)
    )
    prices = prices_result.scalars().all()

    # Calculate stats
    if prices:
        price_values = [p.price_usd for p in prices if p.price_usd]
        context["stats"] = {
            "count": len(price_values),
            "avg": round(sum(price_values) / len(price_values), 2) if price_values else 0,
            "min": round(min(price_values), 2) if price_values else 0,
            "max": round(max(price_values), 2) if price_values else 0,
            "latest": round(price_values[0], 2) if price_values else 0,
        }
    else:
        context["stats"] = {"count": 0, "avg": 0, "min": 0, "max": 0, "latest": 0}

    # Get similar bottles (same category, similar name)
    similar_result = await db.execute(
        select(Bottle)
        .where(Bottle.category == bottle.category)
        .where(Bottle.id != bottle_id)
        .limit(6)
    )
    similar_bottles = similar_result.scalars().all()

    # Prepare chart data (JSON-safe)
    chart_data = {
        "prices": [float(p.price_usd) if p.price_usd else 0 for p in reversed(prices)],
        "dates": [p.transaction_date.strftime('%b %d') if p.transaction_date else '' for p in reversed(prices)],
    }

    context["bottle"] = bottle
    context["prices"] = prices
    context["similar_bottles"] = similar_bottles
    context["chart_data"] = chart_data

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
