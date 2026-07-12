"""
API route aggregation.
"""

from fastapi import APIRouter

from src.api.routes.ai import router as ai_router
from src.api.routes.alerts import router as alerts_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.auth import router as auth_router
from src.api.routes.bottles import router as bottles_router
from src.api.routes.collections import router as collections_router
from src.api.routes.dashboard import router as dashboard_router
from src.api.routes.export import router as export_router
from src.api.routes.feed import router as feed_router
from src.api.routes.health import router as health_router
from src.api.routes.portfolio import router as portfolio_router
from src.api.routes.prices import router as prices_router
from src.api.routes.recommendations import router as recommendations_router
from src.api.routes.submissions import router as submissions_router
from src.api.routes.admin.scraping import router as admin_scraping_router

router = APIRouter()

# Include all route modules
router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(ai_router, prefix="/ai", tags=["AI"])
router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(bottles_router, prefix="/bottles", tags=["Bottles"])
router.include_router(prices_router, prefix="/prices", tags=["Prices"])
router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
router.include_router(submissions_router, prefix="/submissions", tags=["Submissions"])
router.include_router(collections_router, prefix="/collections", tags=["Collections"])
router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
router.include_router(export_router, prefix="/export", tags=["Export"])
router.include_router(feed_router, prefix="/feed", tags=["Feed"])
router.include_router(portfolio_router, prefix="/portfolio", tags=["Portfolio"])
router.include_router(recommendations_router, prefix="/recommendations", tags=["Recommendations"])

# Admin routes
router.include_router(admin_scraping_router, prefix="/admin", tags=["Admin"])
