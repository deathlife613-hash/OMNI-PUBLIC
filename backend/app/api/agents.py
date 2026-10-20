"""Agent tasks (bounded, resumable), approval queue, and the read-only workspace viewer.
There is deliberately NO endpoint that executes commands."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents import workspace as ws
from app.agents.engine import run_task
from app.core import db
from app.core.config import Settings, get_settings
from app.security.auth import require_auth
from app.security.limits import limit_model_calls
from app.tools.base import ToolError

router = APIRouter(dependencies=[Depends(require_auth)])


class NewTask(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


def _audit(path, what: str) -> None:
    with db.session(path) as c:
        c.execute("INSERT INTO audit_log(tool, outcome) VALUES (?, ?)", ("agent", what))


def _task_or_404(c, task_id):
    r = c.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "Task not found.")
    return dict(r)


@router.get("/agents/limits")
def limits(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "execution": "sequential (one step at a time, one model)",
        "max_steps": settings.agent_max_steps,
        "max_model_calls": settings.agent_max_model_calls,
        "max_seconds_per_run": settings.agent_max_seconds,
        "workspace_configured": bool(settings.workspace_dir),
        "roles": ["manager", "research", "planning", "coding", "review", "documentation", "data"],
        "not_enabled": ["testing", "devops", "skill_creator", "memory"],
        "command_execution": False,
    }


@router.get("/agents/tasks")
def list_tasks(settings: Settings = Depends(get_settings)) -> list[dict]:
    with db.session(settings.db_path) as c:
        return [dict(r) for r in c.execute("SELECT * FROM agent_tasks ORDER BY created_at DESC LIMIT 50").fetchall()]


@router.post("/agents/tasks", status_code=201)
def create_task(body: NewTask, settings: Settings = Depends(get_settings)) -> dict:
    tid = uuid.uuid4().hex
    with db.session(settings.db_path) as c:
        c.execute("INSERT INTO agent_tasks(id, goal) VALUES (?, ?)", (tid, body.goal.strip()))
        return _task_or_404(c, tid)


@router.get("/agents/tasks/{task_id}")
def get_task(task_id: str, settings: Settings = Depends(get_settings)) -> dict:
    with db.session(settings.db_path) as c:
        t = _task_or_404(c, task_id)
        t["steps"] = [dict(r) for r in c.execute("SELECT idx, role, instruction, status, output, sources FROM agent_steps WHERE task_id = ? ORDER BY idx", (task_id,)).fetchall()]
        t["approvals"] = [dict(r) for r in c.execute("SELECT id, path, diff, status FROM agent_approvals WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()]
    return t


@router.post("/agents/tasks/{task_id}/run", dependencies=[Depends(limit_model_calls)])
async def run(task_id: str, request: Request, settings: Settings = Depends(get_settings)) -> StreamingResponse:
    """Start or resume. Streams progress. If the connection closes, the task is paused and resumable."""
    with db.session(settings.db_path) as c:
        t = _task_or_404(c, task_id)
        if t["status"] in ("succeeded", "cancelled", "waiting_approval"):
            raise HTTPException(409, f"Task is already {t['status']}.")
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=settings.agent_max_seconds + 60)).strftime("%Y-%m-%dT%H:%M:%fZ")
        busy = c.execute("SELECT id FROM agent_tasks WHERE status = 'running' AND updated_at > ? AND id != ?", (cutoff, task_id)).fetchone()
        if busy:
            raise HTTPException(409, "Another agent task is running. Agents run one at a time to protect your free model quota.")
        c.execute("UPDATE agent_tasks SET cancel_requested = 0 WHERE id = ?", (task_id,))
    _audit(settings.db_path, "run_task")
    return StreamingResponse(run_task(request, settings, task_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/agents/tasks/{task_id}/cancel")
def cancel(task_id: str, settings: Settings = Depends(get_settings)) -> dict:
    with db.session(settings.db_path) as c:
        t = _task_or_404(c, task_id)
        if t["status"] in ("succeeded", "cancelled", "failed"):
            raise HTTPException(409, f"Task is already {t['status']}.")
        if t["status"] == "running":
            c.execute("UPDATE agent_tasks SET cancel_requested = 1 WHERE id = ?", (task_id,))
        else:  # not running: cancel immediately
            c.execute("UPDATE agent_tasks SET status = 'cancelled', error = 'Cancelled by you.' WHERE id = ?", (task_id,))
    _audit(settings.db_path, "cancel_task")
    return {"cancel_requested": True}


@router.delete("/agents/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, settings: Settings = Depends(get_settings)) -> None:
    with db.session(settings.db_path) as c:
        t = _task_or_404(c, task_id)
        if t["status"] == "running":
            raise HTTPException(409, "Cancel the running task first.")
        pending = c.execute("SELECT COUNT(*) AS n FROM agent_approvals WHERE task_id = ? AND status = 'pending'", (task_id,)).fetchone()["n"]
        if pending:
            raise HTTPException(409, "Decide the pending approvals first.")
        c.execute("DELETE FROM agent_tasks WHERE id = ?", (task_id,))


# ---- approvals -------------------------------------------------------------------------------
@router.get("/agents/approvals")
def approvals(status: str = Query(default="pending"), settings: Settings = Depends(get_settings)) -> list[dict]:
    with db.session(settings.db_path) as c:
        rows = c.execute("SELECT id, task_id, path, diff, status, created_at FROM agent_approvals WHERE status = ? ORDER BY id", (status,)).fetchall()
    return [dict(r) for r in rows]


def _approval(c, aid):
    r = c.execute("SELECT * FROM agent_approvals WHERE id = ?", (aid,)).fetchone()
    if r is None:
        raise HTTPException(404, "Approval not found.")
    return dict(r)


def _settle_task(c, task_id):
    left = c.execute("SELECT COUNT(*) AS n FROM agent_approvals WHERE task_id = ? AND status = 'pending'", (task_id,)).fetchone()["n"]
    if not left:
        c.execute("UPDATE agent_tasks SET status = 'succeeded' WHERE id = ? AND status = 'waiting_approval'", (task_id,))


@router.post("/agents/approvals/{aid}/approve")
def approve(aid: int, settings: Settings = Depends(get_settings)) -> dict:
    """Applies the reviewed diff. Fails (409) if the file changed since it was proposed."""
    with db.session(settings.db_path) as c:
        a = _approval(c, aid)
        if a["status"] != "pending":
            raise HTTPException(409, f"Already {a['status']}.")
        try:
            root = ws.root_of(settings.workspace_dir)
            p = ws.resolve(root, a["path"], must_exist=False)
            cur = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
            if cur != a["base_content"]:
                raise HTTPException(409, "The file changed since this was proposed. Reject it and ask for a fresh proposal.")
            if len(a["new_content"].encode()) > settings.workspace_max_file_bytes:
                raise HTTPException(409, "Proposed file is too large.")
            p.write_text(a["new_content"], encoding="utf-8")
        except ToolError as e:
            raise HTTPException(400, str(e)) from None
        c.execute("UPDATE agent_approvals SET status = 'applied' WHERE id = ?", (aid,))
        _settle_task(c, a["task_id"])
    _audit(settings.db_path, "approval_applied")
    return {"applied": a["path"]}


@router.post("/agents/approvals/{aid}/reject")
def reject(aid: int, settings: Settings = Depends(get_settings)) -> dict:
    with db.session(settings.db_path) as c:
        a = _approval(c, aid)
        if a["status"] != "pending":
            raise HTTPException(409, f"Already {a['status']}.")
        c.execute("UPDATE agent_approvals SET status = 'rejected' WHERE id = ?", (aid,))
        _settle_task(c, a["task_id"])
    _audit(settings.db_path, "approval_rejected")
    return {"rejected": a["path"]}


@router.post("/agents/approvals/{aid}/revert")
def revert(aid: int, settings: Settings = Depends(get_settings)) -> dict:
    """Undo an applied change, only if the file still matches what was applied."""
    with db.session(settings.db_path) as c:
        a = _approval(c, aid)
        if a["status"] != "applied":
            raise HTTPException(409, "Only applied changes can be reverted.")
        try:
            p = ws.resolve(ws.root_of(settings.workspace_dir), a["path"], must_exist=True)
        except ToolError as e:
            raise HTTPException(400, str(e)) from None
        if p.read_text(encoding="utf-8", errors="replace") != a["new_content"]:
            raise HTTPException(409, "The file was edited after it was applied; refusing to overwrite your newer edits.")
        if a["base_content"] is None:
            p.unlink()
        else:
            p.write_text(a["base_content"], encoding="utf-8")
        c.execute("UPDATE agent_approvals SET status = 'reverted' WHERE id = ?", (aid,))
    _audit(settings.db_path, "approval_reverted")
    return {"reverted": a["path"]}


# ---- workspace viewer (read-only) --------------------------------------------------------------
@router.get("/workspace/tree")
def workspace_tree(settings: Settings = Depends(get_settings)) -> dict:
    try:
        return {"files": ws.tree(ws.root_of(settings.workspace_dir))}
    except ToolError as e:
        raise HTTPException(400, str(e)) from None


@router.get("/workspace/file")
def workspace_file(path: str = Query(min_length=1, max_length=300), settings: Settings = Depends(get_settings)) -> dict:
    try:
        return {"path": path, "text": ws.read_text(ws.root_of(settings.workspace_dir), path, settings.workspace_max_file_bytes)}
    except ToolError as e:
        raise HTTPException(400, str(e)) from None
