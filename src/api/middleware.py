"""FastAPI middleware for D10 Web UI."""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logging import get_logger

_log = get_logger("D10-WEBUI")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if not request.url.path.startswith("/api/health"):
            _log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(elapsed_ms, 2),
            )
        return response