"""Tests for web_service.token_validation — pure format validation, no DB.

validate_token_format() is a pure function: regex check only, no side effects.
These tests are fast and require no fixtures.

Token format spec: ^lb_pk_[A-Za-z0-9_-]{43}$
  - Total length: 49 characters (6-char prefix + 43-char body)
  - Body alphabet: A-Z, a-z, 0-9, _, - (URL-safe base64)

Whitespace handling (STRICT): validate_token_format does NOT strip input.
Leading or trailing whitespace causes MALFORMED. Callers are responsible for
stripping form/JSON input before invoking this function.

Import note: TokenValidationErrorCode, TokenValidationError, and
TokenValidationResult are defined in web_service.token_store (single source
of truth) and re-exported by web_service.token_validation. Both import paths
are exercised below to document this equivalence.
"""

from __future__ import annotations

import pytest

from web_service.token_validation import (
    TokenValidationErrorCode,
    TokenValidationResult,
    validate_token_format,
)
# Also import from token_store to verify same type identity (re-export test)
from web_service.token_store import (
    TokenValidationErrorCode as _StoreErrorCode,
    TokenValidationResult as _StoreResult,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_BODY = "A" * 43
_VALID_TOKEN = f"lb_pk_{_VALID_BODY}"


# ---------------------------------------------------------------------------
# Re-export identity check
# ---------------------------------------------------------------------------

def test_reexported_types_are_identical():
    """TokenValidationErrorCode imported from token_validation == from token_store."""
    assert TokenValidationErrorCode is _StoreErrorCode
    assert TokenValidationResult is _StoreResult


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_token_all_uppercase():
    """Exact 43-char uppercase body returns ok=True."""
    result = validate_token_format("lb_pk_" + "A" * 43)
    assert result.ok is True
    assert result.error is None


def test_valid_token_all_lowercase():
    """Exact 43-char lowercase body returns ok=True."""
    result = validate_token_format("lb_pk_" + "a" * 43)
    assert result.ok is True
    assert result.error is None


def test_valid_token_mixed_alphabet():
    """Mixed alphanumeric + underscore + hyphen body returns ok=True."""
    body = "AbCdEf0123456789_-AbCdEf0123456789_-AbCdEf0"
    assert len(body) == 43, f"Test body must be 43 chars, got {len(body)}"
    result = validate_token_format(f"lb_pk_{body}")
    assert result.ok is True


def test_valid_token_with_hyphens_and_underscores():
    """URL-safe base64 characters (- and _) are accepted."""
    body = "_" * 21 + "-" * 22
    assert len(body) == 43
    result = validate_token_format(f"lb_pk_{body}")
    assert result.ok is True


# ---------------------------------------------------------------------------
# Body length edge cases
# ---------------------------------------------------------------------------

def test_body_42_chars_is_malformed():
    """Body of 42 characters (one short) returns MALFORMED."""
    result = validate_token_format("lb_pk_" + "A" * 42)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == TokenValidationErrorCode.MALFORMED
    assert result.error.http_status == 422


def test_body_44_chars_is_malformed():
    """Body of 44 characters (one over) returns MALFORMED."""
    result = validate_token_format("lb_pk_" + "A" * 44)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == TokenValidationErrorCode.MALFORMED
    assert result.error.http_status == 422


def test_body_zero_chars_is_malformed():
    """Prefix only with no body returns MALFORMED."""
    result = validate_token_format("lb_pk_")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_body_one_char_is_malformed():
    """Prefix plus 1-char body returns MALFORMED."""
    result = validate_token_format("lb_pk_A")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


# ---------------------------------------------------------------------------
# Invalid characters in body
# ---------------------------------------------------------------------------

def test_at_sign_in_body_is_malformed():
    """@ is not in the URL-safe base64 alphabet — returns MALFORMED."""
    body = "A" * 42 + "@"
    result = validate_token_format(f"lb_pk_{body}")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_plus_in_body_is_malformed():
    """+ is standard base64 but not URL-safe base64 — returns MALFORMED."""
    body = "A" * 42 + "+"
    result = validate_token_format(f"lb_pk_{body}")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_slash_in_body_is_malformed():
    """/ is standard base64 but not URL-safe base64 — returns MALFORMED."""
    body = "A" * 42 + "/"
    result = validate_token_format(f"lb_pk_{body}")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_equals_sign_in_body_is_malformed():
    """= (padding) is not in the alphabet — returns MALFORMED."""
    body = "A" * 42 + "="
    result = validate_token_format(f"lb_pk_{body}")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_space_in_body_is_malformed():
    """Space character in body returns MALFORMED."""
    body = "A" * 42 + " "
    result = validate_token_format(f"lb_pk_{body}")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


# ---------------------------------------------------------------------------
# Empty and None-ish inputs
# ---------------------------------------------------------------------------

def test_empty_string_is_malformed():
    """Empty string returns MALFORMED."""
    result = validate_token_format("")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_whitespace_only_is_malformed():
    """Whitespace-only string returns MALFORMED."""
    result = validate_token_format("   ")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


# ---------------------------------------------------------------------------
# Wrong prefix
# ---------------------------------------------------------------------------

def test_wrong_prefix_sk_live():
    """Stripe secret key prefix (sk_live_xxx) returns MALFORMED."""
    result = validate_token_format("sk_live_" + "A" * 43)
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_wrong_prefix_pk_test():
    """Stripe publishable key prefix (pk_test_xxx) returns MALFORMED."""
    result = validate_token_format("pk_test_" + "A" * 43)
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_wrong_prefix_no_prefix():
    """43 body chars with no prefix returns MALFORMED."""
    result = validate_token_format("A" * 43)
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_wrong_prefix_lb_pk_missing_underscore():
    """lb_pk without trailing underscore returns MALFORMED."""
    result = validate_token_format("lb_pk" + "A" * 43)
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


# ---------------------------------------------------------------------------
# Whitespace handling — STRICT (no trimming)
# ---------------------------------------------------------------------------

def test_leading_whitespace_is_malformed():
    """Valid token with a leading space returns MALFORMED (strict, no trim).

    Callers should strip() input from form fields before calling
    validate_token_format().
    """
    result = validate_token_format(" " + _VALID_TOKEN)
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_trailing_whitespace_is_malformed():
    """Valid token with a trailing space returns MALFORMED (strict, no trim)."""
    result = validate_token_format(_VALID_TOKEN + " ")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


def test_trailing_newline_is_malformed():
    """Valid token with trailing newline returns MALFORMED (strict, no trim)."""
    result = validate_token_format(_VALID_TOKEN + "\n")
    assert result.ok is False
    assert result.error.code == TokenValidationErrorCode.MALFORMED


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------

def test_malformed_error_has_useful_message():
    """MALFORMED error message mentions expected format."""
    result = validate_token_format("not-a-token")
    assert result.error is not None
    assert "lb_pk_" in result.error.message
    assert "43" in result.error.message


def test_malformed_error_http_status_is_422():
    """MALFORMED error always carries http_status=422."""
    result = validate_token_format("bad")
    assert result.error is not None
    assert result.error.http_status == 422


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

def test_return_type_is_token_validation_result():
    """Return type is always TokenValidationResult regardless of input."""
    for token in [_VALID_TOKEN, "", "bad", "lb_pk_" + "A" * 42]:
        result = validate_token_format(token)
        assert isinstance(result, TokenValidationResult)
