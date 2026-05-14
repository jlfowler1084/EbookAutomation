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
