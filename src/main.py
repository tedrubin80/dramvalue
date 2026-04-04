"""
WTracker - Secondary Market Spirits Price Intelligence Platform

FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.routes import router as api_router
from src.api.routes.frontend import router as frontend_router
from src.core.config import get_settings

# ---------------------------------------------------------------------------
# Rate limiter (shared instance, importable by route modules)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    yield
    print(f"Shutting down {settings.app_name}")


# ---------------------------------------------------------------------------
# Security headers middleware (pure ASGI — avoids BaseHTTPMiddleware issues)
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]
                settings = get_settings()
                if settings.is_production:
                    extra.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Price tracking and valuation engine for secondary market bourbon and scotch",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Security headers (pure ASGI middleware)
    app.add_middleware(SecurityHeadersMiddleware)  # Starlette wraps ASGI callables

    # CORS — never use wildcard with credentials
    if settings.is_development:
        allowed_origins = [
            "http://localhost:8000",
            "http://localhost:8001",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8001",
        ]
    else:
        allowed_origins = [
            origin.strip()
            for origin in settings.cors_origins.split(",")
            if origin.strip()
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Global exception handler — hide internals in production
    if not settings.debug:
        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
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
