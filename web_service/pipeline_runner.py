"""Pipeline subprocess runner for web service conversion jobs.

Wraps both conversion tiers as controlled subprocess calls:
  - Free tier:    ebook-convert <input> <output.fmt>  (direct Calibre pass-through)
  - Premium tier: python tools/pdf_to_balabolka.py --cli ...  (full smart pipeline)

Key design constraints (from institutional learnings):
  - shell=False on all calls: prevents shell injection from user-supplied filenames
  - Capture both stdout AND stderr: Calibre writes errors to stdout (EB-142)
  - Verify exit==0 AND file_exists AND size>0: Calibre can silently emit 0-byte output (SCRUM-290)
  - KFX filename mismatch recovery: scan dir for newest .kfx if expected path missing
  - Subprocess isolation: a pipeline crash cannot take down the FastAPI server
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import TimeoutExpired

from web_service.config import Settings, get_settings

log = logging.getLogger(__name__)

# Tiered timeout by input file size (departure from R4f flat 120s — see plan Open Questions)
_TIMEOUT_TIERS: list[tuple[int, int]] = [
    (10 * 1024 * 1024, 120),    # < 10 MB  → 120 s
    (50 * 1024 * 1024, 300),    # < 50 MB  → 300 s
    (100 * 1024 * 1024, 600),   # < 100 MB → 600 s
]
_TIMEOUT_DEFAULT = 600


@dataclass(frozen=True)
class RunResult:
    success: bool
    output_path: str = ""
    output_size: int = 0
    error_message: str = ""


def _timeout_for_size(file_size: int) -> int:
    for threshold, seconds in _TIMEOUT_TIERS:
        if file_size < threshold:
            return seconds
    return _TIMEOUT_DEFAULT


def _extract_calibre_error(stdout: str, stderr: str, exit_code: int) -> str:
    """Return a human-readable error from Calibre output.

    Calibre writes its error messages to stdout, not stderr (EB-142 lesson).
    We scan stdout for the last non-empty line as the primary error indicator.
    """
    for text in (stdout, stderr):
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        if lines:
            return lines[-1]
    return f"Calibre exited with code {exit_code}"


def _find_newest_kfx(directory: Path, after_timestamp: float) -> Path | None:
    """Scan a directory for the newest .kfx file created after a reference time.

    Recovers from KFX filename mismatch: the KFX Output plugin may write a
    different filename than the one ebook-convert was given (BookSmith plan lesson).
    """
    candidates = [
        p for p in directory.glob("*.kfx")
        if p.stat().st_mtime >= after_timestamp
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _verify_output(expected_path: Path, job_start: float) -> Path | None:
    """Return the actual output path if it passes size checks, or None.

    Also performs KFX mismatch recovery if expected_path is missing.
    """
    if expected_path.exists() and expected_path.stat().st_size > 0:
        return expected_path

    if expected_path.suffix.lower() == ".kfx":
        recovered = _find_newest_kfx(expected_path.parent, job_start)
        if recovered:
            log.warning(
                "KFX filename mismatch: expected %s, recovered %s",
                expected_path.name,
                recovered.name,
            )
            return recovered

    return None


def run_free(
    job_id: str,
    input_path: Path,
    output_format: str,
    temp_dir: Path,
    settings: Settings | None = None,
) -> RunResult:
    """Run a free-tier conversion: direct Calibre ebook-convert pass-through.

    Args:
        job_id: Used only for logging context.
        input_path: Absolute path to the uploaded input file.
        output_format: Target format (epub, mobi).
        temp_dir: Per-job isolated temp directory for output.
        settings: Injected for testing; defaults to get_settings().
    """
    cfg = settings or get_settings()
    output_path = temp_dir / f"output.{output_format}"
    job_start = time.time()
    file_size = input_path.stat().st_size
    timeout = _timeout_for_size(file_size)

    cmd = [
        str(cfg.calibre_path),
        str(input_path),
        str(output_path),
    ]
    log.info("[%s] free-tier cmd: %s (timeout=%ds)", job_id, cmd, timeout)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,   # never True — prevents shell injection from filenames
        )
    except TimeoutExpired:
        log.warning("[%s] Conversion timed out after %ds", job_id, timeout)
        return RunResult(
            success=False,
            error_message=f"Conversion timed out after {timeout} seconds.",
        )
    except OSError as exc:
        log.error("[%s] Failed to launch Calibre: %s", job_id, exc)
        return RunResult(success=False, error_message=f"Calibre could not be launched: {exc}")

    if proc.stdout:
        for line in proc.stdout.splitlines():
            log.debug("[%s] calibre stdout: %s", job_id, line)
    if proc.stderr:
        for line in proc.stderr.splitlines():
            log.debug("[%s] calibre stderr: %s", job_id, line)

    if proc.returncode != 0:
        error = _extract_calibre_error(proc.stdout, proc.stderr, proc.returncode)
        log.warning("[%s] Calibre exited %d: %s", job_id, proc.returncode, error)
        return RunResult(success=False, error_message=error)

    actual_path = _verify_output(output_path, job_start)
    if actual_path is None:
        log.warning("[%s] Calibre exited 0 but output is missing or 0-byte", job_id)
        return RunResult(
            success=False,
            error_message="Conversion produced no output. The file may be DRM-protected or corrupt.",
        )

    return RunResult(
        success=True,
        output_path=str(actual_path),
        output_size=actual_path.stat().st_size,
    )


def run_premium(
    job_id: str,
    input_path: Path,
    output_format: str,
    temp_dir: Path,
    settings: Settings | None = None,
) -> RunResult:
    """Run a premium-tier conversion: full smart pipeline via subprocess CLI.

    Invokes tools/pdf_to_balabolka.py as a subprocess to avoid tkinter import
    on headless Linux (EB-221/BookSmith plan lesson). The subprocess uses the
    existing --cli entry point with JSON output.
    """
    cfg = settings or get_settings()
    output_path = temp_dir / f"output.{output_format}"
    job_start = time.time()
    file_size = input_path.stat().st_size
    timeout = _timeout_for_size(file_size)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # ensure clean UTF-8 output on all platforms

    cmd = [
        str(cfg.python_path),
        str(cfg.pipeline_script),
        "--cli",
        "--input", str(input_path),
        "--output-dir", str(temp_dir),
        "--output-format", output_format,
        # EB-245: selective Gemini OCR remediation. pdf_to_balabolka.py runs
        # score_text_layer_quality(multi_sample=True) and only re-extracts pages
        # in flagged problem regions, so clean text PDFs incur $0. Mutually
        # exclusive with --use-gemini (full transcription) and --use-vision —
        # gate at pdf_to_balabolka.py:13203 is `gemini_remediate and not use_gemini
        # and not use_vision`. Graceful degrade is already wired at
        # pdf_to_balabolka.py:12762-12772 — Gemini failures fall through to
        # standard extraction without killing the conversion.
        "--gemini-remediate",
        "--gemini-cost-limit", str(cfg.premium_gemini_cost_limit_usd),
    ]
    log.info("[%s] premium-tier cmd: %s (timeout=%ds)", job_id, cmd, timeout)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            env=env,
            cwd=str(cfg.project_root),  # settings.json resolves relative to project root
        )
    except TimeoutExpired:
        log.warning("[%s] Premium pipeline timed out after %ds", job_id, timeout)
        return RunResult(
            success=False,
            error_message=f"Conversion timed out after {timeout} seconds.",
        )
    except OSError as exc:
        log.error("[%s] Failed to launch pipeline: %s", job_id, exc)
        return RunResult(success=False, error_message=f"Pipeline could not be launched: {exc}")

    if proc.returncode != 0:
        error = _extract_calibre_error(proc.stdout, proc.stderr, proc.returncode)
        log.warning("[%s] Pipeline exited %d: %s", job_id, proc.returncode, error)
        return RunResult(success=False, error_message=error)

    actual_path = _verify_output(output_path, job_start)
    if actual_path is None:
        return RunResult(
            success=False,
            error_message="Pipeline produced no output file.",
        )

    return RunResult(
        success=True,
        output_path=str(actual_path),
        output_size=actual_path.stat().st_size,
    )
