import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.config import Settings
from app.main import create_app
from app.models.base import ModelInfo, Provider, StreamEvent
from app.security.auth import reset_throttle
from app.services.search import SearchProvider, SearchResult


class FakeSearch(SearchProvider):
    name = "fakesearch"

    def __init__(self, results=None, error=None):
        self.results = results if results is not None else [SearchResult("Title A", "https://a.example/x", "Snippet A")]
        self.error, self.calls = error, 0

    async def search(self, query, limit):
        self.calls += 1
        if self.error:
            raise self.error
        return self.results


class ScriptedProvider(Provider):
    """Returns one scripted response per model call (a str, or a ProviderError to raise)."""

    name = "scripted"

    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    async def list_models(self):
        return [ModelInfo("m1", 8192)]

    async def stream_chat(self, messages, model, max_tokens):
        self.calls.append(messages)
        r = self.responses.pop(0) if self.responses else "(no more scripted responses)"
        if isinstance(r, Exception):
            raise r
        yield StreamEvent(delta=r)


class FakeProvider(Provider):
    """Scriptable provider: yields `chunks`, then raises `error` if given."""

    name = "fake"

    def __init__(self, chunks=("Hello", " world"), error=None, models=("m1", "m2")):
        self.chunks, self.error, self.models = list(chunks), error, list(models)
        self.calls: list[tuple] = []

    async def list_models(self):
        if self.error and not self.chunks:
            raise self.error
        return [ModelInfo(m, 8192) for m in self.models]

    async def stream_chat(self, messages, model, max_tokens):
        self.calls.append((messages, model, max_tokens))
        for c in self.chunks:
            yield StreamEvent(delta=c)
        if self.error:
            raise self.error


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Tests must not depend on the shell: a real OMNI_AI_API_KEY etc. exported in Colab/CI would change defaults."""
    import os

    for k in list(os.environ):
        if k.startswith("OMNI_"):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture
def make_client(tmp_path):
    """Factory: make_client(provider=FakeProvider(), env="production", ...) -> TestClient."""
    reset_throttle()

    def _make(provider=None, search=None, sync_transport=None, **overrides) -> TestClient:
        base = dict(
            env="development",
            db_path=tmp_path / "test.db",
            access_token="",
            ai_api_key="",
            frontend_dist=tmp_path / "no-dist",
        search_provider="",  # tests never touch the network; opt in with search=/search_provider=
        )
        base.update(overrides)
        settings = Settings(_env_file=None, **base)
        db.init_db(settings.db_path)  # TestClient without `with` skips the lifespan hook
        return TestClient(create_app(settings, provider_override=provider, search_override=search, sync_transport=sync_transport))

    return _make
