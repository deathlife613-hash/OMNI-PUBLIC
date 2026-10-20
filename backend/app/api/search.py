"""Web search endpoints + the helper chat uses. Never reports a search that did not happen."""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import db
from app.core.config import Settings, get_settings
from app.security.auth import require_auth
from app.services.search import SearchError, build_search

router = APIRouter(dependencies=[Depends(require_auth)])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=300)


def _today_key() -> str:
    return "search_count:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def used_today(settings: Settings) -> int:
    return int(db.get_meta(settings.db_path, _today_key()) or 0)


async def run_search(request: Request, settings: Settings, query: str) -> list[dict]:
    """Returns [{title,url,snippet}]. Raises SearchError (disabled, rate_limit, daily_cap, ...)."""
    guard = request.app.state.search_guard
    key = query.strip().lower()
    cached = guard.get(key, time.monotonic(), settings.search_cache_ttl_s)
    if cached is not None:
        return [r.__dict__ for r in cached]
    provider = request.app.state.search_provider or build_search(settings)
    if used_today(settings) >= settings.search_daily_cap:
        raise SearchError("daily_cap", f"OMNI's own daily search limit ({settings.search_daily_cap}) is reached, to protect your free allowance. Try tomorrow or raise OMNI_SEARCH_DAILY_CAP.")
    results = await provider.search(query.strip(), settings.search_max_results)
    db.set_meta(settings.db_path, _today_key(), str(used_today(settings) + 1))  # counted only when a real request was made
    guard.searches += 1
    guard.put(key, time.monotonic(), results)
    return [r.__dict__ for r in results]


@router.get("/search/status")
def search_status(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    configured = bool(request.app.state.search_provider) or bool(settings.search_provider)
    guard = request.app.state.search_guard
    return {
        "configured": configured,
        "provider": request.app.state.search_provider.name if request.app.state.search_provider else (settings.search_provider or None),
        "used_today": used_today(settings),
        "daily_cap": settings.search_daily_cap,
        "cache_hits": guard.cache_hits,
    }


@router.post("/search")
async def search(body: SearchIn, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    try:
        results = await run_search(request, settings, body.query)
    except SearchError as e:
        status = {"disabled": 503, "not_configured": 503, "unsupported": 503, "daily_cap": 429}.get(e.kind, 502)
        # 429 here is OMNI's own cap; use 409 so the frontend never confuses it with its login throttle.
        raise HTTPException(409 if status == 429 else status, {"kind": e.kind, "message": e.message}) from None
    return {"query": body.query, "results": results}
