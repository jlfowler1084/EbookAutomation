"""Tests for web service HTTP endpoints — POST /convert, GET /status, GET /download."""

from __future__ import annotations

import json
import sys
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
        assert resp.json() == {"status": "ok"}


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
