"""Tests for POST /webhooks/resend — EB-324 Unit 10.

Resend delivers signed webhook events via Svix when a previously-sent
email transitions through delivery states. This module covers the full
webhook contract:

  - **Signature verification (load-bearing — write first per plan
    execution note):** invalid or missing Svix signature → 401. Without
    this, the entire telemetry signal is attacker-forgeable.
  - **Event dispatch (4 known types):** email.delivered / .bounced /
    .failed / .delivery_delayed each update `kindle_delivery_status`
    and emit the matching `send_to_kindle_*` telemetry event.
  - **Idempotency + out-of-order arrival:** Resend retries webhooks;
    delivery events can arrive in any order. Terminal states (delivered,
    bounced, failed) stick — later out-of-order `delivery_delayed`
    events are logged and ignored.
  - **Privacy:** the recipient address MUST NOT appear in any captured
    log record, even when Resend echoes it in `bounce.message`.

Plan reference: docs/plans/2026-05-19-001-feat-eb-324-wave-1-action-cluster-plan.md
Unit 10 (lines 691-748).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import importlib.util
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/test_web_send_to_kindle.py)
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
    """TestClient with dispatch_job mocks (no real conversion pipeline)."""
    import web_service.job_store as js
    import web_service.main as main_mod
    from web_service.config import load_settings

    settings = load_settings()
    js.init_db(settings.db_path)
    importlib.reload(main_mod)

    convert_patch = patch(
        "web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()
    )
    init_patch = patch("web_service.job_queue.init_queue")
    cleanup_patch = patch(
        "web_service.job_queue.cleanup_expired_jobs", return_value=AsyncMock()
    )
    reconvert_exists = (
        importlib.util.find_spec("web_service.routes.reconvert") is not None
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


def _seed_done_parent_with_message_id(settings, db_path, resend_message_id: str) -> str:
    """Create a done parent job with a known resend_message_id so the
    webhook handler can correlate the incoming event.
    """
    import sqlite3

    import web_service.job_store as js

    parent_id = js.new_job_id()
    parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
    parent_temp.mkdir(parents=True, exist_ok=True)
    src = parent_temp / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n" + b"\x00" * 200)
    out = parent_temp / "output.epub"
    out.write_bytes(b"PK\x03\x04" + b"\x00" * 200)

    js.create_job(
        job_id=parent_id, tier="free", input_fmt="pdf", output_fmt="epub",
        temp_dir=str(parent_temp), input_path=str(src),
    )
    js.set_done(parent_id, str(out), out.stat().st_size)

    # Seed resend_message_id + kindle_delivery_status='accepted_by_resend'
    # to mirror the state after a successful Send-to-Kindle.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE jobs SET resend_message_id = ?, kindle_delivery_status = ? "
            "WHERE job_id = ?",
            (resend_message_id, "accepted_by_resend", parent_id),
        )
        conn.commit()
    finally:
        conn.close()
    return parent_id


# ---------------------------------------------------------------------------
# Svix signature helper
# ---------------------------------------------------------------------------


def _sign_payload(payload_dict: dict, *, secret: str | None = None) -> tuple[bytes, dict]:
    """Return (raw_body, headers) for a test webhook POST.

    Computes a Svix v1 signature: HMAC-SHA256 of "{id}.{timestamp}.{body}"
    keyed by the base64-decoded secret. Output header format matches what
    Resend (via Svix) sends in production.
    """
    import os
    if secret is None:
        secret = os.environ["WEB_RESEND_WEBHOOK_SECRET"]

    raw_body = json.dumps(payload_dict).encode("utf-8")
    msg_id = f"msg_{uuid.uuid4().hex[:16]}"
    timestamp = str(int(time.time()))

    # Decode "whsec_<base64>" → raw key bytes
    _, _, b64 = secret.partition("_")
    secret_bytes = base64.b64decode(b64)

    to_sign = f"{msg_id}.{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
    sig = base64.b64encode(
        hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
    ).decode("ascii")

    headers = {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{sig}",
        "content-type": "application/json",
    }
    return raw_body, headers


# ---------------------------------------------------------------------------
# Load-bearing — signature verification (write FIRST per plan execution note)
# ---------------------------------------------------------------------------


class TestResendWebhookSignatureVerification:
    """If signature verification can be bypassed, the entire telemetry
    signal is attacker-forgeable — an unauthenticated POST could flip
    any job's kindle_delivery_status to whatever the attacker wants.
    """

    def test_missing_svix_headers_returns_401(self, client):
        tc, _, _ = client
        resp = tc.post(
            "/webhooks/resend",
            content=b'{"type": "email.delivered", "data": {"email_id": "x"}}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_invalid_svix_signature_returns_401(self, client):
        tc, _, _ = client
        raw_body, headers = _sign_payload({"type": "email.delivered", "data": {"email_id": "x"}})
        # Corrupt the signature.
        headers["svix-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
        resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Happy paths — 4 event types
# ---------------------------------------------------------------------------


class TestResendWebhookEventDispatch:
    def test_email_delivered_transitions_status_and_emits_telemetry(self, client):
        import sqlite3

        from web_service import recovery_events_store

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        parent_id = _seed_done_parent_with_message_id(settings, db_path, message_id)

        captured: list[tuple[str, dict | None]] = []
        original_log_event = recovery_events_store.log_event

        def _capture(event_type, details=None, db_path=None):
            captured.append((event_type, details))
            return original_log_event(event_type, details=details, db_path=db_path)

        raw_body, headers = _sign_payload({
            "type": "email.delivered",
            "data": {"email_id": message_id},
        })

        with patch.object(recovery_events_store, "log_event", side_effect=_capture):
            resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)

        assert resp.status_code == 200, resp.text

        # Status updated.
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT kindle_delivery_status FROM jobs WHERE job_id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        assert row[0] == "delivered_to_mail_server"

        # Telemetry emitted with the matching event type.
        event_types = [e[0] for e in captured]
        assert "send_to_kindle_delivered_to_mail_server" in event_types

    def test_email_bounced_transitions_status_and_includes_subtype(self, client):
        import sqlite3

        from web_service import recovery_events_store

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        parent_id = _seed_done_parent_with_message_id(settings, db_path, message_id)

        captured: list[tuple[str, dict | None]] = []
        original_log_event = recovery_events_store.log_event

        def _capture(event_type, details=None, db_path=None):
            captured.append((event_type, details))
            return original_log_event(event_type, details=details, db_path=db_path)

        raw_body, headers = _sign_payload({
            "type": "email.bounced",
            "data": {
                "email_id": message_id,
                "bounce": {"type": "Permanent", "subType": "Suppressed"},
            },
        })

        with patch.object(recovery_events_store, "log_event", side_effect=_capture):
            resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert resp.status_code == 200, resp.text

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT kindle_delivery_status FROM jobs WHERE job_id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        assert row[0] == "bounced"

        bounce_events = [e for e in captured if e[0] == "send_to_kindle_bounced"]
        assert len(bounce_events) == 1
        # Bounce subtype must be in the telemetry details for dashboards.
        details = bounce_events[0][1] or {}
        assert details.get("bounce_type") == "Permanent" or details.get("bounce_subtype") == "Suppressed", (
            "Bounce telemetry must include bounce type/subtype. Got: " + repr(details)
        )

    def test_email_failed_transitions_status(self, client):
        import sqlite3

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        parent_id = _seed_done_parent_with_message_id(settings, db_path, message_id)

        raw_body, headers = _sign_payload({
            "type": "email.failed",
            "data": {
                "email_id": message_id,
                "failed": {"reason": "Generic provider failure"},
            },
        })

        resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert resp.status_code == 200, resp.text

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT kindle_delivery_status FROM jobs WHERE job_id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        assert row[0] == "failed"

    def test_email_delivery_delayed_transitions_status(self, client):
        import sqlite3

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        parent_id = _seed_done_parent_with_message_id(settings, db_path, message_id)

        raw_body, headers = _sign_payload({
            "type": "email.delivery_delayed",
            "data": {"email_id": message_id},
        })

        resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert resp.status_code == 200, resp.text

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT kindle_delivery_status FROM jobs WHERE job_id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        assert row[0] == "delivery_delayed"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestResendWebhookEdgeCases:
    def test_unknown_event_type_returns_200_no_state_change(self, client):
        import sqlite3

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        parent_id = _seed_done_parent_with_message_id(settings, db_path, message_id)

        raw_body, headers = _sign_payload({
            "type": "email.opened",  # not in our handled set
            "data": {"email_id": message_id},
        })

        resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert resp.status_code == 200

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT kindle_delivery_status FROM jobs WHERE job_id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        # Still the original 'accepted_by_resend' from the seed.
        assert row[0] == "accepted_by_resend"

    def test_unknown_message_id_returns_200_without_recipient_in_logs(self, client, caplog):
        tc, _, _ = client
        ghost_message_id = "resend_msg_ghost_does_not_exist"
        recipient_marker = "leak-canary@kindle.com"

        raw_body, headers = _sign_payload({
            "type": "email.delivered",
            "data": {
                "email_id": ghost_message_id,
                # If the handler logs the raw payload, this would surface.
                "to": [recipient_marker],
            },
        })

        caplog.set_level(logging.DEBUG)
        resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        # 200 (not 404) — Resend retries on 4xx/5xx and we don't want to retry a ghost.
        assert resp.status_code == 200

        # The address must NOT appear in any captured log record.
        for record in caplog.records:
            assert "@kindle.com" not in record.getMessage(), (
                f"Unknown-message_id log path leaked recipient: {record.getMessage()!r}"
            )
        assert "@kindle.com" not in caplog.text

    def test_out_of_order_arrival_keeps_terminal_state(self, client):
        """delivered arrives first, then delivery_delayed arrives — the
        terminal `delivered_to_mail_server` state MUST stick.
        """
        import sqlite3

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        parent_id = _seed_done_parent_with_message_id(settings, db_path, message_id)

        # 1. Deliver
        body1, hdr1 = _sign_payload({
            "type": "email.delivered",
            "data": {"email_id": message_id},
        })
        r1 = tc.post("/webhooks/resend", content=body1, headers=hdr1)
        assert r1.status_code == 200

        # 2. Out-of-order delay arrival
        body2, hdr2 = _sign_payload({
            "type": "email.delivery_delayed",
            "data": {"email_id": message_id},
        })
        r2 = tc.post("/webhooks/resend", content=body2, headers=hdr2)
        assert r2.status_code == 200

        # State must still be delivered, NOT regressed to delivery_delayed.
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT kindle_delivery_status FROM jobs WHERE job_id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        assert row[0] == "delivered_to_mail_server", (
            f"Out-of-order delay must NOT regress from delivered. Got: {row[0]!r}"
        )

    def test_duplicate_webhook_is_idempotent(self, client):
        """Resend retries on webhook timeouts; the same event arriving twice
        must not double-emit telemetry or flip the state needlessly.
        """
        from web_service import recovery_events_store

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        _seed_done_parent_with_message_id(settings, db_path, message_id)

        captured: list[tuple[str, dict | None]] = []
        original = recovery_events_store.log_event

        def _capture(event_type, details=None, db_path=None):
            captured.append((event_type, details))
            return original(event_type, details=details, db_path=db_path)

        body, hdr = _sign_payload({
            "type": "email.delivered",
            "data": {"email_id": message_id},
        })

        with patch.object(recovery_events_store, "log_event", side_effect=_capture):
            r1 = tc.post("/webhooks/resend", content=body, headers=hdr)
            # Re-sign with a different svix-id (same payload) to mimic
            # Resend's actual retry behavior (new svix delivery attempt).
            body2, hdr2 = _sign_payload({
                "type": "email.delivered",
                "data": {"email_id": message_id},
            })
            r2 = tc.post("/webhooks/resend", content=body2, headers=hdr2)
        assert r1.status_code == 200 and r2.status_code == 200

        # Only one delivery telemetry event — duplicate is a no-op.
        delivered_events = [
            e for e in captured if e[0] == "send_to_kindle_delivered_to_mail_server"
        ]
        assert len(delivered_events) == 1, (
            f"Duplicate webhook must not emit telemetry twice. Got "
            f"{len(delivered_events)} delivery events: {delivered_events!r}"
        )

    def test_malformed_payload_returns_400(self, client):
        tc, _, _ = client
        # Valid signature over malformed JSON (missing 'type' field).
        raw_body, headers = _sign_payload({"data": {"email_id": "x"}})
        resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Privacy — load-bearing for the "we never log the recipient" promise
# ---------------------------------------------------------------------------


class TestResendWebhookPrivacy:
    def test_bounce_message_with_recipient_does_not_leak_to_logs(self, client, caplog):
        """Resend sometimes echoes the recipient in `bounce.message`. The
        webhook handler MUST scrub the address before logging or storing
        in the telemetry details dict.
        """
        from web_service import recovery_events_store

        tc, db_path, settings = client
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"
        _seed_done_parent_with_message_id(settings, db_path, message_id)
        recipient_marker = "leak-canary@kindle.com"

        captured_details: list[dict | None] = []
        original = recovery_events_store.log_event

        def _capture(event_type, details=None, db_path=None):
            captured_details.append(details)
            return original(event_type, details=details, db_path=db_path)

        raw_body, headers = _sign_payload({
            "type": "email.bounced",
            "data": {
                "email_id": message_id,
                "to": [recipient_marker],
                "bounce": {
                    "type": "Permanent",
                    "subType": "General",
                    # Resend echoes the address back in the human message.
                    "message": f"Mailbox not found: {recipient_marker}",
                },
            },
        })

        caplog.set_level(logging.DEBUG)
        with patch.object(recovery_events_store, "log_event", side_effect=_capture):
            resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert resp.status_code == 200

        # caplog: no recipient.
        for record in caplog.records:
            assert "@kindle.com" not in record.getMessage(), (
                f"Log leaked recipient in {record.name}: {record.getMessage()!r}"
            )
        assert "@kindle.com" not in caplog.text, (
            f"caplog.text leaked recipient marker. Search the logging "
            f"paths for unintended echoes of bounce.message or data.to."
        )

        # Telemetry details: also no recipient.
        for details in captured_details:
            if details is None:
                continue
            serialized = json.dumps(details, default=str)
            assert "@kindle.com" not in serialized, (
                f"Telemetry details leaked recipient: {serialized!r}"
            )
