"""Tests for web_service.config — Settings loading and validation."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from web_service.config import (
    ConfigurationError,
    Settings,
    _require_env,
    load_settings,
    reset_settings,
)

# ---------------------------------------------------------------------------
# Phase 2 Stripe + token env vars — placeholder values used by all tests that
# call load_settings().  Individual tests override specific vars as needed.
# ---------------------------------------------------------------------------
_STRIPE_ENV_DEFAULTS = {
    "STRIPE_SECRET_KEY": "sk_test_placeholder",
    "STRIPE_PUBLISHABLE_KEY": "pk_test_placeholder",
    "STRIPE_WEBHOOK_SECRET": "whsec_placeholder",
    "TOKEN_HMAC_SECRET": "placeholder_hmac_secret_for_tests",
    "STRIPE_PRICE_STARTER": "price_starter_test",
    "STRIPE_PRICE_STANDARD": "price_standard_test",
    "STRIPE_PRICE_POWER": "price_power_test",
}


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch):
    """Ensure each test starts with a fresh settings cache and Phase 2 env vars set."""
    for key, value in _STRIPE_ENV_DEFAULTS.items():
        monkeypatch.setenv(key, value)
    reset_settings()
    yield
    reset_settings()


@pytest.fixture()
def linux_config(tmp_path: Path) -> Path:
    """Write a minimal settings.json with Linux-style paths."""
    cfg = {
        "paths": {
            "calibre": "/usr/bin/ebook-convert",
            "python": "/home/joe/EbookAutomation/.venv/bin/python3.12",
            "kindle": "output/kindle",
        }
    }
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "settings.json"
    config_file.write_text(json.dumps(cfg), encoding="utf-8")
    return config_file


@pytest.fixture()
def windows_config(tmp_path: Path) -> Path:
    """Write a minimal settings.json with Windows-style paths."""
    cfg = {
        "paths": {
            "calibre": "C:\\Program Files\\Calibre2\\ebook-convert.exe",
            "python": "C:\\Python312\\python.exe",
            "kindle": "output\\kindle",
        }
    }
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "settings.json"
    config_file.write_text(json.dumps(cfg), encoding="utf-8")
    return config_file


def _patch_project_root(monkeypatch, config_file: Path):
    """Point web_service.config._PROJECT_ROOT at the tmp config's parent."""
    import web_service.config as cfg_module
    monkeypatch.setattr(cfg_module, "_PROJECT_ROOT", config_file.parent.parent)


class TestLoadSettings:
    def test_happy_path_linux_paths(self, monkeypatch, linux_config):
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")
        # EB-245: the cross-platform resolver only trusts a configured path when
        # it exists on disk. The test's configured paths don't exist on the test
        # runner's filesystem, so we mock is_file to assert the configured-path
        # branch (not the fallback branch — that's tested separately below).
        monkeypatch.setattr(Path, "is_file", lambda self: True)

        settings = load_settings()

        assert isinstance(settings, Settings)
        assert settings.calibre_path == Path("/usr/bin/ebook-convert")
        assert settings.python_path == Path("/home/joe/EbookAutomation/.venv/bin/python3.12")
        assert settings.max_file_size_free == 20 * 1024 * 1024
        assert settings.max_file_size_premium == 100 * 1024 * 1024
        assert settings.max_concurrent_jobs == 3
        assert settings.job_ttl_free == 3600
        assert settings.job_ttl_premium == 86400

    def test_calibre_exe_stripped_on_linux(self, monkeypatch, windows_config):
        """Windows config with .exe suffix — stripped when running on Linux."""
        _patch_project_root(monkeypatch, windows_config)
        monkeypatch.setattr(sys, "platform", "linux")
        # Pretend the stripped path exists so we test the strip branch directly,
        # not the shutil.which fallback (that has its own test).
        monkeypatch.setattr(Path, "is_file", lambda self: True)

        settings = load_settings()

        assert not str(settings.calibre_path).endswith(".exe")
        assert "ebook-convert" in str(settings.calibre_path)

    def test_calibre_exe_preserved_on_windows(self, monkeypatch, windows_config):
        """Windows config with .exe suffix — preserved when running on Windows."""
        _patch_project_root(monkeypatch, windows_config)
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(Path, "is_file", lambda self: True)

        settings = load_settings()

        assert str(settings.calibre_path).endswith(".exe")

    # ---------------------------------------------------------------------------
    # EB-245: cross-platform path resolution fallback
    # ---------------------------------------------------------------------------

    def test_calibre_falls_back_to_shutil_which_when_configured_path_missing(
        self, monkeypatch, windows_config
    ):
        """When the configured Calibre path doesn't exist on disk, fall back to
        shutil.which('ebook-convert'). This is the production code path on the
        Hetzner VM, where settings.json holds Windows defaults but the binary
        lives at /usr/bin/ebook-convert."""
        _patch_project_root(monkeypatch, windows_config)
        monkeypatch.setattr(sys, "platform", "linux")
        # Configured path does NOT exist
        monkeypatch.setattr(Path, "is_file", lambda self: False)
        # shutil.which returns the live binary path
        import web_service.config as cfg_module
        monkeypatch.setattr(cfg_module.shutil, "which",
                            lambda name: "/usr/bin/ebook-convert" if name == "ebook-convert" else None)

        settings = load_settings()

        assert settings.calibre_path == Path("/usr/bin/ebook-convert")

    def test_python_falls_back_to_sys_executable_when_configured_path_missing(
        self, monkeypatch, windows_config
    ):
        """When the configured Python path doesn't exist, fall back to
        sys.executable (the currently-running interpreter is always valid)."""
        _patch_project_root(monkeypatch, windows_config)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(Path, "is_file", lambda self: False)
        monkeypatch.setattr(sys, "executable", "/usr/bin/python3.12")

        settings = load_settings()

        assert settings.python_path == Path("/usr/bin/python3.12")

    def test_calibre_returns_configured_when_shutil_which_also_fails(
        self, monkeypatch, windows_config
    ):
        """If both the configured path and shutil.which fail, return the
        configured path unchanged. subprocess.run will raise FileNotFoundError
        with a clear message — better than silent misbehavior."""
        _patch_project_root(monkeypatch, windows_config)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(Path, "is_file", lambda self: False)
        import web_service.config as cfg_module
        monkeypatch.setattr(cfg_module.shutil, "which", lambda name: None)

        settings = load_settings()

        # Returns the configured (stripped) path — subprocess will fail later
        # with a helpful error rather than the helper masking the misconfiguration
        assert "ebook-convert" in str(settings.calibre_path)

    def test_missing_config_file_raises(self, monkeypatch, tmp_path):
        """FileNotFoundError raised with clear message when settings.json is absent."""
        import web_service.config as cfg_module
        monkeypatch.setattr(cfg_module, "_PROJECT_ROOT", tmp_path)

        with pytest.raises(FileNotFoundError, match="Pipeline config not found"):
            load_settings()

    def test_allowed_origins_from_env(self, monkeypatch, linux_config):
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("WEB_SERVICE_ALLOWED_ORIGINS", "https://a.com,https://b.com")

        settings = load_settings()

        assert settings.allowed_origins == ["https://a.com", "https://b.com"]

    def test_allowed_origins_defaults_to_wildcard(self, monkeypatch, linux_config):
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("WEB_SERVICE_ALLOWED_ORIGINS", raising=False)

        settings = load_settings()

        assert settings.allowed_origins == ["*"]

    def test_relative_output_dir_resolved_to_project_root(self, monkeypatch, linux_config):
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")

        settings = load_settings()

        assert settings.output_dir.is_absolute()
        assert settings.output_dir == settings.project_root / "output" / "kindle"


class TestRequireEnv:
    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_VAR", "secret-value")
        assert _require_env("MY_TEST_VAR") == "secret-value"

    def test_raises_configuration_error_when_missing(self, monkeypatch):
        monkeypatch.delenv("MY_MISSING_VAR", raising=False)
        with pytest.raises(ConfigurationError, match="MY_MISSING_VAR"):
            _require_env("MY_MISSING_VAR")


class TestGetSettings:
    def test_returns_singleton(self, monkeypatch, linux_config):
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")

        from web_service.config import get_settings
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset_clears_cache(self, monkeypatch, linux_config):
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")

        from web_service.config import get_settings
        s1 = get_settings()
        reset_settings()
        s2 = get_settings()
        assert s1 is not s2


class TestStripeSettingsHappyPath:
    """Unit 1: All 7 Phase 2 env vars set -> Settings populated correctly."""

    def test_all_stripe_vars_loaded(self, monkeypatch, linux_config):
        """Happy path: all 7 new env vars present -> fields populated on Settings."""
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")

        settings = load_settings()

        assert settings.stripe_secret_key == "sk_test_placeholder"
        assert settings.stripe_publishable_key == "pk_test_placeholder"
        assert settings.stripe_webhook_secret == "whsec_placeholder"
        assert settings.token_hmac_secret == "placeholder_hmac_secret_for_tests"
        assert settings.stripe_price_starter == "price_starter_test"
        assert settings.stripe_price_standard == "price_standard_test"
        assert settings.stripe_price_power == "price_power_test"

    def test_phase1_settings_still_load_alongside_phase2(self, monkeypatch, linux_config):
        """Regression: Phase 1 settings still load correctly when Phase 2 vars are set."""
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")

        settings = load_settings()

        # Phase 1 fields unchanged
        assert settings.calibre_path == Path("/usr/bin/ebook-convert")
        assert settings.max_file_size_free == 20 * 1024 * 1024
        assert settings.max_file_size_premium == 100 * 1024 * 1024
        assert settings.max_concurrent_jobs == 3
        assert settings.job_ttl_free == 3600
        assert settings.job_ttl_premium == 86400

    def test_settings_dataclass_is_frozen(self, monkeypatch, linux_config):
        """Frozen dataclass prevents runtime mutation — no nullity guards needed in handlers."""
        from dataclasses import FrozenInstanceError

        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")

        settings = load_settings()

        with pytest.raises(FrozenInstanceError):
            settings.stripe_secret_key = "mutated"  # type: ignore[misc]


class TestStripeSettingsErrorPath:
    """Unit 1: Any missing env var raises ConfigurationError naming the variable."""

    @pytest.mark.parametrize("missing_var", [
        "STRIPE_SECRET_KEY",
        "STRIPE_PUBLISHABLE_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "TOKEN_HMAC_SECRET",
        "STRIPE_PRICE_STARTER",
        "STRIPE_PRICE_STANDARD",
        "STRIPE_PRICE_POWER",
    ])
    def test_missing_env_var_raises_configuration_error(
        self, monkeypatch, linux_config, missing_var
    ):
        """Each of the 7 required env vars, when unset, raises ConfigurationError naming it."""
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv(missing_var, raising=False)

        with pytest.raises(ConfigurationError, match=missing_var):
            load_settings()


class TestStartupChecks:
    """Unit 1: Startup check helpers (env-mismatch and NTP) behave correctly."""

    def test_env_mismatch_logs_warning_on_test_live_mix(
        self, monkeypatch, linux_config, caplog
    ):
        """pk_test_ + sk_live_ mismatch -> WARN logged; load_settings still succeeds."""
        _patch_project_root(monkeypatch, linux_config)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_abc123")
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_xyz789")

        import web_service.main as main_module

        with caplog.at_level(logging.WARNING, logger="web_service.main"):
            main_module._check_stripe_env_mismatch()

        assert any("mismatch" in record.message.lower() for record in caplog.records), (
            f"Expected 'mismatch' in WARN log; records: {[r.message for r in caplog.records]}"
        )

    def test_env_mismatch_no_warning_when_both_test(
        self, monkeypatch, linux_config, caplog
    ):
        """pk_test_ + sk_test_ -> no mismatch warning."""
        monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_abc123")
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xyz789")

        import web_service.main as main_module

        with caplog.at_level(logging.WARNING, logger="web_service.main"):
            main_module._check_stripe_env_mismatch()

        mismatch_records = [r for r in caplog.records if "mismatch" in r.message.lower()]
        assert not mismatch_records, f"Unexpected mismatch warning: {mismatch_records}"

    def test_env_mismatch_no_warning_when_both_live(
        self, monkeypatch, linux_config, caplog
    ):
        """pk_live_ + sk_live_ -> no mismatch warning."""
        monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_live_abc123")
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_xyz789")

        import web_service.main as main_module

        with caplog.at_level(logging.WARNING, logger="web_service.main"):
            main_module._check_stripe_env_mismatch()

        mismatch_records = [r for r in caplog.records if "mismatch" in r.message.lower()]
        assert not mismatch_records, f"Unexpected mismatch warning: {mismatch_records}"

    def test_ntp_not_synced_check_ntp_returns_false(self, monkeypatch):
        """When timedatectl returns 'no', _check_ntp_sync() returns False."""
        import web_service.main as main_module

        # Sentinel file absent on this machine (test host is likely Windows/macOS)
        # Mock subprocess.run to simulate a Linux host with NTP not synced
        mock_result = MagicMock()
        mock_result.stdout = "no\n"

        with patch("web_service.main.Path") as mock_path_cls, \
             patch("web_service.main.subprocess.run", return_value=mock_result):
            # Make sentinel path.exists() return False so we fall through to timedatectl
            mock_sentinel = MagicMock()
            mock_sentinel.exists.return_value = False
            mock_path_cls.return_value = mock_sentinel

            result = main_module._check_ntp_sync()

        assert result is False

    def test_ntp_synced_check_ntp_returns_true(self, monkeypatch):
        """When timedatectl returns 'yes', _check_ntp_sync() returns True."""
        import web_service.main as main_module

        mock_result = MagicMock()
        mock_result.stdout = "yes\n"

        with patch("web_service.main.Path") as mock_path_cls, \
             patch("web_service.main.subprocess.run", return_value=mock_result):
            mock_sentinel = MagicMock()
            mock_sentinel.exists.return_value = False
            mock_path_cls.return_value = mock_sentinel

            result = main_module._check_ntp_sync()

        assert result is True

    def test_ntp_sentinel_file_present_returns_true(self):
        """When the systemd timesync sentinel file exists, _check_ntp_sync() returns True."""
        import web_service.main as main_module

        with patch("web_service.main.Path") as mock_path_cls:
            mock_sentinel = MagicMock()
            mock_sentinel.exists.return_value = True
            mock_path_cls.return_value = mock_sentinel

            result = main_module._check_ntp_sync()

        assert result is True

    def test_ntp_not_available_returns_true(self):
        """When timedatectl is not installed (FileNotFoundError), assume synced."""
        import web_service.main as main_module

        with patch("web_service.main.Path") as mock_path_cls, \
             patch("web_service.main.subprocess.run", side_effect=FileNotFoundError):
            mock_sentinel = MagicMock()
            mock_sentinel.exists.return_value = False
            mock_path_cls.return_value = mock_sentinel

            result = main_module._check_ntp_sync()

        assert result is True
