"""Provider status, model list, connection test, model selection.

None of these spend chat quota: they only call the provider's model-list
endpoint. Errors are returned as JSON with a `kind`; they use 502/409, never
401/429, so the browser never confuses a provider problem with OMNI's own login.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import db
from app.core.config import DEFAULT_MODELS, Settings, get_settings
from app.models.base import Provider, ProviderError
from app.models.registry import build_provider
from app.security.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


def resolve_provider(request: Request, settings: Settings) -> Provider:
    injected = getattr(request.app.state, "provider", None)
    return injected or build_provider(settings)


def effective_model(settings: Settings) -> str:
    if settings.ai_model is None:
        configured = DEFAULT_MODELS.get(settings.ai_provider, "")
    else:
        configured = settings.ai_model
    return db.get_meta(settings.db_path, "ai_model") or configured


def _http(e: ProviderError) -> HTTPException:
    code = 409 if e.kind in ("not_configured", "no_model", "unsupported") else 502
    return HTTPException(code, {"kind": e.kind, "message": e.message})


@router.get("/provider")
def provider_info(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "provider": settings.ai_provider,
        "model": effective_model(settings) or None,
        "api_key_configured": bool(settings.ai_api_key),
        "custom_base_url": bool(settings.ai_base_url),
        "paid_providers_allowed": settings.allow_paid_providers,
    }


@router.get("/provider/models")
async def provider_models(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    try:
        models = await resolve_provider(request, settings).list_models()
    except ProviderError as e:
        raise _http(e)
    return {"models": [{"id": m.id, "context_window": m.context_window} for m in models]}


@router.post("/provider/test")
async def provider_test(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """Validates key + endpoint with one cheap model-list call (no chat quota used)."""
    started = time.monotonic()
    state: dict
    try:
        models = await resolve_provider(request, settings).list_models()
        state = {"ok": True, "models_available": len(models)}
    except ProviderError as e:
        state = {"ok": False, "kind": e.kind, "message": e.message}
    state["latency_ms"] = int((time.monotonic() - started) * 1000)
    state["checked_at"] = datetime.now(timezone.utc).isoformat()
    request.app.state.provider_state = state
    return state


class ModelChoice(BaseModel):
    model: str = Field(min_length=1, max_length=200)


@router.put("/provider/model")
async def select_model(
    body: ModelChoice, request: Request, settings: Settings = Depends(get_settings)
) -> dict:
    try:
        models = await resolve_provider(request, settings).list_models()
    except ProviderError as e:
        raise _http(e)
    if body.model not in {m.id for m in models}:
        raise HTTPException(400, {"kind": "bad_request", "message": "That model is not in the provider's available list."})
    db.set_meta(settings.db_path, "ai_model", body.model)
    return {"model": body.model}


@router.get("/usage")
def usage(request: Request) -> dict:
    return request.app.state.usage.snapshot()
