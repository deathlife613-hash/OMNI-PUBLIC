from fastapi import APIRouter, Depends

from app.core import db
from app.core.config import APP_VERSION, Settings, get_settings

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    """Public liveness/readiness probe. Deliberately reveals nothing sensitive."""
    database_ok = db.ping(settings.db_path)
    return {
        "status": "ok" if database_ok else "degraded",
        "version": APP_VERSION,
        "database": "ok" if database_ok else "unavailable",
    }
