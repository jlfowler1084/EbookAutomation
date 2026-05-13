"""Cryptographic utilities for the leafbind.io token system.

Provides:
- HKDF-SHA256 key derivation from TOKEN_HMAC_SECRET with key_version support
- Fernet symmetric encryption helpers (cached singleton per key_version)
- Token minting: lb_pk_<43-char-base64url> format, 256 bits entropy
- Token hashing: HMAC-SHA256 using TOKEN_HMAC_SECRET

Key design decisions (from the Phase 2 plan):
- HKDF info=b"leafbind-token-recovery-v{key_version}" provides domain separation
  so a leak in one role (HMAC validation) does not compromise the other (recovery encryption).
- HKDF instances are single-use per the library recommendation; reinstantiate per derivation.
- get_fernet() is cached per key_version to avoid re-deriving on every encrypt/decrypt call.
- MultiFernet is available for future key rotation without re-encrypting all rows.
- TOKEN_HMAC_SECRET is loaded via get_settings() — fail-closed on missing env var.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from web_service.config import get_settings

log = logging.getLogger(__name__)

# Token format: "lb_pk_" prefix + 43 URL-safe base64 characters (no padding)
# Derived from 32 random bytes → base64url → strip "=" padding → 43 chars
# Total entropy: 256 bits. Format regex: ^lb_pk_[A-Za-z0-9_-]{43}$
_TOKEN_PREFIX = "lb_pk_"
_TOKEN_RANDOM_BYTES = 32

# Cache Fernet instances keyed by (secret, key_version) to avoid repeated HKDF calls.
# Using a plain dict (not lru_cache) to allow cache invalidation between test runs
# when the settings singleton is reset via reset_settings().
_fernet_cache: dict[int, Fernet] = {}


def derive_fernet_key(secret: bytes, key_version: int = 1) -> bytes:
    """Derive a 32-byte Fernet key from secret using HKDF-SHA256.

    The info parameter encodes key_version for domain separation:
        info = b"leafbind-token-recovery-v{key_version}"

    Returns the key as base64url-encoded bytes (44 chars including padding),
    which is the format Fernet() expects.

    HKDF instances are single-use per the cryptography library recommendation.
    Each call creates a fresh HKDF instance.

    Args:
        secret: Raw secret bytes (typically from TOKEN_HMAC_SECRET env var).
        key_version: Integer version for domain separation. Default 1.

    Returns:
        44-byte base64url-encoded Fernet key.
    """
    info = f"leafbind-token-recovery-v{key_version}".encode()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    )
    raw_key = hkdf.derive(secret)
    return base64.urlsafe_b64encode(raw_key)


def _build_fernet(key_version: int) -> Fernet:
    """Build a Fernet instance for the given key_version using the current settings."""
    settings = get_settings()
    secret = settings.token_hmac_secret.encode()
    key = derive_fernet_key(secret, key_version)
    return Fernet(key)


def get_fernet(key_version: int = 1) -> Fernet:
    """Return a cached Fernet instance for the given key_version.

    The cache is module-level. Individual tests reset it via clear_crypto_cache()
    when the settings singleton is cleared (handled by the clear_settings fixture
    in existing test files).

    Args:
        key_version: The key version to use. Default 1.

    Returns:
        A Fernet instance ready for encrypt()/decrypt() calls.
    """
    if key_version not in _fernet_cache:
        _fernet_cache[key_version] = _build_fernet(key_version)
    return _fernet_cache[key_version]


def clear_crypto_cache() -> None:
    """Clear the Fernet instance cache. Called when settings are reset in tests."""
    _fernet_cache.clear()


def mint_token() -> tuple[str, bytes]:
    """Mint a new single-use token and compute its HMAC-SHA256 hash.

    Token format: "lb_pk_" + base64url(32 random bytes, no padding)
    Token hash:   HMAC-SHA256(TOKEN_HMAC_SECRET, token_string).digest()

    Returns:
        Tuple of (token_string, token_hash_bytes).
        token_string: 49-char string matching ^lb_pk_[A-Za-z0-9_-]{43}$
        token_hash_bytes: 32-byte HMAC-SHA256 digest used as DB primary key.
    """
    random_bytes = secrets.token_bytes(_TOKEN_RANDOM_BYTES)
    token_suffix = base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode()
    token = _TOKEN_PREFIX + token_suffix
    token_hash = compute_token_hash(token)
    return token, token_hash


def compute_token_hash(token: str) -> bytes:
    """Compute the HMAC-SHA256 hash of a token string.

    Uses TOKEN_HMAC_SECRET as the HMAC key. The hash is used as the
    primary key in the tokens table to avoid storing the raw token server-side.

    Args:
        token: The raw token string (e.g. "lb_pk_AAAA...").

    Returns:
        32-byte HMAC-SHA256 digest.
    """
    settings = get_settings()
    secret = settings.token_hmac_secret.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).digest()
