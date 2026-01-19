"""
API route aggregation.
"""

from fastapi import APIRouter

from src.api.routes.analytics import router as analytics_router
from src.api.routes.auth import router as auth_router
from src.api.routes.bottles import router as bottles_router
from src.api.routes.collections import router as collections_router
from src.api.routes.health import router as health_router
from src.api.routes.prices import router as prices_router
from src.api.routes.submissions import router as submissions_router
from src.api.routes.admin.scraping import router as admin_scraping_router

router = APIRouter()

# Include all route modules
router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(bottles_router, prefix="/bottles", tags=["Bottles"])
router.include_router(prices_router, prefix="/prices", tags=["Prices"])
router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
router.include_router(submissions_router, prefix="/submissions", tags=["Submissions"])
router.include_router(collections_router, prefix="/collections", tags=["Collections"])

# Admin routes
router.include_router(admin_scraping_router, prefix="/admin", tags=["Admin"])
