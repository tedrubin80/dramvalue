"""Middleware that allows HEAD requests by delegating to GET handlers."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class HeadRequestMiddleware(BaseHTTPMiddleware):
    """Treat HEAD like GET (FastAPI routes here only register GET)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method != "HEAD":
            return await call_next(request)

        request.scope["method"] = "GET"
        response = await call_next(request)

        # Drop body-related headers — HEAD must not advertise a GET-sized body.
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")
        }
        return Response(
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
            background=response.background,
        )
