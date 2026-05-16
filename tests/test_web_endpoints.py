"""Tests for web service HTTP endpoints — POST /convert, GET /status, GET /download."""

from __future__ import annotations

import json
import sys
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from web_service.config import reset_settings
from web_service.job_store import STATUS_DONE, STATUS_EXPIRED, STATUS_FAILED, STATUS_QUEUED

PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 300


@pytest.fixture(autouse=True)
def clear_settings():
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def project_root(tmp_path, monkeypatch):
    """Set up a temp project root with a minimal config/settings.json."""
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
    """TestClient backed by a fresh temp DB; dispatch_job is mocked (no real pipeline)."""
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
            yield tc, settings.db_path


def _seed_job(db_path, status=STATUS_QUEUED, output_file: Path | None = None):
    """Create a job record and return its job_id."""
    import web_service.job_store as js
    jid = js.new_job_id()
    js.create_job(
        job_id=jid,
        tier="free",
        input_fmt="pdf",
        output_fmt="epub",
        temp_dir=str(db_path.parent),
        input_path=str(db_path.parent / "input.pdf"),
        db_path=db_path,
    )
    if status == STATUS_DONE and output_file:
        js.set_done(jid, str(output_file), output_file.stat().st_size, db_path=db_path)
    elif status == STATUS_FAILED:
        js.set_failed(jid, "Pipeline crashed", db_path=db_path)
    elif status == STATUS_EXPIRED:
        js.set_expired(jid, db_path=db_path)
    return jid


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_ok(self, client):
        tc, _ = client
        resp = tc.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        # Phase 2 (EB-45 Unit 1) added ntp_synced — should be True in tests
        # because the NTP check defaults to True when unavailable (Windows/macOS dev hosts).
        assert body["ntp_synced"] is True


# ---------------------------------------------------------------------------
# POST /convert
# ---------------------------------------------------------------------------


class TestConvertEndpoint:
    def test_valid_pdf_returns_202_with_job_id(self, client):
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert len(body["job_id"]) == 36  # UUID4 length

    def test_empty_file_returns_422(self, client):
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free"},
            files={"file": ("book.pdf", BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code == 422

    def test_kfx_on_free_tier_returns_422(self, client):
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "free"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422

    def test_png_disguised_as_pdf_rejected(self, client):
        tc, _ = client
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 300
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free"},
            files={"file": ("notapdf.pdf", BytesIO(png_bytes), "application/pdf")},
        )
        assert resp.status_code == 422

    # -----------------------------------------------------------------------
    # Phase 2 (Unit 6): token validation tests
    # -----------------------------------------------------------------------

    def test_premium_without_token_returns_422_missing_token(self, client):
        """tier=premium with no token → 422 MISSING_TOKEN."""
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "MISSING_TOKEN"

    def test_premium_with_malformed_token_returns_422_malformed(self, client):
        """tier=premium with a token that fails the format regex → 422 MALFORMED."""
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": "not_a_valid_format"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "MALFORMED"

    def test_premium_with_unknown_token_returns_422_invalid_or_expired(self, client):
        """tier=premium with correct-format token not in DB → 422 TOKEN_INVALID_OR_EXPIRED."""
        tc, db_path = client
        import web_service.token_store as ts
        ts.init_db(db_path)

        # Valid format but not stored in DB
        unknown_token = "lb_pk_" + "A" * 43
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": unknown_token},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "INVALID_OR_EXPIRED"

    def test_premium_with_valid_token_consumes_and_returns_202(self, client):
        """tier=premium with a valid minted token → 202 + job_id; token is consumed."""
        import sqlite3

        import web_service.token_store as ts

        tc, db_path = client
        ts.init_db(db_path)

        # Mint a real token to consume
        mint_result = ts.mint_tokens_if_absent(
            session_id="cs_test_unit6_valid",
            count=1,
            payment_intent_id="pi_test_unit6",
            db_path=db_path,
        )
        assert mint_result.ok
        token = mint_result.tokens[0]

        with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()):
            resp = tc.post(
                "/convert",
                data={"output_format": "kfx", "tier": "premium", "token": token},
                files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body

        # Verify token is now marked used=1 in DB
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT used FROM tokens WHERE pack_id=?",
            ("cs_test_unit6_valid",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 1

    def test_premium_with_already_used_token_returns_422_already_used(self, client):
        """Using the same token twice → second call returns 422 TOKEN_ALREADY_USED."""
        import web_service.token_store as ts

        tc, db_path = client
        ts.init_db(db_path)

        mint_result = ts.mint_tokens_if_absent(
            session_id="cs_test_unit6_double",
            count=1,
            payment_intent_id="pi_test_unit6_double",
            db_path=db_path,
        )
        assert mint_result.ok
        token = mint_result.tokens[0]

        with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()):
            resp1 = tc.post(
                "/convert",
                data={"output_format": "kfx", "tier": "premium", "token": token},
                files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
            )
        assert resp1.status_code == 202

        resp2 = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": token},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp2.status_code == 422
        body = resp2.json()
        assert body["detail"]["code"] == "ALREADY_USED"

    def test_premium_with_disputed_token_returns_422_disputed(self, client):
        """Minting then marking disputed → 422 TOKEN_DISPUTED."""
        import web_service.token_store as ts

        tc, db_path = client
        ts.init_db(db_path)

        session_id = "cs_test_unit6_disputed"
        mint_result = ts.mint_tokens_if_absent(
            session_id=session_id,
            count=1,
            payment_intent_id="pi_test_unit6_disputed",
            db_path=db_path,
        )
        assert mint_result.ok
        token = mint_result.tokens[0]

        ts.mark_disputed(session_id, db_path=db_path)

        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": token},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "DISPUTED"

    def test_premium_with_expired_token_returns_422_invalid_or_expired(self, client):
        """Token minted with expires_at in the past → 422 TOKEN_INVALID_OR_EXPIRED."""
        import sqlite3

        import web_service.token_store as ts
        from web_service.crypto import compute_token_hash, get_fernet, mint_token

        tc, db_path = client
        ts.init_db(db_path)

        # Manually insert an expired token
        token_str, token_hash = mint_token()
        f = get_fernet(key_version=1)
        encrypted = f.encrypt(token_str.encode())
        past = int(time.time()) - 100  # 100 seconds ago

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO tokens
               (token_hash, token_encrypted_for_recovery, key_version,
                pack_id, payment_intent_id, created_at, expires_at, used, disputed)
               VALUES (?, ?, 1, ?, ?, ?, ?, 0, 0)""",
            (token_hash, encrypted, "cs_test_unit6_expired", "pi_unit6_expired", past, past),
        )
        conn.commit()
        conn.close()

        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": token_str},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "INVALID_OR_EXPIRED"

    def test_free_tier_ignores_token_field(self, client):
        """tier=free with any token value → 202 (token field silently ignored)."""
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free", "token": "some_random_token"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    def test_circuit_breaker_open_returns_503(self, client):
        """When circuit breaker is open, premium conversion returns 503 DB_UNAVAILABLE."""
        import web_service.circuit_breaker as cb

        tc, db_path = client
        import web_service.token_store as ts
        ts.init_db(db_path)

        # Valid-format token (format check passes before circuit breaker check)
        valid_format_token = "lb_pk_" + "B" * 43

        # Force circuit open
        original_open_until = cb._circuit_open_until
        cb._circuit_open_until = float("inf")
        try:
            resp = tc.post(
                "/convert",
                data={"output_format": "kfx", "tier": "premium", "token": valid_format_token},
                files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
            )
        finally:
            cb._circuit_open_until = original_open_until

        assert resp.status_code == 503
        body = resp.json()
        assert body["detail"]["code"] == "DB_UNAVAILABLE"


# ---------------------------------------------------------------------------
# GET /status/{job_id}
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    def test_unknown_job_returns_404(self, client):
        tc, _ = client
        resp = tc.get("/status/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_queued_job_returns_queued_status(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_QUEUED)

        resp = tc.get(f"/status/{jid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == STATUS_QUEUED

    def test_done_job_includes_download_url(self, client, tmp_path):
        tc, db_path = client
        output_file = tmp_path / "output.epub"
        output_file.write_bytes(b"epub")
        jid = _seed_job(db_path, STATUS_DONE, output_file)

        resp = tc.get(f"/status/{jid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == STATUS_DONE
        assert "download_url" in body
        assert jid in body["download_url"]

    def test_failed_job_includes_error(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_FAILED)

        resp = tc.get(f"/status/{jid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == STATUS_FAILED
        assert "error" in body


# ---------------------------------------------------------------------------
# GET /download/{job_id}
# ---------------------------------------------------------------------------


class TestDownloadEndpoint:
    def test_unknown_job_returns_404(self, client):
        tc, _ = client
        resp = tc.get("/download/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_failed_job_returns_422(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_FAILED)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 422

    def test_expired_job_returns_410(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_EXPIRED)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 410

    def test_done_job_serves_file(self, client, tmp_path):
        tc, db_path = client
        output_file = tmp_path / "output.epub"
        output_file.write_bytes(b"fake epub content")
        jid = _seed_job(db_path, STATUS_DONE, output_file)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.content == b"fake epub content"

    def test_download_after_file_deleted_returns_410(self, client, tmp_path):
        tc, db_path = client
        # Seed a done job pointing to a non-existent file
        import web_service.job_store as js
        jid = js.new_job_id()
        js.create_job(jid, "free", "pdf", "epub", str(tmp_path), str(tmp_path / "in.pdf"),
                      db_path=db_path)
        js.set_done(jid, str(tmp_path / "gone.epub"), 1024, db_path=db_path)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 410

    # ------------------------------------------------------------------ EB-274

    def _seed_done_job_with_filename(self, db_path, tmp_path, *,
                                     original_filename: str | None,
                                     output_fmt: str = "epub"):
        """Seed a done job with a real on-disk output file and explicit
        original_filename. Used by the EB-274 polish tests below."""
        import web_service.job_store as js
        jid = js.new_job_id()
        output_file = tmp_path / f"{jid}.{output_fmt}"
        output_file.write_bytes(b"fake ebook content")
        js.create_job(
            job_id=jid,
            tier="free",
            input_fmt="pdf",
            output_fmt=output_fmt,
            temp_dir=str(tmp_path),
            input_path=str(tmp_path / "input.pdf"),
            db_path=db_path,
            original_filename=original_filename,
        )
        js.set_done(jid, str(output_file), output_file.stat().st_size, db_path=db_path)
        return jid

    def test_head_returns_200_with_headers_no_body(self, client, tmp_path):
        """HEAD /download/{job_id} returns 200 + same headers as GET, empty body.

        Pre-EB-274 the route was @router.get only, so HEAD probes (Lighthouse,
        link-checkers, browser prefetch) all 405'd. F2-05 in the audit.
        """
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="leafbind-demo.pdf"
        )

        resp = tc.head(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.content == b""  # HEAD has no body
        assert resp.headers["content-type"] == "application/epub+zip"
        assert "content-disposition" in resp.headers
        assert "leafbind-demo.epub" in resp.headers["content-disposition"]

    def test_get_returns_format_specific_media_type(self, client, tmp_path):
        """F2-04: serve application/epub+zip rather than octet-stream for EPUB."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="paper.pdf", output_fmt="epub"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/epub+zip"

    def test_get_kfx_keeps_octet_stream(self, client, tmp_path):
        """KFX has no registered IANA media type — must stay octet-stream."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="paper.pdf", output_fmt="kfx"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"

    def test_content_disposition_uses_original_basename(self, client, tmp_path):
        """F2-04: 'leafbind-demo.pdf' uploaded → 'leafbind-demo.epub' downloaded,
        not the raw UUID-based output filename."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="My Big Book.pdf", output_fmt="epub"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert 'filename="My Big Book.epub"' in resp.headers["content-disposition"]

    def test_content_disposition_falls_back_to_output_name_when_no_original(
        self, client, tmp_path
    ):
        """Pre-EB-274 jobs that predate the original_filename column still
        download cleanly using the output file's own basename."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename=None, output_fmt="epub"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        # Output filename is "{jid}.epub" — the UUID-based name, but still a
        # well-formed download with the right extension.
        assert resp.headers["content-disposition"].endswith(f'{jid}.epub"')

    def test_head_does_not_trigger_cleanup(self, client, tmp_path):
        """HEAD probes must not delete the output file. Only GET schedules the
        post-delivery cleanup task."""
        import web_service.job_store as js
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="paper.pdf"
        )
        output_file = Path(js.get_job(jid, db_path=db_path)["output_path"])
        assert output_file.exists()

        resp = tc.head(f"/download/{jid}")
        assert resp.status_code == 200
        # File should still be on disk after a HEAD; job should still be DONE.
        assert output_file.exists()
        assert js.get_job(jid, db_path=db_path)["status"] == STATUS_DONE
