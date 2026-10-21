"""Tool endpoints: list registered tools and run one with validated input.
Consequential tools need confirm=true. Every run is audit-logged (tool name + outcome only, no arguments)."""
import asyncio
from types import SimpleNamespace
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.core import db
from app.core.config import Settings, get_settings
from app.security.auth import require_auth
from app.tools.base import ToolContext, ToolError, run_with_timeout
from app.tools.builtin import REGISTRY

router = APIRouter(dependencies=[Depends(require_auth)])


class RunBody(BaseModel):
    args: dict = {}
    confirm: bool = False


def _audit(path, tool: str, outcome: str) -> None:
    with db.session(path) as c:
        c.execute("INSERT INTO audit_log(tool, outcome) VALUES (?, ?)", (tool, outcome))


@router.get("/tools")
def list_tools() -> list[dict]:
    return [t.schema() for t in REGISTRY.values()]


@router.get("/audit")
def audit(settings: Settings = Depends(get_settings)) -> list[dict]:
    with db.session(settings.db_path) as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100").fetchall()]


@router.post("/tools/{name}/run")
async def run_tool(name: str, body: RunBody, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    tool = REGISTRY.get(name)
    if tool is None:
        raise HTTPException(404, "Unknown tool.")
    try:
        args = tool.input_model.model_validate(body.args)
    except ValidationError as e:
        _audit(settings.db_path, name, "invalid_input")
        raise HTTPException(422, "Invalid input: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from None
    if tool.needs_confirmation and not body.confirm:
        _audit(settings.db_path, name, "confirmation_required")
        raise HTTPException(409, {"kind": "needs_confirmation", "message": f"'{name}' changes or deletes data. Resend with confirm=true to proceed."})
    ctx = ToolContext(settings.db_path, settings.docs_dir, lambda: datetime.now(timezone.utc), SimpleNamespace(n8n=request.app.state.n8n))
    try:
        result = await run_with_timeout(tool, ctx, args, settings.tool_timeout_s)
    except ToolError as e:
        _audit(settings.db_path, name, "refused")
        raise HTTPException(400, str(e)) from None
    except asyncio.TimeoutError:
        _audit(settings.db_path, name, "timeout")
        raise HTTPException(504, "The tool timed out.") from None
    _audit(settings.db_path, name, "ok")
    return {"tool": name, "result": result}
