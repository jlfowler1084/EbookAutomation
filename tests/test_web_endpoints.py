"""Tests for web service HTTP endpoints — POST /convert, GET /status, GET /download."""

from __future__ import annotations

import json
import sys
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from web_service.config import reset_settings
from web_service.job_store import STATUS_DONE, STATUS_EXPIRED, STATUS_FAILED, STATUS_QUEUED

PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 300


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
    """TestClient backed by a fresh temp DB; dispatch_job is mocked (no real pipeline)."""
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
        with TestClient(main_mod.app) as tc:
            yield tc, settings.db_path


def _seed_job(db_path, status=STATUS_QUEUED, output_file: Path | None = None):
    """Create a job record and return its job_id."""
    import web_service.job_store as js
    jid = js.new_job_id()
    js.create_job(
        job_id=jid,
        tier="free",
        input_fmt="pdf",
        output_fmt="epub",
        temp_dir=str(db_path.parent),
        input_path=str(db_path.parent / "input.pdf"),
        db_path=db_path,
    )
    if status == STATUS_DONE and output_file:
        js.set_done(jid, str(output_file), output_file.stat().st_size, db_path=db_path)
    elif status == STATUS_FAILED:
        js.set_failed(jid, "Pipeline crashed", db_path=db_path)
    elif status == STATUS_EXPIRED:
        js.set_expired(jid, db_path=db_path)
    return jid


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_ok(self, client):
        tc, _ = client
        resp = tc.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        # Phase 2 (EB-45 Unit 1) added ntp_synced — should be True in tests
        # because the NTP check defaults to True when unavailable (Windows/macOS dev hosts).
        assert body["ntp_synced"] is True


# ---------------------------------------------------------------------------
# POST /convert
# ---------------------------------------------------------------------------


class TestConvertEndpoint:
    def test_valid_pdf_returns_202_with_job_id(self, client):
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert len(body["job_id"]) == 36  # UUID4 length

    def test_empty_file_returns_422(self, client):
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free"},
            files={"file": ("book.pdf", BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code == 422

    def test_kfx_on_free_tier_returns_422(self, client):
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "free"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422

    def test_png_disguised_as_pdf_rejected(self, client):
        tc, _ = client
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 300
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free"},
            files={"file": ("notapdf.pdf", BytesIO(png_bytes), "application/pdf")},
        )
        assert resp.status_code == 422

    # -----------------------------------------------------------------------
    # Phase 2 (Unit 6): token validation tests
    # -----------------------------------------------------------------------

    def test_premium_without_token_returns_422_missing_token(self, client):
        """tier=premium with no token → 422 MISSING_TOKEN."""
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "MISSING_TOKEN"

    def test_premium_with_malformed_token_returns_422_malformed(self, client):
        """tier=premium with a token that fails the format regex → 422 MALFORMED."""
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": "not_a_valid_format"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "MALFORMED"

    def test_premium_with_unknown_token_returns_422_invalid_or_expired(self, client):
        """tier=premium with correct-format token not in DB → 422 TOKEN_INVALID_OR_EXPIRED."""
        tc, db_path = client
        import web_service.token_store as ts
        ts.init_db(db_path)

        # Valid format but not stored in DB
        unknown_token = "lb_pk_" + "A" * 43
        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": unknown_token},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "INVALID_OR_EXPIRED"

    def test_premium_with_valid_token_consumes_and_returns_202(self, client):
        """tier=premium with a valid minted token → 202 + job_id; token is consumed."""
        import sqlite3

        import web_service.token_store as ts

        tc, db_path = client
        ts.init_db(db_path)

        # Mint a real token to consume
        mint_result = ts.mint_tokens_if_absent(
            session_id="cs_test_unit6_valid",
            count=1,
            payment_intent_id="pi_test_unit6",
            db_path=db_path,
        )
        assert mint_result.ok
        token = mint_result.tokens[0]

        with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()):
            resp = tc.post(
                "/convert",
                data={"output_format": "kfx", "tier": "premium", "token": token},
                files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body

        # Verify token is now marked used=1 in DB
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT used FROM tokens WHERE pack_id=?",
            ("cs_test_unit6_valid",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 1

    def test_premium_with_already_used_token_returns_422_already_used(self, client):
        """Using the same token twice → second call returns 422 TOKEN_ALREADY_USED."""
        import web_service.token_store as ts

        tc, db_path = client
        ts.init_db(db_path)

        mint_result = ts.mint_tokens_if_absent(
            session_id="cs_test_unit6_double",
            count=1,
            payment_intent_id="pi_test_unit6_double",
            db_path=db_path,
        )
        assert mint_result.ok
        token = mint_result.tokens[0]

        with patch("web_service.routes.convert.job_queue.dispatch_job", new=AsyncMock()):
            resp1 = tc.post(
                "/convert",
                data={"output_format": "kfx", "tier": "premium", "token": token},
                files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
            )
        assert resp1.status_code == 202

        resp2 = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": token},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp2.status_code == 422
        body = resp2.json()
        assert body["detail"]["code"] == "ALREADY_USED"

    def test_premium_with_disputed_token_returns_422_disputed(self, client):
        """Minting then marking disputed → 422 TOKEN_DISPUTED."""
        import web_service.token_store as ts

        tc, db_path = client
        ts.init_db(db_path)

        session_id = "cs_test_unit6_disputed"
        mint_result = ts.mint_tokens_if_absent(
            session_id=session_id,
            count=1,
            payment_intent_id="pi_test_unit6_disputed",
            db_path=db_path,
        )
        assert mint_result.ok
        token = mint_result.tokens[0]

        ts.mark_disputed(session_id, db_path=db_path)

        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": token},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "DISPUTED"

    def test_premium_with_expired_token_returns_422_invalid_or_expired(self, client):
        """Token minted with expires_at in the past → 422 TOKEN_INVALID_OR_EXPIRED."""
        import sqlite3

        import web_service.token_store as ts
        from web_service.crypto import compute_token_hash, get_fernet, mint_token

        tc, db_path = client
        ts.init_db(db_path)

        # Manually insert an expired token
        token_str, token_hash = mint_token()
        f = get_fernet(key_version=1)
        encrypted = f.encrypt(token_str.encode())
        past = int(time.time()) - 100  # 100 seconds ago

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO tokens
               (token_hash, token_encrypted_for_recovery, key_version,
                pack_id, payment_intent_id, created_at, expires_at, used, disputed)
               VALUES (?, ?, 1, ?, ?, ?, ?, 0, 0)""",
            (token_hash, encrypted, "cs_test_unit6_expired", "pi_unit6_expired", past, past),
        )
        conn.commit()
        conn.close()

        resp = tc.post(
            "/convert",
            data={"output_format": "kfx", "tier": "premium", "token": token_str},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["code"] == "INVALID_OR_EXPIRED"

    def test_free_tier_ignores_token_field(self, client):
        """tier=free with any token value → 202 (token field silently ignored)."""
        tc, _ = client
        resp = tc.post(
            "/convert",
            data={"output_format": "epub", "tier": "free", "token": "some_random_token"},
            files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        )
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    def test_circuit_breaker_open_returns_503(self, client):
        """When circuit breaker is open, premium conversion returns 503 DB_UNAVAILABLE."""
        import web_service.circuit_breaker as cb

        tc, db_path = client
        import web_service.token_store as ts
        ts.init_db(db_path)

        # Valid-format token (format check passes before circuit breaker check)
        valid_format_token = "lb_pk_" + "B" * 43

        # Force circuit open
        original_open_until = cb._circuit_open_until
        cb._circuit_open_until = float("inf")
        try:
            resp = tc.post(
                "/convert",
                data={"output_format": "kfx", "tier": "premium", "token": valid_format_token},
                files={"file": ("book.pdf", BytesIO(PDF_BYTES), "application/pdf")},
            )
        finally:
            cb._circuit_open_until = original_open_until

        assert resp.status_code == 503
        body = resp.json()
        assert body["detail"]["code"] == "DB_UNAVAILABLE"


# ---------------------------------------------------------------------------
# GET /status/{job_id}
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    def test_unknown_job_returns_404(self, client):
        tc, _ = client
        resp = tc.get("/status/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_queued_job_returns_queued_status(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_QUEUED)

        resp = tc.get(f"/status/{jid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == STATUS_QUEUED

    def test_done_job_includes_download_url(self, client, tmp_path):
        tc, db_path = client
        output_file = tmp_path / "output.epub"
        output_file.write_bytes(b"epub")
        jid = _seed_job(db_path, STATUS_DONE, output_file)

        resp = tc.get(f"/status/{jid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == STATUS_DONE
        assert "download_url" in body
        assert jid in body["download_url"]

    def test_failed_job_includes_error(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_FAILED)

        resp = tc.get(f"/status/{jid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == STATUS_FAILED
        assert "error" in body


# ---------------------------------------------------------------------------
# EB-324 Unit 5: GET /status extension — expires_at, source_present,
# output_present, children[] surface the state the frontend action cluster
# needs to gate Send-to-Kindle, Re-convert, and the disabled-state copy.
#
# The four new top-level fields land on EVERY status (done/queued/running/
# failed/expired) so the frontend can render the action cluster the same
# way regardless of where the job is in its lifecycle. download_url stays
# done-only for backward compat. Children are independent: a parent can
# be expired while children are still running, and the response preserves
# children[] for the lifetime of the parent row so the UI can render
# history.
# ---------------------------------------------------------------------------


def _seed_done_parent_with_files(tmp_path, db_path) -> tuple[str, Path, Path]:
    """Create a done parent job whose input + output actually exist on disk.

    Returns (job_id, input_path, output_path) so individual tests can rm
    files to flip source_present / output_present.
    """
    import web_service.job_store as js

    parent_id = js.new_job_id()
    parent_temp = tmp_path / f"job_{parent_id}"
    parent_temp.mkdir(parents=True, exist_ok=True)
    input_path = parent_temp / "input.pdf"
    input_path.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)
    output_path = parent_temp / "output.epub"
    output_path.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

    js.create_job(
        job_id=parent_id,
        tier="free",
        input_fmt="pdf",
        output_fmt="epub",
        temp_dir=str(parent_temp),
        input_path=str(input_path),
        db_path=db_path,
    )
    js.set_done(parent_id, str(output_path), output_path.stat().st_size, db_path=db_path)
    return parent_id, input_path, output_path


def _seed_child(parent_id: str, db_path, tmp_path, *, output_fmt: str = "mobi", status: str = STATUS_QUEUED) -> str:
    """Create a re-convert child job with its own temp_dir + source on disk.

    Status defaults to queued; pass STATUS_DONE + an output_file path to mark done.
    """
    import web_service.job_store as js

    child_id = js.new_job_id()
    child_temp = tmp_path / f"job_{child_id}"
    child_temp.mkdir(parents=True, exist_ok=True)
    child_input = child_temp / "input.pdf"
    child_input.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)

    js.create_job(
        job_id=child_id,
        tier="free",
        input_fmt="pdf",
        output_fmt=output_fmt,
        temp_dir=str(child_temp),
        input_path=str(child_input),
        parent_job_id=parent_id,
        db_path=db_path,
    )
    if status == STATUS_DONE:
        child_output = child_temp / f"output.{output_fmt}"
        child_output.write_bytes(b"FAKE OUTPUT" + b"\x00" * 100)
        js.set_done(child_id, str(child_output), child_output.stat().st_size, db_path=db_path)
    return child_id


class TestStatusEndpointEB324Extension:
    """The status response surfaces the EB-324 contract fields the action
    cluster gates on."""

    def test_done_includes_expires_at_source_present_output_present_children(
        self, client, tmp_path,
    ):
        tc, db_path = client
        parent_id, _, _ = _seed_done_parent_with_files(tmp_path, db_path)

        resp = tc.get(f"/status/{parent_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == STATUS_DONE
        assert "expires_at" in body
        assert isinstance(body["expires_at"], int)
        assert body["expires_at"] > 0
        assert body["source_present"] is True
        assert body["output_present"] is True
        assert body["children"] == []

    def test_source_present_false_when_input_file_removed(self, client, tmp_path):
        tc, db_path = client
        parent_id, input_path, _ = _seed_done_parent_with_files(tmp_path, db_path)

        input_path.unlink()

        resp = tc.get(f"/status/{parent_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_present"] is False
        # output is still on disk → still present
        assert body["output_present"] is True

    def test_output_present_false_when_output_file_removed(self, client, tmp_path):
        tc, db_path = client
        parent_id, _, output_path = _seed_done_parent_with_files(tmp_path, db_path)

        output_path.unlink()

        resp = tc.get(f"/status/{parent_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["output_present"] is False
        # source is still on disk → still present
        assert body["source_present"] is True

    def test_children_array_populated_with_full_per_child_shape(self, client, tmp_path):
        """After a reconvert, parent's children[] contains the child with all 9 fields."""
        tc, db_path = client
        parent_id, _, _ = _seed_done_parent_with_files(tmp_path, db_path)
        child_id = _seed_child(parent_id, db_path, tmp_path, output_fmt="mobi")

        resp = tc.get(f"/status/{parent_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["children"]) == 1
        child = body["children"][0]

        # Canonical per-child shape per plan line 478-489 — all 9 fields.
        expected_keys = {
            "job_id",
            "format",
            "status",
            "expires_at",
            "source_present",
            "output_present",
            "kindle_delivery_status",
            "resend_message_id",
            "download_url",
        }
        missing = expected_keys - set(child.keys())
        assert not missing, f"Child entry missing fields: {missing}. Got: {child!r}"

        assert child["job_id"] == child_id
        assert child["format"] == "mobi"
        assert child["status"] == STATUS_QUEUED
        assert isinstance(child["expires_at"], int)
        # Source was copied at dispatch (per Unit 3) → still present.
        assert child["source_present"] is True
        # Output doesn't exist yet for a queued child.
        assert child["output_present"] is False
        # No Send-to-Kindle has been attempted on this child.
        assert child["kindle_delivery_status"] is None
        assert child["resend_message_id"] is None
        # download_url only appears when the child is done.
        assert child["download_url"] is None

    def test_child_download_url_appears_only_when_done(self, client, tmp_path):
        tc, db_path = client
        parent_id, _, _ = _seed_done_parent_with_files(tmp_path, db_path)
        child_id = _seed_child(
            parent_id, db_path, tmp_path,
            output_fmt="mobi", status=STATUS_DONE,
        )

        resp = tc.get(f"/status/{parent_id}")
        body = resp.json()
        child = body["children"][0]
        assert child["status"] == STATUS_DONE
        assert child["download_url"] == f"/download/{child_id}"
        assert child["output_present"] is True

    def test_children_ordered_oldest_first(self, client, tmp_path):
        """list_children returns ORDER BY created_at ASC; status response keeps that order."""
        tc, db_path = client
        parent_id, _, _ = _seed_done_parent_with_files(tmp_path, db_path)
        first_child = _seed_child(parent_id, db_path, tmp_path, output_fmt="mobi")
        # Small sleep so created_at differs.
        import time as _time
        _time.sleep(1.1)
        second_child = _seed_child(parent_id, db_path, tmp_path, output_fmt="kfx")

        resp = tc.get(f"/status/{parent_id}")
        body = resp.json()
        ids = [c["job_id"] for c in body["children"]]
        assert ids == [first_child, second_child], (
            "Children must surface in created_at ascending order so the UI "
            "renders them in the sequence the user dispatched them."
        )

    def test_expired_job_still_surfaces_new_fields(self, client, tmp_path):
        """Expired parents keep returning the four fields so the UI can render
        the disabled-state copy AND any preserved children history.
        """
        tc, db_path = client
        parent_id, input_path, output_path = _seed_done_parent_with_files(
            tmp_path, db_path,
        )
        # Simulate the TTL sweep: file cleanup + status flip.
        import web_service.job_store as js
        input_path.unlink()
        output_path.unlink()
        js.set_expired(parent_id, db_path=db_path)

        resp = tc.get(f"/status/{parent_id}")
        body = resp.json()
        assert body["status"] == STATUS_EXPIRED
        assert "expires_at" in body
        assert body["source_present"] is False
        assert body["output_present"] is False
        assert body["children"] == []

    def test_queued_job_surfaces_new_fields(self, client):
        """Queued jobs (no output_path yet) still return the four fields."""
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_QUEUED)
        resp = tc.get(f"/status/{jid}")
        body = resp.json()
        assert body["status"] == STATUS_QUEUED
        assert "expires_at" in body
        assert "source_present" in body
        assert "output_present" in body
        assert body["children"] == []

    def test_failed_job_surfaces_new_fields_and_error(self, client):
        """Failed jobs keep the new fields AND the existing error field."""
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_FAILED)
        resp = tc.get(f"/status/{jid}")
        body = resp.json()
        assert body["status"] == STATUS_FAILED
        assert "error" in body  # backward compat
        assert "expires_at" in body
        assert "source_present" in body
        assert "output_present" in body
        assert body["children"] == []

    def test_parent_send_to_kindle_state_surfaces_at_top_level(
        self, client, tmp_path,
    ):
        """When a user sends the parent EPUB to Kindle, the parent's
        kindle_delivery_status and resend_message_id MUST appear at the top
        level of the response so the EPUB row can render the delivery state.
        Without this, Unit 10's webhook can update the DB but the UI can never
        see accepted_by_resend / delivered_to_mail_server / bounced / failed /
        delivery_delayed for the parent.
        """
        import web_service.job_store as js

        tc, db_path = client
        parent_id, _, _ = _seed_done_parent_with_files(tmp_path, db_path)

        # Simulate Unit 4's post-send state: resend_message_id + the
        # accepted_by_resend baseline that Unit 10 then transitions from.
        # In production this is one UPDATE inside the route handler; the
        # test reproduces that shape directly to avoid coupling to the
        # send_to_kindle route's other validation.
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE jobs SET resend_message_id = ?, "
                "kindle_delivery_status = ? WHERE job_id = ?",
                ("msg_abc123", "accepted_by_resend", parent_id),
            )
            conn.commit()
        finally:
            conn.close()

        resp = tc.get(f"/status/{parent_id}")
        body = resp.json()
        assert body["kindle_delivery_status"] == "accepted_by_resend"
        assert body["resend_message_id"] == "msg_abc123"

        # Then simulate Unit 10's webhook flipping to one of the terminal
        # states — use the column-canonical "failed" (NOT the telemetry
        # event name "delivery_failed").
        js.update_kindle_delivery_status(parent_id, "failed", db_path=db_path)
        resp2 = tc.get(f"/status/{parent_id}")
        body2 = resp2.json()
        assert body2["kindle_delivery_status"] == "failed", (
            "Canonical column value is 'failed'. 'delivery_failed' is the "
            "telemetry event name, not the kindle_delivery_status value."
        )

    def test_parent_delivery_fields_default_to_null_before_send(
        self, client, tmp_path,
    ):
        """A done job that has not been sent to Kindle returns null for both
        delivery fields — never absent, never the empty string.
        """
        tc, db_path = client
        parent_id, _, _ = _seed_done_parent_with_files(tmp_path, db_path)

        resp = tc.get(f"/status/{parent_id}")
        body = resp.json()
        assert "kindle_delivery_status" in body
        assert "resend_message_id" in body
        assert body["kindle_delivery_status"] is None
        assert body["resend_message_id"] is None

    def test_ai_telemetry_block_preserved_alongside_new_fields(
        self, client, tmp_path,
    ):
        """Regression guard: the EB-245 AI telemetry block at status.py:30-44
        must still appear when its fields are non-null AND alongside the new
        EB-324 fields.
        """
        import web_service.job_store as js

        tc, db_path = client
        parent_id, _, output_path = _seed_done_parent_with_files(tmp_path, db_path)

        # Re-mark done with AI telemetry populated (premium-tier shape).
        js.set_done(
            parent_id,
            str(output_path),
            output_path.stat().st_size,
            gemini_cost_usd=0.15,
            vqa_score=8,
            vqa_pass=True,
            vqa_cost_usd=0.10,
            db_path=db_path,
        )

        resp = tc.get(f"/status/{parent_id}")
        body = resp.json()
        # New EB-324 fields present.
        assert body["source_present"] is True
        assert body["children"] == []
        # EB-245 AI telemetry preserved.
        assert "ai" in body, "AI telemetry block must remain when fields populated"
        assert body["ai"]["gemini_cost_usd"] == 0.15
        assert body["ai"]["vqa_score"] == 8
        assert body["ai"]["vqa_pass"] is True


# ---------------------------------------------------------------------------
# GET /download/{job_id}
# ---------------------------------------------------------------------------


class TestDownloadEndpoint:
    def test_unknown_job_returns_404(self, client):
        tc, _ = client
        resp = tc.get("/download/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_failed_job_returns_422(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_FAILED)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 422

    def test_expired_job_returns_410(self, client):
        tc, db_path = client
        jid = _seed_job(db_path, STATUS_EXPIRED)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 410

    def test_done_job_serves_file(self, client, tmp_path):
        tc, db_path = client
        output_file = tmp_path / "output.epub"
        output_file.write_bytes(b"fake epub content")
        jid = _seed_job(db_path, STATUS_DONE, output_file)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.content == b"fake epub content"

    def test_download_after_file_deleted_returns_410(self, client, tmp_path):
        tc, db_path = client
        # Seed a done job pointing to a non-existent file
        import web_service.job_store as js
        jid = js.new_job_id()
        js.create_job(jid, "free", "pdf", "epub", str(tmp_path), str(tmp_path / "in.pdf"),
                      db_path=db_path)
        js.set_done(jid, str(tmp_path / "gone.epub"), 1024, db_path=db_path)

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 410

    # ------------------------------------------------------------------ EB-324

    def test_eb_324_download_does_not_delete_output_or_expire_job(self, client, tmp_path):
        """EB-324 Unit 2 regression: download must NOT delete output_path or call
        set_expired. The TTL sweep in job_queue.py is the sole cleanup mechanism;
        post-download persistence is what enables the action cluster (Send-to-Kindle
        + re-convert) to work after the user has clicked Download.

        This test would fail against the prior implementation (where
        _cleanup_after_download was a background task that unlink'd the file and
        called job_store.set_expired). Pass criteria after Unit 2 lands:
            - File still exists on disk after the response is fully consumed
            - Job's `status` field is still STATUS_DONE (not STATUS_EXPIRED)
            - A subsequent GET /download/{jid} returns 200 with the same bytes
            - A subsequent GET /status/{jid} returns the done payload
        """
        import web_service.job_store as js

        tc, db_path = client
        output_file = tmp_path / "output.epub"
        output_file.write_bytes(b"epub bytes that survive the download")
        jid = _seed_job(db_path, STATUS_DONE, output_file)

        # First download: consume the response fully so any BackgroundTasks
        # would have a chance to run.
        resp1 = tc.get(f"/download/{jid}")
        assert resp1.status_code == 200
        assert resp1.content == b"epub bytes that survive the download"

        # EB-324 invariant 1: output file still exists.
        assert output_file.exists(), (
            "EB-324 Unit 2 regression: download deleted the output file. The "
            "_cleanup_after_download background task should have been removed."
        )

        # EB-324 invariant 2: job is not marked expired.
        job_row = js.get_job(jid, db_path=db_path)
        assert job_row is not None
        assert job_row["status"] == STATUS_DONE, (
            f"EB-324 Unit 2 regression: download marked job {jid} as "
            f"{job_row['status']!r}. set_expired should not be called on the "
            "post-download path; the TTL sweep handles expiry."
        )

        # EB-324 invariant 3: a second download still works.
        resp2 = tc.get(f"/download/{jid}")
        assert resp2.status_code == 200
        assert resp2.content == b"epub bytes that survive the download"

    def test_eb_324_head_probe_does_not_delete_output(self, client, tmp_path):
        """HEAD requests were already excluded from the prior cleanup; this test
        locks in that they remain side-effect-free after Unit 2. Belt and braces."""
        import web_service.job_store as js

        tc, db_path = client
        output_file = tmp_path / "output.epub"
        output_file.write_bytes(b"x" * 32)
        jid = _seed_job(db_path, STATUS_DONE, output_file)

        resp = tc.head(f"/download/{jid}")
        assert resp.status_code == 200
        assert output_file.exists()
        assert js.get_job(jid, db_path=db_path)["status"] == STATUS_DONE

    # ------------------------------------------------------------------ EB-274

    def _seed_done_job_with_filename(self, db_path, tmp_path, *,
                                     original_filename: str | None,
                                     output_fmt: str = "epub"):
        """Seed a done job with a real on-disk output file and explicit
        original_filename. Used by the EB-274 polish tests below."""
        import web_service.job_store as js
        jid = js.new_job_id()
        output_file = tmp_path / f"{jid}.{output_fmt}"
        output_file.write_bytes(b"fake ebook content")
        js.create_job(
            job_id=jid,
            tier="free",
            input_fmt="pdf",
            output_fmt=output_fmt,
            temp_dir=str(tmp_path),
            input_path=str(tmp_path / "input.pdf"),
            db_path=db_path,
            original_filename=original_filename,
        )
        js.set_done(jid, str(output_file), output_file.stat().st_size, db_path=db_path)
        return jid

    def test_head_returns_200_with_headers_no_body(self, client, tmp_path):
        """HEAD /download/{job_id} returns 200 + same headers as GET, empty body.

        Pre-EB-274 the route was @router.get only, so HEAD probes (Lighthouse,
        link-checkers, browser prefetch) all 405'd. F2-05 in the audit.
        """
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="leafbind-demo.pdf"
        )

        resp = tc.head(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.content == b""  # HEAD has no body
        assert resp.headers["content-type"] == "application/epub+zip"
        assert "content-disposition" in resp.headers
        assert "leafbind-demo.epub" in resp.headers["content-disposition"]

    def test_get_returns_format_specific_media_type(self, client, tmp_path):
        """F2-04: serve application/epub+zip rather than octet-stream for EPUB."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="paper.pdf", output_fmt="epub"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/epub+zip"

    def test_get_kfx_keeps_octet_stream(self, client, tmp_path):
        """KFX has no registered IANA media type — must stay octet-stream."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="paper.pdf", output_fmt="kfx"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"

    def test_content_disposition_uses_original_basename(self, client, tmp_path):
        """F2-04: 'leafbind-demo.pdf' uploaded → 'leafbind-demo.epub' downloaded,
        not the raw UUID-based output filename."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="My Big Book.pdf", output_fmt="epub"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        assert 'filename="My Big Book.epub"' in resp.headers["content-disposition"]

    def test_content_disposition_falls_back_to_output_name_when_no_original(
        self, client, tmp_path
    ):
        """Pre-EB-274 jobs that predate the original_filename column still
        download cleanly using the output file's own basename."""
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename=None, output_fmt="epub"
        )

        resp = tc.get(f"/download/{jid}")
        assert resp.status_code == 200
        # Output filename is "{jid}.epub" — the UUID-based name, but still a
        # well-formed download with the right extension.
        assert resp.headers["content-disposition"].endswith(f'{jid}.epub"')

    def test_head_does_not_trigger_cleanup(self, client, tmp_path):
        """HEAD probes must not delete the output file. Only GET schedules the
        post-delivery cleanup task."""
        import web_service.job_store as js
        tc, db_path = client
        jid = self._seed_done_job_with_filename(
            db_path, tmp_path, original_filename="paper.pdf"
        )
        output_file = Path(js.get_job(jid, db_path=db_path)["output_path"])
        assert output_file.exists()

        resp = tc.head(f"/download/{jid}")
        assert resp.status_code == 200
        # File should still be on disk after a HEAD; job should still be DONE.
        assert output_file.exists()
        assert js.get_job(jid, db_path=db_path)["status"] == STATUS_DONE
