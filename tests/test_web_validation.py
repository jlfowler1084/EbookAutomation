"""Tests for web_service.validation — magic byte, size, and format checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from web_service.config import Settings, reset_settings
from web_service.validation import (
    FREE_OUTPUT_FORMATS,
    ValidationErrorCode,
    validate_upload,
)

# ---------------------------------------------------------------------------
# Magic byte sample headers
# ---------------------------------------------------------------------------

# Real PDF header
PDF_HEADER = b"%PDF-1.4\n" + b"\x00" * 260

# Real EPUB: PK header + mimetype file as first ZIP entry
EPUB_HEADER = (
    b"PK\x03\x04"
    + b"\x14\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    + b"\x3a\x90\x3c\xfe"
    + b"\x1a\x00\x00\x00\x1a\x00\x00\x00"
    + b"\x08\x00\x00\x00"
    + b"mimetype"
    + b"application/epub+zip"
    + b"\x00" * 200
)

# Generic ZIP (EPUB created by tools that don't put mimetype first)
ZIP_AS_EPUB_HEADER = b"PK\x03\x04" + b"\x00" * 300

# PNG header (known bad — should be rejected)
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 300

# Opaque bytes that filetype cannot identify (simulate MOBI)
OPAQUE_HEADER = b"\x00" * 300


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_settings_cache():
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def settings(tmp_path, monkeypatch) -> Settings:
    """Minimal Settings with 20 MB free / 100 MB premium limits."""
    cfg = {
        "paths": {
            "calibre": "/usr/bin/ebook-convert",
            "python": "/usr/bin/python3",
            "kindle": "output/kindle",
        }
    }
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text(json.dumps(cfg), encoding="utf-8")

    import web_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")

    from web_service.config import load_settings
    return load_settings()


FREE_20MB = 20 * 1024 * 1024
ONE_BYTE_OVER = FREE_20MB + 1


class TestHappyPaths:
    def test_valid_pdf_accepted(self, settings):
        result = validate_upload(PDF_HEADER, 1024, "epub", "free", settings, "book.pdf")
        assert result.ok
        assert result.detected_fmt == "pdf"

    def test_valid_epub_accepted(self, settings):
        result = validate_upload(EPUB_HEADER, 2048, "epub", "free", settings, "book.epub")
        assert result.ok
        assert result.detected_fmt == "epub"

    def test_zip_epub_accepted(self, settings):
        """EPUBs without first-entry mimetype are detected as generic ZIP — still accepted."""
        result = validate_upload(ZIP_AS_EPUB_HEADER, 2048, "epub", "free", settings, "book.epub")
        assert result.ok
        assert result.detected_fmt == "epub"

    def test_mobi_accepted_via_extension_fallback(self, settings):
        """MOBI files can't be detected by magic bytes — extension fallback is used."""
        result = validate_upload(OPAQUE_HEADER, 1024, "epub", "free", settings, "book.mobi")
        assert result.ok
        assert result.detected_fmt == "mobi"

    def test_file_exactly_at_size_limit_accepted(self, settings):
        result = validate_upload(PDF_HEADER, FREE_20MB, "epub", "free", settings, "book.pdf")
        assert result.ok


class TestSizeLimits:
    def test_one_byte_over_limit_rejected(self, settings):
        result = validate_upload(PDF_HEADER, ONE_BYTE_OVER, "epub", "free", settings, "book.pdf")
        assert not result.ok
        assert result.error.code == ValidationErrorCode.FILE_TOO_LARGE
        assert result.error.http_status == 413

    def test_premium_allows_larger_file(self, settings):
        result = validate_upload(PDF_HEADER, FREE_20MB + 1, "epub", "premium", settings, "book.pdf")
        assert result.ok

    def test_empty_file_rejected(self, settings):
        result = validate_upload(PDF_HEADER, 0, "epub", "free", settings, "book.pdf")
        assert not result.ok
        assert result.error.code == ValidationErrorCode.EMPTY_FILE
        assert result.error.http_status == 422


class TestMagicByteRejection:
    def test_png_disguised_as_pdf_rejected(self, settings):
        """PNG magic bytes → rejected even with a .pdf filename."""
        result = validate_upload(PNG_HEADER, 1024, "epub", "free", settings, "notapdf.pdf")
        assert not result.ok
        assert result.error.code == ValidationErrorCode.INVALID_MIME
        assert result.error.http_status == 422

    def test_unidentifiable_without_known_extension_rejected(self, settings):
        """Opaque bytes with an unrecognised extension → rejected."""
        result = validate_upload(OPAQUE_HEADER, 1024, "epub", "free", settings, "book.docx")
        assert not result.ok
        assert result.error.code == ValidationErrorCode.INVALID_MIME

    def test_no_filename_unidentifiable_rejected(self, settings):
        """Opaque bytes with no filename → rejected (no extension fallback)."""
        result = validate_upload(OPAQUE_HEADER, 1024, "epub", "free", settings)
        assert not result.ok
        assert result.error.code == ValidationErrorCode.INVALID_MIME


class TestOutputFormatValidation:
    def test_kfx_rejected_on_free_tier(self, settings):
        result = validate_upload(PDF_HEADER, 1024, "kfx", "free", settings, "book.pdf")
        assert not result.ok
        assert result.error.code == ValidationErrorCode.INVALID_OUTPUT_FORMAT
        assert "free" in result.error.message

    def test_kfx_accepted_on_premium_tier(self, settings):
        result = validate_upload(PDF_HEADER, 1024, "kfx", "premium", settings, "book.pdf")
        assert result.ok

    def test_invalid_output_format_rejected(self, settings):
        result = validate_upload(PDF_HEADER, 1024, "docx", "free", settings, "book.pdf")
        assert not result.ok
        assert result.error.code == ValidationErrorCode.INVALID_OUTPUT_FORMAT

    def test_free_tier_shows_available_formats(self, settings):
        result = validate_upload(PDF_HEADER, 1024, "kfx", "free", settings, "book.pdf")
        assert result.error is not None
        for fmt in FREE_OUTPUT_FORMATS:
            assert fmt in result.error.message
