"""POST /convert — validate, persist, and enqueue a conversion job."""

from __future__ import annotations

import asyncio
import logging
import sqlite3

from fastapi import APIRouter, Form, HTTPException, UploadFile

from web_service import circuit_breaker, job_queue, job_store, recovery_events_store, token_store, token_validation, validation
from web_service.config import get_settings
from web_service.crypto import compute_token_hash
from web_service.job_queue import billing_executor
from web_service.job_store import new_job_id

log = logging.getLogger(__name__)
router = APIRouter()


async def _refund_after_setup_failure(token_hash_hex: str, job_id: str) -> None:
    """Refund a just-consumed premium token when job setup fails before dispatch.

    Best-effort: errors are logged, never propagated — the caller already raises
    a 500 to the client. Mirrors job_queue._maybe_refund_failed_job's shape.
    """
    loop = asyncio.get_running_loop()
    try:
        token_hash_bytes = bytes.fromhex(token_hash_hex)
    except ValueError:
        log.warning("Cannot refund setup failure for %s: token_hash not hex", job_id)
        return
    if billing_executor is None:
        log.warning("Cannot refund setup failure for %s: billing_executor not initialised", job_id)
        return
    try:
        refund = await loop.run_in_executor(
            billing_executor,
            token_store.refund_token,
            token_hash_bytes,
            job_id,
            "convert_setup_failed",
        )
    except Exception:
        log.exception("Refund after setup failure raised for %s", job_id)
        return
    try:
        recovery_events_store.log_event(
            "premium_refund_applied",
            details={
                "job_id": job_id,
                "reason": "convert_setup_failed",
                "refunded": refund.refunded,
                "ledgered": refund.ledgered,
                "refund_id": refund.refund_id,
            },
        )
    except Exception:
        log.exception("Telemetry log_event failed for setup-failure refund %s", job_id)


@router.post("/convert", status_code=202)
async def convert_file(
    file: UploadFile,
    output_format: str = Form("epub"),
    tier: str = Form("free"),
    token: str | None = Form(default=None),
) -> dict:
    """Accept an uploaded ebook and enqueue a conversion job.

    Returns 202 with a job_id immediately — the caller polls /status/{job_id}.

    For tier=premium, a valid single-use token is required. The token is
    consumed atomically before the job is created. If job setup or the
    conversion later fails, the token is refunded (reverse-consumed) — see
    _refund_after_setup_failure below and job_queue._maybe_refund_failed_job.

    For tier=free, the token field is silently ignored.
    """
    settings = get_settings()

    file_bytes = await file.read()
    file_size = len(file_bytes)

    result = validation.validate_upload(
        header=file_bytes[:262],
        file_size=file_size,
        output_format=output_format,
        tier=tier,
        settings=settings,
        filename=file.filename or "",
    )
    if not result.ok:
        raise HTTPException(
            status_code=result.error.http_status,
            detail={"error": result.error.message, "code": result.error.code},
        )

    token_hash_hex: str | None = None

    # Phase 2 (Unit 6): token validation for premium tier
    if tier == "premium":
        if not token:
            raise HTTPException(
                status_code=422,
                detail={"error": "Token required for premium tier", "code": "MISSING_TOKEN"},
            )
        # Format check first (fast fail, no DB hit)
        format_result = token_validation.validate_token_format(token)
        if not format_result.ok:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": format_result.error.message,
                    "code": format_result.error.code.value,
                },
            )
        # Consume atomically (with circuit breaker check)
        if circuit_breaker.circuit_is_open():
            raise HTTPException(
                status_code=503,
                detail={"error": "Service temporarily degraded, retry", "code": "DB_UNAVAILABLE"},
            )
        loop = asyncio.get_event_loop()
        try:
            consume_result = await loop.run_in_executor(
                billing_executor,
                token_store.validate_and_consume,
                token,
            )
            if not consume_result.ok:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": consume_result.error.message,
                        "code": consume_result.error.code.value,
                    },
                )
            circuit_breaker.db_call_succeeded()
            token_hash_hex = compute_token_hash(token).hex()
        except sqlite3.OperationalError:
            circuit_breaker.db_call_failed()
            raise HTTPException(
                status_code=503,
                detail={"error": "Database temporarily unavailable", "code": "DB_UNAVAILABLE"},
            )
    # tier == "free" path: token field silently ignored

    job_id = new_job_id()
    temp_dir = settings.temp_dir / f"job_{job_id}"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        input_path = temp_dir / f"input.{result.detected_fmt}"
        input_path.write_bytes(file_bytes)
        job_store.create_job(
            job_id=job_id,
            tier=tier,
            input_fmt=result.detected_fmt,
            output_fmt=output_format,
            temp_dir=str(temp_dir),
            input_path=str(input_path),
            original_filename=file.filename or None,
            token_hash_hex=token_hash_hex,
        )
    except Exception:
        log.exception("Job setup failed after token consume for job %s", job_id)
        if token_hash_hex:
            await _refund_after_setup_failure(token_hash_hex, job_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Could not start conversion; your credit was not used.",
                "code": "JOB_SETUP_FAILED",
            },
        )

    asyncio.create_task(job_queue.dispatch_job(job_id))
    log.info("Queued job %s (%s → %s, tier=%s)", job_id, result.detected_fmt, output_format, tier)

    return {"job_id": job_id}
