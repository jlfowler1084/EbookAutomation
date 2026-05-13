"""POST /convert — validate, persist, and enqueue a conversion job."""

from __future__ import annotations

import asyncio
import logging
import sqlite3

from fastapi import APIRouter, Form, HTTPException, UploadFile

from web_service import circuit_breaker, job_queue, job_store, token_store, token_validation, validation
from web_service.config import get_settings
from web_service.job_queue import billing_executor
from web_service.job_store import new_job_id

log = logging.getLogger(__name__)
router = APIRouter()


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
    consumed atomically before the job is created — no refund on conversion
    failure (by design, documented in Phase 2 plan).

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
        except sqlite3.OperationalError:
            circuit_breaker.db_call_failed()
            raise HTTPException(
                status_code=503,
                detail={"error": "Database temporarily unavailable", "code": "DB_UNAVAILABLE"},
            )
    # tier == "free" path: token field silently ignored

    job_id = new_job_id()
    temp_dir = settings.temp_dir / f"job_{job_id}"
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
    )

    asyncio.create_task(job_queue.dispatch_job(job_id))
    log.info("Queued job %s (%s → %s, tier=%s)", job_id, result.detected_fmt, output_format, tier)

    return {"job_id": job_id}
