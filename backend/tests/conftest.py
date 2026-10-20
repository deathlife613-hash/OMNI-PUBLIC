import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.security.auth import reset_throttle


@pytest.fixture
def make_client(tmp_path):
    """Factory: make_client(env="production", access_token="x") -> TestClient."""
    reset_throttle()

    def _make(**overrides) -> TestClient:
        base = dict(
            env="development",
            db_path=tmp_path / "test.db",
            access_token="",
            ai_api_key="",
            frontend_dist=tmp_path / "no-dist",
        )
        base.update(overrides)
        return TestClient(create_app(Settings(_env_file=None, **base)))

    return _make
