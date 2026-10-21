import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import agents, chat, health, memory, provider, search, skills, system, tools, voice
from app.core import db
from app.core.config import APP_VERSION, Settings, get_settings
from app.models.base import Provider
from app.security.limits import ModelCallLimiter, SecurityHeaders
from app.services.search import SearchGuard, SearchProvider
from app.services.n8n import N8NClient
from app.services.sync import build_sync
from app.services.tts import TTSGuard, build_tts
from app.services.usage import UsageTracker


def create_app(
    settings: Settings | None = None,
    provider_override: Provider | None = None,
    search_override: SearchProvider | None = None,
    sync_transport=None,
    tts_transport=None,
    n8n_transport=None,
    n8n_resolver=None,
) -> FastAPI:
    """Build the app. Passing settings/provider explicitly keeps tests isolated."""
    settings = settings or get_settings()

    sync = build_sync(settings, sync_transport)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if sync:
            await sync.restore_if_needed()  # before init_db; only when no local database exists
        db.init_db(settings.db_path)
        task = asyncio.create_task(sync.run_forever()) if sync and sync.enabled else None
        yield
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(sync.push(), timeout=20)  # final snapshot on graceful shutdown
            except asyncio.TimeoutError:
                pass

    app = FastAPI(title="OMNI", version=APP_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.provider = provider_override
    app.state.provider_state = None  # result of the last "Test connection", None = never tested
    app.state.usage = UsageTracker()
    app.state.search_provider = search_override
    app.state.search_guard = SearchGuard()
    app.state.limiter = ModelCallLimiter()
    app.state.sync = sync
    app.state.tts = build_tts(settings, tts_transport)
    app.state.tts_guard = TTSGuard(settings.tts_cache_entries)
    app.state.n8n = N8NClient(settings, n8n_transport, n8n_resolver)
    app.add_middleware(SecurityHeaders)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(tools.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(skills.router, prefix="/api")
    app.include_router(voice.router, prefix="/api")

    # Single-container deployment: serve the built frontend when present.
    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app


app = create_app()
