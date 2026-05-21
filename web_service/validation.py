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


# EB-324 Unit 4 scenario suite: Kindle-specific validation codes.
# Kept in a separate enum so the upload-validation surface (above) stays
# focused on input validation and the Kindle codes have an explicit
# namespace.
class KindleErrorCode(str, Enum):
    INVALID_RECIPIENT_FORM = "INVALID_RECIPIENT_FORM"     # display name, plus alias, malformed
    INVALID_RECIPIENT_DOMAIN = "INVALID_RECIPIENT_DOMAIN"  # not kindle.com / free.kindle.com
    FORMAT_NOT_KINDLE_ELIGIBLE = "FORMAT_NOT_KINDLE_ELIGIBLE"
    OUTPUT_TOO_LARGE_FOR_KINDLE = "OUTPUT_TOO_LARGE_FOR_KINDLE"


@dataclass(frozen=True)
class KindleValidationResult:
    """Outcome of a single Kindle-validation helper.

    On success: ``ok=True`` and ``normalized`` carries the post-normalization
    value (lowercased recipient or output format) the route should use
    downstream. On failure: ``ok=False`` and ``code`` carries the
    machine-friendly error tag that the route maps to an HTTPException.
    """
    ok: bool
    normalized: str = ""
    code: KindleErrorCode | None = None
    message: str = ""


# Strict equality allowlist. Amazon offers exactly two domains for
# Send-to-Kindle email delivery; anything else (incl. evil-kindle.com)
# must be rejected. NO wildcard / endswith matching.
_KINDLE_ALLOWED_DOMAINS: frozenset[str] = frozenset({"kindle.com", "free.kindle.com"})

# Wave 1 only ships EPUB through the Send-to-Kindle pipeline. MOBI and KFX
# are produced by the conversion pipeline but not Kindle-mail-eligible
# (MOBI is deprecated by Amazon; KFX is for sideload only).
_KINDLE_OUTPUT_FORMATS: frozenset[str] = frozenset({"epub"})

# Per plan R3.3 size portion, calibrated against Resend's 40 MB
# POST-encoding limit. The cap is on RAW bytes; the wrapper Base64-encodes
# before send.
#
# Base64 expansion math: encoded = 4 * ceil(raw/3) ≈ raw * 4/3.
# Line-wrapping (CRLF every 76 chars) adds ~1.3% more. MIME envelope
# (headers, boundary markers, Content-Disposition) adds ~3-5 KB.
#
# At the previous 30 MiB cap: 30 MiB raw → 40 MiB encoded EXACTLY before
# envelope or line-wrap → over Resend's limit on every send. Dropping to
# 25 MiB raw: 25 MiB → ~33.3 MiB encoded → ~33.8 MiB with line-wrap →
# ~33.9 MiB total → ~6 MiB headroom against Resend's 40 MiB ceiling.
_KINDLE_MAX_SIZE_BYTES: int = 25 * 1024 * 1024


def validate_kindle_recipient(recipient: str) -> KindleValidationResult:
    """Parse + normalize + domain-check a Kindle recipient address.

    Rules (per plan R3.1 + R3.4):
    - parseaddr split. Reject if a display name is present.
    - Local part must be non-empty and must NOT contain '+'.
    - Domain must be strict-equality match against
      ``{"kindle.com", "free.kindle.com"}``. No suffix/endswith matching.

    Stdlib ``email.utils.parseaddr`` is sufficient for our needs (we don't
    need full RFC-5322 mailbox grammar — just display-name detection plus
    a token-comparison check on the address). email-validator is in
    requirements.txt for future use but not on the hot path here.
    """
    from email.utils import parseaddr

    stripped = recipient.strip().lower() if recipient else ""
    display, addr = parseaddr(stripped)

    if display:
        return KindleValidationResult(
            ok=False,
            code=KindleErrorCode.INVALID_RECIPIENT_FORM,
            message="Recipient must not include a display name",
        )

    # parseaddr is permissive: it strips angle brackets, internal whitespace,
    # comments, source routes, and other RFC-5322 oddities silently, then
    # returns the normalized address. We require the user to have typed the
    # canonical address — anything that parseaddr "fixed up" is rejected.
    # Catches `<x@kindle.com>`, `x @kindle.com`, `(c)x@kindle.com`, etc.
    if addr != stripped:
        return KindleValidationResult(
            ok=False,
            code=KindleErrorCode.INVALID_RECIPIENT_FORM,
            message="Recipient must be a bare canonical email address (no angle brackets, whitespace, or RFC-5322 decoration)",
        )

    if not addr or "@" not in addr:
        return KindleValidationResult(
            ok=False,
            code=KindleErrorCode.INVALID_RECIPIENT_FORM,
            message="Recipient must be a bare email address",
        )

    local, _, domain = addr.rpartition("@")

    if not local:
        return KindleValidationResult(
            ok=False,
            code=KindleErrorCode.INVALID_RECIPIENT_FORM,
            message="Recipient local-part is empty",
        )

    if "+" in local:
        return KindleValidationResult(
            ok=False,
            code=KindleErrorCode.INVALID_RECIPIENT_FORM,
            message="Plus-aliased Kindle addresses are not supported",
        )

    if domain not in _KINDLE_ALLOWED_DOMAINS:
        return KindleValidationResult(
            ok=False,
            code=KindleErrorCode.INVALID_RECIPIENT_DOMAIN,
            message="Recipient domain must be kindle.com or free.kindle.com",
        )

    return KindleValidationResult(ok=True, normalized=addr)


def validate_kindle_format(output_fmt: str) -> KindleValidationResult:
    """Confirm the job's output format is Kindle-eligible.

    Defense-in-depth — the frontend gates this row at the UI level, but
    a forged POST or a future format-routing bug must not slip MOBI/KFX
    to Resend.
    """
    normalized = (output_fmt or "").lower()
    if normalized in _KINDLE_OUTPUT_FORMATS:
        return KindleValidationResult(ok=True, normalized=normalized)
    return KindleValidationResult(
        ok=False,
        code=KindleErrorCode.FORMAT_NOT_KINDLE_ELIGIBLE,
        message=f"Output format '{output_fmt}' is not Kindle-eligible",
    )


def validate_kindle_attachment_size(size_bytes: int) -> KindleValidationResult:
    """Raw-byte size check against the 25 MiB cap.

    Cap is calibrated against Resend's 40 MB POST-Base64-encoding ceiling.
    25 MiB raw → ~33.3 MiB encoded → ~6 MiB headroom for envelope +
    line-wrapping overhead. See the comment on _KINDLE_MAX_SIZE_BYTES.
    """
    if size_bytes <= _KINDLE_MAX_SIZE_BYTES:
        return KindleValidationResult(ok=True)
    return KindleValidationResult(
        ok=False,
        code=KindleErrorCode.OUTPUT_TOO_LARGE_FOR_KINDLE,
        message=(
            f"Attachment size {size_bytes} bytes exceeds the "
            f"{_KINDLE_MAX_SIZE_BYTES} byte Kindle limit"
        ),
    )


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
