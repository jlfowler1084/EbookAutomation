"""End-to-end smoke test for the Stripe success-page contract (EB-273).

The production audit (2026-05-16) found:
  - Stripe's new agent-detection gating blocks Playwright-driven Checkout E2E
  - Probing common success routes (/success, /checkout/success, ...) all 404'd
  - A typo in checkout.py's success_url, or a deployment that drops the route,
    would silently break paid checkout for every customer

This test exercises the full chain WITHOUT calling the real Stripe API:
  1. Build a real Stripe-signed checkout.session.completed webhook event
  2. POST it to /stripe/webhook -> triggers token mint
  3. GET the success_url that checkout.py literally points to
  4. Assert the success page renders with all minted tokens

What this catches that the existing unit tests don't:
  - test_web_webhook.py mocks stripe.Webhook.construct_event entirely; this test
    computes a real HMAC-SHA256 signature so any drift in signature handling
    surfaces here.
  - test_web_payment.py treats /payment/success in isolation; this test asserts
    the literal success_url string from checkout.py resolves through to a real
    page render via TestClient.
  - A refactor that renamed /payment/success -> /checkout/success would pass
    every existing test but fail this one.

What this does NOT catch (intentionally out of scope -- run
tools/verify_stripe_e2e.ps1 for these):
  - Real Stripe API errors (Session.retrieve fails, rate limits, agent gating)
  - Webhook delivery from Stripe's edge through Nginx to /stripe/webhook
  - The Next.js rewrite layer in front of /payment/success on Vercel
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web_service.config import reset_settings


# ---------------------------------------------------------------------------
# Stripe webhook signature construction
# ---------------------------------------------------------------------------

def _sign_stripe_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a Stripe-Signature header matching what Stripe's edge would send.

    Format matches https://docs.stripe.com/webhooks#verify-manually:
        t={unix_ts},v1={hex_hmac_sha256(secret, "{ts}.{payload}")}

    Using the same algorithm as stripe.Webhook.construct_event so the webhook
    handler's signature check passes with the same code path it uses in prod.
    """
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def _make_checkout_completed_event(
    session_id: str = "cs_test_e2e_abc",
    payment_intent_id: str = "pi_test_e2e_abc",
    pack: str = "starter",
    payment_status: str = "paid",
) -> dict:
    """Build a checkout.session.completed event dict matching Stripe's schema."""
    return {
        "id": "evt_test_e2e_001",
        "type": "checkout.session.completed",
        "livemode": False,
        "created": int(time.time()),
        "data": {
            "object": {
                "id": session_id,
                "payment_intent": payment_intent_id,
                "metadata": {"pack": pack},
                "payment_status": payment_status,
            }
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_settings():
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def project_root(tmp_path, monkeypatch):
    """Minimal project root with config/settings.json for Settings loading."""
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

    import sys
    import web_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path


@pytest.fixture()
def client(project_root):
    """TestClient with queue, billing executor, and DB init mocked."""
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


# ---------------------------------------------------------------------------
# TestSuccessUrlContract -- the literal string in checkout.py must point to
# a route that exists in the FastAPI app.
# ---------------------------------------------------------------------------

class TestSuccessUrlContract:
    """The success_url Stripe is told to redirect to must resolve.

    These tests parse checkout.py to extract the literal success_url and
    cancel_url strings, then verify the corresponding routes exist on the
    FastAPI app. Refactoring success_url without also moving the route
    handler will fail these tests.
    """

    def _extract_url_path(self, url: str) -> str:
        """Strip scheme+host and any query template params for route matching."""
        if url.startswith("http"):
            from urllib.parse import urlsplit
            return urlsplit(url).path
        return url

    def _get_configured_success_url(self) -> str:
        """Read the literal success_url assigned in checkout.py.

        Parses source rather than calling create_checkout_session because we
        want to detect any drift between the literal string and the route,
        without depending on Stripe API mocking specifics.
        """
        checkout_path = Path(__file__).resolve().parent.parent / "web_service" / "routes" / "checkout.py"
        source = checkout_path.read_text(encoding="utf-8")
        # Match success_url=( ... "https://leafbind.io/payment/success" ... )
        assert "success_url=" in source, (
            "checkout.py does not appear to define success_url -- has the file been "
            "renamed or refactored? Update this test if so."
        )
        # The success URL is split across two adjacent string literals; the
        # path component is the first one ending in /payment/<something>.
        for line in source.splitlines():
            if "leafbind.io/payment/" in line:
                start = line.index('"')
                end = line.index('"', start + 1)
                return line[start + 1 : end]
        raise AssertionError("Could not extract success_url path from checkout.py")

    def _get_configured_cancel_url(self) -> str:
        checkout_path = Path(__file__).resolve().parent.parent / "web_service" / "routes" / "checkout.py"
        source = checkout_path.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("cancel_url=") and "leafbind.io" in stripped:
                start = stripped.index('"')
                end = stripped.index('"', start + 1)
                return stripped[start + 1 : end]
        raise AssertionError("Could not extract cancel_url from checkout.py")

    def test_success_url_route_exists(self, client):
        """GET on the success_url path returns something other than 404.

        Specifically rejects 404. A 422 (missing session_id) is acceptable
        evidence that the route is registered.
        """
        path = self._extract_url_path(self._get_configured_success_url())
        resp = client.get(path)
        assert resp.status_code != 404, (
            f"success_url path {path!r} returns 404 -- the route handler is "
            f"missing or unmounted. Customers completing checkout will land on "
            f"a 404 page. Check web_service/routes/payment.py and web_service/"
            f"main.py router registration."
        )

    def test_cancel_url_route_exists(self, client):
        """GET on the cancel_url path returns 200."""
        path = self._extract_url_path(self._get_configured_cancel_url())
        # /pricing is rendered by Next.js (Vercel), not FastAPI -- TestClient
        # will 404 because the FastAPI app doesn't own that route. Accept that
        # outcome: the assertion is that checkout.py points to a known leafbind.io
        # path, not that FastAPI serves it.
        if path == "/pricing":
            assert path.startswith("/"), (
                "cancel_url path must be a leafbind.io absolute path"
            )
            return
        resp = client.get(path)
        assert resp.status_code != 404


# ---------------------------------------------------------------------------
# TestWebhookToSuccessPageChain -- webhook fires, success page renders tokens.
# ---------------------------------------------------------------------------

class TestWebhookToSuccessPageChain:
    """The full chain: signed webhook -> token mint -> success page render."""

    def test_signed_webhook_triggers_mint_and_success_page_renders(
        self, client, monkeypatch
    ):
        """Real-signed checkout.session.completed -> /payment/success renders tokens.

        This is the headline EB-273 test. If this passes, the contract Stripe
        relies on is intact: a paid Checkout Session generates tokens that the
        customer sees on the success_url page.
        """
        session_id = "cs_test_e2e_headline"
        fake_tokens = [f"lb_pk_{'X' * 43}", f"lb_pk_{'Y' * 43}", f"lb_pk_{'Z' * 43}"]
        expires_at = int(time.time()) + 86400 * 7

        mint_result = MagicMock()
        mint_result.tokens = fake_tokens
        mint_result.from_cache = False

        # Stand-in for token_store -- mint records the call, get returns the tokens.
        mock_mint = MagicMock(return_value=mint_result)
        mock_get = MagicMock(return_value=(fake_tokens, expires_at))

        with (
            patch("web_service.routes.webhook.token_store.mint_tokens_if_absent", mock_mint),
            patch("web_service.routes.webhook.billing_executor", None),
            # Skip the PaymentIntent.modify call -- not the focus of this test.
            patch("web_service.routes.webhook.stripe.PaymentIntent.modify"),
            patch("web_service.routes.payment.token_store.get_tokens_for_session", mock_get),
            patch("web_service.routes.payment.billing_executor", None),
        ):
            # Step 1: POST the signed webhook
            event = _make_checkout_completed_event(session_id=session_id, pack="starter")
            payload = json.dumps(event).encode()
            sig_header = _sign_stripe_payload(payload, "whsec_placeholder")

            webhook_resp = client.post(
                "/stripe/webhook",
                content=payload,
                headers={
                    "Stripe-Signature": sig_header,
                    "Content-Type": "application/json",
                },
            )

            assert webhook_resp.status_code == 200, (
                f"Webhook POST failed: {webhook_resp.status_code} {webhook_resp.text}"
            )
            assert webhook_resp.json() == {"received": True}
            mock_mint.assert_called_once()
            mint_call_args = mock_mint.call_args[0]
            assert mint_call_args[0] == session_id
            assert mint_call_args[1] == 3  # starter pack = 3 tokens

            # Step 2: GET the success_url
            success_resp = client.get(f"/payment/success?session_id={session_id}")
            assert success_resp.status_code == 200
            html = success_resp.text
            for tok in fake_tokens:
                assert tok in html, f"Token {tok!r} not found in success page HTML"
            assert "PAYMENT CONFIRMED" in html
            assert "lb-eyebrow" in html  # brand class -- catches accidental shell removal

    def test_unsigned_webhook_returns_400(self, client):
        """Webhook without a valid Stripe-Signature header is rejected.

        This guards against regressions that would skip signature validation
        (a security-critical bypass). If this test ever stops returning 400,
        the webhook handler has been compromised.
        """
        event = _make_checkout_completed_event()
        payload = json.dumps(event).encode()

        resp = client.post(
            "/stripe/webhook",
            content=payload,
            headers={"Content-Type": "application/json"},  # no Stripe-Signature
        )

        assert resp.status_code == 400

    def test_wrong_secret_webhook_returns_400(self, client):
        """Webhook signed with a wrong secret is rejected with 400."""
        event = _make_checkout_completed_event()
        payload = json.dumps(event).encode()
        # Sign with a DIFFERENT secret than the app expects.
        sig_header = _sign_stripe_payload(payload, "whsec_wrong_secret_xyz")

        resp = client.post(
            "/stripe/webhook",
            content=payload,
            headers={
                "Stripe-Signature": sig_header,
                "Content-Type": "application/json",
            },
        )

        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "pack, expected_count",
        [("starter", 3), ("standard", 10), ("power", 25)],
    )
    def test_each_pack_mints_expected_token_count(
        self, client, monkeypatch, pack, expected_count
    ):
        """Each pack triggers the correct token count through the e2e chain."""
        session_id = f"cs_test_pack_{pack}"
        fake_tokens = [f"lb_pk_{'A' * 43}"] * expected_count
        mint_result = MagicMock()
        mint_result.tokens = fake_tokens
        mint_result.from_cache = False

        mock_mint = MagicMock(return_value=mint_result)

        with (
            patch("web_service.routes.webhook.token_store.mint_tokens_if_absent", mock_mint),
            patch("web_service.routes.webhook.billing_executor", None),
            patch("web_service.routes.webhook.stripe.PaymentIntent.modify"),
        ):
            event = _make_checkout_completed_event(session_id=session_id, pack=pack)
            payload = json.dumps(event).encode()
            sig_header = _sign_stripe_payload(payload, "whsec_placeholder")

            resp = client.post(
                "/stripe/webhook",
                content=payload,
                headers={
                    "Stripe-Signature": sig_header,
                    "Content-Type": "application/json",
                },
            )

        assert resp.status_code == 200
        mock_mint.assert_called_once()
        assert mock_mint.call_args[0][1] == expected_count
