"""Token format validation — pure-function interface for validating token strings.

Provides a lightweight format check (regex only, no DB hit) that callers can
run before invoking the DB-backed validate_and_consume() in token_store.

Design note: TokenValidationErrorCode, TokenValidationError, and
TokenValidationResult are defined in web_service.token_store (single source of
truth). This module re-exports them so callers can import from either location
without creating a duplication hazard.

Token format specification: ^lb_pk_[A-Za-z0-9_-]{43}$
  - Prefix:  lb_pk_
  - Body:    43 characters from [A-Za-z0-9_-] (URL-safe base64 alphabet)
  - Total:   49 characters

Whitespace handling: this function is STRICT — no trimming is performed.
Leading or trailing whitespace causes MALFORMED. Callers should strip() before
calling if their input source (e.g., form field) may include padding.
"""

from __future__ import annotations

import re

# Re-export from token_store — single source of truth for these types.
# Callers may import from either module; the names and semantics are identical.
from web_service.token_store import (  # noqa: F401
    TokenValidationError,
    TokenValidationErrorCode,
    TokenValidationResult,
)

# Compiled once at module load — same pattern as token_store._TOKEN_REGEX.
# Kept here as a local constant so validate_token_format() has no import-time
# dependency on token_store internals (avoids circular import risk if
# token_store ever gains an import from this module).
_TOKEN_FORMAT_REGEX = re.compile(r"^lb_pk_[A-Za-z0-9_-]{43}\Z")


def validate_token_format(token: str) -> TokenValidationResult:
    """Check that *token* matches the lb_pk_<43-char> format.

    This is a pure function — no DB access, no side effects.
    It acts as a fast pre-flight check before the caller invokes
    token_store.validate_and_consume().

    Args:
        token: The raw token string to validate. Must be exactly 49 characters:
               lb_pk_ (6) + 43 URL-safe base64 characters.

    Returns:
        TokenValidationResult(ok=True) if the format matches.
        TokenValidationResult(ok=False, error=TokenValidationError(MALFORMED, ...))
        if the format does not match.

    Examples:
        >>> validate_token_format("lb_pk_" + "A" * 43)
        TokenValidationResult(ok=True, error=None)

        >>> validate_token_format("lb_pk_" + "A" * 42)
        TokenValidationResult(ok=False, error=TokenValidationError(...))
    """
    if _TOKEN_FORMAT_REGEX.match(token):
        return TokenValidationResult(ok=True)

    return TokenValidationResult(
        ok=False,
        error=TokenValidationError(
            code=TokenValidationErrorCode.MALFORMED,
            message=(
                "Token format is invalid. Expected format: lb_pk_<43 characters> "
                "(URL-safe base64 alphabet A-Z, a-z, 0-9, _, -). "
                "Please check you copied the token correctly."
            ),
            http_status=422,
        ),
    )
