"""Signed-event end-to-end test for the Send-to-Kindle delivery chain — EB-330.

This is the Send-to-Kindle analogue of ``tests/test_web_payment_e2e.py``: it
exercises the *full* send → webhook → delivery-status round-trip with a real
Svix HMAC signature, but without calling the live Resend API (the outbound
``email_client.send_with_attachment`` is mocked so CI needs no network or
credentials).

What this catches that the isolated unit tests don't
-----------------------------------------------------
  - ``tests/test_web_send_to_kindle.py`` (Unit 4) drives the POST route but
    mocks Resend; it never sees a delivery webhook.
  - ``tests/test_web_resend_webhook.py`` (Unit 10) drives the webhook but
    **seeds** ``resend_message_id`` directly into the DB — it never goes
    through the real send route.

Neither covers the **correlation contract** between the two units: Unit 4's
``_persist_resend_message_id`` writes the key that Unit 10's
``find_by_resend_message_id`` reads. A refactor that renamed the column, or
changed the ``accepted_by_resend`` baseline status, would pass both isolated
suites but break the live delivery-telemetry signal. This test drives the real
route to persist the key, then fires a real signed webhook that must correlate
back to it — exactly the gap the Stripe e2e fills for checkout.

It also re-asserts the load-bearing security guard end-to-end: a delivery
webhook for a genuinely-sent message is still rejected (401) without a valid
Svix signature.

Live-API path (gated, normally skipped)
---------------------------------------
``TestSendToKindleLiveResend`` performs a *real* Resend send and is skipped
unless ``WEB_RESEND_TEST_API_KEY`` **and** a verified sender / real Kindle test
recipient are all configured (the @kindle.com allowlist means a live send needs
a real registered address — see ``tools/verify_send_to_kindle.ps1`` for the
manual equivalent). CI wires ``WEB_RESEND_TEST_API_KEY`` as a secret so the
class runs there when the full rig is configured; otherwise it skips cleanly.

Plan reference: docs/plans/2026-05-19-001-feat-eb-324-wave-1-action-cluster-plan.md
(Unit 4 "Remaining before the flag can flip", items 6-7). Ticket: EB-330 Lane A.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/test_web_send_to_kindle.py + test_web_resend_webhook.py)
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
    """TestClient backed by a fresh temp DB; dispatch_job mocked so route
    imports stay decoupled from the real conversion pipeline. The Send-to-Kindle
    flag is forced on by conftest's _phase2_env_defaults.
    """
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_done_epub_parent(settings) -> str:
    """Create a 'done' parent job whose EPUB output sits on disk inside
    settings.temp_dir (so the route's P1-4 boundary check passes).
    """
    import web_service.job_store as js

    parent_id = js.new_job_id()
    parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
    parent_temp.mkdir(parents=True, exist_ok=True)
    src = parent_temp / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)
    out = parent_temp / "output.epub"
    out.write_bytes(b"PK\x03\x04" + b"\x00" * 400)

    js.create_job(
        job_id=parent_id, tier="free", input_fmt="pdf", output_fmt="epub",
        temp_dir=str(parent_temp), input_path=str(src),
    )
    js.set_done(parent_id, str(out), out.stat().st_size)
    return parent_id


def _sign_resend_payload(payload_dict: dict, *, secret: str | None = None) -> tuple[bytes, dict]:
    """Return (raw_body, headers) for a Svix-signed webhook POST.

    Computes the Svix v1 signature: HMAC-SHA256 of "{id}.{timestamp}.{body}"
    keyed by the base64-decoded secret. Header shape matches what Resend (via
    Svix) emits in production. Identical algorithm to the helper in
    test_web_resend_webhook.py — duplicated rather than imported to keep the
    e2e file self-contained.
    """
    if secret is None:
        secret = os.environ["WEB_RESEND_WEBHOOK_SECRET"]

    raw_body = json.dumps(payload_dict).encode("utf-8")
    msg_id = f"msg_{uuid.uuid4().hex[:16]}"
    timestamp = str(int(time.time()))

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


def _read_job_delivery_state(db_path, job_id: str) -> tuple[str | None, str | None]:
    """Return (resend_message_id, kindle_delivery_status) for a job row."""
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT resend_message_id, kindle_delivery_status FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None, None
    return row[0], row[1]


def _send_to_kindle_with_mocked_resend(tc, job_id: str, *, message_id: str, recipient: str = "reader@kindle.com"):
    """POST /send-to-kindle/{job_id} with email_client.send_with_attachment
    mocked to return a known message_id (no real Resend call). Returns the
    HTTP response.
    """
    from web_service import email_client

    fake_result = email_client.SendResult(message_id=message_id)
    with patch(
        "web_service.email_client.send_with_attachment",
        return_value=fake_result,
    ) as mock_send:
        resp = tc.post(f"/send-to-kindle/{job_id}", data={"recipient": recipient})
    return resp, mock_send


# ---------------------------------------------------------------------------
# Headline e2e — real send route persists the key, real signed webhook reads it
# ---------------------------------------------------------------------------


class TestSendToKindleSignedRoundTrip:
    """Drive the real send route, then fire a real Svix-signed delivery webhook
    that must correlate back to the message_id the route persisted.
    """

    def test_send_then_signed_delivered_webhook_transitions_status(self, client):
        """The headline EB-330 test: POST send → accepted_by_resend persisted →
        signed email.delivered webhook → delivered_to_mail_server.

        If this passes, the Unit 4 → Unit 10 correlation contract is intact: a
        delivery event signed by Resend's secret finds the originating job and
        advances its delivery status. A column rename or baseline-status drift
        between the two units fails here.
        """
        tc, db_path, settings = client
        parent_id = _seed_done_epub_parent(settings)
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"

        # Step 1 — real send route (Resend mocked) persists the correlation key.
        send_resp, mock_send = _send_to_kindle_with_mocked_resend(
            tc, parent_id, message_id=message_id
        )
        assert send_resp.status_code == 200, send_resp.text
        assert send_resp.json() == {"status": "sent"}
        mock_send.assert_called_once()

        persisted_id, status_after_send = _read_job_delivery_state(db_path, parent_id)
        assert persisted_id == message_id, (
            "send route did not persist resend_message_id — Unit 10 will never "
            "correlate the delivery webhook back to this job"
        )
        assert status_after_send == "accepted_by_resend"

        # Step 2 — real Svix-signed delivery webhook correlates and transitions.
        raw_body, headers = _sign_resend_payload({
            "type": "email.delivered",
            "data": {"email_id": message_id},
        })
        wh_resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert wh_resp.status_code == 200, wh_resp.text
        assert wh_resp.json() == {
            "received": True, "handled": True, "transition": "delivered_to_mail_server",
        }

        _, final_status = _read_job_delivery_state(db_path, parent_id)
        assert final_status == "delivered_to_mail_server"

    def test_send_then_signed_bounced_webhook_transitions_status(self, client):
        """A signed email.bounced event transitions the same correlated job to
        'bounced' — and the recipient is scrubbed from bounce telemetry.
        """
        tc, db_path, settings = client
        parent_id = _seed_done_epub_parent(settings)
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"

        send_resp, _ = _send_to_kindle_with_mocked_resend(
            tc, parent_id, message_id=message_id
        )
        assert send_resp.status_code == 200, send_resp.text

        # Resend sometimes echoes the recipient inside bounce.message; the
        # handler must scrub it. We assert the transition here; the scrubbing
        # itself is unit-covered in test_web_resend_webhook.py.
        raw_body, headers = _sign_resend_payload({
            "type": "email.bounced",
            "data": {
                "email_id": message_id,
                "bounce": {
                    "type": "Permanent",
                    "subType": "General",
                    "message": "mailbox reader@kindle.com does not exist",
                },
            },
        })
        wh_resp = tc.post("/webhooks/resend", content=raw_body, headers=headers)
        assert wh_resp.status_code == 200, wh_resp.text
        assert wh_resp.json()["transition"] == "bounced"

        _, final_status = _read_job_delivery_state(db_path, parent_id)
        assert final_status == "bounced"

    def test_unsigned_delivery_webhook_after_real_send_rejected(self, client):
        """Security guard, end-to-end: even for a genuinely-sent message, a
        delivery webhook without a valid Svix signature is rejected with 401.

        If this ever stops returning 401, an unauthenticated attacker could
        flip any job's kindle_delivery_status by guessing a message_id.
        """
        tc, db_path, settings = client
        parent_id = _seed_done_epub_parent(settings)
        message_id = f"resend_msg_{uuid.uuid4().hex[:12]}"

        send_resp, _ = _send_to_kindle_with_mocked_resend(
            tc, parent_id, message_id=message_id
        )
        assert send_resp.status_code == 200, send_resp.text

        # No Svix headers at all → 401, status unchanged.
        unsigned = json.dumps(
            {"type": "email.delivered", "data": {"email_id": message_id}}
        ).encode("utf-8")
        wh_resp = tc.post(
            "/webhooks/resend",
            content=unsigned,
            headers={"content-type": "application/json"},
        )
        assert wh_resp.status_code == 401

        _, status_after = _read_job_delivery_state(db_path, parent_id)
        assert status_after == "accepted_by_resend", (
            "an unsigned webhook must NOT transition delivery status"
        )


# ---------------------------------------------------------------------------
# Live-API path — gated on a real Resend test key + verified sender + recipient
# ---------------------------------------------------------------------------

_LIVE_API_KEY = os.environ.get("WEB_RESEND_TEST_API_KEY")
_LIVE_FROM = os.environ.get("WEB_RESEND_TEST_FROM")
_LIVE_RECIPIENT = os.environ.get("WEB_RESEND_TEST_RECIPIENT")
_LIVE_READY = bool(_LIVE_API_KEY and _LIVE_FROM and _LIVE_RECIPIENT)


@pytest.mark.skipif(
    not _LIVE_READY,
    reason=(
        "live Resend send requires WEB_RESEND_TEST_API_KEY + WEB_RESEND_TEST_FROM "
        "(a verified sender) + WEB_RESEND_TEST_RECIPIENT (a real @kindle.com test "
        "address — the domain allowlist forbids resend.dev sandbox addresses). "
        "Run tools/verify_send_to_kindle.ps1 for the manual equivalent."
    ),
)
class TestSendToKindleLiveResend:
    """Exercises a genuine Resend send through the real route — no mock on
    email_client. Verifies the SDK call shape against Resend's actual API and
    that a real message_id is persisted for webhook correlation.
    """

    @pytest.fixture()
    def live_client(self, project_root, monkeypatch):
        monkeypatch.setenv("WEB_RESEND_API_KEY", _LIVE_API_KEY)
        monkeypatch.setenv("WEB_SEND_TO_KINDLE_FROM", _LIVE_FROM)
        monkeypatch.setenv("WEB_SEND_TO_KINDLE_ENABLED", "true")

        import web_service.job_store as js
        import web_service.main as main_mod
        from web_service.config import load_settings

        settings = load_settings()
        js.init_db(settings.db_path)
        importlib.reload(main_mod)

        with (
            patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()),
            patch("web_service.job_queue.init_queue"),
            patch("web_service.job_queue.cleanup_expired_jobs", return_value=AsyncMock()),
        ):
            with TestClient(main_mod.app) as tc:
                yield tc, settings.db_path, settings

    def test_real_resend_send_persists_message_id(self, live_client):
        tc, db_path, settings = live_client
        parent_id = _seed_done_epub_parent(settings)

        resp = tc.post(
            f"/send-to-kindle/{parent_id}",
            data={"recipient": _LIVE_RECIPIENT},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"status": "sent"}

        persisted_id, status = _read_job_delivery_state(db_path, parent_id)
        assert persisted_id, "real Resend send did not return/persist a message_id"
        assert status == "accepted_by_resend"
