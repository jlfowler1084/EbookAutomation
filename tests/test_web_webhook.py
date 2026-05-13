"""Tests for POST /stripe/webhook -- Stripe webhook handler.

All Stripe SDK calls are mocked. No real network calls or DB writes unless
explicitly testing DB failure paths (which use a real temp SQLite DB).

The conftest.py autouse fixture provides Phase 2 env defaults
(STRIPE_WEBHOOK_SECRET etc.) so tests don't have to set them individually.

Test structure:
- TestWebhookSignatureValidation: signature failure, replay, production livemode
- TestCheckoutSessionCompleted: happy path, mint args, PI modify args
- TestCheckoutSessionCompletedEdgeCases: malformed event, idempotent retry
- TestDisputeHandler: PI metadata path, fallback path, unresolvable, no PI field
- TestCircuitBreakerIntegration: circuit open short-circuit
- TestDBFailurePaths: mint failure -> 500 + failed_mints + cb increment
- TestDisputeDBFailure: mark_disputed failure -> 500
- TestStripeModifyFailureAfterMint: modify fails -> still 200 (tokens minted)
- TestUnknownEventType: unknown -> 200 no side effects
- TestConcurrentWebhookAndSuccessPage: race-loser idempotency
- TestMiddlewareSafetyCheck: non-allowlisted middleware triggers WARN
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

import stripe

from web_service.config import reset_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type: str = "checkout.session.completed",
    session_id: str = "cs_test_abc",
    payment_intent_id: str = "pi_test_abc",
    pack: str = "starter",
    livemode: bool = False,
    event_id: str = "evt_test_001",
    created: int | None = None,
    extra_obj_fields: dict | None = None,
) -> dict:
    """Build a fake Stripe event dict."""
    if created is None:
        created = int(time.time())
    obj: dict = {}
    if event_type == "checkout.session.completed":
        obj = {
            "id": session_id,
            "payment_intent": payment_intent_id,
            "metadata": {"pack": pack},
        }
    elif event_type == "charge.dispute.created":
        obj = {
            "payment_intent": payment_intent_id,
        }
    if extra_obj_fields:
        obj.update(extra_obj_fields)
    return {
        "id": event_id,
        "type": event_type,
        "livemode": livemode,
        "created": created,
        "data": {"object": obj},
    }


def _make_pi_mock(session_id: str | None = "cs_test_abc") -> MagicMock:
    """Build a mock PaymentIntent object whose metadata may contain checkout_session_id."""
    pi = MagicMock()
    if session_id is not None:
        pi.metadata = {"checkout_session_id": session_id}
    else:
        pi.metadata = {}
    return pi


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
    import sys
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path


@pytest.fixture()
def client(project_root):
    """TestClient with Stripe SDK and queue fully mocked.

    Mocks applied:
    - web_service.job_queue.init_queue -- prevents real ThreadPoolExecutor creation
    - web_service.job_queue.init_billing_executor -- prevents real billing executor
    - web_service.job_queue.cleanup_expired_jobs -- no background sweep
    - web_service.token_store.init_db -- no real SQLite writes
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


def _post_webhook(client: TestClient, event: dict) -> object:
    """POST the event to /stripe/webhook with a mocked-valid signature."""
    return client.post(
        "/stripe/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "t=1,v1=fakesig"},
    )


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------

class TestWebhookSignatureValidation:
    """400 on invalid signature; 400 on old timestamp (replay); 400 in production
    when event is test-mode."""

    def test_invalid_signature_returns_400(self, client):
        """Webhook with bad signature returns 400."""
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError(
                "No signatures found", sig_header="t=1,v1=bad"
            ),
        ):
            resp = _post_webhook(client, _make_event())

        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"] == "invalid signature"

    def test_value_error_on_parse_returns_400(self, client):
        """ValueError (bad JSON payload) also returns 400."""
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=ValueError("Could not decode JSON"),
        ):
            resp = _post_webhook(client, {})

        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"] == "invalid signature"

    def test_expired_timestamp_returns_400(self, client, monkeypatch):
        """Timestamp older than 5 minutes (tolerance=300) triggers 400.

        We simulate this by having construct_event raise SignatureVerificationError
        with a timestamp-related message, mimicking Stripe SDK's tolerance check.
        """
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError(
                "Timestamp outside tolerance zone (300s)", sig_header="t=1,v1=oldsig"
            ),
        ):
            event = _make_event(created=int(time.time()) - 400)
            resp = _post_webhook(client, event)

        assert resp.status_code == 400

    def test_invalid_signature_logs_warning(self, client, caplog):
        """Signature failure logs a structured warning with source_ip and payload_len."""
        import logging
        with caplog.at_level(logging.WARNING, logger="web_service.routes.webhook"):
            with patch(
                "stripe.Webhook.construct_event",
                side_effect=stripe.error.SignatureVerificationError(
                    "bad sig", sig_header="t=1,v1=bad"
                ),
            ):
                _post_webhook(client, _make_event())

        # The log record should exist (caplog captures it)
        assert any("webhook_signature_failure" in r.getMessage() or
                   r.message == "webhook_signature_failure"
                   for r in caplog.records), (
            "Expected webhook_signature_failure log record"
        )

    def test_test_event_in_production_returns_400(self, client, monkeypatch):
        """Production mode + test-mode event (livemode=false) returns 400."""
        monkeypatch.setenv("APP_ENV", "production")
        event = _make_event(livemode=False)

        with patch(
            "stripe.Webhook.construct_event",
            return_value=event,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"] == "test event in production"

    def test_livemode_true_in_production_proceeds(self, client, monkeypatch):
        """Production mode + live event passes livemode check and processes normally."""
        monkeypatch.setenv("APP_ENV", "production")
        event = _make_event(livemode=True)

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43])
            resp = _post_webhook(client, event)

        assert resp.status_code == 200

    def test_non_production_env_allows_test_events(self, client, monkeypatch):
        """Non-production APP_ENV allows test-mode events through."""
        monkeypatch.setenv("APP_ENV", "staging")
        event = _make_event(livemode=False)

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43])
            resp = _post_webhook(client, event)

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# checkout.session.completed -- happy path
# ---------------------------------------------------------------------------

class TestCheckoutSessionCompleted:
    """Happy path: mint tokens + extend PaymentIntent metadata."""

    @pytest.mark.parametrize("pack,expected_count", [
        ("starter", 3),
        ("standard", 10),
        ("power", 25),
    ])
    def test_happy_path_returns_200(self, client, pack, expected_count):
        """Valid checkout.session.completed event returns 200."""
        event = _make_event(pack=pack)
        mock_tokens = ["lb_pk_" + "A" * 43] * expected_count
        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=mock_tokens)
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_mint_called_with_correct_session_id(self, client):
        """mint_tokens_if_absent is called with the session_id from the event."""
        event = _make_event(session_id="cs_test_specific", pack="starter")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3)
            _post_webhook(client, event)

        call_args = mock_mint.call_args
        assert call_args.args[0] == "cs_test_specific", (
            "First arg to mint_tokens_if_absent must be the session_id"
        )

    def test_mint_called_with_correct_count_for_each_pack(self, client):
        """mint_tokens_if_absent receives the correct count for each pack."""
        for pack, expected_count in [("starter", 3), ("standard", 10), ("power", 25)]:
            event = _make_event(pack=pack)
            with (
                patch("stripe.Webhook.construct_event", return_value=event),
                patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
                patch("stripe.PaymentIntent.modify"),
            ):
                mock_mint.return_value = MagicMock(
                    ok=True,
                    tokens=["lb_pk_" + "A" * 43] * expected_count,
                )
                _post_webhook(client, event)

            assert mock_mint.call_args.args[1] == expected_count, (
                f"Expected count={expected_count} for pack={pack}"
            )

    def test_mint_called_with_payment_intent_id(self, client):
        """mint_tokens_if_absent receives the payment_intent_id for dispute fallback."""
        event = _make_event(payment_intent_id="pi_test_specific_pi")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3)
            _post_webhook(client, event)

        assert mock_mint.call_args.args[2] == "pi_test_specific_pi", (
            "Third arg to mint_tokens_if_absent must be the payment_intent_id"
        )

    def test_payment_intent_modify_called_with_session_id_and_pack(self, client):
        """stripe.PaymentIntent.modify is called with {checkout_session_id, pack} metadata.

        This is the critical Unit 4 responsibility: extending PI metadata so the
        dispute handler can do a single-hop resolve via PI retrieve.
        """
        event = _make_event(
            session_id="cs_test_for_modify",
            payment_intent_id="pi_test_for_modify",
            pack="standard",
        )

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify") as mock_modify,
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 10)
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_modify.assert_called_once_with(
            "pi_test_for_modify",
            metadata={
                "checkout_session_id": "cs_test_for_modify",
                "pack": "standard",
            },
        )

    def test_payment_intent_modify_called_for_all_packs(self, client):
        """PI modify is called for starter, standard, and power packs."""
        for pack in ("starter", "standard", "power"):
            event = _make_event(
                session_id=f"cs_{pack}",
                payment_intent_id=f"pi_{pack}",
                pack=pack,
            )
            with (
                patch("stripe.Webhook.construct_event", return_value=event),
                patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
                patch("stripe.PaymentIntent.modify") as mock_modify,
            ):
                mock_mint.return_value = MagicMock(ok=True, tokens=[])
                _post_webhook(client, event)

            mock_modify.assert_called_once()
            _, modify_kwargs = mock_modify.call_args
            assert modify_kwargs["metadata"]["checkout_session_id"] == f"cs_{pack}"
            assert modify_kwargs["metadata"]["pack"] == pack


# ---------------------------------------------------------------------------
# checkout.session.completed -- edge cases
# ---------------------------------------------------------------------------

class TestCheckoutSessionCompletedEdgeCases:
    """Malformed events, missing session_id, unknown pack, idempotent retries."""

    def test_missing_session_id_returns_200_no_mint(self, client):
        """Event missing data.object.id returns 200 with WARN log, no mint."""
        event = _make_event()
        event["data"]["object"]["id"] = None  # explicitly None

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_mint.assert_not_called()

    def test_unknown_pack_count_zero_returns_200_no_mint(self, client):
        """Event with unknown pack (count=0) returns 200 with WARN log, no mint."""
        event = _make_event(pack="ultra")  # not in _PACK_TOKEN_COUNT

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_mint.assert_not_called()

    def test_missing_object_id_key_entirely_returns_200(self, client):
        """Event with no 'id' key in data.object returns 200 (defensive .get())."""
        event = _make_event()
        del event["data"]["object"]["id"]

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_mint.assert_not_called()

    def test_idempotent_on_stripe_retry_second_call(self, client):
        """Second Stripe webhook delivery for same event returns 200 idempotently.

        mint_tokens_if_absent returns from_cache=True on second call --
        the handler does not know or care, just returns 200.
        """
        event = _make_event()

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            # First delivery -- fresh mint
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3, from_cache=False)
            resp1 = _post_webhook(client, event)

            # Second delivery -- cache hit (idempotent)
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3, from_cache=True)
            resp2 = _post_webhook(client, event)

            # Third delivery -- still cache hit
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3, from_cache=True)
            resp3 = _post_webhook(client, event)

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp3.status_code == 200
        assert mock_mint.call_count == 3

    def test_no_payment_intent_id_skips_pi_modify(self, client):
        """If payment_intent is absent, PI modify is skipped but tokens are still minted."""
        event = _make_event()
        event["data"]["object"]["payment_intent"] = None

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify") as mock_modify,
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3)
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_mint.assert_called_once()
        mock_modify.assert_not_called()

    def test_webhook_arrives_before_success_page_mints_tokens(self, client):
        """Webhook arrives first -- mint_tokens_if_absent runs, from_cache=False."""
        event = _make_event()
        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3, from_cache=False)
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        assert mock_mint.call_args.args[0] == event["data"]["object"]["id"]

    def test_webhook_arrives_after_success_page_returns_200_idempotently(self, client):
        """Webhook arrives after success page already minted -- from_cache=True, still 200."""
        event = _make_event()
        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3, from_cache=True)
            resp = _post_webhook(client, event)

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# charge.dispute.created -- handler
# ---------------------------------------------------------------------------

class TestDisputeHandler:
    """Dispute handler: PI metadata primary path, fallback, unresolvable, no PI."""

    def test_dispute_with_pi_metadata_calls_mark_disputed(self, client):
        """Dispute event resolves session_id via PI metadata and calls mark_disputed."""
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_dispute_1")
        pi_mock = _make_pi_mock("cs_dispute_session_1")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve", return_value=pi_mock),
            patch("web_service.token_store.mark_disputed") as mock_mark,
            patch("web_service.token_store.find_session_by_payment_intent") as mock_fallback,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_mark.assert_called_once_with("cs_dispute_session_1")
        # Primary path succeeded -- fallback should NOT be called
        mock_fallback.assert_not_called()

    def test_dispute_pi_metadata_path_takes_priority_over_fallback(self, client):
        """When PI metadata has checkout_session_id, fallback is not consulted."""
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_primary")
        pi_mock = _make_pi_mock("cs_primary")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve", return_value=pi_mock),
            patch("web_service.token_store.mark_disputed") as mock_mark,
            patch("web_service.token_store.find_session_by_payment_intent") as mock_fallback,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_mark.assert_called_once_with("cs_primary")
        mock_fallback.assert_not_called()

    def test_dispute_fallback_path_when_pi_metadata_missing(self, client):
        """When PI metadata has no checkout_session_id, fallback find_session_by_payment_intent is used."""
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_fallback")
        pi_mock = _make_pi_mock(session_id=None)  # No checkout_session_id in metadata

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve", return_value=pi_mock),
            patch("web_service.token_store.find_session_by_payment_intent", return_value="cs_from_db") as mock_fallback,
            patch("web_service.token_store.mark_disputed") as mock_mark,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_fallback.assert_called_once_with("pi_fallback")
        mock_mark.assert_called_once_with("cs_from_db")

    def test_dispute_fallback_path_when_stripe_retrieve_fails(self, client):
        """When PI retrieve throws StripeError, fallback is consulted."""
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_stripe_fail")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch(
                "stripe.PaymentIntent.retrieve",
                side_effect=stripe.error.StripeError("Network error"),
            ),
            patch("web_service.token_store.find_session_by_payment_intent", return_value="cs_via_fallback") as mock_fallback,
            patch("web_service.token_store.mark_disputed") as mock_mark,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_fallback.assert_called_once_with("pi_stripe_fail")
        mock_mark.assert_called_once_with("cs_via_fallback")

    def test_dispute_unresolvable_returns_200_no_side_effects(self, client):
        """When neither PI metadata nor fallback resolves session_id, return 200 with ERROR log."""
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_unknown")
        pi_mock = _make_pi_mock(session_id=None)

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve", return_value=pi_mock),
            patch("web_service.token_store.find_session_by_payment_intent", return_value=None),
            patch("web_service.token_store.mark_disputed") as mock_mark,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_mark.assert_not_called()

    def test_dispute_no_payment_intent_field_returns_200(self, client):
        """Dispute event with no payment_intent field returns 200 with WARN, no side effects."""
        event = _make_event(event_type="charge.dispute.created")
        del event["data"]["object"]["payment_intent"]

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve") as mock_retrieve,
            patch("web_service.token_store.mark_disputed") as mock_mark,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_retrieve.assert_not_called()
        mock_mark.assert_not_called()

    def test_dispute_null_payment_intent_returns_200(self, client):
        """Dispute event with payment_intent=null returns 200 with WARN, no side effects."""
        event = _make_event(event_type="charge.dispute.created")
        event["data"]["object"]["payment_intent"] = None

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve") as mock_retrieve,
            patch("web_service.token_store.mark_disputed") as mock_mark,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        mock_retrieve.assert_not_called()
        mock_mark.assert_not_called()

    def test_dispute_calls_mark_disputed_with_correct_pack_id(self, client):
        """mark_disputed is called with the session_id (pack_id) from PI metadata."""
        session_id = "cs_very_specific_session"
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_check")
        pi_mock = _make_pi_mock(session_id)

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve", return_value=pi_mock),
            patch("web_service.token_store.mark_disputed") as mock_mark,
        ):
            _post_webhook(client, event)

        mock_mark.assert_called_once_with(session_id)


# ---------------------------------------------------------------------------
# Unknown event type
# ---------------------------------------------------------------------------

class TestUnknownEventType:
    """Unknown event types return 200 with no side effects."""

    @pytest.mark.parametrize("event_type", [
        "customer.created",
        "payment_method.attached",
        "invoice.payment_succeeded",
        "charge.succeeded",
        "checkout.session.expired",
    ])
    def test_unknown_event_type_returns_200_no_side_effects(self, client, event_type):
        """Unknown event type returns 200 without calling any store functions."""
        event = _make_event(event_type=event_type)

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("web_service.token_store.mark_disputed") as mock_mark,
            patch("stripe.PaymentIntent.retrieve") as mock_retrieve,
            patch("stripe.PaymentIntent.modify") as mock_modify,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        assert resp.json() == {"received": True}
        mock_mint.assert_not_called()
        mock_mark.assert_not_called()
        mock_retrieve.assert_not_called()
        mock_modify.assert_not_called()


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class TestCircuitBreakerIntegration:
    """Circuit open -> 503 short-circuit without hitting DB."""

    def test_circuit_open_returns_503(self, client):
        """When circuit_is_open() returns True, handler short-circuits to 503."""
        import web_service.circuit_breaker as cb

        with (
            patch.object(cb, "circuit_is_open", return_value=True),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.Webhook.construct_event") as mock_construct,
        ):
            resp = _post_webhook(client, _make_event())

        assert resp.status_code == 503
        body = resp.json()
        assert "retry" in body.get("error", "").lower() or "degraded" in body.get("error", "")
        # No DB or Stripe calls should be made when circuit is open
        mock_mint.assert_not_called()
        mock_construct.assert_not_called()

    def test_circuit_closed_proceeds_normally(self, client):
        """When circuit_is_open() returns False (default), handler proceeds."""
        import web_service.circuit_breaker as cb
        event = _make_event()

        with (
            patch.object(cb, "circuit_is_open", return_value=False),
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=[])
            resp = _post_webhook(client, event)

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DB failure paths
# ---------------------------------------------------------------------------

class TestDBFailurePaths:
    """DB write failures return 500 + record failed_mint + increment circuit breaker."""

    def test_mint_db_failure_returns_500(self, client):
        """sqlite3.OperationalError during mint returns 500."""
        event = _make_event()

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch(
                "web_service.token_store.mint_tokens_if_absent",
                side_effect=sqlite3.OperationalError("database is locked"),
            ),
            patch("web_service.token_store.record_failed_mint") as mock_record,
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 500
        body = resp.json()
        assert "transient" in body["detail"]["error"].lower() or "retry" in body["detail"]["error"].lower()

    def test_mint_db_failure_calls_record_failed_mint(self, client):
        """After mint OperationalError, record_failed_mint is called with session_id and pack."""
        event = _make_event(session_id="cs_fail_mint", pack="power")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch(
                "web_service.token_store.mint_tokens_if_absent",
                side_effect=sqlite3.OperationalError("database is locked"),
            ),
            patch("web_service.token_store.record_failed_mint") as mock_record,
        ):
            _post_webhook(client, event)

        mock_record.assert_called_once()
        call_args = mock_record.call_args.args
        assert call_args[0] == "cs_fail_mint", "First arg must be session_id"
        assert call_args[1] == "power", "Second arg must be pack name"

    def test_mint_db_failure_increments_circuit_breaker(self, client):
        """DB failure during mint calls circuit_breaker.db_call_failed()."""
        import web_service.circuit_breaker as cb
        event = _make_event()

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch(
                "web_service.token_store.mint_tokens_if_absent",
                side_effect=sqlite3.OperationalError("locked"),
            ),
            patch("web_service.token_store.record_failed_mint"),
            patch.object(cb, "db_call_failed") as mock_failed,
        ):
            _post_webhook(client, event)

        mock_failed.assert_called_once()

    def test_mint_success_resets_circuit_breaker(self, client):
        """Successful mint calls circuit_breaker.db_call_succeeded()."""
        import web_service.circuit_breaker as cb
        event = _make_event()

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch("stripe.PaymentIntent.modify"),
            patch.object(cb, "db_call_succeeded") as mock_succeeded,
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=[])
            _post_webhook(client, event)

        mock_succeeded.assert_called_once()


# ---------------------------------------------------------------------------
# Dispute DB failure
# ---------------------------------------------------------------------------

class TestDisputeDBFailure:
    """mark_disputed DB failure returns 500 + circuit breaker increment."""

    def test_mark_disputed_db_failure_returns_500(self, client):
        """sqlite3.OperationalError during mark_disputed returns 500."""
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_dispute_fail")
        pi_mock = _make_pi_mock("cs_dispute_fail")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve", return_value=pi_mock),
            patch(
                "web_service.token_store.mark_disputed",
                side_effect=sqlite3.OperationalError("database is locked"),
            ),
        ):
            resp = _post_webhook(client, event)

        assert resp.status_code == 500

    def test_mark_disputed_db_failure_increments_circuit_breaker(self, client):
        """DB failure during mark_disputed calls circuit_breaker.db_call_failed()."""
        import web_service.circuit_breaker as cb
        event = _make_event(event_type="charge.dispute.created", payment_intent_id="pi_cb_test")
        pi_mock = _make_pi_mock("cs_cb_test")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("stripe.PaymentIntent.retrieve", return_value=pi_mock),
            patch(
                "web_service.token_store.mark_disputed",
                side_effect=sqlite3.OperationalError("locked"),
            ),
            patch.object(cb, "db_call_failed") as mock_failed,
        ):
            _post_webhook(client, event)

        mock_failed.assert_called_once()


# ---------------------------------------------------------------------------
# PaymentIntent.modify failure after successful mint
# ---------------------------------------------------------------------------

class TestStripeModifyFailureAfterMint:
    """PI modify failure after mint -> still 200 (tokens are minted; fallback exists)."""

    def test_pi_modify_failure_still_returns_200(self, client):
        """If stripe.PaymentIntent.modify raises StripeError after mint, return 200.

        Tokens are already minted. The dispute handler has find_session_by_payment_intent
        as a fallback, so PI modify failure is non-fatal.
        """
        event = _make_event(pack="starter")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch(
                "stripe.PaymentIntent.modify",
                side_effect=stripe.error.StripeError("API error"),
            ),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=["lb_pk_" + "A" * 43] * 3)
            resp = _post_webhook(client, event)

        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_pi_modify_failure_mint_was_still_called(self, client):
        """Even when PI modify fails, mint_tokens_if_absent was called."""
        event = _make_event()

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch(
                "stripe.PaymentIntent.modify",
                side_effect=stripe.error.StripeError("API error"),
            ),
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=[])
            _post_webhook(client, event)

        mock_mint.assert_called_once()

    def test_pi_modify_failure_circuit_breaker_not_tripped(self, client):
        """PI modify failure does not trip the DB circuit breaker."""
        import web_service.circuit_breaker as cb
        event = _make_event()

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
            patch(
                "stripe.PaymentIntent.modify",
                side_effect=stripe.error.StripeError("API error"),
            ),
            patch.object(cb, "db_call_failed") as mock_failed,
        ):
            mock_mint.return_value = MagicMock(ok=True, tokens=[])
            _post_webhook(client, event)

        # DB circuit breaker should NOT be called for a Stripe API failure
        mock_failed.assert_not_called()


# ---------------------------------------------------------------------------
# Concurrent webhook + success-page (race-loser idempotency)
# ---------------------------------------------------------------------------

class TestConcurrentWebhookAndSuccessPage:
    """Race-loser invariant: only one set of tokens persists under concurrent access."""

    def test_concurrent_mint_calls_idempotent(self, tmp_path, monkeypatch):
        """Concurrent mint_tokens_if_absent for same session_id is idempotent.

        Simulates the webhook path and success-page path calling mint concurrently.
        Both should return successfully (one mints, one returns from_cache=True);
        the token DB should contain exactly N rows for the session.
        """
        import sys
        import json as _json
        import web_service.config as cfg_mod

        # Set up a real temp DB for this integration test
        cfg = {
            "paths": {
                "calibre": "/usr/bin/ebook-convert",
                "python": "/usr/bin/python3",
                "kindle": "output/kindle",
            }
        }
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(_json.dumps(cfg), encoding="utf-8")
        (tmp_path / "data").mkdir()
        monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(sys, "platform", "linux")
        reset_settings()

        import web_service.token_store as ts
        ts.init_db(tmp_path / "data" / "web_service.db")

        results = []
        errors = []
        barrier = threading.Barrier(2)

        def mint_thread(thread_name: str) -> None:
            barrier.wait()  # Both threads start at the same time
            try:
                result = ts.mint_tokens_if_absent(
                    "cs_concurrent_race",
                    3,
                    "pi_concurrent_race",
                    db_path=tmp_path / "data" / "web_service.db",
                )
                results.append((thread_name, result))
            except Exception as exc:
                errors.append((thread_name, exc))

        t1 = threading.Thread(target=mint_thread, args=("webhook",))
        t2 = threading.Thread(target=mint_thread, args=("success_page",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 2, "Both threads should complete"

        # Both threads should report success
        for thread_name, result in results:
            assert result.ok, f"{thread_name} result should be ok"
            assert len(result.tokens) == 3, f"{thread_name} should return 3 tokens"

        # Verify DB has exactly 3 rows for this session (no duplicates)
        import sqlite3 as _sqlite3
        db_path = tmp_path / "data" / "web_service.db"
        conn = _sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT COUNT(*) FROM tokens WHERE pack_id=?",
            ("cs_concurrent_race",),
        ).fetchone()
        conn.close()
        assert row[0] == 3, f"Expected exactly 3 tokens in DB, got {row[0]}"

        reset_settings()


# ---------------------------------------------------------------------------
# Middleware safety check (startup warning)
# ---------------------------------------------------------------------------

class TestMiddlewareSafetyCheck:
    """Non-allowlisted middleware triggers WARN at startup."""

    def test_non_allowlisted_middleware_triggers_warning(self, project_root, caplog):
        """Adding a non-CORSMiddleware class triggers the startup WARN log."""
        import logging
        import web_service.main as main_mod

        # Re-import to get fresh app
        importlib.reload(main_mod)

        # Simulate checking a hypothetical body-consuming middleware
        class BodyLoggingMiddleware:
            pass

        fake_entry = MagicMock()
        fake_entry.cls = BodyLoggingMiddleware

        app = main_mod.create_app()
        with caplog.at_level(logging.WARNING, logger="web_service.main"):
            # Directly call the internal checker with a non-allowlisted middleware
            main_mod._check_middleware_safety.__func__ if hasattr(
                main_mod._check_middleware_safety, "__func__"
            ) else main_mod._check_middleware_safety

            # Patch app.user_middleware to include a non-allowlisted entry
            with patch.object(app, "user_middleware", [fake_entry]):
                main_mod._check_middleware_safety(app)

        assert any(
            "non_allowlisted_middleware" in r.getMessage().lower() or
            "non-allowlisted" in r.getMessage().lower() or
            "BodyLoggingMiddleware" in r.getMessage()
            for r in caplog.records
        ), "Expected non-allowlisted middleware warning in logs"

    def test_cors_middleware_is_allowlisted_no_warning(self, project_root, caplog):
        """CORSMiddleware class does NOT trigger a warning."""
        import logging
        from fastapi.middleware.cors import CORSMiddleware
        import web_service.main as main_mod

        importlib.reload(main_mod)

        fake_entry = MagicMock()
        fake_entry.cls = CORSMiddleware

        app = main_mod.create_app()
        with caplog.at_level(logging.WARNING, logger="web_service.main"):
            with patch.object(app, "user_middleware", [fake_entry]):
                main_mod._check_middleware_safety(app)

        # No warning should be logged for CORSMiddleware
        warning_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING and
            ("non_allowlisted" in r.getMessage().lower() or
             "CORSMiddleware" in r.getMessage())
        ]
        assert not warning_records, (
            f"CORSMiddleware should not trigger a warning, got: {warning_records}"
        )


# ---------------------------------------------------------------------------
# Integration: router is registered in app
# ---------------------------------------------------------------------------

class TestWebhookRouterRegistration:
    """Verify the webhook router is properly included in the FastAPI app."""

    def test_webhook_route_exists_in_app(self, client):
        """The /stripe/webhook POST route is registered and reachable."""
        # With invalid signature, we get 400 -- not 404 (route exists)
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad", "bad"),
        ):
            resp = client.post(
                "/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=bad"},
            )

        # 400 means the route exists and processed the request (not 404/405)
        assert resp.status_code == 400, (
            f"Expected 400 (route exists, bad sig), got {resp.status_code}"
        )

    def test_webhook_route_not_found_without_post(self, client):
        """GET /stripe/webhook returns 405 Method Not Allowed (not 404)."""
        resp = client.get("/stripe/webhook")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Clock drift warning
# ---------------------------------------------------------------------------

class TestClockDriftWarning:
    """Events with large timestamp drift log a warning (advisory, not blocking)."""

    def test_large_clock_drift_logs_warning_but_proceeds(self, client, caplog):
        """Event with >60s drift logs webhook_clock_drift_warn but still returns 200."""
        import logging
        # Create event with timestamp 5 minutes in the past
        old_created = int(time.time()) - 400
        event = _make_event(created=old_created)
        # Note: construct_event tolerance check is different from our drift warning.
        # Here we test our own advisory drift warning by having construct_event succeed.
        event_with_old_ts = dict(event)
        event_with_old_ts["created"] = old_created

        with caplog.at_level(logging.WARNING, logger="web_service.routes.webhook"):
            with (
                patch("stripe.Webhook.construct_event", return_value=event_with_old_ts),
                patch("web_service.token_store.mint_tokens_if_absent") as mock_mint,
                patch("stripe.PaymentIntent.modify"),
            ):
                mock_mint.return_value = MagicMock(ok=True, tokens=[])
                resp = _post_webhook(client, event_with_old_ts)

        # Advisory warning -- does NOT block processing
        assert resp.status_code == 200
        # Check that the drift warning was logged
        drift_logs = [
            r for r in caplog.records
            if "drift" in r.getMessage().lower() or "drift" in str(getattr(r, "extra", {})).lower()
        ]
        assert drift_logs, "Expected webhook_clock_drift_warn log for >60s drift"
