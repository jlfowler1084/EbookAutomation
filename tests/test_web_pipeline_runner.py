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
    _extract_gemini_cost,
    _find_newest_kfx,
    _run_vqa,
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

    def test_premium_passes_gemini_remediate_flag(self, small_pdf, temp_dir, settings):
        """EB-245: premium tier must invoke --gemini-remediate (selective fallback).

        Guards against a regression where the always-on --use-gemini flag gets
        wired instead. The two are mutually exclusive in pdf_to_balabolka.py and
        have very different cost profiles (~$0 vs ~$0.50 per conversion).
        """
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            run_premium("job_eb245_a", small_pdf, "epub", temp_dir, settings=settings)

        assert "--gemini-remediate" in captured_cmd
        assert "--use-gemini" not in captured_cmd

    def test_premium_passes_gemini_cost_limit_from_settings(self, small_pdf, temp_dir, settings):
        """EB-245: --gemini-cost-limit must read from Settings, not be hardcoded."""
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            run_premium("job_eb245_b", small_pdf, "epub", temp_dir, settings=settings)

        # The flag and its value should appear as adjacent argv tokens
        assert "--gemini-cost-limit" in captured_cmd
        flag_idx = captured_cmd.index("--gemini-cost-limit")
        assert captured_cmd[flag_idx + 1] == str(settings.premium_gemini_cost_limit_usd)

    def test_premium_default_skips_vqa_and_reports_reason(self, small_pdf, temp_dir, settings):
        """EB-245 Phase 4: with premium_vqa_enabled=False (default), VQA is skipped
        and the RunResult records skipped_reason='disabled'."""

        def fake_run(cmd, **kwargs):
            # Only the pipeline subprocess should run (the cmd contains --cli),
            # not the visual_qa.py subprocess (which contains visual_qa.py).
            assert "visual_qa.py" not in " ".join(cmd), \
                "VQA must NOT run when premium_vqa_enabled=False"
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0, stdout="No Gemini activity\n")

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = run_premium("job_vqa_off", small_pdf, "epub", temp_dir, settings=settings)

        assert result.success
        assert result.vqa_score is None
        assert result.vqa_pass is None
        assert result.vqa_cost_usd == 0.0
        assert result.vqa_skipped_reason == "disabled"
        assert result.gemini_cost_usd == 0.0  # no Gemini line in fake stdout

    def test_premium_parses_gemini_cost_from_stdout(self, small_pdf, temp_dir, settings):
        """EB-245: gemini_cost_usd is parsed from pdf_to_balabolka.py stdout."""
        gemini_log = (
            "Other unrelated log line\n"
            "  Gemini remediated 7 pages, cost: $0.0152\n"
            "Conversion complete\n"
        )

        def fake_run(cmd, **kwargs):
            output = temp_dir / "output.epub"
            output.write_bytes(b"epub")
            return self._make_proc(0, stdout=gemini_log)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = run_premium("job_gemini", small_pdf, "epub", temp_dir, settings=settings)

        assert result.success
        assert result.gemini_cost_usd == pytest.approx(0.0152)


# ---------------------------------------------------------------------------
# EB-245 helper unit tests
# ---------------------------------------------------------------------------


class TestExtractGeminiCost:
    def test_matches_canonical_pattern(self):
        stdout = "  Gemini remediated 3 pages, cost: $0.0072\n"
        assert _extract_gemini_cost(stdout) == pytest.approx(0.0072)

    def test_no_match_returns_zero(self):
        assert _extract_gemini_cost("nothing about gemini here") == 0.0

    def test_empty_stdout_returns_zero(self):
        assert _extract_gemini_cost("") == 0.0
        assert _extract_gemini_cost(None) == 0.0  # type: ignore[arg-type]

    def test_picks_first_match_when_multiple(self):
        stdout = (
            "  Gemini remediated 2 pages, cost: $0.0050\n"
            "  Gemini remediated 5 pages, cost: $0.0125\n"
        )
        # First match wins (re.search returns the leftmost)
        assert _extract_gemini_cost(stdout) == pytest.approx(0.0050)


class TestRunVqa:
    """EB-245 Phase 4: _run_vqa subprocess helper."""

    def _vqa_dir(self, output_path: Path) -> Path:
        return output_path.parent / "vqa"

    def test_skips_when_disabled(self, tmp_path, settings, monkeypatch):
        """premium_vqa_enabled=False short-circuits before subprocess is touched."""
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        # If subprocess.run gets called, the test fails because there's no patch.
        # We rely on the skip path returning before any subprocess invocation.
        result = _run_vqa(output, settings, "job_skip_disabled")

        assert result["score"] is None
        assert result["pass"] is None
        assert result["cost_usd"] == 0.0
        assert result["skipped_reason"] == "disabled"

    def test_skips_when_api_key_missing(self, tmp_path, settings, monkeypatch):
        """No OPENROUTER_API_KEY → skipped_reason='no_api_key'."""
        # Override settings to enable VQA but ensure no API key in env
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        enabled_settings = Settings(
            **{**settings.__dict__, "premium_vqa_enabled": True}
        )
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        result = _run_vqa(output, enabled_settings, "job_skip_no_key")

        assert result["skipped_reason"] == "no_api_key"

    def test_returns_score_when_report_parses(self, tmp_path, settings, monkeypatch):
        """Happy path: visual_qa.py runs, writes report.json, _run_vqa extracts the score."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        enabled_settings = Settings(
            **{**settings.__dict__, "premium_vqa_enabled": True}
        )
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        def fake_run(cmd, **kwargs):
            # Simulate visual_qa.py writing its report file
            vqa_dir = self._vqa_dir(output)
            vqa_dir.mkdir(parents=True, exist_ok=True)
            report = {
                "overall_score": 87,
                "overall_pass": True,
                "token_counts": {"cost_usd": 0.0421},
            }
            (vqa_dir / "book_visual_qa_report.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = _run_vqa(output, enabled_settings, "job_vqa_happy")

        assert result["score"] == 87
        assert result["pass"] is True
        assert result["cost_usd"] == pytest.approx(0.0421)
        assert result["skipped_reason"] is None

    def test_timeout_returns_skipped_reason(self, tmp_path, settings, monkeypatch):
        """visual_qa.py timeout → skipped_reason='timeout', conversion success preserved."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        enabled_settings = Settings(
            **{**settings.__dict__, "premium_vqa_enabled": True}
        )
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        def fake_run(cmd, **kwargs):
            raise TimeoutExpired(cmd=cmd, timeout=60)

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = _run_vqa(output, enabled_settings, "job_vqa_timeout")

        assert result["skipped_reason"] == "timeout"
        assert result["score"] is None

    def test_nonzero_exit_returns_skipped_reason(self, tmp_path, settings, monkeypatch):
        """visual_qa.py exit != 0 → skipped_reason='error', no exception leaks."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        enabled_settings = Settings(
            **{**settings.__dict__, "premium_vqa_enabled": True}
        )
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        def fake_run(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 1
            proc.stdout = ""
            proc.stderr = "OpenRouter 503 Service Unavailable"
            return proc

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = _run_vqa(output, enabled_settings, "job_vqa_5xx")

        assert result["skipped_reason"] == "error"

    def test_missing_report_file_returns_skipped_reason(self, tmp_path, settings, monkeypatch):
        """exit==0 but no report file → skipped_reason='missing_report'."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        enabled_settings = Settings(
            **{**settings.__dict__, "premium_vqa_enabled": True}
        )
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        def fake_run(cmd, **kwargs):
            # Don't write the report file
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            result = _run_vqa(output, enabled_settings, "job_vqa_no_report")

        assert result["skipped_reason"] == "missing_report"

    def test_passes_calibre_path_from_settings(self, tmp_path, settings, monkeypatch):
        """EB-245: --calibre is propagated from Settings so visual_qa.py doesn't
        re-read settings.json and pick up the Windows default on a Linux VM."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        enabled_settings = Settings(
            **{**settings.__dict__, "premium_vqa_enabled": True}
        )
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        captured_cmd: list = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            # Skip writing a report — we only care about the cmd shape
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            _run_vqa(output, enabled_settings, "job_vqa_calibre_flag")

        assert "--calibre" in captured_cmd
        idx = captured_cmd.index("--calibre")
        assert captured_cmd[idx + 1] == str(enabled_settings.calibre_path)

    def test_sets_qtwebengine_disable_sandbox(self, tmp_path, settings, monkeypatch):
        """EB-245: VQA subprocess must inject QTWEBENGINE_DISABLE_SANDBOX=1.

        Calibre's PDF output plugin uses Qt WebEngine (Chromium), which
        refuses to run as root without --no-sandbox. The web service runs as
        root on claude-dev-01, so without this env var every VQA invocation
        would fail at the Calibre input-to-PDF conversion step.
        """
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        enabled_settings = Settings(
            **{**settings.__dict__, "premium_vqa_enabled": True}
        )
        output = tmp_path / "book.kfx"
        output.write_bytes(b"kfx")

        captured_env: dict = {}

        def fake_run(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("web_service.pipeline_runner.subprocess.run", side_effect=fake_run):
            _run_vqa(output, enabled_settings, "job_vqa_qt_flag")

        assert captured_env.get("QTWEBENGINE_DISABLE_SANDBOX") == "1"
