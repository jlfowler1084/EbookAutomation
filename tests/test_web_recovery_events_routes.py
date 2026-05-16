"""Tests for /api/recovery-events/* endpoints (EB-292)."""

from __future__ import annotations

import json
import sqlite3
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
    """TestClient with mocked queue/dispatch. recovery_events_store.init_db is run."""
    import importlib

    import web_service.job_store as js
    import web_service.main as main_mod
    import web_service.recovery_events_store as res
    from web_service.config import load_settings

    settings = load_settings()
    js.init_db(settings.db_path)
    res.init_db(settings.db_path)

    importlib.reload(main_mod)

    with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()), \
         patch("web_service.job_queue.init_queue"), \
         patch("web_service.job_queue.cleanup_expired_jobs", return_value=AsyncMock()):
        with TestClient(main_mod.app, follow_redirects=False) as tc:
            yield tc, settings.db_path


def _count_events(db_path, event_type: str) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM recovery_events WHERE event_type=?",
            (event_type,),
        ).fetchone()
    return row[0]


def _wait_for_event(db_path, event_type: str, target: int = 1, attempts: int = 50) -> None:
    """Poll briefly for the fire-and-forget executor to land the row.

    log_event() runs in the billing_executor — it may not have completed
    when the HTTP response returns. ~500ms ceiling.
    """
    import time as _t
    for _ in range(attempts):
        if _count_events(db_path, event_type) >= target:
            return
        _t.sleep(0.01)


class TestRecoverViewEndpoint:
    def test_valid_state_logged(self, client):
        tc, db_path = client
        resp = tc.post(
            "/api/recovery-events/recover-view",
            json={"localStorage_state": "empty"},
        )
        assert resp.status_code == 204
        _wait_for_event(db_path, "recover_page_view")
        assert _count_events(db_path, "recover_page_view") == 1

    def test_all_whitelisted_states_accepted(self, client):
        tc, db_path = client
        for state in ("empty", "has_tokens", "has_expired_tokens", "invalid", "unavailable"):
            resp = tc.post(
                "/api/recovery-events/recover-view",
                json={"localStorage_state": state},
            )
            assert resp.status_code == 204
        _wait_for_event(db_path, "recover_page_view", target=5)
        assert _count_events(db_path, "recover_page_view") == 5

    def test_unknown_state_recorded_as_unknown(self, client):
        tc, db_path = client
        resp = tc.post(
            "/api/recovery-events/recover-view",
            json={"localStorage_state": "<script>alert(1)</script>"},
        )
        assert resp.status_code == 204
        _wait_for_event(db_path, "recover_page_view")
        # Row exists; details JSON contains state="unknown" (not the attacker payload)
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT details FROM recovery_events WHERE event_type=?",
                ("recover_page_view",),
            ).fetchone()
        details = json.loads(row[0])
        assert details["localStorage_state"] == "unknown"

    def test_empty_body_returns_204_and_logs_unknown(self, client):
        tc, db_path = client
        resp = tc.post("/api/recovery-events/recover-view", json={})
        assert resp.status_code == 204
        _wait_for_event(db_path, "recover_page_view")
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT details FROM recovery_events"
            ).fetchone()
        details = json.loads(row[0])
        assert details["localStorage_state"] == "unknown"


class TestRecoverEndpointInstrumentation:
    """Smoke test that POST /api/recover (EB-292) actually writes the event row."""

    def test_successful_recover_logs_event(self, client):
        tc, db_path = client
        resp = tc.post("/api/recover", data={"session_id": "cs_test_abc123"})
        assert resp.status_code == 302
        _wait_for_event(db_path, "api_recover_post")
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT details FROM recovery_events WHERE event_type=?",
                ("api_recover_post",),
            ).fetchone()
        details = json.loads(row[0])
        assert details["result"] == "success"

    def test_malformed_recover_logs_event(self, client):
        tc, db_path = client
        resp = tc.post("/api/recover", data={"session_id": "not_valid"})
        assert resp.status_code == 422
        _wait_for_event(db_path, "api_recover_post")
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT details FROM recovery_events WHERE event_type=?",
                ("api_recover_post",),
            ).fetchone()
        details = json.loads(row[0])
        assert details["result"] == "malformed"
