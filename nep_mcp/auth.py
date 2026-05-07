"""API-key middleware for the streamable-http transport.

Protects every MCP HTTP endpoint with a static X-API-Key header check.
Rotate by setting the NEP_API_KEY environment variable / Azure Functions
app setting and restarting the function. If NEP_API_KEY is unset, the
middleware is bypassed (intended for local dev only).
"""

from __future__ import annotations

import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


log = logging.getLogger(__name__)


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, expected_key: str | None):
        super().__init__(app)
        self._expected = expected_key

    async def dispatch(self, request, call_next):
        if not self._expected:
            return await call_next(request)

        provided = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(provided, self._expected):
            log.warning("Rejected request to %s: invalid API key", request.url.path)
            return JSONResponse(
                {"error": "unauthorized", "detail": "Invalid or missing X-API-Key"},
                status_code=401,
            )
        return await call_next(request)


def install(app, expected_key: str | None) -> None:
    """Attach the middleware to a Starlette app in-place."""
    app.add_middleware(APIKeyMiddleware, expected_key=expected_key)
