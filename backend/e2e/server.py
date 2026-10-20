"""E2E test server: the REAL app + built frontend, with a scripted fake model/search (no keys, no network)."""
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.main import create_app
from tests.conftest import FakeProvider, FakeSearch

settings = Settings(
    _env_file=None,
    env="development",
    db_path=Path(tempfile.mkdtemp()) / "e2e.db",
    ai_model="m1",
    frontend_dist=Path(__file__).resolve().parents[2] / "frontend" / "dist",
)
app = create_app(settings, provider_override=FakeProvider(chunks=["Hello", " from OMNI"]), search_override=FakeSearch())
