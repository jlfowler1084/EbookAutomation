"""Tests for EB-324 Unit 8 — slowapi rate limiting with trusted-proxy gating.

The load-bearing security property (write/verify first per plan P1-1):
the rate-limit key extractor honors the `CF-Connecting-IP` header ONLY when
the immediate peer (`request.client.host`) is the local nginx proxy. An
attacker who discovers the Hetzner VM's raw IP and hits it directly (bypassing
Cloudflare) has a non-loopback `request.client.host` and a *forgeable*
`CF-Connecting-IP` — the extractor MUST ignore the forged header and key on
the real peer address, otherwise per-IP rate limiting is trivially bypassed
(fresh bucket per forged header value).

Integration coverage: exceeding a route's per-IP limit returns 429.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request


# ---------------------------------------------------------------------------
# Key-extractor unit tests (the security core)
# ---------------------------------------------------------------------------


def _make_request(client_host: str | None, headers: dict | None = None) -> Request:
    """Build a minimal Starlette Request with a given peer host + headers."""
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/reconvert/abc",
        "raw_path": b"/reconvert/abc",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 12345) if client_host else None,
        "server": ("testserver", 80),
    }
    return Request(scope)


class TestTrustedClientKey:
    """trusted_client_key honors CF-Connecting-IP only from the local proxy."""

    def test_forged_cf_ip_from_untrusted_origin_is_ignored(self):
        """LOAD-BEARING: a direct hit on the VM IP (non-loopback peer) with a
        forged CF-Connecting-IP must key on the REAL peer, not the header.
        """
        from web_service.rate_limit import trusted_client_key

        req = _make_request(
            client_host="203.0.113.5",  # attacker's real IP (not nginx loopback)
            headers={"cf-connecting-ip": "10.0.0.1"},  # forged
        )
        key = trusted_client_key(req)
        assert key == "203.0.113.5", (
            f"Forged CF-Connecting-IP from a non-proxy origin must be ignored. "
            f"Keyed on {key!r} instead of the real peer 203.0.113.5 — an "
            f"attacker could rotate the header to get unlimited buckets."
        )

    def test_cf_ip_honored_from_trusted_loopback_proxy(self):
        """When the peer IS the local nginx (127.0.0.1), the real client IP
        lives in CF-Connecting-IP and we key on it.
        """
        from web_service.rate_limit import trusted_client_key

        req = _make_request(
            client_host="127.0.0.1",
            headers={"cf-connecting-ip": "198.51.100.7"},
        )
        key = trusted_client_key(req)
        assert key == "198.51.100.7", (
            f"From the trusted loopback proxy, the CF-Connecting-IP is the real "
            f"client and must be the rate-limit key. Got {key!r}."
        )

    def test_no_cf_header_falls_back_to_peer_address(self):
        """No CF header (local dev, direct curl) → key on the peer address."""
        from web_service.rate_limit import trusted_client_key

        req = _make_request(client_host="127.0.0.1", headers={})
        key = trusted_client_key(req)
        assert key == "127.0.0.1"

    def test_untrusted_origin_without_header_uses_peer(self):
        from web_service.rate_limit import trusted_client_key

        req = _make_request(client_host="203.0.113.5", headers={})
        key = trusted_client_key(req)
        assert key == "203.0.113.5"

    def test_ipv6_loopback_is_trusted(self):
        """nginx may forward over ::1 in IPv6 setups."""
        from web_service.rate_limit import trusted_client_key

        req = _make_request(
            client_host="::1",
            headers={"cf-connecting-ip": "2001:db8::42"},
        )
        key = trusted_client_key(req)
        assert key == "2001:db8::42"


# ---------------------------------------------------------------------------
# Integration — limiter is wired and 429s fire past the limit
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_settings():
    from web_service.config import reset_settings
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def project_root(tmp_path, monkeypatch):
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
    import web_service.job_store as js
    import web_service.main as main_mod
    from web_service.config import load_settings

    settings = load_settings()
    js.init_db(settings.db_path)
    importlib.reload(main_mod)

    with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()), \
         patch("web_service.routes.reconvert.job_queue.dispatch_job", new=AsyncMock()), \
         patch("web_service.job_queue.init_queue"), \
         patch("web_service.job_queue.cleanup_expired_jobs", return_value=AsyncMock()):
        with TestClient(main_mod.app) as tc:
            yield tc, settings.db_path, settings


@pytest.fixture()
def _enable_limiter():
    """Re-enable the limiter (disabled globally by conftest) for the
    integration tests that actually exercise 429 behavior. Reset storage
    on entry + exit so these tests don't leak counters into each other or
    into the rest of the suite.
    """
    from web_service.rate_limit import limiter
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


class TestRateLimitIntegration:
    def test_reconvert_exceeding_per_parent_limit_returns_429(self, client, _enable_limiter):
        """The per-parent_job_id limit (5/min) trips on the 6th request to the
        same parent. Earlier requests may 404/410/422 (validation) but still
        count against the limit; the 6th must be 429.
        """
        tc, _, _ = client
        # Hit the same parent id repeatedly; the per-parent limit is the
        # lowest threshold so it trips first.
        parent_id = "00000000-0000-0000-0000-000000000000"
        statuses = []
        for _ in range(7):
            resp = tc.post(
                f"/reconvert/{parent_id}",
                data={"output_format": "mobi"},
            )
            statuses.append(resp.status_code)

        assert 429 in statuses, (
            f"Expected a 429 once the per-parent limit (5/min) is exceeded. "
            f"Got status sequence: {statuses}"
        )

    def test_limiter_is_registered_on_app(self, client):
        """The app must expose a limiter in state for slowapi middleware."""
        tc, _, _ = client
        # The Starlette app stores the limiter at app.state.limiter.
        assert hasattr(tc.app.state, "limiter"), (
            "slowapi Limiter must be registered at app.state.limiter"
        )
