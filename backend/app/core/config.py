"""Environment-driven configuration. Secrets live here only; they are never
returned by any API route (see api/system.py, which exposes booleans only)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.5.0"
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OMNI_", env_file=(".env", "../.env"), extra="ignore"
    )

    env: str = "development"  # "development" | "production"
    db_path: Path = BACKEND_DIR / "data" / "omni.db"
    # Single-owner access token. Required in production.
    access_token: str = Field(default="", repr=False)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    # AI provider
    ai_provider: str = "groq"  # groq | openrouter
    ai_model: str = ""  # default model; can be changed at runtime from the UI
    ai_base_url: str = ""  # override only if you know the endpoint is free to you
    ai_api_key: str = Field(default="", repr=False)
    allow_paid_providers: bool = False  # hard guard; never flipped automatically
    ai_max_output_tokens: int = 1024
    ai_timeout_s: float = 60
    ai_max_retries: int = 2  # timeouts/5xx only; never for 429
    context_char_budget: int = 12000

    # Agents & coding workspace (Phase 9). Workspace = a folder OMNI may read; edits need your approval.
    workspace_dir: Path | None = None
    workspace_max_file_bytes: int = 200_000
    agent_max_steps: int = 6
    agent_max_model_calls: int = 12
    agent_max_seconds: float = 300
    agent_step_output_chars: int = 4000

    # Web search (optional). "" = disabled. tavily | searxng
    search_provider: str = ""
    search_api_key: str = Field(default="", repr=False)
    search_base_url: str = ""  # for searxng
    search_max_results: int = 5
    search_cache_ttl_s: float = 3600
    search_daily_cap: int = 30  # own guard: Tavily free = 1,000 credits/month

    # Folder OMNI may search/read (read-only, .txt/.md/.csv). Empty = document tools disabled.
    docs_dir: Path | None = None
    tool_timeout_s: float = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
