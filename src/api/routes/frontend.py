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
# Market Routes
# =============================================================================

@router.get("/market", response_class=HTMLResponse, name="market")
async def market_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Market overview page with auction trends."""
    from src.models.market_stat import MarketStat

    context = await get_template_context(request, db)

    # Summary stats
    total_volume_result = await db.execute(
        select(func.sum(MarketStat.trading_volume))
    )
    total_volume_raw = total_volume_result.scalar() or 0

    total_lots_result = await db.execute(
        select(func.sum(MarketStat.lots_count))
    )
    total_lots_raw = total_lots_result.scalar() or 0

    auction_count_result = await db.execute(
        select(func.count(func.distinct(MarketStat.auction_slug)))
    )
    auction_count = auction_count_result.scalar() or 0

    date_range_result = await db.execute(
        select(
            func.min(MarketStat.period_date),
            func.max(MarketStat.period_date),
        )
    )
    date_row = date_range_result.fetchone()
    min_date = date_row[0] if date_row else None
    max_date = date_row[1] if date_row else None

    months_result = await db.execute(
        select(func.count(func.distinct(MarketStat.period_date)))
    )
    months_tracked = months_result.scalar() or 0

    # Format summary
    if total_volume_raw >= 1_000_000_000:
        total_volume_str = f"${total_volume_raw / 1_000_000_000:.1f}B"
    elif total_volume_raw >= 1_000_000:
        total_volume_str = f"${total_volume_raw / 1_000_000:.0f}M"
    else:
        total_volume_str = f"${total_volume_raw:,.0f}"

    date_range_str = ""
    if min_date and max_date:
        date_range_str = f"{min_date.strftime('%b %Y')} - {max_date.strftime('%b %Y')}"

    context["total_volume"] = total_volume_str
    context["total_lots"] = f"{total_lots_raw:,}"
    context["auction_count"] = auction_count
    context["months_tracked"] = months_tracked
    context["date_range"] = date_range_str

    # Monthly aggregates for charts (sum across all auction houses per month)
    monthly_result = await db.execute(
        select(
            MarketStat.period_date,
            func.sum(MarketStat.trading_volume).label("volume"),
            func.avg(MarketStat.winning_bid_mean).label("avg_price"),
            func.sum(MarketStat.lots_count).label("lots"),
        )
        .group_by(MarketStat.period_date)
        .order_by(MarketStat.period_date)
    )
    monthly_rows = monthly_result.fetchall()

    context["chart_labels"] = [r.period_date.strftime("%b %Y") for r in monthly_rows]
    context["chart_volume"] = [round(float(r.volume), 2) for r in monthly_rows]
    context["chart_price"] = [round(float(r.avg_price), 2) for r in monthly_rows]
    context["chart_lots"] = [int(r.lots) for r in monthly_rows]

    # Auction houses ranked by volume
    houses_result = await db.execute(
        select(
            MarketStat.auction_name,
            func.sum(MarketStat.trading_volume).label("total_volume"),
            func.sum(MarketStat.lots_count).label("total_lots"),
            func.avg(MarketStat.winning_bid_mean).label("avg_bid"),
            func.max(MarketStat.winning_bid_max).label("max_bid"),
            func.count(MarketStat.id).label("months"),
        )
        .group_by(MarketStat.auction_name)
        .order_by(func.sum(MarketStat.trading_volume).desc())
    )

    context["auction_houses"] = [
        {
            "name": r.auction_name,
            "total_volume": f"{float(r.total_volume):,.0f}",
            "total_lots": f"{int(r.total_lots):,}",
            "avg_bid": f"{float(r.avg_bid):,.0f}",
            "max_bid": f"{float(r.max_bid):,.0f}",
            "months": r.months,
        }
        for r in houses_result
    ]

    return templates.TemplateResponse("market.html", context)


@router.get("/brands", response_class=HTMLResponse, name="brands")
async def brands_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    category: str = None,
    q: str = None,
    page: int = 1,
):
    """Browse whisky brands."""
    from src.models.bottle import SpiritCategory

    context = await get_template_context(request, db)
    per_page = 48

    # Base query - brands are bottles with brand field set
    query = select(Bottle).where(Bottle.brand.isnot(None)).where(Bottle.is_active == True)

    # Category filter
    if category:
        try:
            cat = SpiritCategory(category)
            query = query.where(Bottle.category == cat)
        except ValueError:
            pass
    context["selected_category"] = category

    # Search filter
    if q:
        query = query.where(Bottle.name.ilike(f"%{q}%"))
    context["search_query"] = q

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Get category counts for filter buttons
    cat_counts_result = await db.execute(
        select(Bottle.category, func.count(Bottle.id))
        .where(Bottle.brand.isnot(None))
        .where(Bottle.is_active == True)
        .group_by(Bottle.category)
        .order_by(func.count(Bottle.id).desc())
    )

    category_labels = {
        "scotch_single_malt": "Scotch",
        "bourbon": "Bourbon",
        "irish": "Irish",
        "japanese": "Japanese",
        "rye": "Rye",
        "scotch_blended": "Blended Scotch",
        "american_single_malt": "American Single Malt",
        "other": "Other",
    }

    context["categories"] = [
        {
            "value": row[0].value,
            "label": category_labels.get(row[0].value, row[0].value.replace("_", " ").title()),
            "count": row[1],
        }
        for row in cat_counts_result
    ]

    # Paginated results
    offset = (page - 1) * per_page
    query = query.order_by(Bottle.name).offset(offset).limit(per_page)
    result = await db.execute(query)
    bottles = result.scalars().all()

    context["brands"] = [
        {
            "id": b.id,
            "name": b.name,
            "category": b.category.value if b.category else "other",
            "price_count": b.price_count or 0,
        }
        for b in bottles
    ]
    context["total"] = total
    context["page"] = page
    context["per_page"] = per_page
    context["total_pages"] = (total + per_page - 1) // per_page

    return templates.TemplateResponse("brands.html", context)


# =============================================================================
# Bottle Routes
# =============================================================================

@router.get("/trending", response_class=HTMLResponse, name="trending")
async def trending_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Trending bottles page."""
    context = await get_template_context(request, db)

    # Get trending bottles (most activity in last 30 days)
    cutoff = datetime.utcnow() - timedelta(days=30)
    result = await db.execute(
        select(
            Bottle.id,
            Bottle.name,
            Bottle.category,
            Bottle.distillery,
            func.count(Price.id).label("recent_sales"),
            func.avg(Price.price_usd).label("avg_price"),
            func.min(Price.price_usd).label("min_price"),
            func.max(Price.price_usd).label("max_price"),
        )
        .join(Price, Price.bottle_id == Bottle.id)
        .where(Price.transaction_date >= cutoff)
        .group_by(Bottle.id)
        .order_by(func.count(Price.id).desc())
        .limit(50)
    )

    trending = []
    for row in result:
        trending.append({
            "id": row.id,
            "name": row.name,
            "category": row.category.value if row.category else "other",
            "distillery": row.distillery,
            "recent_sales": row.recent_sales,
            "avg_price": round(float(row.avg_price), 2) if row.avg_price else None,
            "min_price": round(float(row.min_price), 2) if row.min_price else None,
            "max_price": round(float(row.max_price), 2) if row.max_price else None,
        })

    context["trending_bottles"] = trending

    return templates.TemplateResponse("trending.html", context)


@router.get("/profile", response_class=HTMLResponse, name="profile")
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    """User profile page."""
    from fastapi.responses import RedirectResponse
    from src.models.collection import Collection
    from src.models.alert import PriceAlert

    context = await get_template_context(request, db)

    if not context.get("current_user"):
        return RedirectResponse(url="/auth/login?redirect=/profile", status_code=302)

    user = context["current_user"]

    # Get counts
    collections_count = await db.scalar(
        select(func.count(Collection.id)).where(Collection.user_id == user.id)
    )
    alerts_count = await db.scalar(
        select(func.count(PriceAlert.id)).where(PriceAlert.user_id == user.id)
    )

    context["collections_count"] = collections_count or 0
    context["alerts_count"] = alerts_count or 0

    return templates.TemplateResponse("profile.html", context)


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

@router.get("/alerts", response_class=HTMLResponse, name="alerts_list")
async def alerts_list(request: Request, db: AsyncSession = Depends(get_db)):
    """User's price alerts page."""
    from fastapi.responses import RedirectResponse
    from src.models.alert import PriceAlert, AlertStatus

    context = await get_template_context(request, db)

    # Require login
    if not context.get("current_user"):
        return RedirectResponse(url="/auth/login?redirect=/alerts", status_code=302)

    user = context["current_user"]

    # Get user's alerts
    result = await db.execute(
        select(PriceAlert, Bottle)
        .join(Bottle, PriceAlert.bottle_id == Bottle.id)
        .where(PriceAlert.user_id == user.id)
        .order_by(PriceAlert.created_at.desc())
    )

    alerts = []
    for alert, bottle in result:
        alerts.append({
            "id": alert.id,
            "bottle": bottle,
            "alert_type": alert.alert_type.value,
            "target_price": float(alert.target_price) if alert.target_price else None,
            "status": alert.status.value,
            "times_triggered": alert.times_triggered,
            "last_triggered_at": alert.last_triggered_at,
            "created_at": alert.created_at,
        })

    context["alerts"] = alerts
    context["alert_count"] = len(alerts)

    return templates.TemplateResponse("alerts/list.html", context)


@router.get("/collections", response_class=HTMLResponse, name="collections_list")
async def collections_list(request: Request, db: AsyncSession = Depends(get_db)):
    """User's collections page."""
    from fastapi.responses import RedirectResponse
    from src.models.collection import Collection, CollectionItem

    context = await get_template_context(request, db)

    # Require login
    if not context.get("current_user"):
        return RedirectResponse(url="/auth/login?redirect=/collections", status_code=302)

    user = context["current_user"]

    # Get user's collections with item counts
    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == user.id)
        .order_by(Collection.created_at.desc())
    )
    collections = result.scalars().all()

    context["collections"] = collections

    return templates.TemplateResponse("collections/list.html", context)


@router.get("/collections/{collection_id}", response_class=HTMLResponse, name="collection_detail")
async def collection_detail(request: Request, collection_id: int, db: AsyncSession = Depends(get_db)):
    """Collection detail page."""
    from fastapi.responses import RedirectResponse
    from fastapi import HTTPException
    from src.models.collection import Collection, CollectionItem

    context = await get_template_context(request, db)

    # Require login
    if not context.get("current_user"):
        return RedirectResponse(url=f"/auth/login?redirect=/collections/{collection_id}", status_code=302)

    user = context["current_user"]

    # Get collection and verify ownership
    result = await db.execute(
        select(Collection)
        .where(Collection.id == collection_id)
        .where(Collection.user_id == user.id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get collection items with bottle info
    items_result = await db.execute(
        select(CollectionItem, Bottle)
        .join(Bottle, CollectionItem.bottle_id == Bottle.id)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.created_at.desc())
    )

    items = []
    total_purchase = 0
    total_current = 0
    for item, bottle in items_result:
        items.append({
            "id": item.id,
            "bottle": bottle,
            "quantity": item.quantity,
            "purchase_price": float(item.purchase_price) if item.purchase_price else None,
            "current_value": float(item.current_value) if item.current_value else None,
            "purchase_date": item.purchase_date,
            "notes": item.notes,
        })
        if item.purchase_price:
            total_purchase += float(item.purchase_price) * item.quantity
        if item.current_value:
            total_current += float(item.current_value) * item.quantity

    context["collection"] = collection
    context["items"] = items
    context["total_purchase"] = total_purchase
    context["total_current"] = total_current
    context["gain_loss"] = total_current - total_purchase if total_purchase > 0 else 0

    return templates.TemplateResponse("collections/detail.html", context)


# =============================================================================
# Static Pages
# =============================================================================

@router.get("/about", response_class=HTMLResponse, name="about")
async def about_page(request: Request, db: AsyncSession = Depends(get_db)):
    """About page."""
    context = await get_template_context(request, db)

    # Get stats for the about page
    stats_result = await db.execute(
        select(func.count(Bottle.id).label("bottle_count"))
    )
    bottle_count = stats_result.scalar() or 0

    price_stats = await db.execute(
        select(func.count(Price.id).label("price_count"))
    )
    price_count = price_stats.scalar() or 0

    context["stats"] = {
        "bottle_count": f"{bottle_count:,}",
        "price_count": f"{price_count:,}",
        "source_count": "14",
    }

    return templates.TemplateResponse("about.html", context)


@router.get("/auth/reddit/callback", response_class=HTMLResponse, name="reddit_callback")
async def reddit_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    """
    Reddit OAuth callback endpoint.

    This is the redirect URL for Reddit app authorization.
    Reddit will redirect here after the user authorizes the app.
    """
    context = await get_template_context(request)

    if error:
        context["error"] = f"Reddit authorization failed: {error}"
        context["success"] = False
    elif code:
        # Store the authorization code for token exchange
        # In production, exchange this for access/refresh tokens
        context["success"] = True
        context["message"] = "Reddit authorization successful! You can close this window."
        context["code"] = code[:10] + "..."  # Show partial code for debugging
    else:
        context["error"] = "No authorization code received"
        context["success"] = False

    # Simple HTML response for the callback
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reddit Authorization - DramValue</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #fff;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
                background: rgba(255,255,255,0.1);
                border-radius: 12px;
                max-width: 400px;
            }}
            .success {{ color: #4ade80; }}
            .error {{ color: #f87171; }}
            h1 {{ color: #d4a574; margin-bottom: 1rem; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>DramValue</h1>
            {"<p class='success'>Authorization successful!</p>" if context.get("success") else f"<p class='error'>{context.get('error', 'Unknown error')}</p>"}
            <p style="color: #9ca3af; margin-top: 1rem;">You can close this window.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


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
