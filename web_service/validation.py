"""File validation for uploaded ebook files.

Checks magic bytes (via filetype library — no libmagic C dependency),
file size against tier limits, and format against the pipeline whitelist.
All validation happens before any disk I/O beyond the initial upload buffer.

filetype supports PDF and EPUB natively. MOBI, AZW, and DJVU are not in its
type registry (limitation documented in the plan). For those formats, we fall
back to extension checking after confirming filetype cannot identify the bytes
as a *different*, known-bad format. This still rejects renamed images/executables.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import filetype

from web_service.config import Settings

log = logging.getLogger(__name__)

# MIME types filetype can positively identify as supported ebook formats.
# Source: tools/extract_tts_text.py SUPPORTED_FORMATS list.
DETECTABLE_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/epub+zip": "epub",
    # Some EPUB files omit the 'mimetype' first-entry requirement; filetype
    # then reports generic ZIP. Accept it — Calibre handles these correctly.
    "application/zip": "epub",
}

# Formats filetype cannot detect from bytes alone; fall back to extension check.
# These still require the file to be unidentifiable as a *known-bad* format.
EXTENSION_FALLBACK_FORMATS: frozenset[str] = frozenset({"mobi", "azw", "azw3", "djvu"})

# All formats accepted as INPUT (from pipeline SUPPORTED_FORMATS)
ALL_SUPPORTED_INPUT_FORMATS: frozenset[str] = frozenset(
    DETECTABLE_MIME_TYPES.values()
) | EXTENSION_FALLBACK_FORMATS

# Formats available per tier as OUTPUT
FREE_OUTPUT_FORMATS: frozenset[str] = frozenset({"epub", "mobi"})
PREMIUM_OUTPUT_FORMATS: frozenset[str] = frozenset({"epub", "mobi", "kfx"})


class ValidationErrorCode(str, Enum):
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_MIME = "INVALID_MIME"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    INVALID_OUTPUT_FORMAT = "INVALID_OUTPUT_FORMAT"


@dataclass(frozen=True)
class ValidationError:
    code: ValidationErrorCode
    message: str
    http_status: int


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    detected_fmt: str = ""
    error: ValidationError | None = None


def validate_upload(
    header: bytes,
    file_size: int,
    output_format: str,
    tier: str,
    settings: Settings,
    filename: str = "",
) -> ValidationResult:
    """Validate an uploaded file against size, type, and format rules.

    Args:
        header: First 262+ bytes of the file (magic number range).
        file_size: Total upload size in bytes.
        output_format: Requested output format (epub, mobi, kfx).
        tier: "free" or "premium".
        settings: Loaded Settings instance for size limits.
        filename: Original filename — used as extension fallback for formats
            that filetype cannot detect (MOBI, AZW, DJVU).
    """
    if file_size == 0:
        return ValidationResult(
            ok=False,
            error=ValidationError(
                code=ValidationErrorCode.EMPTY_FILE,
                message="Uploaded file is empty.",
                http_status=422,
            ),
        )

    size_limit = (
        settings.max_file_size_free if tier == "free"
        else settings.max_file_size_premium
    )
    if file_size > size_limit:
        limit_mb = size_limit // (1024 * 1024)
        return ValidationResult(
            ok=False,
            error=ValidationError(
                code=ValidationErrorCode.FILE_TOO_LARGE,
                message=f"File exceeds the {limit_mb} MB limit for the {tier} tier.",
                http_status=413,
            ),
        )

    kind = filetype.guess(header)

    if kind is not None:
        # filetype recognised the bytes — check against our accept-list
        if kind.mime in DETECTABLE_MIME_TYPES:
            detected_fmt = DETECTABLE_MIME_TYPES[kind.mime]
        else:
            # Recognised as something we don't support (e.g. PNG, EXE)
            supported = ", ".join(sorted(ALL_SUPPORTED_INPUT_FORMATS))
            return ValidationResult(
                ok=False,
                error=ValidationError(
                    code=ValidationErrorCode.INVALID_MIME,
                    message=(
                        f"Detected file type '{kind.mime}' is not supported. "
                        f"Supported input formats: {supported}."
                    ),
                    http_status=422,
                ),
            )
    else:
        # filetype returned None — fall back to extension for formats it can't detect
        ext = Path(filename).suffix.lstrip(".").lower() if filename else ""
        if ext in EXTENSION_FALLBACK_FORMATS:
            detected_fmt = ext
        else:
            supported = ", ".join(sorted(ALL_SUPPORTED_INPUT_FORMATS))
            return ValidationResult(
                ok=False,
                error=ValidationError(
                    code=ValidationErrorCode.INVALID_MIME,
                    message=(
                        "File format could not be identified from its content. "
                        f"Supported input formats: {supported}."
                    ),
                    http_status=422,
                ),
            )

    allowed_output = FREE_OUTPUT_FORMATS if tier == "free" else PREMIUM_OUTPUT_FORMATS
    if output_format not in allowed_output:
        return ValidationResult(
            ok=False,
            error=ValidationError(
                code=ValidationErrorCode.INVALID_OUTPUT_FORMAT,
                message=(
                    f"Output format '{output_format}' is not available on the {tier} tier. "
                    f"Available: {', '.join(sorted(allowed_output))}."
                ),
                http_status=422,
            ),
        )

    return ValidationResult(ok=True, detected_fmt=detected_fmt)
