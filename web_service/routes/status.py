"""GET /status/{job_id} — return current job state."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from web_service import job_store

router = APIRouter()


@router.get("/status/{job_id}")
async def get_status(job_id: str) -> dict:
    """Return the current status of a conversion job.

    Always returns 200 for known jobs regardless of status.
    Returns 404 for unknown job_ids.
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    response: dict = {"job_id": job_id, "status": job["status"]}

    if job["status"] == job_store.STATUS_DONE:
        response["download_url"] = f"/download/{job_id}"
        response["output_size"] = job.get("output_size")

    if job["status"] == job_store.STATUS_FAILED:
        response["error"] = job.get("error_msg", "Conversion failed")

    return response
