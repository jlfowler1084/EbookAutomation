"""Shared pytest fixtures for web_service tests.

Phase 2 (EB-45) added 7 fail-closed env vars (Stripe + token HMAC secret) that
`_require_env` raises ConfigurationError on if absent. This module-level autouse
fixture sets placeholder values so individual tests don't have to.

Individual tests can override or delete specific vars via their own
`monkeypatch.setenv()` / `monkeypatch.delenv()` calls — pytest's monkeypatch
overrides this fixture's defaults cleanly within the test scope.
"""

from __future__ import annotations

import pytest

# Placeholder values used by every test that calls `load_settings()`.
# Real-looking enough that startup checks (env-mismatch) don't false-positive,
# but obviously-fake so a secrets scanner won't flag them as real keys.
_PHASE2_ENV_DEFAULTS = {
    "STRIPE_SECRET_KEY": "sk_test_placeholder",
    "STRIPE_PUBLISHABLE_KEY": "pk_test_placeholder",
    "STRIPE_WEBHOOK_SECRET": "whsec_placeholder",
    "TOKEN_HMAC_SECRET": "placeholder_hmac_secret_for_tests",
    "STRIPE_PRICE_STARTER": "price_starter_test",
    "STRIPE_PRICE_STANDARD": "price_standard_test",
    "STRIPE_PRICE_POWER": "price_power_test",
    # EB-227: explicit version pin matching code default. Tests can override.
    "STRIPE_API_VERSION": "2026-04-22.dahlia",
    # EB-324 Unit 4: Send-to-Kindle. Placeholders so existing tests that don't
    # exercise the send_to_kindle route still pass load_settings(); tests that
    # exercise the route may override via their own monkeypatch.
    "WEB_SEND_TO_KINDLE_FROM": "kindle-test@send.example.com",
    "WEB_RESEND_API_KEY": "re_test_placeholder_resend_key",
    # EB-324 Unit 10: Svix-format signing secret. The webhook tests sign
    # payloads with this same secret so verify() succeeds. Base64-decoded
    # length must match Svix's expected key size (32 bytes).
    "WEB_RESEND_WEBHOOK_SECRET": "whsec_dGVzdHNlY3JldHRlc3RzZWNyZXR0ZXN0c2VjcmV0dGVzdA==",
    # Feature flag defaults to True for tests so the existing route tests
    # exercise the live path. The disabled-state test overrides this via
    # its own monkeypatch.setenv.
    "WEB_SEND_TO_KINDLE_ENABLED": "true",
}


@pytest.fixture(autouse=True)
def _phase2_env_defaults(monkeypatch):
    """Set Phase 2 fail-closed env vars to placeholder values for every test.

    Tests that need to verify the missing-env-var error path should use their
    own `monkeypatch.delenv(...)` after this fixture has set the defaults.
    """
    for key, value in _PHASE2_ENV_DEFAULTS.items():
        monkeypatch.setenv(key, value)
    yield


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """EB-324 Unit 8: disable slowapi rate limiting by default in tests.

    slowapi's in-memory storage persists across tests within a process, so a
    multi-request test case would otherwise trip limits set by an earlier
    test (and the per-resource keys collide across files that reuse the same
    job_id / parent_job_id). Disabling globally keeps existing route tests
    unaffected. The dedicated rate-limit tests opt back in via their own
    fixture (see tests/test_web_rate_limit.py::_enable_limiter).
    """
    from web_service.rate_limit import limiter
    previous = limiter.enabled
    limiter.enabled = False
    limiter.reset()
    yield
    limiter.enabled = previous
    limiter.reset()
