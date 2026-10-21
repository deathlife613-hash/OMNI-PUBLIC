"""Restart-surviving persistence for hosts with an ephemeral disk (e.g. Render's free web service).

The SQLite database is snapshotted as gzipped SQL text and stored in a PRIVATE Hugging Face Dataset repo
(free, no card). On startup, if there is no local database, the latest snapshot is restored. While running,
a snapshot is pushed every `sync_interval_s` when something changed, and once more at graceful shutdown.

Honest limits: writes made after the last successful push are lost if the host kills the process without
a graceful shutdown; HF's simple commit API caps a file at ~10 MB, so very large databases are refused
(an error is reported, never silently ignored); the repo must be private or sync refuses to run.
"""
import asyncio
import base64
import gzip
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core import db

log = logging.getLogger("omni.sync")
HF = "https://huggingface.co"
SNAPSHOT_NAME = "omni.sql.gz"
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


class SyncError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind, self.message = kind, message


def snapshot(db_path: Path) -> tuple[bytes, str]:
    """Returns (gzipped SQL dump, sha256 of the dump). Deterministic so unchanged data hashes equally."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        sql = "\n".join(conn.iterdump()).encode()
    finally:
        conn.close()
    return gzip.compress(sql, mtime=0), hashlib.sha256(sql).hexdigest()


def restore_snapshot(data: bytes, db_path: Path) -> None:
    """Builds a fresh database from a snapshot and moves it into place atomically."""
    sql = gzip.decompress(data).decode()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=db_path.parent, suffix=".restore")
    os.close(fd)
    os.unlink(tmp)
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)


class HFDatasetStore:
    def __init__(self, repo: str, token: str, transport=None, timeout: float = 30):
        self.repo, self.token, self.transport, self.timeout = repo, token, transport, timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout, follow_redirects=True,
            headers={"Authorization": f"Bearer {self.token}"},
        )

    async def _call(self, method: str, url: str, **kw) -> httpx.Response:
        try:
            async with self._client() as c:
                return await c.request(method, url, **kw)
        except httpx.TimeoutException:
            raise SyncError("timeout", "Hugging Face did not respond in time.") from None
        except httpx.HTTPError:
            raise SyncError("unavailable", "Could not reach Hugging Face.") from None

    async def check_private(self) -> None:
        r = await self._call("GET", f"{HF}/api/datasets/{self.repo}")
        if r.status_code in (401, 403):
            raise SyncError("auth", "Hugging Face rejected the token (needs read+write access to the dataset).")
        if r.status_code == 404:
            raise SyncError("not_found", f"Dataset '{self.repo}' not found. Create it as a PRIVATE dataset first.")
        if r.status_code != 200:
            raise SyncError("unavailable", f"Hugging Face returned {r.status_code}.")
        if r.json().get("private") is not True:
            raise SyncError("repo_public", f"Dataset '{self.repo}' is not private. OMNI refuses to sync personal data to a public repo.")

    async def download(self) -> bytes | None:
        r = await self._call("GET", f"{HF}/datasets/{self.repo}/resolve/main/{SNAPSHOT_NAME}")
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            raise SyncError("auth", "Hugging Face rejected the token.")
        if r.status_code != 200:
            raise SyncError("unavailable", f"Hugging Face returned {r.status_code}.")
        return r.content

    async def upload(self, data: bytes) -> None:
        if len(data) > MAX_SNAPSHOT_BYTES:
            raise SyncError("too_large", "The compressed database exceeds 8 MB, which the simple sync cannot store.")
        lines = [
            {"key": "header", "value": {"summary": "OMNI snapshot"}},
            {"key": "file", "value": {"content": base64.b64encode(data).decode(), "path": SNAPSHOT_NAME, "encoding": "base64"}},
        ]
        body = "\n".join(json.dumps(x) for x in lines)
        r = await self._call(
            "POST", f"{HF}/api/datasets/{self.repo}/commit/main",
            content=body, headers={"Content-Type": "application/x-ndjson"},
        )
        if r.status_code in (401, 403):
            raise SyncError("auth", "Hugging Face rejected the token (write access needed).")
        if r.status_code >= 400:
            raise SyncError("unavailable", f"Hugging Face commit failed ({r.status_code}).")


class SyncManager:
    def __init__(self, store: HFDatasetStore | None, db_path: Path, interval_s: float, config_error: str | None = None):
        self.store, self.db_path, self.interval_s = store, db_path, interval_s
        self.last_hash: str | None = None
        self.last_success: str | None = None
        self.last_error: str | None = config_error
        self.pushes = 0
        self.push_blocked = False  # set when a startup restore FAILED: never overwrite the remote with an empty DB
        self._private_ok = False
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.store is not None

    def state(self) -> dict:
        return {"configured": self.enabled, "provider": "hf_dataset", "last_success": self.last_success,
                "last_error": self.last_error, "pushes": self.pushes}

    def _fail(self, e: SyncError) -> None:
        self.last_error = f"{e.kind}: {e.message}"
        log.warning("sync failed: %s", self.last_error)

    async def _ensure_private(self) -> None:
        if not self._private_ok:
            await self.store.check_private()
            self._private_ok = True

    async def restore_if_needed(self) -> bool:
        """Only when there is no local database - never overwrites existing local data."""
        if not self.enabled or self.db_path.exists():
            return False
        try:
            await self._ensure_private()
            data = await self.store.download()
            if data is None:
                return False
            await asyncio.to_thread(restore_snapshot, data, self.db_path)
            self.last_success = datetime.now(timezone.utc).isoformat()
            self.last_error = None
            return True
        except SyncError as e:
            self.push_blocked = True
            self._fail(e)
        except Exception as e:  # corrupt snapshot etc.: start empty rather than crash the app
            self.push_blocked = True
            self.last_error = f"restore_failed: {type(e).__name__}"
            log.warning("restore failed: %s", type(e).__name__)
        return False

    async def push(self, force: bool = False) -> bool:
        if not self.enabled or not self.db_path.exists() or self.push_blocked:
            return False
        async with self._lock:
            try:
                data, digest = await asyncio.to_thread(snapshot, self.db_path)
                if digest == self.last_hash and not force:
                    return False
                await self._ensure_private()
                await self.store.upload(data)
                self.last_hash, self.pushes = digest, self.pushes + 1
                self.last_success = datetime.now(timezone.utc).isoformat()
                self.last_error = None
                return True
            except SyncError as e:
                self._fail(e)
            except Exception as e:
                self.last_error = f"push_failed: {type(e).__name__}"
                log.warning("push failed: %s", type(e).__name__)
            return False

    async def run_forever(self) -> None:
        while True:
            await asyncio.sleep(self.interval_s)
            await self.push()


def build_sync(settings, transport=None) -> SyncManager | None:
    if not settings.sync_provider:
        return None
    if db.is_postgres(settings.db_path):
        return SyncManager(None, settings.db_path, settings.sync_interval_s, "not_supported: HF snapshot sync is for SQLite mode; with Postgres use JSON export for backups")
    if settings.sync_provider != "hf_dataset":
        return SyncManager(None, settings.db_path, settings.sync_interval_s, f"unsupported sync provider '{settings.sync_provider}'")
    if not settings.sync_hf_repo or not settings.sync_hf_token:
        return SyncManager(None, settings.db_path, settings.sync_interval_s, "not_configured: set OMNI_SYNC_HF_REPO and OMNI_SYNC_HF_TOKEN")
    return SyncManager(HFDatasetStore(settings.sync_hf_repo, settings.sync_hf_token, transport), settings.db_path, settings.sync_interval_s)
