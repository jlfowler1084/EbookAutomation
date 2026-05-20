"""GET/HEAD /download/{job_id} — serve the converted file.

EB-324 Unit 2: this handler is read-only on the job-store side. The TTL sweep
in web_service/job_queue.py:_cleanup_job is the sole cleanup mechanism — the
output file survives download so the result-page action cluster can offer
Send-to-Kindle and re-convert against it within the retention window.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from web_service import job_store

log = logging.getLogger(__name__)
router = APIRouter()


# EB-274: registered IANA / commonly-accepted MIME types per output format.
# KFX has no registered type so falls back to octet-stream.
_MEDIA_TYPES: dict[str, str] = {
    "epub": "application/epub+zip",
    "mobi": "application/x-mobipocket-ebook",
    "azw":  "application/vnd.amazon.ebook",
    "azw3": "application/vnd.amazon.ebook",
    "kfx":  "application/octet-stream",
}


def _media_type_for(output_fmt: str, output_path: Path) -> str:
    """Pick the most-specific MIME type for the served file.

    Prefer the job record's output_fmt; fall back to the file's extension; then
    application/octet-stream as the safe default.
    """
    fmt = (output_fmt or output_path.suffix.lstrip(".")).lower()
    return _MEDIA_TYPES.get(fmt, "application/octet-stream")


def _download_filename(original: str | None, output_path: Path) -> str:
    """Derive the Content-Disposition filename.

    Uses the user's original upload basename + the output extension when
    available (e.g., 'leafbind-demo.pdf' uploaded as PDF → 'leafbind-demo.epub'
    when converted to EPUB). Falls back to the output file's name for
    pre-EB-274 jobs that have no stored original_filename.
    """
    if original:
        stem = Path(original).stem  # strip whatever extension the upload had
        ext = output_path.suffix    # use the output's actual extension
        if stem and ext:
            return f"{stem}{ext}"
    return output_path.name


# EB-274: api_route(..., methods=["GET", "HEAD"]) lets Starlette serve HEAD
# directly from the same handler — it returns headers only, no body, so
# Lighthouse / link-checkers / browser prefetch all stop getting 405s.
#
# EB-324 Unit 2: download no longer deletes the output file or marks the job
# expired. The TTL sweep in web_service/job_queue.py:_cleanup_job is the sole
# cleanup mechanism — letting the file survive download is required for the
# post-conversion action cluster (Send-to-Kindle and re-convert both run after
# the user has downloaded the EPUB and need the artifacts to still exist on
# disk). The earlier `_cleanup_after_download` background task has been
# removed entirely; `set_expired` is now only invoked by the TTL sweep.
@router.api_route("/download/{job_id}", methods=["GET", "HEAD"])
async def download_file(job_id: str) -> FileResponse:
    """Serve the converted output file. Cleanup is the TTL sweep's responsibility.

    EB-324 Unit 2: this handler no longer schedules a post-download deletion.
    Allowing the file to persist until the TTL sweep is what lets the
    post-conversion action cluster offer Send-to-Kindle / re-convert after the
    user has clicked Download. The job row remains in `status=done` until the
    TTL elapses; at that point the sweep wipes `temp_dir` and the next
    `GET /status/{job_id}` returns `status=expired` with `output_present=false`.
    """
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

    filename = _download_filename(job.get("original_filename"), output_path)
    media_type = _media_type_for(job.get("output_fmt", ""), output_path)

    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
