"""Tests for web_service.crypto — HKDF key derivation, Fernet helpers, token minting.

Exercises:
- HKDF domain separation: key_version=1 vs key_version=2 produce different keys
- HKDF determinism: same secret + version always returns same key
- Token format: mint_token() returns token matching ^lb_pk_[A-Za-z0-9_-]{43}$
- Token hash: compute_token_hash(token) returns 32-byte HMAC-SHA256 digest
- Hash uniqueness: two distinct tokens produce different hashes
- Fernet round-trip: encrypt then decrypt with get_fernet(1) round-trips correctly
"""

from __future__ import annotations

import os
import re

import pytest

from web_service.crypto import (
    compute_token_hash,
    derive_fernet_key,
    get_fernet,
    mint_token,
)

TOKEN_REGEX = re.compile(r"^lb_pk_[A-Za-z0-9_-]{43}$")
_SECRET = b"test_hmac_secret_for_crypto_unit_tests"


class TestDeriveKey:
    def test_domain_separation_key_version(self):
        """Different key_version values must produce different keys (info param differs)."""
        key1 = derive_fernet_key(_SECRET, key_version=1)
        key2 = derive_fernet_key(_SECRET, key_version=2)
        assert key1 != key2

    def test_deterministic_hkdf(self):
        """Same secret + version always produces the same key (HKDF is deterministic)."""
        key_a = derive_fernet_key(_SECRET, key_version=1)
        key_b = derive_fernet_key(_SECRET, key_version=1)
        assert key_a == key_b

    def test_different_secrets_produce_different_keys(self):
        """Different secrets must produce different keys."""
        key_a = derive_fernet_key(b"secret_one", key_version=1)
        key_b = derive_fernet_key(b"secret_two", key_version=1)
        assert key_a != key_b

    def test_output_is_bytes(self):
        """derive_fernet_key must return bytes (base64url-encoded Fernet key)."""
        key = derive_fernet_key(_SECRET, key_version=1)
        assert isinstance(key, bytes)
        # Fernet keys are 32 bytes base64url-encoded = 44 URL-safe chars with padding
        assert len(key) == 44


class TestGetFernet:
    def test_returns_fernet_instance(self):
        """get_fernet() must return a usable Fernet instance."""
        from cryptography.fernet import Fernet
        f = get_fernet(key_version=1)
        assert isinstance(f, Fernet)

    def test_encrypt_decrypt_round_trip(self):
        """Encrypt then decrypt with get_fernet(1) must round-trip correctly."""
        f = get_fernet(key_version=1)
        plaintext = b"lb_pk_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        ciphertext = f.encrypt(plaintext)
        assert f.decrypt(ciphertext) == plaintext

    def test_same_version_same_instance_or_equivalent(self):
        """Two calls with the same version must produce the same key (cached or re-derived)."""
        f1 = get_fernet(key_version=1)
        f2 = get_fernet(key_version=1)
        # Both must decrypt each other's output
        plaintext = b"hello_leafbind"
        ct = f1.encrypt(plaintext)
        assert f2.decrypt(ct) == plaintext

    def test_different_versions_cannot_cross_decrypt(self):
        """Fernet instances for different key_version values must not interoperate."""
        from cryptography.fernet import InvalidToken
        f1 = get_fernet(key_version=1)
        f2 = get_fernet(key_version=2)
        ct = f1.encrypt(b"test_data")
        with pytest.raises(InvalidToken):
            f2.decrypt(ct)


class TestMintToken:
    def test_token_matches_format_regex(self):
        """mint_token() must return a token matching ^lb_pk_[A-Za-z0-9_-]{43}$."""
        token, token_hash = mint_token()
        assert TOKEN_REGEX.match(token), f"Token {token!r} did not match expected format"

    def test_returns_tuple(self):
        """mint_token() must return a (str, bytes) tuple."""
        result = mint_token()
        assert isinstance(result, tuple) and len(result) == 2
        token, token_hash = result
        assert isinstance(token, str)
        assert isinstance(token_hash, bytes)

    def test_hash_is_32_bytes(self):
        """The token_hash from mint_token() must be 32 bytes (HMAC-SHA256 digest)."""
        _, token_hash = mint_token()
        assert len(token_hash) == 32

    def test_tokens_are_unique(self):
        """Two mint_token() calls must return different tokens."""
        token_a, _ = mint_token()
        token_b, _ = mint_token()
        assert token_a != token_b

    def test_hashes_are_unique_for_different_tokens(self):
        """Two different tokens must produce different hashes."""
        token_a, hash_a = mint_token()
        token_b, hash_b = mint_token()
        assert hash_a != hash_b


class TestComputeTokenHash:
    def test_returns_32_bytes(self):
        """compute_token_hash must return a 32-byte HMAC-SHA256 digest."""
        token, _ = mint_token()
        h = compute_token_hash(token)
        assert isinstance(h, bytes)
        assert len(h) == 32

    def test_consistency_with_mint_token_hash(self):
        """compute_token_hash(token) must equal the hash returned by mint_token()."""
        token, expected_hash = mint_token()
        computed = compute_token_hash(token)
        assert computed == expected_hash

    def test_hash_differs_for_different_tokens(self):
        """Two different token strings must hash to different values."""
        token_a, _ = mint_token()
        token_b, _ = mint_token()
        assert compute_token_hash(token_a) != compute_token_hash(token_b)

    def test_deterministic(self):
        """Calling compute_token_hash twice on the same token must return the same value."""
        token, _ = mint_token()
        h1 = compute_token_hash(token)
        h2 = compute_token_hash(token)
        assert h1 == h2
