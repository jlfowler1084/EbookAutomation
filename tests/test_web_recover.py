"""Tests for POST /api/recover endpoint."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from web_service.config import reset_settings


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
    """TestClient with mocked queue and dispatch (no real pipeline)."""
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
        with TestClient(main_mod.app, follow_redirects=False) as tc:
            yield tc


# ---------------------------------------------------------------------------
# POST /api/recover — happy path
# ---------------------------------------------------------------------------

class TestRecoverEndpoint:
    def test_valid_session_id_redirects_302(self, client):
        """Valid cs_test_xxx session_id → 302 redirect to /payment/success?session_id=..."""
        resp = client.post(
            "/api/recover",
            data={"session_id": "cs_test_abc123"},
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/payment/success?session_id=cs_test_abc123"

    def test_redirect_location_contains_session_id(self, client):
        """Redirect URL must embed the session_id verbatim."""
        session_id = "cs_live_xyz789abcdefghij"
        resp = client.post(
            "/api/recover",
            data={"session_id": session_id},
        )
        assert resp.status_code == 302
        assert f"session_id={session_id}" in resp.headers["location"]

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    def test_short_cs_session_id_returns_422(self, client):
        """cs_ followed by only 1 char (total len 4) → 422 MALFORMED_SESSION_ID."""
        resp = client.post(
            "/api/recover",
            data={"session_id": "cs_x"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "MALFORMED_SESSION_ID"

    def test_wrong_prefix_returns_422(self, client):
        """session_id that doesn't start with cs_ → 422 MALFORMED_SESSION_ID."""
        resp = client.post(
            "/api/recover",
            data={"session_id": "not_a_session"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "MALFORMED_SESSION_ID"

    def test_empty_session_id_returns_422(self, client):
        """Empty string session_id → 422 MALFORMED_SESSION_ID."""
        resp = client.post(
            "/api/recover",
            data={"session_id": ""},
        )
        assert resp.status_code == 422

    def test_leading_trailing_whitespace_trimmed(self, client):
        """Whitespace around a valid session_id is stripped before validation."""
        resp = client.post(
            "/api/recover",
            data={"session_id": "  cs_test_trimmed123  "},
        )
        assert resp.status_code == 302
        assert "cs_test_trimmed123" in resp.headers["location"]
        # No leading/trailing whitespace in the redirect URL
        assert "  " not in resp.headers["location"]

    def test_missing_session_id_field_returns_422(self, client):
        """Omitting session_id form field entirely → FastAPI 422 auto-validation."""
        resp = client.post(
            "/api/recover",
            data={},
        )
        assert resp.status_code == 422

    def test_pi_prefixed_session_id_returns_422(self, client):
        """A PaymentIntent ID (pi_...) is not a valid session_id → 422."""
        resp = client.post(
            "/api/recover",
            data={"session_id": "pi_live_somepaymentintentid"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "MALFORMED_SESSION_ID"
