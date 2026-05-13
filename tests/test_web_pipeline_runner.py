"""Tests for web_service.pipeline_runner — subprocess wrapping, timeouts, artifact verification."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, patch

import pytest

from web_service.config import Settings, reset_settings
from web_service.pipeline_runner import (
    RunResult,
    _extract_calibre_error,
    _find_newest_kfx,
    _timeout_for_size,
    _verify_output,
    run_free,
    run_premium,
)


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


@pytest.fixture()
def small_pdf(tmp_path) -> Path:
    """Fake 5 KB PDF-like file."""
    p = tmp_path / "input.pdf"
    p.write_bytes(b"%PDF-1.4\n" + b"\x00" * (5 * 1024))
    return p


@pytest.fixture()
def temp_dir(tmp_path) -> Path:
    d = tmp_path / "job_abc123"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


class TestTimeoutForSize:
    def test_small_file_120s(self):
        assert _timeout_for_size(5 * 1024 * 1024) == 120

    def test_medium_file_300s(self):
        assert _timeout_for_size(20 * 1024 * 1024) == 300

    def test_large_file_600s(self):
        assert _timeout_for_size(80 * 1024 * 1024) == 600

    def test_exactly_at_boundary(self):
        # 10 MB exactly → falls to next tier (50 MB → 300 s)
        assert _timeout_for_size(10 * 1024 * 1024) == 300


class TestExtractCalibreError:
    def test_prefers_stdout_last_line(self):
        msg = _extract_calibre_error("line1\nActual error here", "", 1)
        assert msg == "Actual error here"

    def test_falls_back_to_stderr(self):
        msg = _extract_calibre_error("", "stderr error", 1)
        assert msg == "stderr error"

    def test_generic_message_when_empty(self):
        msg = _extract_calibre_error("", "", 1)
        assert "1" in msg  # exit code mentioned


class TestFindNewestKfx:
    def test_finds_kfx_created_after_timestamp(self, tmp_path):
        before = time.time() - 1
        kfx = tmp_path / "book.kfx"
        kfx.write_bytes(b"KFX content")
        found = _find_newest_kfx(tmp_path, before)
        assert found == kfx

    def test_ignores_kfx_created_before_timestamp(self, tmp_path):
        kfx = tmp_path / "old.kfx"
        kfx.write_bytes(b"old")
        future = time.time() + 100
        found = _find_newest_kfx(tmp_path, future)
        assert found is None

    def test_returns_none_when_no_kfx(self, tmp_path):
        assert _find_newest_kfx(tmp_path, 0.0) is None


class TestVerifyOutput:
    def test_valid_file_returned(self, tmp_path):
        f = tmp_path / "output.epub"
        f.write_bytes(b"epub content")
        result = _verify_output(f, time.time() - 1)
        assert result == f

    def test_zero_byte_epub_returns_none(self, tmp_path):
        f = tmp_path / "output.epub"
        f.write_bytes(b"")
        result = _verify_output(f, time.time() - 1)
        assert result is None

    def test_missing_epub_returns_none(self, tmp_path):
        f = tmp_path / "output.epub"
        result = _verify_output(f, time.time() - 1)
        assert result is None

    def test_kfx_mismatch_recovery(self, tmp_path):
        """Expected .kfx missing → scanner finds the real output file."""
        expected = tmp_path / "output.kfx"  # does NOT exist
        actual = tmp_path / "Book_Title.kfx"
        actual.write_bytes(b"kfx content")
        result = _verify_output(expected, time.time() - 1)
        assert result == actual


# ---------------------------------------------------------------------------
# Integration: run_free with mocked subprocess
# ---------------------------------------------------------------------------


class TestRunFree:
    def _make_proc(self, returncode, stdout="", stderr=""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def test_happy_path_epub_output(self, small_pdf, temp_dir, settings):
        output_epub = temp_dir / "output.epub"

        def fake_run(cmd, **kwargs):
            output_epub.write_bytes(b"fake epub content")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = run_free("job1", small_pdf, "epub", temp_dir, settings=settings)

        assert result.success
        assert result.output_path == str(output_epub)
        assert result.output_size > 0

    def test_zero_byte_output_fails(self, small_pdf, temp_dir, settings):
        output_epub = temp_dir / "output.epub"

        def fake_run(cmd, **kwargs):
            output_epub.write_bytes(b"")  # 0-byte output
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = run_free("job1", small_pdf, "epub", temp_dir, settings=settings)

        assert not result.success
        assert "empty" in result.error_message.lower() or "no output" in result.error_message.lower()

    def test_nonzero_exit_code_fails(self, small_pdf, temp_dir, settings):
        def fake_run(cmd, **kwargs):
            return self._make_proc(1, stdout="Error: conversion failed\nBroken input")

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = run_free("job1", small_pdf, "epub", temp_dir, settings=settings)

        assert not result.success
        assert "Broken input" in result.error_message

    def test_timeout_returns_failure(self, small_pdf, temp_dir, settings):
        def fake_run(cmd, **kwargs):
            raise TimeoutExpired(cmd=cmd, timeout=120)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = run_free("job1", small_pdf, "epub", temp_dir, settings=settings)

        assert not result.success
        assert "timed out" in result.error_message.lower()

    def test_shell_false_enforced(self, small_pdf, temp_dir, settings):
        """subprocess.run must be called with shell=False."""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["shell"] = kwargs.get("shell", False)
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            run_free("job1", small_pdf, "epub", temp_dir, settings=settings)

        assert captured["shell"] is False

    def test_calibre_path_from_settings(self, small_pdf, temp_dir, settings):
        """Calibre command must use the path from Settings, not a hardcoded string."""
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            run_free("job1", small_pdf, "epub", temp_dir, settings=settings)

        assert captured_cmd[0] == str(settings.calibre_path)


class TestRunPremium:
    def _make_proc(self, returncode, stdout="", stderr=""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def test_uses_pipeline_script_with_cli_flag(self, small_pdf, temp_dir, settings):
        """Premium run must invoke the pipeline script with --cli."""
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            run_premium("job2", small_pdf, "epub", temp_dir, settings=settings)

        assert "--cli" in captured_cmd
        assert str(settings.pipeline_script) in captured_cmd

    def test_pythonioencoding_set_in_env(self, small_pdf, temp_dir, settings):
        """PYTHONIOENCODING must be set to utf-8 in the subprocess environment."""
        captured_env = {}

        def fake_run(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            run_premium("job2", small_pdf, "epub", temp_dir, settings=settings)

        assert captured_env.get("PYTHONIOENCODING") == "utf-8"

    def test_cwd_is_project_root(self, small_pdf, temp_dir, settings):
        """Working directory must be project root so settings.json resolves correctly."""
        captured_cwd = []

        def fake_run(cmd, **kwargs):
            captured_cwd.append(kwargs.get("cwd"))
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            run_premium("job2", small_pdf, "epub", temp_dir, settings=settings)

        assert captured_cwd[0] == str(settings.project_root)
