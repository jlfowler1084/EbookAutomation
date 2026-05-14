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
