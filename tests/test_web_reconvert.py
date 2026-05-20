"""Tests for POST /reconvert/{parent_job_id} — EB-324 Unit 3.

The reconvert endpoint creates a re-convert child job that re-uses the parent
upload's already-on-disk source. Free tier produces additional formats (mobi)
with no token; premium produces token-gated formats (kfx) and consumes a
single-use token. If the child later fails inside the pipeline, the consumed
token must be refunded via token_store.refund_token() — wired in job_queue's
dispatch_job failure path.

R2.5 (parent-TTL elapses while child is running) lives in test_web_sweeps.py
because that's where the cleanup-sweep machinery is exercised.

Fixture design mirrors tests/test_web_endpoints.py (project_root → client with
dispatch_job mocked + queue init no-op'd) so the suite never touches the real
conversion pipeline.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Bind a reference to the REAL dispatch_job at module-import time. The client
# fixture below patches `web_service.routes.convert.job_queue.dispatch_job`
# with an AsyncMock so route handlers don't kick off real conversions — but
# that patch also shadows job_queue.dispatch_job for the refund tests, which
# need to invoke the real failure path. This module-level alias dodges the
# patch by capturing the function object before any fixture is active.
from web_service.job_queue import dispatch_job as _real_dispatch_job  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_settings():
    from web_service.config import reset_settings
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def project_root(tmp_path, monkeypatch):
    """Temp project root with minimal config/settings.json — mirrors test_web_endpoints.py."""
    cfg = {
        "paths": {
            "calibre": "/usr/bin/ebook-convert",
            "python": "/usr/bin/python3",
            "kindle": "output/kindle",
        }
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp_path / "data").mkdir()

    import web_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path


@pytest.fixture()
def client(project_root):
    """TestClient backed by a fresh temp DB with dispatch_job mocked on both routes."""
    import importlib

    import web_service.job_store as js
    import web_service.main as main_mod
    from web_service.config import load_settings

    settings = load_settings()
    js.init_db(settings.db_path)

    importlib.reload(main_mod)

    # Both convert and reconvert dispatch paths are mocked so the test never
    # touches the real pipeline. Reconvert module may not exist on RED — patch
    # only if importable so the suite can run before the route ships.
    import importlib.util as ilu
    reconvert_exists = ilu.find_spec("web_service.routes.reconvert") is not None

    convert_patch = patch(
        "web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()
    )
    init_patch = patch("web_service.job_queue.init_queue")
    cleanup_patch = patch(
        "web_service.job_queue.cleanup_expired_jobs", return_value=AsyncMock()
    )

    with convert_patch, init_patch, cleanup_patch:
        if reconvert_exists:
            with patch(
                "web_service.routes.reconvert.job_queue.dispatch_job",
                new=AsyncMock(),
            ):
                with TestClient(main_mod.app) as tc:
                    yield tc, settings.db_path, settings
        else:
            with TestClient(main_mod.app) as tc:
                yield tc, settings.db_path, settings


def _seed_done_parent(settings, *, input_fmt: str = "pdf") -> tuple[str, Path]:
    """Create a done parent job with an actual source file on disk.

    Returns (parent_job_id, parent_temp_dir).
    """
    import web_service.job_store as js

    parent_id = js.new_job_id()
    parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
    parent_temp.mkdir(parents=True, exist_ok=True)
    src = parent_temp / f"input.{input_fmt}"
    src.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)

    js.create_job(
        job_id=parent_id,
        tier="free",
        input_fmt=input_fmt,
        output_fmt="epub",
        temp_dir=str(parent_temp),
        input_path=str(src),
    )
    out = parent_temp / "output.epub"
    out.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    js.set_done(parent_id, str(out), out.stat().st_size)
    return parent_id, parent_temp


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestReconvertHappyPath:
    def test_free_mobi_creates_child_with_copied_source(self, client):
        """Free tier mobi re-convert → 202; child has parent_job_id; source copied."""
        import web_service.job_store as js

        tc, _, settings = client
        parent_id, parent_temp = _seed_done_parent(settings)

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "mobi"},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "job_id" in body
        child_id = body["job_id"]

        child = js.get_job(child_id)
        assert child is not None
        assert child["parent_job_id"] == parent_id
        assert child["output_fmt"] == "mobi"
        assert child["tier"] == "free"
        assert child["token_hash"] is None
        # Source copied — not moved or symlinked.
        child_input = Path(child["input_path"])
        assert child_input.exists()
        assert child_input != Path(js.get_job(parent_id)["input_path"])
        assert (parent_temp / "input.pdf").exists(), (
            "Parent source must remain intact — re-convert is a copy, not a move"
        )

    def test_premium_kfx_consumes_token_and_persists_token_hash(self, client):
        """Premium kfx re-convert with valid token → 202; token used=1; child.token_hash set."""
        import web_service.job_store as js
        import web_service.token_store as ts
        from web_service.crypto import compute_token_hash

        tc, db_path, settings = client
        ts.init_db(db_path)
        parent_id, _ = _seed_done_parent(settings)

        mint_result = ts.mint_tokens_if_absent(
            session_id="cs_test_reconvert_premium",
            count=1,
            payment_intent_id="pi_test_reconvert_premium",
            db_path=db_path,
        )
        assert mint_result.ok
        token = mint_result.tokens[0]
        expected_hash_hex = compute_token_hash(token).hex()

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "kfx", "token": token},
        )
        assert resp.status_code == 202, resp.text
        child_id = resp.json()["job_id"]

        # Token consumed in tokens table.
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT used FROM tokens WHERE pack_id = ?",
            ("cs_test_reconvert_premium",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 1, "Token must be consumed by the premium re-convert"

        # token_hash_hex persisted on child row so refund can locate it later.
        child = js.get_job(child_id)
        assert child["token_hash"] == expected_hash_hex
        assert child["tier"] == "premium"
        assert child["output_fmt"] == "kfx"


# ---------------------------------------------------------------------------
# Parent-state validation
# ---------------------------------------------------------------------------


class TestReconvertParentValidation:
    def test_unknown_parent_returns_404(self, client):
        tc, _, _ = client
        resp = tc.post(
            "/reconvert/00000000-0000-0000-0000-000000000000",
            data={"output_format": "mobi"},
        )
        assert resp.status_code == 404

    def test_parent_not_done_returns_422(self, client):
        """Parent still queued or running → 422 — can't re-convert before parent finishes."""
        import web_service.job_store as js

        tc, _, settings = client
        # Seed a parent that is queued, not done.
        parent_id = js.new_job_id()
        parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
        parent_temp.mkdir(parents=True, exist_ok=True)
        (parent_temp / "input.pdf").write_bytes(b"%PDF-1.4\n" + b"\x00" * 100)
        js.create_job(
            job_id=parent_id,
            tier="free",
            input_fmt="pdf",
            output_fmt="epub",
            temp_dir=str(parent_temp),
            input_path=str(parent_temp / "input.pdf"),
        )
        # Status is queued, not done.

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "mobi"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_PARENT_STATE"

    def test_parent_source_missing_returns_410(self, client):
        """Parent done but its source file has been rm'd → 410 Gone."""
        tc, _, settings = client
        parent_id, parent_temp = _seed_done_parent(settings)

        # Simulate the TTL sweep having rm'd the temp dir.
        import shutil
        shutil.rmtree(parent_temp, ignore_errors=True)

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "mobi"},
        )
        assert resp.status_code == 410
        assert resp.json()["detail"]["code"] == "PARENT_SOURCE_EXPIRED"


# ---------------------------------------------------------------------------
# Token validation on premium re-convert
# ---------------------------------------------------------------------------


class TestReconvertPremiumTokenValidation:
    def test_premium_missing_token_returns_422_missing_token(self, client):
        tc, _, settings = client
        parent_id, _ = _seed_done_parent(settings)

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "kfx"},  # premium format, no token
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "MISSING_TOKEN"

    def test_premium_malformed_token_returns_422(self, client):
        tc, _, settings = client
        parent_id, _ = _seed_done_parent(settings)

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "kfx", "token": "not-a-real-token"},
        )
        assert resp.status_code == 422
        # token_validation.validate_token_format rejects malformed input with
        # TokenValidationErrorCode.MALFORMED (matches the /convert contract).
        assert resp.json()["detail"]["code"] == "MALFORMED"

    def test_premium_already_used_token_returns_422_already_used(self, client):
        """Token used by /convert first → then re-convert tries same token → 422 ALREADY_USED."""
        import web_service.token_store as ts

        tc, db_path, settings = client
        ts.init_db(db_path)
        parent_id, _ = _seed_done_parent(settings)

        mint_result = ts.mint_tokens_if_absent(
            session_id="cs_test_reconvert_reused",
            count=1,
            payment_intent_id="pi_test_reconvert_reused",
            db_path=db_path,
        )
        token = mint_result.tokens[0]

        # First use succeeds.
        first = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "kfx", "token": token},
        )
        assert first.status_code == 202

        # Second use of the same token must fail.
        second = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "kfx", "token": token},
        )
        assert second.status_code == 422
        assert second.json()["detail"]["code"] == "ALREADY_USED"

    def test_free_tier_cannot_request_premium_format(self, client):
        """Re-convert with kfx but no token → 422 (premium format requires premium tier)."""
        tc, _, settings = client
        parent_id, _ = _seed_done_parent(settings)

        # No token, premium format — same shape as missing-token, just confirming
        # the route doesn't silently downgrade to free.
        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "kfx"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Refund integration — failure path in job_queue.dispatch_job
# ---------------------------------------------------------------------------


class TestReconvertRefundOnChildFailure:
    """When a premium child fails inside the pipeline, the consumed token must
    be refunded via token_store.refund_token(). The hook lives in
    job_queue.dispatch_job's failure branch; this test exercises it end-to-end
    by mocking _run_job to return a failed RunResult.
    """

    @pytest.mark.asyncio
    async def test_failed_child_with_token_hash_triggers_refund(self, client, monkeypatch):
        """Force a premium child to fail → token's used flips back to 0 + refund_ledger row."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        import web_service.job_store as js
        import web_service.token_store as ts
        from web_service import job_queue, pipeline_runner

        tc, db_path, settings = client
        ts.init_db(db_path)
        parent_id, _ = _seed_done_parent(settings)

        # Mint and consume a token via the /reconvert path so we have a child
        # job with token_hash persisted.
        mint_result = ts.mint_tokens_if_absent(
            session_id="cs_test_reconvert_refund",
            count=1,
            payment_intent_id="pi_test_reconvert_refund",
            db_path=db_path,
        )
        token = mint_result.tokens[0]

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "kfx", "token": token},
        )
        assert resp.status_code == 202
        child_id = resp.json()["job_id"]

        # Confirm the token is consumed and the child has token_hash set.
        conn = sqlite3.connect(str(db_path))
        used_before = conn.execute(
            "SELECT used FROM tokens WHERE pack_id = ?",
            ("cs_test_reconvert_refund",),
        ).fetchone()[0]
        conn.close()
        assert used_before == 1
        assert js.get_job(child_id)["token_hash"] is not None

        # Initialise queue executors so dispatch_job can run.
        sem_executor = ThreadPoolExecutor(max_workers=1)
        bill_executor = ThreadPoolExecutor(max_workers=1)
        try:
            monkeypatch.setattr(job_queue, "_semaphore", asyncio.Semaphore(1))
            monkeypatch.setattr(job_queue, "_executor", sem_executor)
            monkeypatch.setattr(job_queue, "billing_executor", bill_executor)

            def _fail_run_job(job):
                return pipeline_runner.RunResult(
                    success=False,
                    output_path="",
                    output_size=0,
                    error_message="forced failure for refund test",
                )

            monkeypatch.setattr(job_queue, "_run_job", _fail_run_job)

            await _real_dispatch_job(child_id)
        finally:
            sem_executor.shutdown(wait=False)
            bill_executor.shutdown(wait=False)

        # Child should be set_failed.
        child_after = js.get_job(child_id)
        assert child_after["status"] == "failed"

        # Token must be refunded: used flips back to 0, and a refund_ledger row exists.
        conn = sqlite3.connect(str(db_path))
        used_after = conn.execute(
            "SELECT used FROM tokens WHERE pack_id = ?",
            ("cs_test_reconvert_refund",),
        ).fetchone()[0]
        ledger_rows = conn.execute(
            "SELECT failed_job_id, refund_reason FROM refund_ledger WHERE failed_job_id = ?",
            (child_id,),
        ).fetchall()
        conn.close()

        assert used_after == 0, (
            "Token must be refunded (used=0) after the child fails — wired in "
            "job_queue.dispatch_job's failure path"
        )
        assert len(ledger_rows) == 1, (
            f"Exactly one refund_ledger row expected for the failed child, got: {ledger_rows}"
        )

    @pytest.mark.asyncio
    async def test_failed_free_child_does_not_invoke_refund(self, client, monkeypatch):
        """Free children have token_hash=None — refund path must NOT fire."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        import web_service.job_store as js
        from web_service import job_queue, pipeline_runner

        tc, db_path, settings = client
        parent_id, _ = _seed_done_parent(settings)

        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "mobi"},  # free
        )
        assert resp.status_code == 202
        child_id = resp.json()["job_id"]
        assert js.get_job(child_id)["token_hash"] is None

        sem_executor = ThreadPoolExecutor(max_workers=1)
        bill_executor = ThreadPoolExecutor(max_workers=1)
        refund_calls = []

        def _capturing_refund(*args, **kwargs):
            refund_calls.append((args, kwargs))
            raise AssertionError(
                "refund_token must NOT be called for free children — guard the "
                "hook with 'if child.token_hash is not None'"
            )

        try:
            monkeypatch.setattr(job_queue, "_semaphore", asyncio.Semaphore(1))
            monkeypatch.setattr(job_queue, "_executor", sem_executor)
            monkeypatch.setattr(job_queue, "billing_executor", bill_executor)
            monkeypatch.setattr(
                job_queue, "_run_job",
                lambda job: pipeline_runner.RunResult(
                    success=False,
                    output_path="",
                    output_size=0,
                    error_message="free failure",
                ),
            )
            monkeypatch.setattr(job_queue.token_store, "refund_token", _capturing_refund)

            await _real_dispatch_job(child_id)
        finally:
            sem_executor.shutdown(wait=False)
            bill_executor.shutdown(wait=False)

        assert js.get_job(child_id)["status"] == "failed"
        assert refund_calls == [], "refund_token must not be called when token_hash is None"
