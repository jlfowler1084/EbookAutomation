"""Async job dispatch queue.

Wraps blocking pipeline calls in a ThreadPoolExecutor, gated by an asyncio
Semaphore(max_concurrent_jobs). A background sweep task expires stale jobs
and cleans their temp directories every 10 minutes.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from web_service import job_store, pipeline_runner
from web_service.config import get_settings

log = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None
_executor: ThreadPoolExecutor | None = None


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
            return

        if result.success:
            job_store.set_done(job_id, result.output_path, result.output_size)
        else:
            job_store.set_failed(job_id, result.error_message)


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


def _cleanup_job(job: dict) -> None:
    temp_dir = job.get("temp_dir")
    if temp_dir:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            log.info("Cleaned up temp dir for expired job %s", job["job_id"])
        except Exception as exc:
            log.warning("Could not clean temp dir %s: %s", temp_dir, exc)
    job_store.set_expired(job["job_id"])
