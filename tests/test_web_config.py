"""Tests for web_service.config — Settings loading and validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from web_service.config import (
    ConfigurationError,
    Settings,
    _require_env,
    load_settings,
    reset_settings,
)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure each test starts with a fresh settings cache."""
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

        settings = load_settings()

        assert not str(settings.calibre_path).endswith(".exe")
        assert "ebook-convert" in str(settings.calibre_path)

    def test_calibre_exe_preserved_on_windows(self, monkeypatch, windows_config):
        """Windows config with .exe suffix — preserved when running on Windows."""
        _patch_project_root(monkeypatch, windows_config)
        monkeypatch.setattr(sys, "platform", "win32")

        settings = load_settings()

        assert str(settings.calibre_path).endswith(".exe")

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
