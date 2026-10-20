from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health, system
from app.core import db
from app.core.config import APP_VERSION, Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Passing settings explicitly keeps tests isolated from the environment."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db(settings.db_path)
        yield

    app = FastAPI(title="OMNI", version=APP_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(system.router, prefix="/api")

    # Single-container deployment: serve the built frontend when present.
    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app


app = create_app()
