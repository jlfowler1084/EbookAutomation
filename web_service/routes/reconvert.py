"""POST /reconvert/{parent_job_id} — re-convert a parent's source into another format.

Mirrors web_service/routes/convert.py for token consume + dispatch, but skips
file upload (source is re-used from the parent's temp_dir, copied at dispatch
into the child's own temp_dir per R2.4 — source-copy at dispatch). The child
job is linked back to the parent via parent_job_id so the result page can
render an action cluster of related jobs.

Operation order — load-bearing for atomicity:

    1. Cheap validation: parent state, format, premium-token format check,
       circuit breaker. No filesystem or DB mutation yet.
    2. Stage source on disk: mkdir child_temp + shutil.copy2.
    3. Consume premium token (irreversible). If consume fails, rm-tree the
       child_temp first so a partial run never burns a token without a
       child to refund against.
    4. Persist child row + asyncio.create_task(dispatch_job).

If a premium child later fails inside the pipeline, the consumed token is
refunded by job_queue.dispatch_job's failure path using the token_hash
persisted on the child row (R2.7).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request

from web_service import (
    circuit_breaker,
    job_queue,
    job_store,
    token_store,
    token_validation,
)
from web_service.config import get_settings
from web_service.crypto import compute_token_hash
from web_service.job_store import STATUS_DONE, new_job_id
from web_service.rate_limit import limiter, parent_job_id_key

log = logging.getLogger(__name__)
router = APIRouter()

# Wave-1 reconvert eligibility. Free → mobi, premium → kfx. EPUB is the default
# upload output, so a "convert to epub" reconvert would be a no-op rerun — not
# in scope until telemetry asks for it.
_RECONVERT_FREE_FORMATS = {"mobi"}
_RECONVERT_PREMIUM_FORMATS = {"kfx"}


@router.post("/reconvert/{parent_job_id}", status_code=202)
@limiter.limit("10/minute")
@limiter.limit("5/minute", key_func=parent_job_id_key)
async def reconvert_job(
    request: Request,
    parent_job_id: str,
    output_format: str = Form(...),
    token: str | None = Form(default=None),
) -> dict:
    settings = get_settings()

    parent = job_store.get_job(parent_job_id)
    if parent is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "Parent job not found", "code": "PARENT_NOT_FOUND"},
        )
    if parent["status"] != STATUS_DONE:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Parent job is not in the done state",
                "code": "INVALID_PARENT_STATE",
            },
        )
    parent_input = Path(parent["input_path"])
    if not parent_input.exists():
        raise HTTPException(
            status_code=410,
            detail={
                "error": "Parent source is no longer available — re-upload to convert again",
                "code": "PARENT_SOURCE_EXPIRED",
            },
        )

    out_lower = output_format.lower()
    if out_lower in _RECONVERT_PREMIUM_FORMATS:
        tier = "premium"
    elif out_lower in _RECONVERT_FREE_FORMATS:
        tier = "free"
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Unsupported reconvert output_format: {output_format}",
                "code": "INVALID_OUTPUT_FORMAT",
            },
        )

    # Cheap premium pre-checks before any filesystem or token-burning work.
    if tier == "premium":
        if not token:
            raise HTTPException(
                status_code=422,
                detail={"error": "Token required for premium re-convert", "code": "MISSING_TOKEN"},
            )
        format_result = token_validation.validate_token_format(token)
        if not format_result.ok:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": format_result.error.message,
                    "code": format_result.error.code.value,
                },
            )
        if circuit_breaker.circuit_is_open():
            raise HTTPException(
                status_code=503,
                detail={"error": "Service temporarily degraded, retry", "code": "DB_UNAVAILABLE"},
            )

    # Stage source on disk BEFORE consuming the token. If copy fails we have
    # nothing to clean up beyond an empty child_temp; no token has been burned.
    child_id = new_job_id()
    child_temp = settings.temp_dir / f"job_{child_id}"
    input_fmt = parent["input_fmt"]
    child_input = child_temp / f"input.{input_fmt}"
    try:
        child_temp.mkdir(parents=True, exist_ok=True)
        shutil.copy2(parent_input, child_input)
    except (OSError, shutil.Error) as exc:
        shutil.rmtree(child_temp, ignore_errors=True)
        log.warning(
            "reconvert: source staging failed for parent %s: %s", parent_job_id, exc
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Could not stage source for re-convert; please retry",
                "code": "SOURCE_COPY_FAILED",
            },
        )

    # Consume the premium token only after the source is staged. If consume
    # fails (race against another worker, DB error, etc.), rm-tree the staged
    # source so we don't leak an orphan child_temp.
    token_hash_hex: str | None = None
    if tier == "premium":
        loop = asyncio.get_event_loop()
        try:
            # job_queue.billing_executor is set by init_billing_executor() at
            # startup. Attribute access at call time (not module-level import)
            # so production picks up the dedicated billing pool instead of the
            # event loop's default executor.
            consume_result = await loop.run_in_executor(
                job_queue.billing_executor,
                token_store.validate_and_consume,
                token,
            )
            if not consume_result.ok:
                shutil.rmtree(child_temp, ignore_errors=True)
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": consume_result.error.message,
                        "code": consume_result.error.code.value,
                    },
                )
            circuit_breaker.db_call_succeeded()
        except sqlite3.OperationalError:
            shutil.rmtree(child_temp, ignore_errors=True)
            circuit_breaker.db_call_failed()
            raise HTTPException(
                status_code=503,
                detail={"error": "Database temporarily unavailable", "code": "DB_UNAVAILABLE"},
            )
        token_hash_hex = compute_token_hash(token).hex()

    job_store.create_job(
        job_id=child_id,
        tier=tier,
        input_fmt=input_fmt,
        output_fmt=out_lower,
        temp_dir=str(child_temp),
        input_path=str(child_input),
        original_filename=parent.get("original_filename"),
        parent_job_id=parent_job_id,
        token_hash_hex=token_hash_hex,
    )

    asyncio.create_task(job_queue.dispatch_job(child_id))
    log.info(
        "Queued reconvert child %s (parent=%s, %s -> %s, tier=%s)",
        child_id, parent_job_id, input_fmt, out_lower, tier,
    )

    return {"job_id": child_id}
