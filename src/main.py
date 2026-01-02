"""
WTracker - Secondary Market Spirits Price Intelligence Platform

FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import router as api_router
from src.api.routes.frontend import router as frontend_router
from src.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Runs startup and shutdown logic.
    """
    # Startup
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")

    yield

    # Shutdown
    print(f"Shutting down {settings.app_name}")


def create_app() -> FastAPI:
    """
    Application factory for creating the FastAPI app.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Price tracking and valuation engine for secondary market bourbon and scotch",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include API routes
    app.include_router(api_router, prefix="/api/v1")

    # Include frontend template routes
    app.include_router(frontend_router)

    return app


# Create application instance
app = create_app()


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}
