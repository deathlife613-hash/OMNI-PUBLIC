"""E2E test server: the REAL app + built frontend, with a scripted fake model/search (no keys, no network)."""
import json
import os
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.main import create_app
from app.models.base import ModelInfo, Provider, StreamEvent
from tests.conftest import FakeSearch

TMP = Path(tempfile.mkdtemp())
WS = TMP / "proj"
(WS / "src").mkdir(parents=True)
(WS / "src" / "app.py").write_text("print('v1')\n")

SKILL = {
    "name": "tidy-notes", "version": "1.0.0", "description": "Rewrites rough notes into a tidy bullet list.",
    "trigger": "When the user pastes messy notes", "inputs": [{"name": "text", "type": "string"}],
    "prompt_template": "Rewrite these notes as short bullet points:\n{{text}}",
    "tests": [{"inputs": {"text": "buy milk"}, "expect_contains": ["buy milk"]}],
}


class E2EProvider(Provider):
    """Answers by role so UI flows are deterministic."""

    name = "e2e"

    async def list_models(self):
        return [ModelInfo("m1", 8192)]

    async def stream_chat(self, messages, model, max_tokens):
        system, user = messages[0].content, messages[-1].content
        if "Manager Agent" in system and "ONLY JSON" in system:
            role = "coding" if "code" in user.lower() else "planning"
            text = json.dumps({"steps": [{"role": role, "instruction": "do the thing in src/app.py"}]})
        elif "Coding Agent" in system:
            text = json.dumps({"notes": "Bumped version.", "changes": [{"path": "src/app.py", "new_content": "print('v2')\n"}]})
        elif "Manager Agent" in system:
            text = "Team summary: done."
        elif "Planning Agent" in system:
            text = "Plan: step one."
        elif "running a user-approved skill" in system:
            text = "- skill output"
        else:
            text = "Hello from OMNI"
        yield StreamEvent(delta=text)


# A real OMNI_* variable exported in the shell (e.g. OMNI_DATABASE_URL from a Postgres test) must never leak in:
# that would make the e2e DB persist across runs and collide with old data.
for _k in [k for k in os.environ if k.startswith("OMNI_")]:
    del os.environ[_k]

settings = Settings(
    _env_file=None, env="development", db_path=TMP / "e2e.db", database_url="", ai_model="m1", workspace_dir=WS,
    frontend_dist=Path(__file__).resolve().parents[2] / "frontend" / "dist",
)
app = create_app(settings, provider_override=E2EProvider(), search_override=FakeSearch())

print(f"[e2e] fresh SQLite database at {TMP / 'e2e.db'} (new on every server start)", flush=True)
