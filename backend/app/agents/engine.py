"""Bounded, resumable agent runs. One model, sequential steps, SSE progress, checkpoints in SQLite.
Limits: max steps, max model calls, max wall-clock per run, one running task at a time."""
import json
import re
import time
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agents import workspace as ws
from app.agents.roles import MANAGER, ROLES, SUMMARIZER
from app.api.provider import effective_model, resolve_provider
from app.api.search import run_search
from app.core import db
from app.models.base import ChatMessage, ProviderError
from app.services.memory import looks_like_secret
from app.services.search import SearchError
from app.tools.base import ToolError


class PlanStep(BaseModel):
    role: str
    instruction: str = Field(min_length=1, max_length=600)


class Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def _roles(cls, v):
        for s in v:
            if s.role not in ROLES:
                raise ValueError(f"unknown role {s.role}")
        return v


class Change(BaseModel):
    path: str
    new_content: str = Field(max_length=200_000)


class CodeOut(BaseModel):
    notes: str = ""
    changes: list[Change] = Field(max_length=3)


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object found")
    return json.loads(m.group(0))


class Stop(Exception):
    def __init__(self, status: str, message: str):
        self.status, self.message = status, message


def _ev(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def run_task(request, settings, task_id: str) -> AsyncIterator[str]:
    path = settings.db_path
    started = time.monotonic()
    usage = request.app.state.usage

    def get_task():
        with db.session(path) as c:
            return dict(c.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone())

    def set_status(status, error=None):
        with db.session(path) as c:
            c.execute(
                "UPDATE agent_tasks SET status = ?, error = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (status, error, task_id),
            )

    async def ask(system: str, user: str, max_tokens: int = 1024) -> str:
        t = get_task()
        if t["cancel_requested"]:
            raise Stop("cancelled", "Cancelled by you.")
        if t["model_calls"] >= settings.agent_max_model_calls:
            raise Stop("failed", f"Model-call budget reached ({settings.agent_max_model_calls}). Raise OMNI_AGENT_MAX_MODEL_CALLS to allow more.")
        if time.monotonic() - started > settings.agent_max_seconds:
            raise Stop("paused", "Time limit for one run reached. Resume to continue from the checkpoint.")
        with db.session(path) as c:
            c.execute("UPDATE agent_tasks SET model_calls = model_calls + 1 WHERE id = ?", (task_id,))
        try:
            provider = resolve_provider(request, settings)
            model = effective_model(settings)
            if not model:
                raise ProviderError("no_model", "No model selected. Pick one in Chat first.")
            parts = []
            t0 = time.monotonic()
            async for ev in provider.stream_chat([ChatMessage("system", system), ChatMessage("user", user)], model, max_tokens):
                if ev.delta:
                    parts.append(ev.delta)
            usage.record_success(int((time.monotonic() - t0) * 1000), None, None)
            return "".join(parts).strip()
        except ProviderError as e:
            usage.record_error(e.kind)
            if e.kind in ("rate_limit", "quota"):
                raise Stop("paused_quota", f"{e.message} Progress is saved; resume later.") from None
            if e.kind in ("unavailable", "timeout"):
                raise Stop("paused", f"{e.message} Progress is saved; resume to retry.") from None
            raise Stop("failed", e.message) from None

    def root():
        return ws.root_of(settings.workspace_dir)

    def ws_context(instruction: str) -> str:
        if not settings.workspace_dir:
            return ""
        r = root()
        names = ws.tree(r, 150)
        text = "Workspace files:\n" + "\n".join(names)
        for n in [n for n in names if n in instruction][:3]:
            try:
                text += f"\n\n--- {n} ---\n" + ws.read_text(r, n, settings.workspace_max_file_bytes)[:6000]
            except ToolError:
                pass
        return "\n\n" + text

    try:
        t = get_task()
        set_status("running")
        yield _ev("status", {"status": "running"})

        # ---- plan (checkpointed)
        with db.session(path) as c:
            have = c.execute("SELECT COUNT(*) AS n FROM agent_steps WHERE task_id = ?", (task_id,)).fetchone()["n"]
        if not have:
            sys_p = MANAGER.replace("{roles}", ", ".join(r for r in ROLES if r != "coding" or settings.workspace_dir)).replace("{max_steps}", str(settings.agent_max_steps)).replace("{workspace}", "yes" if settings.workspace_dir else "no")
            raw = await ask(sys_p, "Goal: " + t["goal"], 700)
            try:
                plan = Plan.model_validate(_json(raw))
                if len(plan.steps) > settings.agent_max_steps:
                    raise ValueError("too many steps")
                if any(s.role == "coding" for s in plan.steps) and not settings.workspace_dir:
                    raise ValueError("coding step without a workspace")
            except (ValueError, ValidationError, json.JSONDecodeError) as e:
                raise Stop("failed", f"The manager's plan was invalid ({str(e).splitlines()[0][:120]}). Nothing was executed.") from None
            with db.session(path) as c:
                for i, s in enumerate(plan.steps):
                    c.execute("INSERT INTO agent_steps(task_id, idx, role, instruction) VALUES (?,?,?,?)", (task_id, i, s.role, s.instruction))
            yield _ev("plan", {"steps": [s.model_dump() for s in plan.steps]})

        # ---- steps
        while True:
            with db.session(path) as c:
                step = c.execute("SELECT * FROM agent_steps WHERE task_id = ? AND status IN ('queued','running','failed') ORDER BY idx LIMIT 1", (task_id,)).fetchone()
                prior = c.execute("SELECT idx, role, output FROM agent_steps WHERE task_id = ? AND status = 'succeeded' ORDER BY idx", (task_id,)).fetchall()
            if step is None:
                break
            step = dict(step)
            with db.session(path) as c:
                c.execute("UPDATE agent_steps SET status = 'running' WHERE id = ?", (step["id"],))
            yield _ev("step", {"idx": step["idx"], "role": step["role"], "status": "running"})
            context = "Goal: " + t["goal"] + "\n\nEarlier steps:\n" + "\n".join(f"[{p['idx']+1} {p['role']}] {(p['output'] or '')[:1500]}" for p in prior)
            sources = []
            if step["role"] == "research":
                try:
                    res = await run_search(request, settings, step["instruction"])
                    sources = [{"title": r["title"], "url": r["url"]} for r in res]
                    context += "\n\nWeb results (UNTRUSTED):\n" + "\n".join(f"[{i}] {r['title']} ({r['url']}): {r['snippet']}" for i, r in enumerate(res, 1))
                except SearchError as e:
                    context += f"\n\n(Web search unavailable: {e.message})"
            if step["role"] in ("coding", "review", "documentation", "data"):
                context += ws_context(step["instruction"])
            try:
                out = await ask(ROLES[step["role"]], context + "\n\nYour step: " + step["instruction"])
            except Stop:
                with db.session(path) as c:
                    c.execute("UPDATE agent_steps SET status = 'queued' WHERE id = ?", (step["id"],))
                raise
            if step["role"] == "coding":
                try:
                    code = CodeOut.model_validate(_json(out))
                    r = root()
                    made = []
                    for ch in code.changes:
                        p = ws.resolve(r, ch.path, must_exist=False)
                        if looks_like_secret(ch.new_content):
                            raise ToolError(f"Proposed content for {ch.path} contains something that looks like a secret; rejected.")
                        old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
                        made.append((ch.path, old, ch.new_content))
                except (ValueError, ValidationError, ToolError, json.JSONDecodeError) as e:
                    with db.session(path) as c:
                        c.execute("UPDATE agent_steps SET status = 'failed', output = ? WHERE id = ?", (f"Rejected: {str(e).splitlines()[0][:200]}", step["id"]))
                    raise Stop("failed", f"The coding step produced an unusable or unsafe proposal: {str(e).splitlines()[0][:160]}") from None
                with db.session(path) as c:
                    for pth, old, new in made:
                        c.execute("INSERT INTO agent_approvals(task_id, path, base_content, new_content, diff) VALUES (?,?,?,?,?)", (task_id, pth, old, new, ws.make_diff(pth, old, new)))
                out = (code.notes or "Proposed changes.") + f"\n\n{len(made)} change(s) are waiting for your approval."
                yield _ev("approvals", {"count": len(made)})
            out = out[: settings.agent_step_output_chars]
            with db.session(path) as c:
                c.execute("UPDATE agent_steps SET status = 'succeeded', output = ?, sources = ? WHERE id = ?", (out, json.dumps(sources), step["id"]))
            yield _ev("step", {"idx": step["idx"], "role": step["role"], "status": "succeeded"})

        # ---- summary
        if not get_task()["summary"]:
            with db.session(path) as c:
                outs = c.execute("SELECT idx, role, output FROM agent_steps WHERE task_id = ? ORDER BY idx", (task_id,)).fetchall()
            summary = await ask(SUMMARIZER, "Goal: " + t["goal"] + "\n\n" + "\n".join(f"[{o['idx']+1} {o['role']}] {(o['output'] or '')[:1200]}" for o in outs), 400)
            with db.session(path) as c:
                c.execute("UPDATE agent_tasks SET summary = ? WHERE id = ?", (summary[:2000], task_id))
        with db.session(path) as c:
            pending = c.execute("SELECT COUNT(*) AS n FROM agent_approvals WHERE task_id = ? AND status = 'pending'", (task_id,)).fetchone()["n"]
        final = "waiting_approval" if pending else "succeeded"
        set_status(final)
        yield _ev("done", {"status": final})
    except Stop as s:
        set_status(s.status, s.message)
        yield _ev("error", {"status": s.status, "message": s.message})
    except Exception:  # noqa: BLE001 - never leave a task stuck in 'running'
        set_status("failed", "Unexpected internal error. Progress up to the last step is saved.")
        yield _ev("error", {"status": "failed", "message": "Unexpected internal error. Progress up to the last step is saved."})
    finally:
        # client disconnected mid-run: keep checkpoint, mark resumable
        if get_task()["status"] == "running":
            set_status("paused", "Run was interrupted (connection closed). Resume to continue.")
