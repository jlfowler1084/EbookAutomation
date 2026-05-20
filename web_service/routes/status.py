"""GET /status/{job_id} — return current job state.

EB-324 Unit 5 extends the response with four fields the result-page action
cluster gates on:

    expires_at       — epoch seconds; frontend renders the coarse TTL
                       countdown ("about an hour", "less than 10 minutes")
    source_present   — bool; the parent's input file is still on disk, so
                       re-convert can re-use it without a re-upload
    output_present   — bool; the parent's output file is still on disk, so
                       Send-to-Kindle and Download remain available
    children[]       — list of re-convert child jobs (newest last) with
                       their own per-child presence + delivery state

All four fields appear on EVERY status value (done/queued/running/failed/
expired). download_url stays done-only for backward compat. The EB-245 AI
telemetry block continues to appear only when its fields are populated.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from web_service import job_store

router = APIRouter()


def _file_exists(path_str: str | None) -> bool:
    """Cheap disk existence check. Treats empty/None as not present."""
    if not path_str:
        return False
    try:
        return Path(path_str).exists()
    except OSError:
        # Unreadable path (permissions, malformed) — treat as not present.
        return False


def _child_entry(child: dict) -> dict:
    """Build the per-child dict surfaced under parent.children[].

    Shape matches the EB-324 canonical contract (plan line 478-489):
    9 fields covering job_id, format, status, expires_at, presence flags,
    Send-to-Kindle delivery state, and a download_url that appears only
    when the child is done.
    """
    status = child["status"]
    download_url: str | None = None
    if status == job_store.STATUS_DONE:
        download_url = f"/download/{child['job_id']}"
    return {
        "job_id": child["job_id"],
        "format": child["output_fmt"],
        "status": status,
        "expires_at": child["expires_at"],
        "source_present": _file_exists(child.get("input_path")),
        "output_present": _file_exists(child.get("output_path")),
        "kindle_delivery_status": child.get("kindle_delivery_status"),
        "resend_message_id": child.get("resend_message_id"),
        "download_url": download_url,
    }


@router.get("/status/{job_id}")
async def get_status(job_id: str) -> dict:
    """Return the current status of a conversion job.

    Always returns 200 for known jobs regardless of status.
    Returns 404 for unknown job_ids.
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    response: dict = {
        "job_id": job_id,
        "status": job["status"],
        # EB-324 Unit 5 contract fields — present on every status value.
        "expires_at": job["expires_at"],
        "source_present": _file_exists(job.get("input_path")),
        "output_present": _file_exists(job.get("output_path")),
        "children": [
            _child_entry(child)
            for child in job_store.list_children(job_id)
        ],
    }

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
