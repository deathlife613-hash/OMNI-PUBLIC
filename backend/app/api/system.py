"""Authenticated system status. Every metric is measured or reported as null
("unavailable"); nothing is estimated or invented."""
import shutil
import time

from fastapi import APIRouter, Depends, Request

from app.api.provider import effective_model
from app.core import db
from app.core.config import APP_VERSION, Settings, get_settings
from app.security.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])
_STARTED = time.monotonic()


def _memory_mb() -> dict | None:
    """Host memory from /proc/meminfo (Linux only); None elsewhere."""
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            info = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in fh)}
        return {
            "total_mb": info["MemTotal"] // 1024,
            "available_mb": info["MemAvailable"] // 1024,
        }
    except (OSError, KeyError, ValueError):
        return None


def _disk(settings: Settings) -> dict | None:
    try:
        target = settings.db_path.parent
        target.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(target)
        db_bytes = settings.db_path.stat().st_size if settings.db_path.exists() else 0
        return {
            "free_mb": usage.free // 2**20,
            "total_mb": usage.total // 2**20,
            "database_kb": db_bytes // 1024,
        }
    except OSError:
        return None


@router.get("/status")
def status(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    last = request.app.state.provider_state  # None until "Test connection" is run
    return {
        "name": "OMNI",
        "version": APP_VERSION,
        "environment": settings.env,
        "uptime_seconds": int(time.monotonic() - _STARTED),
        "database": {"ok": db.ping(settings.db_path), "engine": "sqlite"},
        "storage": _disk(settings),
        "memory": _memory_mb(),
        "ai": {
            # Booleans/names only. The key itself is never serialized.
            "provider": settings.ai_provider,
            "model": effective_model(settings) or None,
            "api_key_configured": bool(settings.ai_api_key),
            "connected": last["ok"] if last else None,  # None = not tested yet
            "last_test": last,
            "paid_providers_allowed": settings.allow_paid_providers,
        },
        "auth": {"token_required": bool(settings.access_token)},
    }
