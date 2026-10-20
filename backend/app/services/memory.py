"""Long-term memory helpers. Memories are created only by the user (or approved by them in the UI);
OMNI never writes them on its own. Retrieval is keyword-based and bounded, so only relevant
memories are sent to the model instead of everything."""
import re
import sqlite3

SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{12,}|"
    r"password\s*[:=]|api[_-]?key\s*[:=]|bearer\s+[A-Za-z0-9._-]{16,})",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "what", "when", "have", "has", "not"}


def looks_like_secret(text: str) -> bool:
    return bool(SECRET_RE.search(text))


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def relevant_memories(
    conn: sqlite3.Connection, query: str, *, limit: int = 8, char_budget: int = 1500
) -> list[str]:
    """Enabled preferences first (they are short and always useful), then facts that share
    keywords with `query`, best match first. Never exceeds `limit` items or `char_budget`."""
    rows = conn.execute("SELECT kind, content FROM memories WHERE enabled = 1 ORDER BY id").fetchall()
    q = _words(query)
    prefs = [r["content"] for r in rows if r["kind"] == "preference"]
    scored = []
    for r in rows:
        if r["kind"] == "fact":
            overlap = len(q & _words(r["content"]))
            if overlap:
                scored.append((overlap, r["content"]))
    scored.sort(key=lambda t: -t[0])
    out, used = [], 0
    for text in [*prefs, *(t for _, t in scored)]:
        if len(out) >= limit or used + len(text) > char_budget:
            break
        out.append(text)
        used += len(text)
    return out
