"""Tests for POST /send-to-kindle/{job_id} — EB-324 Unit 4.

This file covers the two highest-signal scenarios named in the PR #141 review:

1.  Atomic idempotency claim under concurrency. Two simultaneous requests for
    the same (job_id, recipient) hit the route. The plan's atomic-claim design
    (PRIMARY KEY on `kindle_send_idempotency`) MUST guarantee that exactly one
    succeeds with `sent` while the other observes the prior claim and returns
    `already_sent` — and Resend's SDK is called exactly once. If two threads
    can both reach Resend, the user gets duplicate Kindle emails.

2.  Log-leak hardening (P1-3 in the plan). When `email_client.send_with_attachment`
    fails, the recipient address MUST NOT appear in any captured log record.
    This is the load-bearing privacy guard for the "we never log the address"
    claim. Without the sanitizing wrapper, an unhandled `resend.exceptions`
    error or the raw response body could leak the address into logs.

Additional plan scenarios (happy path, recipient validation, format check,
size check, etc.) are out of scope for this file in its initial form and will
be added as Unit 4 implementation matures.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import threading
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/test_web_endpoints.py + test_web_reconvert.py)
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
    # The Resend From-address is a future Unit 4 config setting. Provide a
    # placeholder so settings load even before the field is wired into config.
    monkeypatch.setenv("WEB_SEND_TO_KINDLE_FROM", "kindle@send.leafbind.io")
    monkeypatch.setenv("WEB_RESEND_API_KEY", "re_test_placeholder")
    return tmp_path


@pytest.fixture()
def client(project_root):
    """TestClient backed by a fresh temp DB. dispatch_job is mocked on the
    convert/reconvert paths so route imports stay decoupled from the real
    pipeline. send_to_kindle's route doesn't exist yet — patches that target
    it are conditional on importability.
    """
    import importlib

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


def _seed_epub_parent(settings, *, output_bytes: bytes = b"PK\x03\x04" + b"\x00" * 200) -> str:
    """Seed a done parent whose output is an EPUB on disk (Kindle-eligible)."""
    import web_service.job_store as js

    parent_id = js.new_job_id()
    parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
    parent_temp.mkdir(parents=True, exist_ok=True)
    src = parent_temp / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)
    out = parent_temp / "output.epub"
    out.write_bytes(output_bytes)

    js.create_job(
        job_id=parent_id,
        tier="free",
        input_fmt="pdf",
        output_fmt="epub",
        temp_dir=str(parent_temp),
        input_path=str(src),
    )
    js.set_done(parent_id, str(out), out.stat().st_size)
    return parent_id


# ---------------------------------------------------------------------------
# Test 1 — Atomic idempotency claim under concurrency
# ---------------------------------------------------------------------------


class TestSendToKindleAtomicClaim:
    """Plan invariant: exactly one Resend send per (job_id, recipient_hash)
    even under simultaneous POSTs from two workers. The PRIMARY KEY on
    `kindle_send_idempotency(job_id, recipient_hash)` is the race-gate."""

    def test_two_simultaneous_posts_send_exactly_once(self, client):
        """Two threads POST the same (job_id, recipient) at the same instant.
        One should return {"status": "sent"} and invoke Resend; the other
        should return {"status": "already_sent"} and skip Resend.
        """
        # The email_client module ships in Unit 4. Patch its send entry point
        # via the SAME path the route module will use; if the route doesn't
        # exist yet (RED phase), this test will fail at the response status
        # check below because there's no /send-to-kindle to hit.
        send_calls: list[tuple[str, str]] = []
        send_lock = threading.Lock()

        def _record_send(*, from_addr: str, to: list[str], subject: str, html: str, attachments: list):
            with send_lock:
                send_calls.append((from_addr, to[0]))
            return {"id": f"resend_msg_{len(send_calls)}"}

        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        recipient = "joe-canary@kindle.com"

        # Barrier: both threads release simultaneously to maximise the race.
        barrier = threading.Barrier(2)
        results: dict[int, "object"] = {}

        def _post_send(tid: int):
            barrier.wait()
            try:
                resp = tc.post(
                    f"/send-to-kindle/{parent_id}",
                    data={"recipient": recipient},
                )
                results[tid] = (resp.status_code, resp.text)
            except Exception as exc:
                results[tid] = ("exception", repr(exc))

        # Patch email_client only if the module exists. During RED both
        # requests will 404 from the missing route; the assertion below
        # catches that as the failure mode.
        em_spec = importlib.util.find_spec("web_service.email_client")
        if em_spec is not None:
            patcher = patch(
                "web_service.email_client.send_with_attachment",
                side_effect=_record_send,
            )
        else:
            patcher = patch("web_service.job_store.new_job_id")  # harmless no-op patch

        with patcher:
            t1 = threading.Thread(target=_post_send, args=(1,))
            t2 = threading.Thread(target=_post_send, args=(2,))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        statuses = [results[1], results[2]]
        # Both responses must be 200 — no 5xx, no exception escape.
        assert all(s[0] == 200 for s in statuses), (
            f"Both concurrent POSTs must return 200 (sent or already_sent). "
            f"Got: {statuses}"
        )

        bodies = [json.loads(s[1])["status"] for s in statuses]
        # Exactly one of each — that's the atomic-claim invariant.
        assert sorted(bodies) == ["already_sent", "sent"], (
            f"Expected one 'sent' and one 'already_sent', got: {bodies}. "
            f"If both are 'sent', the atomic claim leaked. If both are "
            f"'already_sent', neither succeeded — a separate bug."
        )

        # Most important: Resend was invoked exactly once. Two invocations
        # mean the user got duplicate Kindle emails.
        assert len(send_calls) == 1, (
            f"Resend MUST be called exactly once for the winning request. "
            f"Got {len(send_calls)} calls: {send_calls}"
        )


# ---------------------------------------------------------------------------
# Test 2 — Caplog log-leak hardening (P1-3)
# ---------------------------------------------------------------------------


class TestSendToKindleNoRecipientInLogs:
    """Plan P1-3 invariant: when the Resend send fails, the recipient address
    MUST NOT appear in any captured log record. Validates the sanitizing
    wrapper in `web_service.email_client`.
    """

    def test_recipient_not_logged_on_send_failure(self, client, caplog):
        """Force email_client to raise; assert no @kindle.com substring in logs."""
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        recipient = "joe-leak-canary@kindle.com"

        # Force the wrapper to raise. The wrapper is expected to translate the
        # underlying Resend error into a sanitized KindleSendError whose
        # repr/str do NOT contain the recipient. The route handler should
        # then log only the error class + code, never the address.
        em_spec = importlib.util.find_spec("web_service.email_client")
        if em_spec is not None:
            patcher = patch(
                "web_service.email_client.send_with_attachment",
                side_effect=RuntimeError("simulated Resend 5xx"),
            )
        else:
            patcher = patch("web_service.job_store.new_job_id")  # no-op for RED

        caplog.set_level(logging.DEBUG)
        with patcher:
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": recipient},
            )

        # Route MUST exist and MUST have reached the failure branch — a 404
        # would pass the "no @kindle.com in logs" assertion vacuously, so we
        # need an explicit ≥500 (or known 502 mapping) to prove the failure
        # path actually executed.
        assert resp.status_code >= 500, (
            f"Expected the route to translate Resend failure to a 5xx. "
            f"Got {resp.status_code}: {resp.text}. A 404 here means the "
            f"route doesn't exist (RED state — implement Unit 4)."
        )

        # The load-bearing assertion. Every captured record (message,
        # exception args, traceback message, exc_info) must be free of the
        # recipient string.
        recipient_domain_marker = "@kindle.com"
        for record in caplog.records:
            msg = record.getMessage()
            assert recipient_domain_marker not in msg, (
                f"Log message leaked recipient domain: {msg!r}"
            )
            if record.exc_info:
                exc = record.exc_info[1]
                assert recipient_domain_marker not in repr(exc), (
                    f"Log record exc_info repr leaked recipient: {exc!r}"
                )
        # Belt-and-suspenders: scan the raw caplog text as well.
        assert recipient_domain_marker not in caplog.text, (
            f"caplog.text leaked '{recipient_domain_marker}' somewhere — "
            f"check log format strings AND exception messages"
        )


# ---------------------------------------------------------------------------
# F1 — Feature-flag gating (router live with no validation = job-id-gated relay)
# ---------------------------------------------------------------------------


class TestSendToKindleFeatureFlag:
    """The minimal route has no domain allowlist, no size cap, no output-path
    boundary check. Production must keep it dark until the validation suite
    lands. The feature flag defaults to False; tests opt in explicitly.
    """

    def test_route_returns_503_when_flag_disabled(self, project_root, monkeypatch):
        """With WEB_SEND_TO_KINDLE_ENABLED=false (or unset), POST → 503."""
        import importlib

        import web_service.job_store as js
        import web_service.main as main_mod
        from web_service.config import load_settings

        # Override the conftest default which sets the flag to "true".
        monkeypatch.setenv("WEB_SEND_TO_KINDLE_ENABLED", "false")

        settings = load_settings()
        js.init_db(settings.db_path)
        importlib.reload(main_mod)

        with TestClient(main_mod.app) as tc:
            resp = tc.post(
                "/send-to-kindle/some-job-id",
                data={"recipient": "user@kindle.com"},
            )
        assert resp.status_code == 503, (
            f"Disabled-by-default flag must keep the endpoint dark in production. "
            f"Got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["detail"]["code"] == "SERVICE_DISABLED"


# ---------------------------------------------------------------------------
# F2 — Idempotency window must expire after 60s (plan line 422)
# ---------------------------------------------------------------------------


class TestSendToKindleIdempotencyExpiry:
    """The 60s idempotency contract requires that retries after the window
    elapses are allowed to re-send. _try_claim must opportunistically DELETE
    expired rows inside BEGIN IMMEDIATE before INSERT.
    """

    def test_retry_after_60s_calls_resend_again(self, client, monkeypatch):
        """First POST sends; >60s later, second POST also sends → Resend twice."""
        send_calls: list[str] = []

        def _record_send(*, from_addr: str, to: list[str], subject: str, html: str, attachments: list):
            send_calls.append(to[0])
            return {"id": f"resend_msg_{len(send_calls)}"}

        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        recipient = "joe-retry-canary@kindle.com"

        from web_service.routes import send_to_kindle as stk_module

        # Patch the module-level _now() helper so we can fast-forward time.
        clock = [1_000_000]  # epoch seconds

        def _fake_now() -> int:
            return clock[0]

        monkeypatch.setattr(stk_module, "_now", _fake_now)

        with patch(
            "web_service.email_client.send_with_attachment",
            side_effect=_record_send,
        ):
            resp1 = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": recipient},
            )
            assert resp1.status_code == 200, resp1.text
            assert resp1.json()["status"] == "sent"

            # Advance the route's clock beyond the 60s window.
            clock[0] += 61

            resp2 = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": recipient},
            )
            assert resp2.status_code == 200, resp2.text
            # Critical: status must be "sent" again, not "already_sent".
            assert resp2.json()["status"] == "sent", (
                "After >60s, a retry must be allowed to re-send. Got "
                f"{resp2.json()['status']} — opportunistic DELETE is missing."
            )

        assert len(send_calls) == 2, (
            "Resend must be invoked once per non-overlapping send window. "
            f"Got {len(send_calls)} calls."
        )


# ---------------------------------------------------------------------------
# F3 — Settings.resend_api_key must be applied to the Resend SDK at send time
# ---------------------------------------------------------------------------


class TestSendToKindleResendApiKeyWiring:
    """The Resend SDK reads its API key from module-level resend.api_key.
    The wrapper MUST set that from Settings.resend_api_key before the call,
    otherwise authentication fails (or worse, uses a stale key from another
    test run that leaked module state).
    """

    def test_api_key_set_to_settings_value_before_send(self, project_root, monkeypatch):
        """Direct unit test on email_client. Asserts resend.api_key matches
        settings.resend_api_key at the moment resend.Emails.send is invoked.
        """
        import resend

        from web_service import email_client
        from web_service.config import load_settings

        monkeypatch.setenv("WEB_RESEND_API_KEY", "re_test_unit4_unique_value")

        settings = load_settings()
        assert settings.resend_api_key == "re_test_unit4_unique_value"

        captured_api_key: list[str | None] = []

        def _capture(payload):
            captured_api_key.append(resend.api_key)
            return {"id": "test_msg_id"}

        with patch("resend.Emails.send", side_effect=_capture):
            result = email_client.send_with_attachment(
                from_addr=settings.send_to_kindle_from,
                to=["test@kindle.com"],
                subject="t",
                html="<p>t</p>",
                attachments=[{"filename": "x.epub", "content": b"PK\x03\x04"}],
            )

        assert result.message_id == "test_msg_id"
        assert captured_api_key == ["re_test_unit4_unique_value"], (
            f"resend.api_key was not set to settings.resend_api_key before "
            f"Emails.send. Captured: {captured_api_key!r}"
        )


# ---------------------------------------------------------------------------
# F4 — KindleSendError must suppress implicit exception chaining
# ---------------------------------------------------------------------------


class TestSendToKindleChainSuppression:
    """Python's implicit exception chaining (__context__) preserves the
    original exception even if you don't use `from exc`. Only `from None`
    suppresses it. Without suppression, a log handler that prints the chain
    will surface the original Resend error — which can contain response
    body content that includes the recipient.
    """

    def test_kindle_send_error_has_no_context_or_cause(self, project_root):
        """Force resend.Emails.send to raise; assert the wrapper's
        KindleSendError has both __context__ and __cause__ set to None.
        """
        from web_service import email_client

        # Patch the SDK call to raise a representative error class.
        class _SimulatedResendError(Exception):
            def __init__(self):
                # The error message intentionally contains a recipient-like
                # substring to prove the chain leak vector.
                super().__init__("Resend response: 422 {'to': 'leak@kindle.com'}")

        with patch("resend.Emails.send", side_effect=_SimulatedResendError()):
            try:
                email_client.send_with_attachment(
                    from_addr="kindle@send.example.com",
                    to=["someone@kindle.com"],
                    subject="t",
                    html="<p>t</p>",
                    attachments=[{"filename": "x.epub", "content": b"PK\x03\x04"}],
                )
            except email_client.KindleSendError as err:
                assert err.__context__ is None, (
                    "KindleSendError.__context__ leaks the original exception. "
                    "Use `raise KindleSendError(...) from None` to suppress the "
                    "implicit chain. Got context: "
                    f"{err.__context__!r}"
                )
                assert err.__cause__ is None, (
                    "KindleSendError.__cause__ leaks the original exception. "
                    "Got cause: " + repr(err.__cause__)
                )
            else:
                pytest.fail("Wrapper should have raised KindleSendError")


# ---------------------------------------------------------------------------
# F5 — kindle_delivery_status must become 'accepted_by_resend' on send success
# ---------------------------------------------------------------------------


class TestSendToKindleSetsDeliveryStatus:
    """Unit 10's webhook contract expects the immediate post-send delivery
    state to be 'accepted_by_resend', which the webhook then transitions to
    delivered/bounced/failed/delayed.
    """

    def test_successful_send_persists_accepted_by_resend(self, client):
        import sqlite3

        from web_service import email_client

        tc, db_path, settings = client
        parent_id = _seed_epub_parent(settings)
        recipient = "joe-status-canary@kindle.com"

        with patch.object(
            email_client,
            "send_with_attachment",
            return_value=email_client.SendResult(message_id="resend_test_msg"),
        ):
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": recipient},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT resend_message_id, kindle_delivery_status FROM jobs WHERE job_id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "resend_test_msg"
        assert row[1] == "accepted_by_resend", (
            f"Expected kindle_delivery_status='accepted_by_resend' after the "
            f"winning send. Got: {row[1]!r}. Unit 10's webhook expects this "
            f"as the baseline state to transition from."
        )


# ---------------------------------------------------------------------------
# F6 — Disabled deploys must boot even when Resend env vars are absent
# ---------------------------------------------------------------------------


class TestSendToKindleDisabledStartupTolerance:
    """Production deploys that ship this PR with WEB_SEND_TO_KINDLE_ENABLED
    unset (default false) must not be blocked from booting just because
    the Resend env vars haven't been configured yet. _require_env on those
    fields should only fire when the flag is enabled.
    """

    def test_flag_false_with_missing_resend_env_vars_loads_settings(
        self, project_root, monkeypatch
    ):
        """Unset the flag and BOTH Resend env vars; load_settings() must succeed."""
        from web_service.config import load_settings

        monkeypatch.delenv("WEB_SEND_TO_KINDLE_ENABLED", raising=False)
        monkeypatch.delenv("WEB_SEND_TO_KINDLE_FROM", raising=False)
        monkeypatch.delenv("WEB_RESEND_API_KEY", raising=False)

        # load_settings must not raise.
        settings = load_settings()
        assert settings.send_to_kindle_enabled is False
        # Empty placeholders are fine — the route returns 503 SERVICE_DISABLED
        # before reading these fields. They're only required when the flag flips.
        assert settings.send_to_kindle_from == ""
        assert settings.resend_api_key == ""

    def test_flag_true_with_missing_resend_env_vars_raises(
        self, project_root, monkeypatch
    ):
        """When the flag IS enabled, the env vars are still load-bearing."""
        from web_service.config import ConfigurationError, load_settings

        monkeypatch.setenv("WEB_SEND_TO_KINDLE_ENABLED", "true")
        monkeypatch.delenv("WEB_SEND_TO_KINDLE_FROM", raising=False)
        monkeypatch.delenv("WEB_RESEND_API_KEY", raising=False)

        with pytest.raises(ConfigurationError):
            load_settings()


# ---------------------------------------------------------------------------
# F7 — Resend attachment content must be Base64 string, not raw bytes
# ---------------------------------------------------------------------------


class TestSendToKindleAttachmentEncoding:
    """Resend's official docs require Base64-encoded content for local
    attachments; the 40 MB limit is measured after encoding. The Python SDK
    does NOT auto-encode raw bytes. The wrapper MUST encode before calling
    Emails.send.
    """

    def test_attachment_content_is_base64_string(self, project_root):
        """Direct unit test on email_client. Capture the payload that gets
        passed to resend.Emails.send and assert the attachment's content
        is a str whose base64 decode equals the original bytes.
        """
        import base64

        from web_service import email_client

        captured: dict = {}

        def _capture(payload):
            captured.update(payload)
            return {"id": "test_msg_id"}

        original_content = b"PK\x03\x04" + b"\x00" * 200

        with patch("resend.Emails.send", side_effect=_capture):
            email_client.send_with_attachment(
                from_addr="kindle@send.example.com",
                to=["test@kindle.com"],
                subject="t",
                html="<p>t</p>",
                attachments=[
                    {"filename": "book.epub", "content": original_content},
                ],
            )

        attachments = captured.get("attachments", [])
        assert len(attachments) == 1
        att = attachments[0]
        assert att["filename"] == "book.epub", "filename must round-trip unchanged"

        content = att["content"]
        assert isinstance(content, str), (
            f"Resend expects a base64 string for local attachments, not "
            f"{type(content).__name__}. Raw bytes get rejected or corrupted."
        )
        # The base64 decode must reproduce the original bytes exactly.
        assert base64.b64decode(content) == original_content, (
            "base64.b64decode(attachment.content) must equal the original "
            "bytes the route passed in"
        )


# ---------------------------------------------------------------------------
# Unit 4 scenario suite — validation scenarios (R3.1, R3.3, R3.4, P1-4)
#
# Each block below targets one of the pre-enable items the plan lists at
# Unit 4's "What is NOT yet implemented and gates flipping the flag" status
# banner (plan lines 382-393). Landing these (plus the existing PR #142
# tests) is what makes WEB_SEND_TO_KINDLE_ENABLED=true safe to flip.
#
# All tests run with the flag enabled (conftest default = true).
# email_client.send_with_attachment is mocked so no real Resend calls fire.
# ---------------------------------------------------------------------------


def _stub_send_success():
    """Return a patch context that makes the wrapper succeed without calling Resend."""
    from web_service import email_client
    return patch.object(
        email_client,
        "send_with_attachment",
        return_value=email_client.SendResult(message_id="test_msg_id"),
    )


class TestSendToKindleRecipientValidation:
    """R3.1 (strict @kindle.com / @free.kindle.com domain allowlist) +
    R3.4 (display-name + plus-aliasing rejection)."""

    def test_non_kindle_domain_returns_422(self, client):
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "evil@example.com"},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_RECIPIENT_DOMAIN"

    def test_wildcard_suffix_attempt_rejected(self, client):
        """`@evil-kindle.com` ends with 'kindle.com' but is NOT kindle.com.
        Strict equality must reject — no endswith() shortcuts.
        """
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "evil@evil-kindle.com"},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_RECIPIENT_DOMAIN"

    def test_free_kindle_subdomain_accepted(self, client):
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "joe@free.kindle.com"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "sent"

    def test_display_name_form_rejected(self, client):
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": '"User Name" <u@kindle.com>'},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_RECIPIENT_FORM"

    def test_plus_aliasing_rejected(self, client):
        """Amazon does not honor plus-aliased Kindle addresses; reject early."""
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "user+tag@kindle.com"},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_RECIPIENT_FORM"

    def test_missing_at_rejected(self, client):
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "just-a-name"},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_RECIPIENT_FORM"


class TestSendToKindleFormatAllowlist:
    """R3.3 format portion: Wave 1 only accepts EPUB; defense-in-depth
    against a frontend that forgets to gate MOBI/KFX rows.
    """

    def test_mobi_output_rejected(self, client, tmp_path):
        import web_service.job_store as js

        tc, _, settings = client
        # Build a parent whose output_fmt is mobi.
        parent_id = js.new_job_id()
        parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
        parent_temp.mkdir(parents=True, exist_ok=True)
        src = parent_temp / "input.pdf"
        src.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)
        out = parent_temp / "output.mobi"
        out.write_bytes(b"MOBI" + b"\x00" * 200)
        js.create_job(
            job_id=parent_id, tier="free", input_fmt="pdf", output_fmt="mobi",
            temp_dir=str(parent_temp), input_path=str(src),
        )
        js.set_done(parent_id, str(out), out.stat().st_size)

        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "u@kindle.com"},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "FORMAT_NOT_KINDLE_ELIGIBLE"

    def test_kfx_output_rejected(self, client, tmp_path):
        import web_service.job_store as js

        tc, _, settings = client
        parent_id = js.new_job_id()
        parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
        parent_temp.mkdir(parents=True, exist_ok=True)
        src = parent_temp / "input.pdf"
        src.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)
        out = parent_temp / "output.kfx"
        out.write_bytes(b"KFX" + b"\x00" * 200)
        js.create_job(
            job_id=parent_id, tier="premium", input_fmt="pdf", output_fmt="kfx",
            temp_dir=str(parent_temp), input_path=str(src),
        )
        js.set_done(parent_id, str(out), out.stat().st_size)

        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "u@kindle.com"},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "FORMAT_NOT_KINDLE_ELIGIBLE"


class TestSendToKindleSizeCap:
    """R3.3 size portion: 30 MB raw cap (measured pre-Base64 since the
    encoding is internal to the wrapper)."""

    def test_30mb_boundary_accepted(self, client):
        tc, _, settings = client
        # Exactly 30 MiB
        thirty_mb = 30 * 1024 * 1024
        parent_id = _seed_epub_parent(settings, output_bytes=b"\x00" * thirty_mb)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "u@kindle.com"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "sent"

    def test_over_30mb_rejected(self, client):
        tc, _, settings = client
        # 30 MB + 1 byte
        too_big = (30 * 1024 * 1024) + 1
        parent_id = _seed_epub_parent(settings, output_bytes=b"\x00" * too_big)
        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "u@kindle.com"},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "OUTPUT_TOO_LARGE_FOR_KINDLE"


class TestSendToKindleJobValidation:
    def test_unknown_job_returns_404(self, client):
        tc, _, _ = client
        with _stub_send_success():
            resp = tc.post(
                "/send-to-kindle/00000000-0000-0000-0000-000000000000",
                data={"recipient": "u@kindle.com"},
            )
        assert resp.status_code == 404

    def test_output_missing_returns_410(self, client):
        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)
        # Remove the output file mid-flight (simulating TTL sweep cleanup).
        import web_service.job_store as js
        job = js.get_job(parent_id)
        Path(job["output_path"]).unlink()

        with _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "u@kindle.com"},
            )
        assert resp.status_code == 410


class TestSendToKindleOutputPathBoundary:
    """P1-4: even with a valid done job, the route MUST resolve output_path
    and confirm it lives inside settings.temp_dir. A corrupted output_path
    pointing at /etc/web_service.env or similar would otherwise let Resend
    exfiltrate secrets via the attachment.
    """

    def test_output_path_outside_temp_dir_rejected_500(self, client, tmp_path):
        import sqlite3

        from web_service import recovery_events_store

        tc, db_path, settings = client
        parent_id = _seed_epub_parent(settings)

        # Forge a malicious output_path pointing outside settings.temp_dir.
        # Use tmp_path (pytest's per-test dir) which is OUTSIDE settings.temp_dir.
        malicious_target = tmp_path / "OUTSIDE_TEMP_DIR.epub"
        malicious_target.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE jobs SET output_path = ? WHERE job_id = ?",
                (str(malicious_target), parent_id),
            )
            conn.commit()
        finally:
            conn.close()

        # Capture telemetry events so we can assert the invariant fires.
        captured_events: list[tuple[str, dict | None]] = []
        original_log_event = recovery_events_store.log_event

        def _capture_log_event(event_type, details=None, db_path=None):
            captured_events.append((event_type, details))
            return original_log_event(event_type, details=details, db_path=db_path)

        with patch.object(recovery_events_store, "log_event", side_effect=_capture_log_event), \
             _stub_send_success():
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "u@kindle.com"},
            )

        assert resp.status_code == 500, (
            f"P1-4 invariant violation must reject with 500. Got {resp.status_code}: {resp.text}"
        )
        # The kindle_send_invariant_violation telemetry MUST fire so the
        # ops team can see the integrity check tripping.
        event_types = [e[0] for e in captured_events]
        assert "kindle_send_invariant_violation" in event_types, (
            f"Expected kindle_send_invariant_violation in telemetry, got: {event_types}"
        )


class TestSendToKindleResendErrorMapping:
    """Resend SDK failures must map to 502 from our endpoint and leave the
    idempotency claim row clean so the user can retry immediately.
    """

    def test_resend_failure_returns_502_and_clears_claim(self, client):
        import sqlite3

        from web_service import email_client

        tc, db_path, settings = client
        parent_id = _seed_epub_parent(settings)
        recipient = "joe-retry-after-fail@kindle.com"

        # Force the wrapper to raise; route catches as 502 and deletes claim.
        with patch.object(
            email_client,
            "send_with_attachment",
            side_effect=email_client.KindleSendError("RESEND_EXCEPTION"),
        ):
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": recipient},
            )
        assert resp.status_code == 502

        # Claim row must be DELETED so a retry would not see "already_sent".
        import hashlib
        recipient_hash = hashlib.sha256(recipient.encode("utf-8")).digest()
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT claim_state FROM kindle_send_idempotency "
                "WHERE job_id = ? AND recipient_hash = ?",
                (parent_id, recipient_hash),
            ).fetchone()
        finally:
            conn.close()
        assert row is None, (
            "Claim row must be deleted after Resend failure so the user can "
            f"retry immediately. Got row: {row!r}"
        )


class TestSendToKindleMultiRecipientIdempotency:
    """Different recipients for the same job within the 60s window must
    both reach Resend — the idempotency key is (job_id, recipient_hash),
    not just job_id. Lets a user send to multiple Kindles without retry-
    block friction.
    """

    def test_different_recipients_both_hit_resend(self, client):
        from web_service import email_client

        tc, _, settings = client
        parent_id = _seed_epub_parent(settings)

        send_calls: list[str] = []

        def _record_send(*, from_addr, to, subject, html, attachments):
            send_calls.append(to[0])
            return email_client.SendResult(message_id=f"msg_{len(send_calls)}")

        with patch.object(email_client, "send_with_attachment", side_effect=_record_send):
            r1 = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "first@kindle.com"},
            )
            r2 = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "second@kindle.com"},
            )

        assert r1.status_code == 200 and r1.json()["status"] == "sent"
        assert r2.status_code == 200 and r2.json()["status"] == "sent"
        assert sorted(send_calls) == ["first@kindle.com", "second@kindle.com"], (
            f"Both recipients should hit Resend. Got: {send_calls}"
        )
