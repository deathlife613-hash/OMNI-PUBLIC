"""Controlled coding workspace: READ-ONLY by default. The only write path is applying a diff the user
approved, and every write is confined to the authorized folder. No command execution exists anywhere."""
import difflib
import hashlib
import re
from pathlib import Path

from app.tools.base import ToolError

BLOCKED_NAME = re.compile(r"(^\.env|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$|\.sqlite3?$|\.db$|secret|credential|password|token)", re.I)
BLOCKED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", ".ssh"}
TEXT_EXT = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".sh", ".ps1", ".csv", ".ini", ".cfg"}


def root_of(workspace_dir) -> Path:
    if not workspace_dir:
        raise ToolError("No workspace is authorized. Set OMNI_WORKSPACE_DIR to a project folder.")
    root = Path(workspace_dir).resolve()
    if not root.is_dir():
        raise ToolError("The configured workspace folder does not exist.")
    return root


def resolve(root: Path, rel: str, *, must_exist: bool) -> Path:
    """Map a user/model-supplied relative path to a safe absolute path inside root, or raise."""
    if not rel or "\x00" in rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        raise ToolError("Invalid path.")
    p = (root / rel)
    parts = Path(rel).parts
    if ".." in parts or any(x in BLOCKED_DIRS for x in parts) or BLOCKED_NAME.search(Path(rel).name):
        raise ToolError("That path is not allowed (outside the workspace, or a protected file).")
    if Path(rel).suffix.lower() not in TEXT_EXT:
        raise ToolError("Only text/code file types can be viewed or edited.")
    # no symlink anywhere between root and the target
    cur = root
    for part in parts:
        cur = cur / part
        if cur.is_symlink():
            raise ToolError("Symlinks are not allowed in the workspace.")
    real = p.resolve()
    if root != real and root not in real.parents:
        raise ToolError("That path is outside the workspace.")
    if must_exist and not real.is_file():
        raise ToolError("File not found.")
    if not must_exist and not real.parent.is_dir():
        raise ToolError("The target folder does not exist.")
    return real


def tree(root: Path, limit: int = 300) -> list[str]:
    out = []
    for p in sorted(root.rglob("*")):
        try:
            rel = p.relative_to(root)
            if any(x in BLOCKED_DIRS for x in rel.parts) or p.is_symlink() or not p.is_file():
                continue
            if p.suffix.lower() in TEXT_EXT and not BLOCKED_NAME.search(p.name):
                out.append(rel.as_posix())
        except (OSError, ValueError):
            continue
        if len(out) >= limit:
            break
    return out


def read_text(root: Path, rel: str, max_bytes: int) -> str:
    p = resolve(root, rel, must_exist=True)
    if p.stat().st_size > max_bytes:
        raise ToolError("File is too large to open here.")
    return p.read_text(encoding="utf-8", errors="replace")


def make_diff(path: str, old: str | None, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            (old or "").splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{path}" if old is not None else "/dev/null", tofile=f"b/{path}",
        )
    )


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
