"""Single-owner bearer-token authentication.

- Production with no OMNI_ACCESS_TOKEN set -> every protected route returns 503
  (fail closed; OMNI never serves private data unauthenticated in production).
- Development with no token -> open, for local-only use on 127.0.0.1.
- Repeated failures from one client are throttled (in-memory, per process).
"""
import hmac
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings

_FAIL_WINDOW_S = 60
_FAIL_LIMIT = 10
_failures: dict[str, deque[float]] = defaultdict(deque)


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent_failures(client: str, now: float) -> deque[float]:
    q = _failures[client]
    while q and now - q[0] > _FAIL_WINDOW_S:
        q.popleft()
    return q


def reset_throttle() -> None:  # used by tests
    _failures.clear()


def require_auth(request: Request, settings: Settings = Depends(get_settings)) -> None:
    if not settings.access_token:
        if settings.is_production and not settings.allow_open_access:
            raise HTTPException(503, "Access token not configured on the server.")
        return

    client, now = _client_id(request), time.monotonic()
    failures = _recent_failures(client, now)
    if len(failures) >= _FAIL_LIMIT:
        raise HTTPException(429, "Too many failed attempts. Try again in a minute.")

    header = request.headers.get("authorization", "")
    supplied = header[7:] if header.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(supplied.encode(), settings.access_token.encode()):
        failures.append(now)
        raise HTTPException(401, "Invalid or missing access token.")
