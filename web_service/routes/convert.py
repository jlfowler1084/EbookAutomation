"""POST /convert — validate, persist, and enqueue a conversion job."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Form, HTTPException, UploadFile

from web_service import job_queue, job_store, validation
from web_service.config import get_settings
from web_service.job_store import new_job_id

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/convert", status_code=202)
async def convert_file(
    file: UploadFile,
    output_format: str = Form("epub"),
    tier: str = Form("free"),
) -> dict:
    """Accept an uploaded ebook and enqueue a conversion job.

    Returns 202 with a job_id immediately — the caller polls /status/{job_id}.
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
