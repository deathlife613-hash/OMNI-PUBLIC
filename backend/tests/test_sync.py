import asyncio
import base64
import gzip
import json
import sqlite3

import httpx
import pytest

from app.core import db
from app.services.sync import HFDatasetStore, SyncManager, restore_snapshot, snapshot


class FakeHF:
    """In-memory stand-in for the Hugging Face dataset endpoints OMNI uses."""

    def __init__(self, private=True, status=200):
        self.private, self.status, self.file, self.commits, self.requests = private, status, None, 0, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append((req.method, req.url.path, req.headers.get("authorization")))
        p = req.url.path
        if self.status != 200:
            return httpx.Response(self.status)
        if p == "/api/datasets/me/omni-data":
            return httpx.Response(200, json={"private": self.private})
        if p == "/datasets/me/omni-data/resolve/main/omni.sql.gz":
            return httpx.Response(200, content=self.file) if self.file else httpx.Response(404)
        if p == "/api/datasets/me/omni-data/commit/main":
            lines = [json.loads(x) for x in req.content.decode().split("\n")]
            assert lines[0]["key"] == "header" and lines[1]["key"] == "file"
            assert lines[1]["value"]["path"] == "omni.sql.gz" and lines[1]["value"]["encoding"] == "base64"
            self.file = base64.b64decode(lines[1]["value"]["content"])
            self.commits += 1
            return httpx.Response(200, json={})
        return httpx.Response(404)


def mgr(tmp_path, hf, name="a.db", interval=0.05):
    store = HFDatasetStore("me/omni-data", "TOKEN", transport=httpx.MockTransport(hf))
    return SyncManager(store, tmp_path / name, interval)


def run(c):
    return asyncio.run(c)


def seed(path):
    db.init_db(path)
    db.set_meta(path, "ai_model", "openai/gpt-oss-120b")


def test_snapshot_roundtrip_restores_all_data(tmp_path):
    seed(tmp_path / "a.db")
    data, _ = snapshot(tmp_path / "a.db")
    restore_snapshot(data, tmp_path / "b.db")
    assert db.get_meta(tmp_path / "b.db", "ai_model") == "openai/gpt-oss-120b"
    assert db.init_db(tmp_path / "b.db") == db.init_db(tmp_path / "a.db")  # same schema version


def test_push_uploads_only_when_changed_then_restore_on_a_fresh_disk(tmp_path):
    hf = FakeHF()
    m = mgr(tmp_path, hf)
    seed(m.db_path)
    assert run(m.push()) is True and hf.commits == 1
    assert run(m.push()) is False and hf.commits == 1  # unchanged -> no commit
    db.set_meta(m.db_path, "ai_model", "other")
    assert run(m.push()) is True and hf.commits == 2
    assert all(auth == "Bearer TOKEN" for _, _, auth in hf.requests)
    # "restart on an ephemeral disk": new empty location, same remote
    fresh = mgr(tmp_path, hf, name="new.db")
    assert run(fresh.restore_if_needed()) is True
    assert db.get_meta(fresh.db_path, "ai_model") == "other"


def test_restore_never_overwrites_an_existing_local_database(tmp_path):
    hf = FakeHF()
    m = mgr(tmp_path, hf)
    seed(m.db_path)
    run(m.push())
    db.set_meta(m.db_path, "ai_model", "local-newer")
    assert run(m.restore_if_needed()) is False
    assert db.get_meta(m.db_path, "ai_model") == "local-newer"


def test_public_repo_is_refused_for_both_directions(tmp_path):
    hf = FakeHF(private=False)
    m = mgr(tmp_path, hf)
    seed(m.db_path)
    assert run(m.push()) is False and "repo_public" in m.last_error and hf.commits == 0
    fresh = mgr(tmp_path, hf, name="n.db")
    assert run(fresh.restore_if_needed()) is False and not fresh.db_path.exists()


def test_failed_restore_blocks_pushes_so_the_remote_is_not_overwritten_with_an_empty_db(tmp_path):
    hf = FakeHF()
    good = mgr(tmp_path, hf)
    seed(good.db_path)
    run(good.push())
    remote_before = hf.file
    hf.status = 503  # Hugging Face down at boot
    fresh = mgr(tmp_path, hf, name="boot.db")
    assert run(fresh.restore_if_needed()) is False and fresh.push_blocked
    db.init_db(fresh.db_path)  # app starts empty
    hf.status = 200
    assert run(fresh.push()) is False
    assert hf.file == remote_before and hf.commits == 1


def test_missing_snapshot_on_first_boot_is_not_an_error_and_pushing_is_allowed(tmp_path):
    hf = FakeHF()
    m = mgr(tmp_path, hf)
    assert run(m.restore_if_needed()) is False and not m.push_blocked and m.last_error is None
    db.init_db(m.db_path)
    assert run(m.push()) is True


def test_auth_failure_is_reported_without_leaking_the_token(tmp_path):
    hf = FakeHF(status=401)
    m = mgr(tmp_path, hf)
    seed(m.db_path)
    assert run(m.push()) is False
    assert m.last_error.startswith("auth") and "TOKEN" not in m.last_error


def test_oversized_snapshot_is_refused_clearly(tmp_path):
    hf = FakeHF()
    m = mgr(tmp_path, hf)
    seed(m.db_path)
    store = m.store
    with pytest.raises(Exception) as ei:
        run(store.upload(b"x" * (9 * 1024 * 1024)))
    assert getattr(ei.value, "kind", "") == "too_large"


def test_app_restores_on_startup_pushes_on_shutdown_and_status_reports_sync(make_client, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    hf = FakeHF()
    src = mgr(tmp_path, hf, name="src.db")
    seed(src.db_path)
    run(src.push())

    settings = Settings(_env_file=None, env="development", db_path=tmp_path / "boot.db", access_token="",
                        ai_api_key="", frontend_dist=tmp_path / "x", search_provider="",
                        sync_provider="hf_dataset", sync_hf_repo="me/omni-data", sync_hf_token="TOKEN", sync_interval_s=3600)
    app = create_app(settings, sync_transport=httpx.MockTransport(hf))
    with TestClient(app) as c:  # runs lifespan: restore, then init_db
        assert db.get_meta(settings.db_path, "ai_model") == "openai/gpt-oss-120b"
        st = c.get("/api/status").json()["integrations"]["sync"]
        assert st["configured"] is True and st["last_error"] is None and "TOKEN" not in json.dumps(st)
        db.set_meta(settings.db_path, "ai_model", "changed-before-shutdown")
    # leaving the context = graceful shutdown -> final push
    assert gzip.decompress(hf.file).decode().count("changed-before-shutdown") == 1


def test_sync_misconfiguration_is_reported_not_crashing(make_client):
    c = make_client(sync_provider="hf_dataset")  # no repo/token
    st = c.get("/api/status").json()["integrations"]["sync"]
    assert st["configured"] is False and "not_configured" in st["last_error"]
    assert make_client().get("/api/status").json()["integrations"]["sync"] == {"configured": False}


def test_open_access_requires_explicit_opt_in_in_production(make_client):
    assert make_client(env="production").get("/api/status").status_code == 503  # still fails closed
    c = make_client(env="production", allow_open_access=True)
    r = c.get("/api/status")
    assert r.status_code == 200 and r.json()["auth"] == {"token_required": False, "open_access": True}
    guarded = make_client(env="production", allow_open_access=True, access_token="t")
    assert guarded.get("/api/status").status_code == 401  # a token, when set, is always enforced
