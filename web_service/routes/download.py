"""GET /download/{job_id} — serve the converted file, then trigger cleanup."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from web_service import job_store

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/download/{job_id}")
async def download_file(job_id: str, background_tasks: BackgroundTasks) -> FileResponse:
    """Serve the converted output file and schedule cleanup after delivery."""
    job = job_store.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job["status"]
    if status == job_store.STATUS_FAILED:
        raise HTTPException(
            status_code=422,
            detail={"error": job.get("error_msg", "Conversion failed")},
        )

    if status == job_store.STATUS_EXPIRED:
        raise HTTPException(status_code=410, detail="File has expired and been deleted")

    if status != job_store.STATUS_DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not yet complete (status: {status})",
        )

    output_path_str = job.get("output_path", "")
    output_path = Path(output_path_str) if output_path_str else None

    if not output_path or not output_path.exists():
        raise HTTPException(status_code=410, detail="Output file has been deleted")

    filename = output_path.name
    background_tasks.add_task(_cleanup_after_download, job_id, str(output_path))

    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _cleanup_after_download(job_id: str, output_path: str) -> None:
    """Delete output file and mark job expired — runs after response is sent."""
    path = Path(output_path)
    if path.exists():
        path.unlink(missing_ok=True)
        log.info("Deleted output file for job %s after download", job_id)
    job_store.set_expired(job_id)
