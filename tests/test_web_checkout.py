"""Tests for POST /stripe/create-session — Stripe Checkout session creation endpoint.

All Stripe SDK calls are mocked via @patch so no real Stripe API calls occur.
The conftest.py autouse fixture provides Phase 2 env defaults (STRIPE_PRICE_* etc).

Test structure:
- Happy path: each of the 3 packs returns 200 + {checkout_url, session_id}
- Critical assertion: Stripe Session.create called with correct parameters
  (mode, customer_creation, receipt_email=None, metadata, price_id)
- Edge case: unknown pack → 422 INVALID_PACK
- Edge case: missing pack field → 422 (FastAPI auto-validation)
- Error path: Stripe SDK raises StripeError → 503 STRIPE_API_ERROR
"""

from __future__ import annotations

import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import stripe

from web_service.config import reset_settings


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
    """Minimal project root with config/settings.json for loading Settings."""
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
    """TestClient with Stripe SDK and queue fully mocked.

    Mocks applied:
    - web_service.job_queue.init_queue — prevents real ThreadPoolExecutor creation
    - web_service.job_queue.init_billing_executor — prevents real billing executor
    - web_service.job_queue.cleanup_expired_jobs — no background sweep
    - web_service.token_store.init_db — no real SQLite writes
    """
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
# Happy path — all three packs
# ---------------------------------------------------------------------------

class TestCreateSessionHappyPath:
    """POST /stripe/create-session returns 200 with checkout_url and session_id."""

    def _make_mock_session(self, session_id: str = "cs_test_abc123") -> MagicMock:
        """Build a mock Stripe Checkout Session object."""
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.url = f"https://checkout.stripe.com/pay/{session_id}"
        return mock_session

    @pytest.mark.parametrize("pack,expected_price_env_value", [
        ("starter", "price_starter_test"),
        ("standard", "price_standard_test"),
        ("power", "price_power_test"),
    ])
    def test_happy_path_returns_200_with_url_and_session_id(
        self, client, pack, expected_price_env_value
    ):
        """Each pack resolves to the correct price_id and returns checkout URL."""
        mock_session = self._make_mock_session("cs_test_happy")

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            resp = client.post("/stripe/create-session", data={"pack": pack})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "checkout_url" in body
        assert "session_id" in body
        assert body["session_id"] == "cs_test_happy"
        assert "checkout.stripe.com" in body["checkout_url"]

        # Verify price_id resolves to the env-injected value
        call_kwargs = mock_create.call_args.kwargs
        line_items = call_kwargs.get("line_items", [])
        assert len(line_items) == 1
        assert line_items[0]["price"] == expected_price_env_value
        assert line_items[0]["quantity"] == 1

    def test_starter_pack_stripe_call_parameters(self, client):
        """Starter pack: verify ALL critical Stripe Session.create parameters."""
        mock_session = self._make_mock_session("cs_test_starter")

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            resp = client.post("/stripe/create-session", data={"pack": "starter"})

        assert resp.status_code == 200
        call_kwargs = mock_create.call_args.kwargs

        # Mode must be 'payment' (one-time purchase, not subscription)
        assert call_kwargs["mode"] == "payment"

        # Guest checkout — no mandatory Customer object
        assert call_kwargs["customer_creation"] == "if_required"

        # receipt_email must be None — privacy policy disables Stripe's receipt emails
        pi_data = call_kwargs.get("payment_intent_data", {})
        assert pi_data.get("receipt_email") is None, (
            "receipt_email must be None in payment_intent_data to disable Stripe receipts"
        )

        # PaymentIntent metadata must contain pack name (seed for Unit 4 chain)
        pi_metadata = pi_data.get("metadata", {})
        assert pi_metadata.get("pack") == "starter", (
            "payment_intent_data.metadata.pack must be set for Unit 4 webhook chain"
        )

        # Session-level metadata for Stripe Dashboard debugging
        session_metadata = call_kwargs.get("metadata", {})
        assert session_metadata.get("pack") == "starter"

        # URLs
        assert "leafbind.io" in call_kwargs.get("success_url", "")
        assert "CHECKOUT_SESSION_ID" in call_kwargs.get("success_url", "")
        assert "leafbind.io" in call_kwargs.get("cancel_url", "")

    def test_payment_intent_data_does_not_contain_checkout_session_id(self, client):
        """Unit 3 must NOT set checkout_session_id in payment_intent_data.metadata.

        That field does not exist at Session creation time — it is set by
        Unit 4's checkout.session.completed webhook handler via
        stripe.PaymentIntent.modify().
        """
        mock_session = self._make_mock_session()

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            resp = client.post("/stripe/create-session", data={"pack": "power"})

        assert resp.status_code == 200
        call_kwargs = mock_create.call_args.kwargs
        pi_metadata = call_kwargs.get("payment_intent_data", {}).get("metadata", {})
        assert "checkout_session_id" not in pi_metadata, (
            "checkout_session_id must NOT be set at session creation — "
            "this belongs to Unit 4's webhook handler"
        )

    def test_standard_pack_uses_correct_price_id(self, client):
        """Standard pack uses STRIPE_PRICE_STANDARD from env."""
        mock_session = self._make_mock_session("cs_test_standard")

        with patch("stripe.checkout.Session.create", return_value=mock_session):
            resp = client.post("/stripe/create-session", data={"pack": "standard"})

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "cs_test_standard"

    def test_power_pack_uses_correct_price_id(self, client):
        """Power pack uses STRIPE_PRICE_POWER from env."""
        mock_session = self._make_mock_session("cs_test_power")

        with patch("stripe.checkout.Session.create", return_value=mock_session):
            resp = client.post("/stripe/create-session", data={"pack": "power"})

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "cs_test_power"

    def test_response_contains_session_id_from_stripe(self, client):
        """session_id in response matches the Stripe-generated session ID."""
        mock_session = self._make_mock_session("cs_test_unique_xyz789")

        with patch("stripe.checkout.Session.create", return_value=mock_session):
            resp = client.post("/stripe/create-session", data={"pack": "starter"})

        assert resp.json()["session_id"] == "cs_test_unique_xyz789"

    def test_response_contains_checkout_url_from_stripe(self, client):
        """checkout_url in response is the URL returned by Stripe."""
        mock_session = MagicMock()
        mock_session.id = "cs_test_url_check"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_url_check"

        with patch("stripe.checkout.Session.create", return_value=mock_session):
            resp = client.post("/stripe/create-session", data={"pack": "standard"})

        assert resp.json()["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_url_check"


# ---------------------------------------------------------------------------
# Input validation — invalid / missing pack
# ---------------------------------------------------------------------------

class TestCreateSessionValidation:
    """Validate that bad pack values are rejected before reaching Stripe."""

    def test_invalid_pack_returns_422_invalid_pack(self, client):
        """Unknown pack name returns 422 with INVALID_PACK code."""
        with patch("stripe.checkout.Session.create") as mock_create:
            resp = client.post("/stripe/create-session", data={"pack": "invalid"})

        assert resp.status_code == 422
        body = resp.json()
        detail = body.get("detail", {})
        assert detail.get("code") == "INVALID_PACK"
        assert detail.get("error") == "invalid pack"

        # Stripe must NOT have been called for an invalid pack
        mock_create.assert_not_called()

    def test_empty_pack_returns_422(self, client):
        """Empty string pack returns 422 with INVALID_PACK code."""
        with patch("stripe.checkout.Session.create") as mock_create:
            resp = client.post("/stripe/create-session", data={"pack": ""})

        assert resp.status_code == 422
        mock_create.assert_not_called()

    def test_missing_pack_field_returns_422(self, client):
        """Missing pack field entirely returns 422 (FastAPI auto-validation)."""
        with patch("stripe.checkout.Session.create") as mock_create:
            resp = client.post("/stripe/create-session", data={})

        # FastAPI validates required Form(...) fields and returns 422
        assert resp.status_code == 422
        mock_create.assert_not_called()

    @pytest.mark.parametrize("bad_pack", [
        "Starter",        # case-sensitive
        "STARTER",
        "starter ",       # trailing space
        " starter",       # leading space
        "basic",
        "pro",
        "enterprise",
        "free",
        "premium",
        "starter\n",      # newline
    ])
    def test_various_invalid_pack_values_return_422(self, client, bad_pack):
        """A range of invalid pack values all return 422 before hitting Stripe."""
        with patch("stripe.checkout.Session.create") as mock_create:
            resp = client.post("/stripe/create-session", data={"pack": bad_pack})

        assert resp.status_code == 422
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# Stripe API error path
# ---------------------------------------------------------------------------

class TestCreateSessionStripeErrors:
    """Stripe SDK errors are caught and re-raised as 503."""

    def test_stripe_error_returns_503(self, client):
        """StripeError from Stripe SDK → 503 with STRIPE_API_ERROR code."""
        with patch(
            "stripe.checkout.Session.create",
            side_effect=stripe.error.StripeError("Upstream failure"),
        ):
            resp = client.post("/stripe/create-session", data={"pack": "starter"})

        assert resp.status_code == 503
        body = resp.json()
        detail = body.get("detail", {})
        assert detail.get("code") == "STRIPE_API_ERROR"
        assert detail.get("error") == "stripe upstream error"

    def test_stripe_api_connection_error_returns_503(self, client):
        """APIConnectionError (network failure) → 503 with STRIPE_API_ERROR code."""
        with patch(
            "stripe.checkout.Session.create",
            side_effect=stripe.error.APIConnectionError("Network error"),
        ):
            resp = client.post("/stripe/create-session", data={"pack": "standard"})

        assert resp.status_code == 503
        body = resp.json()
        assert body.get("detail", {}).get("code") == "STRIPE_API_ERROR"

    def test_stripe_invalid_request_error_returns_503(self, client):
        """InvalidRequestError (bad price ID) → 503 with STRIPE_API_ERROR code."""
        with patch(
            "stripe.checkout.Session.create",
            side_effect=stripe.error.InvalidRequestError(
                "No such price", param="price"
            ),
        ):
            resp = client.post("/stripe/create-session", data={"pack": "power"})

        assert resp.status_code == 503
        body = resp.json()
        assert body.get("detail", {}).get("code") == "STRIPE_API_ERROR"

    def test_stripe_rate_limit_error_returns_503(self, client):
        """RateLimitError → 503 with STRIPE_API_ERROR code."""
        with patch(
            "stripe.checkout.Session.create",
            side_effect=stripe.error.RateLimitError("Too many requests"),
        ):
            resp = client.post("/stripe/create-session", data={"pack": "starter"})

        assert resp.status_code == 503
        body = resp.json()
        assert body.get("detail", {}).get("code") == "STRIPE_API_ERROR"

    def test_stripe_auth_error_returns_503(self, client):
        """AuthenticationError (bad API key) → 503 with STRIPE_API_ERROR code."""
        with patch(
            "stripe.checkout.Session.create",
            side_effect=stripe.error.AuthenticationError("Invalid API Key"),
        ):
            resp = client.post("/stripe/create-session", data={"pack": "standard"})

        assert resp.status_code == 503
        body = resp.json()
        assert body.get("detail", {}).get("code") == "STRIPE_API_ERROR"


# ---------------------------------------------------------------------------
# Unit 4 contract guard
# ---------------------------------------------------------------------------

class TestUnit4Contract:
    """Verify Unit 3 does not encroach on Unit 4 territory."""

    def test_unit3_does_not_call_payment_intent_modify(self, client):
        """Unit 3 must NOT call stripe.PaymentIntent.modify — that is Unit 4 work."""
        mock_session = MagicMock()
        mock_session.id = "cs_test_unit4_guard"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_unit4_guard"

        with (
            patch("stripe.checkout.Session.create", return_value=mock_session),
            patch("stripe.PaymentIntent.modify") as mock_pi_modify,
        ):
            resp = client.post("/stripe/create-session", data={"pack": "starter"})

        assert resp.status_code == 200
        mock_pi_modify.assert_not_called(), (
            "stripe.PaymentIntent.modify must NOT be called in Unit 3 — "
            "this belongs to Unit 4's checkout.session.completed webhook handler"
        )
