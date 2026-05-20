"""Tests for Unit 8 cleanup sweep tasks in web_service.job_queue.

Verifies that cleanup_expired_tokens_sweep() and cleanup_failed_mints_sweep()
call the correct token_store functions via the billing_executor, and that the
loop pauses on the correct sleep interval.

Design note: the sweep loops run `asyncio.sleep(3600)` / `asyncio.sleep(86400)`
before the first DB call, so tests mock asyncio.sleep to return immediately and
also mock the token_store functions so they complete without hitting the DB.

The billing_executor module-level is None in tests (init_billing_executor() is
not called in isolation). Tests that verify the function is dispatched patch
billing_executor with a real ThreadPoolExecutor so run_in_executor succeeds.
Tests that only verify sleep intervals or exception handling patch token_store
directly and don't need the executor alive.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from web_service import job_queue


class TestCleanupExpiredTokensSweep:
    """cleanup_expired_tokens_sweep fires cleanup_expired_tokens via billing_executor."""

    @pytest.mark.asyncio
    async def test_calls_token_store_cleanup_on_first_iteration(self, tmp_path):
        """After one sleep cycle the sweep invokes token_store.cleanup_expired_tokens."""
        call_log: list[str] = []

        def fake_cleanup_expired_tokens(db_path=None):
            call_log.append("cleanup_expired_tokens")
            return 5

        # Provide a live executor so run_in_executor succeeds in test context.
        # (billing_executor is None until init_billing_executor() is called in app.)
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            with (
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
                patch.object(job_queue, "billing_executor", executor),
                patch.object(
                    job_queue.token_store,
                    "cleanup_expired_tokens",
                    side_effect=fake_cleanup_expired_tokens,
                ),
            ):
                mock_sleep.side_effect = [None, asyncio.CancelledError()]

                with pytest.raises(asyncio.CancelledError):
                    await job_queue.cleanup_expired_tokens_sweep()
        finally:
            executor.shutdown(wait=False)

        assert "cleanup_expired_tokens" in call_log, (
            "cleanup_expired_tokens was not called during the sweep"
        )

    @pytest.mark.asyncio
    async def test_sleep_interval_is_3600(self):
        """The sweep sleeps for 3600 seconds (hourly) between iterations."""
        sleep_calls: list[float] = []

        async def recording_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 1:
                raise asyncio.CancelledError()

        with (
            patch("asyncio.sleep", side_effect=recording_sleep),
            patch.object(job_queue.token_store, "cleanup_expired_tokens", return_value=0),
        ):
            with pytest.raises(asyncio.CancelledError):
                await job_queue.cleanup_expired_tokens_sweep()

        assert sleep_calls[0] == 3600, (
            f"Expected sleep(3600) but got sleep({sleep_calls[0]})"
        )

    @pytest.mark.asyncio
    async def test_exception_in_cleanup_does_not_stop_loop(self):
        """An exception in cleanup_expired_tokens is caught; the loop continues."""
        iteration_count = [0]

        async def recording_sleep(seconds):
            iteration_count[0] += 1
            if iteration_count[0] >= 2:
                raise asyncio.CancelledError()

        def failing_cleanup(db_path=None):
            raise RuntimeError("DB unavailable")

        with (
            patch("asyncio.sleep", side_effect=recording_sleep),
            patch.object(
                job_queue.token_store,
                "cleanup_expired_tokens",
                side_effect=failing_cleanup,
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await job_queue.cleanup_expired_tokens_sweep()

        assert iteration_count[0] >= 2, (
            "Loop stopped after exception — sweep must continue on error"
        )


class TestCleanupFailedMintsSweep:
    """cleanup_failed_mints_sweep fires cleanup_failed_mints via billing_executor."""

    @pytest.mark.asyncio
    async def test_calls_token_store_cleanup_on_first_iteration(self):
        """After one sleep cycle the sweep invokes token_store.cleanup_failed_mints."""
        call_log: list[str] = []

        def fake_cleanup_failed_mints(db_path=None):
            call_log.append("cleanup_failed_mints")
            return 2

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            with (
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
                patch.object(job_queue, "billing_executor", executor),
                patch.object(
                    job_queue.token_store,
                    "cleanup_failed_mints",
                    side_effect=fake_cleanup_failed_mints,
                ),
            ):
                mock_sleep.side_effect = [None, asyncio.CancelledError()]

                with pytest.raises(asyncio.CancelledError):
                    await job_queue.cleanup_failed_mints_sweep()
        finally:
            executor.shutdown(wait=False)

        assert "cleanup_failed_mints" in call_log, (
            "cleanup_failed_mints was not called during the sweep"
        )

    @pytest.mark.asyncio
    async def test_sleep_interval_is_86400(self):
        """The sweep sleeps for 86400 seconds (daily) between iterations."""
        sleep_calls: list[float] = []

        async def recording_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 1:
                raise asyncio.CancelledError()

        with (
            patch("asyncio.sleep", side_effect=recording_sleep),
            patch.object(job_queue.token_store, "cleanup_failed_mints", return_value=0),
        ):
            with pytest.raises(asyncio.CancelledError):
                await job_queue.cleanup_failed_mints_sweep()

        assert sleep_calls[0] == 86400, (
            f"Expected sleep(86400) but got sleep({sleep_calls[0]})"
        )

    @pytest.mark.asyncio
    async def test_exception_in_cleanup_does_not_stop_loop(self):
        """An exception in cleanup_failed_mints is caught; the loop continues."""
        iteration_count = [0]

        async def recording_sleep(seconds):
            iteration_count[0] += 1
            if iteration_count[0] >= 2:
                raise asyncio.CancelledError()

        def failing_cleanup(db_path=None):
            raise RuntimeError("DB locked")

        with (
            patch("asyncio.sleep", side_effect=recording_sleep),
            patch.object(
                job_queue.token_store,
                "cleanup_failed_mints",
                side_effect=failing_cleanup,
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await job_queue.cleanup_failed_mints_sweep()

        assert iteration_count[0] >= 2, (
            "Loop stopped after exception — sweep must continue on error"
        )


class TestSweepFunctionsExported:
    """Sanity check: both sweep functions are importable from job_queue."""

    def test_cleanup_expired_tokens_sweep_importable(self):
        from web_service.job_queue import cleanup_expired_tokens_sweep

        assert callable(cleanup_expired_tokens_sweep)

    def test_cleanup_failed_mints_sweep_importable(self):
        from web_service.job_queue import cleanup_failed_mints_sweep

        assert callable(cleanup_failed_mints_sweep)


# ---------------------------------------------------------------------------
# EB-324 Unit 3 / R2.5 — parent-TTL elapses while child is running.
#
# This is the load-bearing regression test for the "source-copy at dispatch"
# architectural decision: when /reconvert/{parent_id} creates a child job, it
# copies the parent's source into the child's own temp_dir so the child no
# longer depends on parent disk lifetime. If the parent's TTL elapses and the
# cleanup sweep rm-trees the parent's temp_dir mid-flight, the child must
# still own a working source file in its own temp_dir.
#
# The race is reproduced deterministically: dispatch_job is mocked (no real
# pipeline), so the child sits in queued/running state with its source file
# already on disk. We then directly invoke the same _cleanup_job() routine the
# sweep uses, on the parent dict, and assert: parent's source is gone, child's
# source survives.
# ---------------------------------------------------------------------------


import json as _json
import sys as _sys
from io import BytesIO as _BytesIO
from unittest.mock import patch as _patch


@pytest.fixture()
def _reconvert_project_root(tmp_path, monkeypatch):
    """Minimal config + data dir so load_settings() succeeds. Mirrors test_web_endpoints.py."""
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

    import web_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(_sys, "platform", "linux")
    return tmp_path


@pytest.fixture()
def _reconvert_client(_reconvert_project_root):
    """TestClient with dispatch_job mocked so child jobs sit in queued state."""
    import importlib

    import web_service.job_store as _js
    import web_service.main as _main_mod
    from fastapi.testclient import TestClient as _TestClient
    from unittest.mock import AsyncMock as _AsyncMock

    from web_service.config import load_settings, reset_settings
    reset_settings()

    settings = load_settings()
    _js.init_db(settings.db_path)

    importlib.reload(_main_mod)

    # Mock dispatch on both convert and reconvert paths so neither tries to
    # launch a real pipeline. The reconvert module may not exist yet during RED
    # (route ships in this same unit) — only patch its symbol if the import
    # works, otherwise the convert-side patch already prevents real dispatch.
    import importlib.util as _ilu
    reconvert_module_exists = (
        _ilu.find_spec("web_service.routes.reconvert") is not None
    )

    convert_patch = _patch(
        "web_service.routes.convert.job_queue.dispatch_job", new=_AsyncMock()
    )
    init_queue_patch = _patch("web_service.job_queue.init_queue")
    cleanup_patch = _patch(
        "web_service.job_queue.cleanup_expired_jobs", return_value=_AsyncMock()
    )

    with convert_patch, init_queue_patch, cleanup_patch:
        if reconvert_module_exists:
            with _patch(
                "web_service.routes.reconvert.job_queue.dispatch_job",
                new=_AsyncMock(),
            ):
                with _TestClient(_main_mod.app) as tc:
                    yield tc, settings
        else:
            with _TestClient(_main_mod.app) as tc:
                yield tc, settings

    reset_settings()


class TestReconvertParentTTLRace:
    """EB-324 R2.5 — child survives parent temp_dir cleanup.

    Validates the source-copy-at-dispatch architectural decision: once
    /reconvert/{parent_id} returns 202, the child owns an independent copy of
    the source on disk and is not coupled to the parent's TTL. The cleanup
    sweep rm-treeing the parent's temp_dir does NOT damage the child.
    """

    def test_child_source_survives_parent_temp_dir_cleanup(self, _reconvert_client):
        from pathlib import Path

        import web_service.job_store as js
        from web_service import job_queue
        from web_service.job_store import STATUS_DONE

        tc, settings = _reconvert_client

        # 1) Seed a parent job: status=done, source file on disk in its temp_dir.
        parent_id = js.new_job_id()
        parent_temp = Path(settings.temp_dir) / f"job_{parent_id}"
        parent_temp.mkdir(parents=True, exist_ok=True)
        parent_input = parent_temp / "input.pdf"
        parent_input.write_bytes(b"%PDF-1.4\n" + b"\x00" * 300)

        js.create_job(
            job_id=parent_id,
            tier="free",
            input_fmt="pdf",
            output_fmt="epub",
            temp_dir=str(parent_temp),
            input_path=str(parent_input),
        )
        # Mark done with a fake output file so source_present + output_present both true.
        parent_output = parent_temp / "output.epub"
        parent_output.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        js.set_done(parent_id, str(parent_output), parent_output.stat().st_size)

        # 2) Re-convert: free tier, output=mobi (no token needed).
        resp = tc.post(
            f"/reconvert/{parent_id}",
            data={"output_format": "mobi"},
        )
        assert resp.status_code == 202, (
            f"Expected 202 from /reconvert/{{parent}} (source-copy-at-dispatch), "
            f"got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert "job_id" in body, f"Expected child job_id in response, got: {body}"
        child_id = body["job_id"]
        assert child_id != parent_id, "Child must have a distinct job_id"

        # 3) Inspect the child row: parent_job_id linkage + distinct temp_dir.
        child = js.get_job(child_id)
        assert child is not None, "Child job row not persisted"
        assert child["parent_job_id"] == parent_id, (
            "Child must record parent_job_id for the action-cluster UI"
        )
        child_temp = Path(child["temp_dir"])
        assert child_temp != parent_temp, (
            "Child temp_dir must be distinct from parent — coupling them defeats source-copy"
        )
        child_input = Path(child["input_path"])
        assert child_input.exists(), (
            f"Child input file must exist on disk after /reconvert returns "
            f"(source-copy at dispatch). Expected: {child_input}"
        )
        # Source bytes must match — copy, not move.
        assert child_input.read_bytes() == parent_input.read_bytes(), (
            "Child input bytes must match parent's — the copy must not corrupt content"
        )

        # 4) Simulate the TTL sweep: parent's TTL has elapsed mid-child-run.
        #    Reach directly into _cleanup_job (same call the sweep makes) so the
        #    test is deterministic and doesn't depend on the 10-minute timer.
        parent_dict = js.get_job(parent_id)
        job_queue._cleanup_job(parent_dict)

        # 5) Load-bearing assertions: parent dir gone, child untouched.
        assert not parent_temp.exists(), (
            "Parent temp_dir should be rm-tree'd by the cleanup sweep"
        )
        assert child_temp.exists(), (
            "Child temp_dir must SURVIVE parent cleanup — this is the source-copy "
            "decision validated"
        )
        assert child_input.exists(), (
            "Child input file must SURVIVE parent cleanup — if this fails, the "
            "reconvert endpoint is reusing the parent's source path instead of "
            "copying into the child's own temp_dir"
        )
        # And the child row in the DB is still queryable + still 'queued'/'running'
        # (dispatch_job was mocked).
        child_after = js.get_job(child_id)
        assert child_after is not None, (
            "Child row must still exist in DB after parent cleanup — cleanup must "
            "not cascade to children"
        )
