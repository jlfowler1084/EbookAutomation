"""EB-332: a failed top-level premium /convert must refund the consumed token.

Mirrors tests/test_web_reconvert.py's refund integration test, but for the
first-conversion path (no parent_job_id). The fix persists token_hash on the
job row in convert.py so job_queue.dispatch_job's existing failure-refund hook
fires for top-level uploads too.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from web_service.job_queue import dispatch_job as _real_dispatch_job  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings():
    from web_service.config import reset_settings
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def project_root(tmp_path, monkeypatch):
    cfg = {"paths": {"calibre": "/usr/bin/ebook-convert", "python": "/usr/bin/python3", "kindle": "output/kindle"}}
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp_path / "data").mkdir()
    import web_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path


@pytest.fixture()
def client(project_root):
    import importlib
    import web_service.job_store as js
    import web_service.main as main_mod
    from web_service.config import load_settings

    settings = load_settings()
    js.init_db(settings.db_path)
    importlib.reload(main_mod)

    with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()), \
         patch("web_service.job_queue.init_queue"), \
         patch("web_service.job_queue.cleanup_expired_jobs", return_value=AsyncMock()):
        with TestClient(main_mod.app) as tc:
            yield tc, settings.db_path, settings


def _premium_kfx_post(tc, db_path, *, session_id, pi_id):
    """Mint a token, POST a premium kfx /convert, return (job_id, token)."""
    import web_service.token_store as ts
    ts.init_db(db_path)
    mint = ts.mint_tokens_if_absent(session_id=session_id, count=1, payment_intent_id=pi_id, db_path=db_path)
    assert mint.ok
    token = mint.tokens[0]
    files = {"file": ("book.pdf", b"%PDF-1.4\n" + b"\x00" * 4000, "application/pdf")}
    resp = tc.post("/convert", files=files, data={"output_format": "kfx", "tier": "premium", "token": token})
    assert resp.status_code == 202, resp.text
    return resp.json()["job_id"], token


@pytest.mark.asyncio
async def test_failed_premium_convert_refunds_token(client, monkeypatch):
    """A top-level premium kfx job that fails in the pipeline refunds the token."""
    import web_service.job_store as js
    from web_service import job_queue, pipeline_runner

    tc, db_path, settings = client
    job_id, _ = _premium_kfx_post(tc, db_path, session_id="cs_eb332_refund", pi_id="pi_eb332_refund")

    # token_hash must be persisted on the top-level job (this is the fix).
    assert js.get_job(job_id)["token_hash"] is not None, "convert.py must persist token_hash"

    conn = sqlite3.connect(str(db_path))
    assert conn.execute("SELECT used FROM tokens WHERE pack_id=?", ("cs_eb332_refund",)).fetchone()[0] == 1
    conn.close()

    sem_executor = ThreadPoolExecutor(max_workers=1)
    bill_executor = ThreadPoolExecutor(max_workers=1)
    try:
        monkeypatch.setattr(job_queue, "_semaphore", asyncio.Semaphore(1))
        monkeypatch.setattr(job_queue, "_executor", sem_executor)
        monkeypatch.setattr(job_queue, "billing_executor", bill_executor)
        monkeypatch.setattr(
            job_queue, "_run_job",
            lambda job: pipeline_runner.RunResult(success=False, output_path="", output_size=0, error_message="forced kfx failure"),
        )
        await _real_dispatch_job(job_id)
    finally:
        sem_executor.shutdown(wait=False)
        bill_executor.shutdown(wait=False)

    assert js.get_job(job_id)["status"] == "failed"
    conn = sqlite3.connect(str(db_path))
    used_after = conn.execute("SELECT used FROM tokens WHERE pack_id=?", ("cs_eb332_refund",)).fetchone()[0]
    ledger = conn.execute("SELECT refund_reason FROM refund_ledger WHERE failed_job_id=?", (job_id,)).fetchall()
    events = conn.execute("SELECT COUNT(*) FROM recovery_events WHERE event_type='premium_refund_applied'").fetchone()[0]
    conn.close()

    assert used_after == 0, "token must be refunded after a top-level premium failure"
    assert [r[0] for r in ledger] == ["pipeline_failed"], f"expected one pipeline_failed ledger row, got {ledger}"
    assert events == 1, "a premium_refund_applied telemetry event must be emitted (not reconvert_refund_applied)"
