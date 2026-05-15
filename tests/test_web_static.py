"""Tests for the /static/ StaticFiles mount added in EB-248 Unit 1.

Verifies that:
- GET /static/leafbind-tokens.css returns 200 with the correct cache policy.
- GET /static/<missing> returns 404.
- The CSS body contains the expected --color-brand token value.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    """Minimal project root for Settings loading."""
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
    import sys
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path


@pytest.fixture()
def client(project_root):
    """TestClient with queue and DB mocked, static files mounted from real path."""
    import web_service.main as main_mod

    importlib.reload(main_mod)

    with (
        patch("web_service.job_queue.init_queue"),
        patch("web_service.job_queue.init_billing_executor"),
        patch("web_service.job_queue.cleanup_expired_jobs", return_value=MagicMock()),
        patch("web_service.token_store.init_db"),
    ):
        with TestClient(main_mod.app) as tc:
            yield tc


class TestStaticFilesMount:
    """GET /static/* — static file serving for brand CSS."""

    def test_brand_css_returns_200(self, client):
        resp = client.get("/static/leafbind-tokens.css")
        assert resp.status_code == 200

    def test_brand_css_content_type(self, client):
        resp = client.get("/static/leafbind-tokens.css")
        assert "text/css" in resp.headers["content-type"]

    def test_brand_css_contains_color_brand(self, client):
        resp = client.get("/static/leafbind-tokens.css")
        assert "--color-brand" in resp.text
        assert "#2f5d3a" in resp.text

    def test_brand_css_contains_root_block(self, client):
        resp = client.get("/static/leafbind-tokens.css")
        assert ":root" in resp.text

    def test_missing_static_file_returns_404(self, client):
        resp = client.get("/static/does-not-exist.css")
        assert resp.status_code == 404

    def test_brand_css_cache_control_public(self, client):
        resp = client.get("/static/leafbind-tokens.css")
        cc = resp.headers.get("cache-control", "")
        assert "public" in cc
        assert "max-age=3600" in cc
