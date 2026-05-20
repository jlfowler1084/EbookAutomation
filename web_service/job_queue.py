"""Async job dispatch queue.

Wraps blocking pipeline calls in a ThreadPoolExecutor, gated by an asyncio
Semaphore(max_concurrent_jobs). A background sweep task expires stale jobs
and cleans their temp directories every 10 minutes.

Unit 8 sweep tasks:
  - cleanup_expired_tokens_sweep: hourly; purges consumed tokens >30 days past expiry.
  - cleanup_failed_mints_sweep: daily; purges failed_mints records >7 days old.
Both sweep tasks mirror the cleanup_expired_jobs pattern: while True → sleep →
try/except that never lets the sweep crash and stop.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from web_service import job_store, pipeline_runner, recovery_events_store, token_store
from web_service.config import get_settings

log = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None
_executor: ThreadPoolExecutor | None = None

# Unit 3+ addition: dedicated executor for fast Stripe SDK + token store operations.
# Separate from the conversion executor because 30s webhook timeout vs 120s conversion
# timeout is incompatible on a shared pool (Phase 2 plan, Unit 4 reliability deepening).
billing_executor: ThreadPoolExecutor | None = None


def init_billing_executor() -> None:
    """Initialise the billing thread pool. Call once at app startup.

    Kept separate from init_queue() so the billing executor can be started and
    stopped independently (e.g. in tests that don't need the conversion queue).
    """
    global billing_executor
    if billing_executor is None:
        billing_executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="billing"
        )
        log.info("Billing executor initialised (max_workers=4)")


def init_queue() -> None:
    """Initialise the semaphore and thread pool. Call once at app startup."""
    global _semaphore, _executor
    settings = get_settings()
    _semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
    _executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs)
    log.info("Job queue initialised (max_concurrent=%d)", settings.max_concurrent_jobs)


def _run_job(job: dict) -> pipeline_runner.RunResult:
    """Dispatch the job to the appropriate pipeline tier (runs in a thread)."""
    tier = job["tier"]
    input_path = Path(job["input_path"])
    output_format = job["output_fmt"]
    temp_dir = Path(job["temp_dir"])

    if tier == "free":
        return pipeline_runner.run_free(job["job_id"], input_path, output_format, temp_dir)
    return pipeline_runner.run_premium(job["job_id"], input_path, output_format, temp_dir)


async def dispatch_job(job_id: str) -> None:
    """Acquire a concurrency slot, run the pipeline, update job state."""
    if _semaphore is None or _executor is None:
        log.error("Queue not initialised — call init_queue() first")
        job_store.set_failed(job_id, "Internal error: queue not initialised")
        return

    async with _semaphore:
        job = job_store.get_job(job_id)
        if job is None:
            log.error("dispatch_job called for unknown job %s", job_id)
            return

        job_store.set_running(job_id)
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(_executor, _run_job, job)
        except Exception as exc:
            log.exception("Unhandled error in job %s", job_id)
            job_store.set_failed(job_id, str(exc))
            await _maybe_refund_failed_child(job, reason="dispatch_exception")
            return

        if result.success:
            job_store.set_done(
                job_id, result.output_path, result.output_size,
                gemini_cost_usd=result.gemini_cost_usd,
                vqa_score=result.vqa_score,
                vqa_pass=result.vqa_pass,
                vqa_cost_usd=result.vqa_cost_usd,
                vqa_skipped_reason=result.vqa_skipped_reason,
            )
        else:
            job_store.set_failed(job_id, result.error_message)
            await _maybe_refund_failed_child(job, reason="child_job_failed")


async def _maybe_refund_failed_child(job: dict, *, reason: str) -> None:
    """Refund a premium re-convert child's token after the child fails (EB-324 R2.7).

    Strict no-op when token_hash is None — every free conversion failure path
    must remain refund-free, so the guard MUST short-circuit before touching
    the executor.

    Best-effort: any error inside the refund call is logged but never
    propagated; the caller has already set_failed on the job row.
    """
    token_hash_hex = job.get("token_hash")
    if not token_hash_hex:
        return
    if billing_executor is None:
        log.warning(
            "Cannot refund failed child %s: billing_executor not initialised",
            job["job_id"],
        )
        return
    try:
        token_hash_bytes = bytes.fromhex(token_hash_hex)
    except ValueError:
        log.warning(
            "Cannot refund failed child %s: token_hash is not valid hex (%r)",
            job["job_id"],
            token_hash_hex,
        )
        return
    loop = asyncio.get_event_loop()
    try:
        refund = await loop.run_in_executor(
            billing_executor,
            token_store.refund_token,
            token_hash_bytes,
            job["job_id"],
            reason,
        )
    except Exception:
        log.exception(
            "Refund failed inside billing_executor for child %s", job["job_id"]
        )
        return

    try:
        recovery_events_store.log_event(
            "reconvert_refund_applied",
            details={
                "child_job_id": job["job_id"],
                "parent_job_id": job.get("parent_job_id"),
                "reason": reason,
                "refunded": refund.refunded,
                "ledgered": refund.ledgered,
                "refund_id": refund.refund_id,
            },
        )
    except Exception:
        # Telemetry must never block the dispatcher's return path.
        log.exception("Telemetry log_event failed for refund on child %s", job["job_id"])


async def cleanup_expired_jobs() -> None:
    """Background sweep: expire TTL-elapsed jobs and delete their temp dirs."""
    while True:
        await asyncio.sleep(600)
        try:
            expired = job_store.get_expired_jobs()
            for job in expired:
                _cleanup_job(job)
        except Exception:
            log.exception("Error during expired-job cleanup sweep")


async def cleanup_expired_tokens_sweep() -> None:
    """Background sweep: delete consumed tokens >30 days past expiry.

    Runs hourly via billing_executor so blocking SQLite I/O stays off the
    event loop. Never lets an exception stop the sweep — error is logged and
    the loop continues on the next iteration.
    """
    while True:
        await asyncio.sleep(3600)
        try:
            loop = asyncio.get_event_loop()
            deleted = await loop.run_in_executor(
                billing_executor, token_store.cleanup_expired_tokens
            )
            log.info("cleanup_expired_tokens_sweep: deleted %d rows", deleted)
        except Exception:
            log.exception("Error during expired-tokens cleanup sweep")


async def cleanup_failed_mints_sweep() -> None:
    """Background sweep: delete failed_mints records older than 7 days.

    Runs daily via billing_executor so blocking SQLite I/O stays off the
    event loop. Never lets an exception stop the sweep — error is logged and
    the loop continues on the next iteration.
    """
    while True:
        await asyncio.sleep(86400)
        try:
            loop = asyncio.get_event_loop()
            deleted = await loop.run_in_executor(
                billing_executor, token_store.cleanup_failed_mints
            )
            log.info("cleanup_failed_mints_sweep: deleted %d rows", deleted)
        except Exception:
            log.exception("Error during failed-mints cleanup sweep")


def _cleanup_job(job: dict) -> None:
    temp_dir = job.get("temp_dir")
    if temp_dir:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            log.info("Cleaned up temp dir for expired job %s", job["job_id"])
        except Exception as exc:
            log.warning("Could not clean temp dir %s: %s", temp_dir, exc)
    job_store.set_expired(job["job_id"])
