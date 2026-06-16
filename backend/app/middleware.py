from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.observability import bind_log_context, log_event


logger = logging.getLogger("app.middleware.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        start = perf_counter()
        with bind_log_context(request_id=request_id):
            log_event(
                logger,
                "http.request.started",
                method=request.method,
                path=request.url.path,
                client_host=request.client.host if request.client else None,
            )
            status_code = 500
            try:
                response = await call_next(request)
                status_code = response.status_code
                return response
            finally:
                duration_ms = round((perf_counter() - start) * 1000, 2)
                level = logging.ERROR if status_code >= 500 else logging.INFO
                log_event(
                    logger,
                    "http.request.finished",
                    level=level,
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
                if "response" in locals():
                    response.headers["X-Request-ID"] = request_id
