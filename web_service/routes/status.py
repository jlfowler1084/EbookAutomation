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
        # EB-245: surface AI telemetry only when present. Free-tier rows have
        # zeros/NULLs and we omit them rather than emit misleading "0" fields.
        gemini_cost = job.get("gemini_cost_usd") or 0.0
        vqa_score = job.get("vqa_score")
        vqa_skipped = job.get("vqa_skipped_reason")
        if gemini_cost or vqa_score is not None or vqa_skipped:
            ai: dict = {
                "gemini_cost_usd": round(gemini_cost, 4),
                "vqa_cost_usd": round(job.get("vqa_cost_usd") or 0.0, 4),
            }
            if vqa_score is not None:
                ai["vqa_score"] = vqa_score
                vqa_pass_int = job.get("vqa_pass")
                ai["vqa_pass"] = bool(vqa_pass_int) if vqa_pass_int is not None else None
            if vqa_skipped:
                ai["vqa_skipped_reason"] = vqa_skipped
            response["ai"] = ai

    if job["status"] == job_store.STATUS_FAILED:
        response["error"] = job.get("error_msg", "Conversion failed")

    return response
