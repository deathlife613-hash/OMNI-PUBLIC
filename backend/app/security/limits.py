"""Security headers and a small in-memory limiter for endpoints that spend model quota."""
import time
from collections import deque

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
        if not request.url.path.startswith("/api/"):
            resp.headers.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp


class ModelCallLimiter:
    """Sliding window: at most `per_minute` model-spending requests per minute (single-owner app, so global)."""

    def __init__(self):
        self.hits: deque[float] = deque()

    def check(self, per_minute: int) -> None:
        now = time.monotonic()
        while self.hits and now - self.hits[0] > 60:
            self.hits.popleft()
        if len(self.hits) >= per_minute:
            wait = int(60 - (now - self.hits[0])) + 1
            raise HTTPException(429, {"kind": "local_rate_limit", "message": f"OMNI's own limit of {per_minute} model requests/minute was reached (protects your free quota). Try again in {wait}s."}, headers={"Retry-After": str(wait)})
        self.hits.append(now)


def limit_model_calls(request: Request) -> None:
    from app.core.config import get_settings

    settings = request.app.dependency_overrides.get(get_settings, get_settings)()
    request.app.state.limiter.check(settings.model_rpm_limit)
