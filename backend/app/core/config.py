"""Environment-driven configuration. Secrets live here only; they are never
returned by any API route (see api/system.py, which exposes booleans only)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.db import PgTarget

APP_VERSION = "1.0.0-rc1"
BACKEND_DIR = Path(__file__).resolve().parents[2]


DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b"}  # verified on Groq 2026-10-20; catalogs change, so it is only a default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OMNI_", env_file=(".env", "../.env"), extra="ignore"
    )

    env: str = "development"  # "development" | "production"
    db_path: Path = BACKEND_DIR / "data" / "omni.db"
    # Postgres (e.g. Neon). Empty = SQLite at db_path. Server-side secret: it contains the password.
    database_url: str = Field(default="", repr=False)
    database_schema: str = ""  # optional Postgres schema (the test suite uses one per test)
    # Single-owner access token. Required in production.
    access_token: str = Field(default="", repr=False)
    # Production without a token fails closed. Set true ONLY if you accept that anyone with the URL can use
    # your model quota and read/replace your data (see docs/DEPLOYMENT.md "Open access").
    allow_open_access: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    # AI provider
    ai_provider: str = "groq"  # groq | openrouter | ollama | huggingface
    ai_model: str | None = None  # None = recommended default for the provider; "" = none; changeable in the UI
    ai_base_url: str = ""  # override only if you know the endpoint is free to you
    ai_api_key: str = Field(default="", repr=False)
    allow_paid_providers: bool = False  # hard guard; never flipped automatically
    ai_max_output_tokens: int = 1024
    ai_timeout_s: float = 60
    ai_max_retries: int = 2  # timeouts/5xx only; never for 429
    context_char_budget: int = 12000
    model_rpm_limit: int = 20  # OMNI's own cap on model-spending requests per minute

    # Agents & coding workspace (Phase 9). Workspace = a folder OMNI may read; edits need your approval.
    workspace_dir: Path | None = None
    workspace_max_file_bytes: int = 200_000
    agent_max_steps: int = 6
    agent_max_model_calls: int = 12
    agent_max_seconds: float = 300
    agent_step_output_chars: int = 4000

    # Web search. "" = disabled. auto (DuckDuckGo, then Wikipedia; no signup) | duckduckgo | wikipedia | tavily | searxng
    search_provider: str = "auto"
    search_api_key: str = Field(default="", repr=False)
    search_base_url: str = ""  # for searxng
    search_max_results: int = 5
    search_cache_ttl_s: float = 3600
    search_daily_cap: int = 30  # own guard: Tavily free = 1,000 credits/month

    # Persistence for hosts with an ephemeral disk. "" = off | hf_dataset (private Hugging Face Dataset)
    sync_provider: str = ""
    sync_hf_repo: str = ""  # e.g. "yourname/omni-data" - must be a PRIVATE dataset
    sync_hf_token: str = Field(default="", repr=False)  # fine-grained token, write access to that one repo
    sync_interval_s: float = 120

    # Text-to-speech. "" = off (browser-native voice only). elevenlabs = server-side TTS; the key never leaves the server.
    tts_provider: str = ""
    tts_api_key: str = Field(default="", repr=False)
    tts_voice_id: str = ""  # required when tts_provider is set; pick one from your ElevenLabs voice list
    tts_model: str = "eleven_flash_v2_5"  # UNVERIFIED default; confirm with GET /v1/models, override via env
    tts_base_url: str = "https://api.elevenlabs.io"
    tts_max_chars_per_reply: int = 1500
    tts_monthly_char_cap: int = 8000  # OMNI's own estimate guard; free plan is ~10k credits/month
    tts_cache_entries: int = 64
    tts_timeout_s: float = 30

    # Folder OMNI may search/read (read-only, .txt/.md/.csv). Empty = document tools disabled.
    docs_dir: Path | None = None
    tool_timeout_s: float = 5

    @model_validator(mode="after")
    def _use_postgres_when_configured(self):
        if self.database_url:
            self.db_path = PgTarget(self.database_url, self.database_schema)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
