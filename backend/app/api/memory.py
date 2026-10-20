"""Memories (user-approved long-term facts/preferences), notes, search, export and restore.

Nothing here is written by the model. Secrets are refused so API keys/passwords never land in memory.
Export contains only user data (never settings, tokens or provider keys).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core import db
from app.core.config import APP_VERSION, Settings, get_settings
from app.security.auth import require_auth
from app.services.memory import looks_like_secret

router = APIRouter(dependencies=[Depends(require_auth)])
NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def _no_secret(text: str) -> None:
    if looks_like_secret(text):
        raise HTTPException(422, "That looks like a password or API key. OMNI never stores secrets in memory.")


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    kind: Literal["fact", "preference"] = "fact"


class MemoryPatch(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=500)
    kind: Literal["fact", "preference"] | None = None
    enabled: bool | None = None


class NoteIn(BaseModel):
    title: str = Field(default="Untitled", min_length=1, max_length=120)
    body: str = Field(default="", max_length=20000)


class NotePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=20000)


class MemorySettings(BaseModel):
    enabled: bool


def _mem(r) -> dict:
    d = dict(r)
    d["enabled"] = bool(d["enabled"])
    return d


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ---- memory on/off ---------------------------------------------------------------------------
@router.get("/memory/settings")
def get_memory_settings(settings: Settings = Depends(get_settings)) -> dict:
    v = db.get_meta(settings.db_path, "memory_enabled")
    return {"enabled": v is None or v == "1"}


@router.put("/memory/settings")
def put_memory_settings(body: MemorySettings, settings: Settings = Depends(get_settings)) -> dict:
    db.set_meta(settings.db_path, "memory_enabled", "1" if body.enabled else "0")
    return {"enabled": body.enabled}


# ---- memories --------------------------------------------------------------------------------
@router.get("/memories")
def list_memories(q: str = Query(default="", max_length=200), settings: Settings = Depends(get_settings)) -> list[dict]:
    with db.session(settings.db_path) as conn:
        if q.strip():
            rows = conn.execute(
                "SELECT * FROM memories WHERE content LIKE ? ESCAPE '\\' ORDER BY id DESC", (_like(q.strip()),)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM memories ORDER BY id DESC").fetchall()
    return [_mem(r) for r in rows]


@router.post("/memories", status_code=201)
def create_memory(body: MemoryIn, settings: Settings = Depends(get_settings)) -> dict:
    _no_secret(body.content)
    with db.session(settings.db_path) as conn:
        cur = conn.execute("INSERT INTO memories(kind, content) VALUES (?, ?)", (body.kind, body.content.strip()))
        return _mem(conn.execute("SELECT * FROM memories WHERE id = ?", (cur.lastrowid,)).fetchone())


@router.patch("/memories/{mem_id}")
def update_memory(mem_id: int, body: MemoryPatch, settings: Settings = Depends(get_settings)) -> dict:
    if body.content is not None:
        _no_secret(body.content)
    with db.session(settings.db_path) as conn:
        if conn.execute("SELECT 1 FROM memories WHERE id = ?", (mem_id,)).fetchone() is None:
            raise HTTPException(404, "Memory not found.")
        if body.content is not None:
            conn.execute(f"UPDATE memories SET content = ?, updated_at = {NOW} WHERE id = ?", (body.content.strip(), mem_id))
        if body.kind is not None:
            conn.execute(f"UPDATE memories SET kind = ?, updated_at = {NOW} WHERE id = ?", (body.kind, mem_id))
        if body.enabled is not None:
            conn.execute(f"UPDATE memories SET enabled = ?, updated_at = {NOW} WHERE id = ?", (int(body.enabled), mem_id))
        return _mem(conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone())


@router.delete("/memories/{mem_id}", status_code=204)
def delete_memory(mem_id: int, settings: Settings = Depends(get_settings)) -> None:
    with db.session(settings.db_path) as conn:
        if conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,)).rowcount == 0:
            raise HTTPException(404, "Memory not found.")


# ---- notes -----------------------------------------------------------------------------------
@router.get("/notes")
def list_notes(q: str = Query(default="", max_length=200), settings: Settings = Depends(get_settings)) -> list[dict]:
    with db.session(settings.db_path) as conn:
        if q.strip():
            p = _like(q.strip())
            rows = conn.execute(
                "SELECT * FROM notes WHERE title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\' ORDER BY updated_at DESC",
                (p, p),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("/notes", status_code=201)
def create_note(body: NoteIn, settings: Settings = Depends(get_settings)) -> dict:
    _no_secret(body.title + " " + body.body)
    with db.session(settings.db_path) as conn:
        cur = conn.execute("INSERT INTO notes(title, body) VALUES (?, ?)", (body.title.strip(), body.body))
        return dict(conn.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone())


@router.patch("/notes/{note_id}")
def update_note(note_id: int, body: NotePatch, settings: Settings = Depends(get_settings)) -> dict:
    _no_secret((body.title or "") + " " + (body.body or ""))
    with db.session(settings.db_path) as conn:
        if conn.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone() is None:
            raise HTTPException(404, "Note not found.")
        if body.title is not None:
            conn.execute("UPDATE notes SET title = ? WHERE id = ?", (body.title.strip(), note_id))
        if body.body is not None:
            conn.execute("UPDATE notes SET body = ? WHERE id = ?", (body.body, note_id))
        conn.execute(f"UPDATE notes SET updated_at = {NOW} WHERE id = ?", (note_id,))
        return dict(conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone())


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, settings: Settings = Depends(get_settings)) -> None:
    with db.session(settings.db_path) as conn:
        if conn.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount == 0:
            raise HTTPException(404, "Note not found.")


# ---- export / restore ------------------------------------------------------------------------
@router.get("/export")
def export_all(settings: Settings = Depends(get_settings)) -> dict:
    """Portable JSON backup of user data. Contains no tokens, keys or provider settings."""
    with db.session(settings.db_path) as conn:
        q = lambda sql: [dict(r) for r in conn.execute(sql).fetchall()]  # noqa: E731
        return {
            "format": "omni-backup",
            "format_version": 1,
            "app_version": APP_VERSION,
            "conversations": q("SELECT * FROM conversations ORDER BY created_at"),
            "messages": q("SELECT * FROM messages ORDER BY id"),
            "memories": q("SELECT * FROM memories ORDER BY id"),
            "notes": q("SELECT * FROM notes ORDER BY id"),
        }


class Restore(BaseModel):
    confirm: bool = False
    backup: dict


@router.post("/restore")
def restore(body: Restore, settings: Settings = Depends(get_settings)) -> dict:
    """REPLACES conversations, memories and notes with the backup's contents (all-or-nothing)."""
    if not body.confirm:
        raise HTTPException(400, "Restore replaces your current data. Send confirm=true to proceed.")
    b = body.backup
    if b.get("format") != "omni-backup" or b.get("format_version") != 1:
        raise HTTPException(422, "Not a valid OMNI backup file.")
    try:
        convs, msgs, mems, notes = b["conversations"], b["messages"], b["memories"], b["notes"]
        for lst in (convs, msgs, mems, notes):
            if not isinstance(lst, list):
                raise TypeError
        with db.session(settings.db_path) as conn:  # rolled back entirely on any error
            for t in ("messages", "conversations", "memories", "notes"):
                conn.execute(f"DELETE FROM {t}")
            for c in convs:
                conn.execute(
                    "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?,?,?,?)",
                    (c["id"], c["title"], c["created_at"], c["updated_at"]),
                )
            for m in msgs:
                conn.execute(
                    "INSERT INTO messages(id, conversation_id, role, content, created_at) VALUES (?,?,?,?,?)",
                    (m["id"], m["conversation_id"], m["role"], m["content"], m["created_at"]),
                )
            for m in mems:
                _no_secret(m["content"])
                conn.execute(
                    "INSERT INTO memories(id, kind, content, enabled, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (m["id"], m["kind"], m["content"], int(m["enabled"]), m["created_at"], m["updated_at"]),
                )
            for n in notes:
                conn.execute(
                    "INSERT INTO notes(id, title, body, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (n["id"], n["title"], n["body"], n["created_at"], n["updated_at"]),
                )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "The backup is malformed or inconsistent; nothing was changed.") from None
    return {"restored": {"conversations": len(convs), "messages": len(msgs), "memories": len(mems), "notes": len(notes)}}
