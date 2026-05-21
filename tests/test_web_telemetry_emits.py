"""Tests for EB-324 Unit 9b — server-side telemetry emit calls.

Covers the server-side half of Unit 9b: the reconvert and send-to-kindle
routes (and the job-queue dispatcher) emit their lifecycle events through
recovery_events_store.log_event. The client-side Plausible emissions land
with Unit 6's frontend components.

Event funnel:
  Re-convert:
    reconvert_attempted   — route, when a child is dispatched
    reconvert_succeeded   — dispatcher, when a CHILD job completes
    reconvert_failed      — dispatcher, when a CHILD job fails
  Send-to-Kindle (all synchronous in the route):
    send_to_kindle_attempted              — on entry (genuine request)
    send_to_kindle_rejected_by_validation — any 422 validation reject
    send_to_kindle_accepted_by_resend     — Resend 2xx
    send_to_kindle_send_error             — Resend 4xx/5xx/exception

Privacy: the recipient address MUST NOT appear in any telemetry details.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Real dispatch_job reference captured at import time (the client fixture
# mocks the module attribute — see test_web_reconvert.py for the rationale).
from web_service.job_queue import dispatch_job as _real_dispatch_job  # noqa: E402


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


def _capture_events(monkeypatch):
    """Patch recovery_events_store.log_event and return the captured list."""
    from web_service import recovery_events_store
    captured: list[tuple[str, dict | None]] = []
    original = recovery_events_store.log_event

    def _capture(event_type, details=None, db_path=None):
        captured.append((event_type, details))
        return original(event_type, details=details, db_path=db_path)

    monkeypatch.setattr(recovery_events_store, "log_event", _capture)
    return captured


def _seed_done_parent(settings) -> str:
    import web_service.job_store as js
    parent_id = js.new_job_id()
    parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
    parent_temp.mkdir(parents=True, exist_ok=True)
    src = parent_temp / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)
    out = parent_temp / "output.epub"
    out.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    js.create_job(
        job_id=parent_id, tier="free", input_fmt="pdf", output_fmt="epub",
        temp_dir=str(parent_temp), input_path=str(src),
    )
    js.set_done(parent_id, str(out), out.stat().st_size)
    return parent_id


# ---------------------------------------------------------------------------
# Re-convert emits
# ---------------------------------------------------------------------------


class TestReconvertTelemetry:
    def test_reconvert_emits_attempted_on_dispatch(self, client, monkeypatch):
        tc, _, settings = client
        parent_id = _seed_done_parent(settings)
        captured = _capture_events(monkeypatch)

        resp = tc.post(f"/reconvert/{parent_id}", data={"output_format": "mobi"})
        assert resp.status_code == 202

        attempted = [e for e in captured if e[0] == "reconvert_attempted"]
        assert len(attempted) == 1, f"Expected one reconvert_attempted, got: {captured}"
        details = attempted[0][1] or {}
        assert details.get("output_format") == "mobi"
        assert details.get("tier") == "free"
        assert details.get("parent_job_id") == parent_id

    @pytest.mark.asyncio
    async def test_dispatch_emits_reconvert_succeeded_for_child(self, client, monkeypatch):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        import web_service.job_store as js
        from web_service import job_queue, pipeline_runner

        tc, db_path, settings = client
        parent_id = _seed_done_parent(settings)

        # Create a child via the route (dispatch is mocked there).
        resp = tc.post(f"/reconvert/{parent_id}", data={"output_format": "mobi"})
        child_id = resp.json()["job_id"]

        captured = _capture_events(monkeypatch)

        sem_exec = ThreadPoolExecutor(max_workers=1)
        try:
            monkeypatch.setattr(job_queue, "_semaphore", asyncio.Semaphore(1))
            monkeypatch.setattr(job_queue, "_executor", sem_exec)
            monkeypatch.setattr(
                job_queue, "_run_job",
                lambda job: pipeline_runner.RunResult(
                    success=True, output_path="/tmp/out.mobi", output_size=123,
                ),
            )
            await _real_dispatch_job(child_id)
        finally:
            sem_exec.shutdown(wait=False)

        assert js.get_job(child_id)["status"] == "done"
        succeeded = [e for e in captured if e[0] == "reconvert_succeeded"]
        assert len(succeeded) == 1, f"Expected reconvert_succeeded, got: {captured}"
        assert succeeded[0][1].get("output_format") == "mobi"

    @pytest.mark.asyncio
    async def test_dispatch_emits_reconvert_failed_for_child(self, client, monkeypatch):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        import web_service.job_store as js
        from web_service import job_queue, pipeline_runner

        tc, db_path, settings = client
        parent_id = _seed_done_parent(settings)
        resp = tc.post(f"/reconvert/{parent_id}", data={"output_format": "mobi"})
        child_id = resp.json()["job_id"]

        captured = _capture_events(monkeypatch)

        sem_exec = ThreadPoolExecutor(max_workers=1)
        bill_exec = ThreadPoolExecutor(max_workers=1)
        try:
            monkeypatch.setattr(job_queue, "_semaphore", asyncio.Semaphore(1))
            monkeypatch.setattr(job_queue, "_executor", sem_exec)
            monkeypatch.setattr(job_queue, "billing_executor", bill_exec)
            monkeypatch.setattr(
                job_queue, "_run_job",
                lambda job: pipeline_runner.RunResult(
                    success=False, error_message="boom",
                ),
            )
            await _real_dispatch_job(child_id)
        finally:
            sem_exec.shutdown(wait=False)
            bill_exec.shutdown(wait=False)

        assert js.get_job(child_id)["status"] == "failed"
        failed = [e for e in captured if e[0] == "reconvert_failed"]
        assert len(failed) == 1, f"Expected reconvert_failed, got: {captured}"

    @pytest.mark.asyncio
    async def test_dispatch_does_not_emit_reconvert_events_for_top_level_upload(
        self, client, monkeypatch
    ):
        """A top-level upload (parent_job_id is None) must NOT emit reconvert_*
        telemetry — those events are re-convert-specific.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        import web_service.job_store as js
        from web_service import job_queue, pipeline_runner

        tc, db_path, settings = client
        # A normal top-level job (no parent_job_id).
        jid = js.new_job_id()
        temp = Path(settings.temp_dir) / f"job_{jid}"
        temp.mkdir(parents=True, exist_ok=True)
        (temp / "input.pdf").write_bytes(b"%PDF-1.4\n")
        js.create_job(
            job_id=jid, tier="free", input_fmt="pdf", output_fmt="epub",
            temp_dir=str(temp), input_path=str(temp / "input.pdf"),
        )

        captured = _capture_events(monkeypatch)
        sem_exec = ThreadPoolExecutor(max_workers=1)
        try:
            monkeypatch.setattr(job_queue, "_semaphore", asyncio.Semaphore(1))
            monkeypatch.setattr(job_queue, "_executor", sem_exec)
            monkeypatch.setattr(
                job_queue, "_run_job",
                lambda job: pipeline_runner.RunResult(
                    success=True, output_path="/tmp/o.epub", output_size=1,
                ),
            )
            await _real_dispatch_job(jid)
        finally:
            sem_exec.shutdown(wait=False)

        reconvert_events = [e for e in captured if e[0].startswith("reconvert_")]
        assert reconvert_events == [], (
            f"Top-level upload must not emit reconvert_* events. Got: {reconvert_events}"
        )


# ---------------------------------------------------------------------------
# Send-to-Kindle emits
# ---------------------------------------------------------------------------


class TestSendToKindleTelemetry:
    def test_emits_attempted_then_accepted_on_success(self, client, monkeypatch):
        from web_service import email_client

        tc, _, settings = client
        parent_id = _seed_done_parent(settings)
        captured = _capture_events(monkeypatch)

        with patch.object(
            email_client, "send_with_attachment",
            return_value=email_client.SendResult(message_id="m1"),
        ):
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "joe@kindle.com"},
            )
        assert resp.status_code == 200

        types = [e[0] for e in captured]
        assert "send_to_kindle_attempted" in types
        assert "send_to_kindle_accepted_by_resend" in types

        # Canonical schema (plan): output_format (NOT output_fmt), tier, and
        # the privacy-safe recipient hash on every send-to-kindle event.
        import hashlib
        expected_hash = hashlib.sha256("joe@kindle.com".encode("utf-8")).hexdigest()
        for event_type in ("send_to_kindle_attempted", "send_to_kindle_accepted_by_resend"):
            details = next(e[1] for e in captured if e[0] == event_type)
            assert details.get("output_format") == "epub", (
                f"{event_type} must use canonical key 'output_format', got: {details}"
            )
            assert details.get("tier") == "free", (
                f"{event_type} must include tier, got: {details}"
            )
            assert details.get("recipient_hash") == expected_hash, (
                f"{event_type} must include sha256(normalized_recipient).hexdigest(); "
                f"got recipient_hash={details.get('recipient_hash')!r}"
            )

    def test_emits_rejected_by_validation_on_bad_domain(self, client, monkeypatch):
        tc, _, settings = client
        parent_id = _seed_done_parent(settings)
        captured = _capture_events(monkeypatch)

        resp = tc.post(
            f"/send-to-kindle/{parent_id}",
            data={"recipient": "evil@example.com"},
        )
        assert resp.status_code == 422

        types = [e[0] for e in captured]
        assert "send_to_kindle_attempted" in types
        assert "send_to_kindle_rejected_by_validation" in types
        # The rejection details should carry the failure code for dashboards.
        rejected = [e for e in captured if e[0] == "send_to_kindle_rejected_by_validation"]
        assert rejected[0][1].get("code") == "INVALID_RECIPIENT_DOMAIN"

    def test_emits_send_error_on_resend_failure(self, client, monkeypatch):
        from web_service import email_client

        tc, _, settings = client
        parent_id = _seed_done_parent(settings)
        captured = _capture_events(monkeypatch)

        with patch.object(
            email_client, "send_with_attachment",
            side_effect=email_client.KindleSendError("RESEND_EXCEPTION"),
        ):
            resp = tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": "joe@kindle.com"},
            )
        assert resp.status_code == 502

        types = [e[0] for e in captured]
        assert "send_to_kindle_attempted" in types
        assert "send_to_kindle_send_error" in types

    def test_no_recipient_in_any_telemetry_details(self, client, monkeypatch):
        """Privacy: the recipient address must never appear in telemetry."""
        from web_service import email_client

        tc, _, settings = client
        parent_id = _seed_done_parent(settings)
        recipient = "leak-canary@kindle.com"
        captured = _capture_events(monkeypatch)

        with patch.object(
            email_client, "send_with_attachment",
            return_value=email_client.SendResult(message_id="m1"),
        ):
            tc.post(
                f"/send-to-kindle/{parent_id}",
                data={"recipient": recipient},
            )

        for event_type, details in captured:
            if details is None:
                continue
            serialized = json.dumps(details, default=str)
            assert "@kindle.com" not in serialized, (
                f"Telemetry event {event_type} leaked recipient: {serialized}"
            )
