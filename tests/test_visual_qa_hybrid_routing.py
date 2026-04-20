"""Tests for hybrid routing: run_claude_fallback helper + run_visual_qa integration.

SCRUM-281 Units 2, 3, 4, and 5.

Test classes:
  TestRunClaudeFallback        -- Unit 2: the standalone fallback helper
  TestRunVisualQAHybridRouting -- Unit 3: detector + helper wired into run_visual_qa
  TestConfigRoundTrip          -- Unit 4: config -> runtime, CLI override, legacy compat
  TestRegressionContract       -- Unit 5: frozen fixtures that lock detector+merge behavior
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# --- path setup ---
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import visual_qa
from visual_qa import run_claude_fallback

from tools.llm_providers.base import VisionResponse


# ---------------------------------------------------------------------------
# Helpers / fixtures shared across test classes
# ---------------------------------------------------------------------------

PNG_FIXTURE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24  # minimal PNG header

CORPUS_PATH = (
    Path(__file__).resolve().parent.parent
    / "tools" / "visual_qa_fallback_fingerprints.json"
)


def _make_page(page_number: int, score: int = 90, issues: list | None = None) -> dict:
    return {
        "page_number": page_number,
        "page_type": "body",
        "score": score,
        "pass": score >= 70,
        "issues": issues if issues is not None else [],
    }


def _make_claude_raw_response(pages: list[dict]) -> str:
    return json.dumps({"pages": pages})


_PROVIDER_ATTRS = ["name", "build_request", "call", "estimate_cost"]


def _make_mock_claude_provider(pages: list[dict], input_tokens: int = 500,
                               output_tokens: int = 200) -> MagicMock:
    """Return a mock that acts like ClaudeVisionProvider.

    Uses spec to prevent MagicMock from auto-creating two_pass_call,
    which would cause visual_qa.py to route via the wrong branch.
    """
    provider = MagicMock(spec=_PROVIDER_ATTRS)
    provider.name = "claude"
    provider.build_request.return_value = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": []}],
    }
    provider.call.return_value = VisionResponse(
        raw_text=_make_claude_raw_response(pages),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    provider.estimate_cost.return_value = 0.01
    return provider


def _make_mock_cloud_provider(raw_response: str, input_tokens: int = 300,
                               output_tokens: int = 100) -> MagicMock:
    """Return a mock that acts like CloudVLProvider (no two_pass_call)."""
    provider = MagicMock(spec=_PROVIDER_ATTRS)
    provider.name = "cloud_vl"
    provider.build_request.return_value = {"model": "qwen", "messages": []}
    provider.call.return_value = VisionResponse(
        raw_text=raw_response, input_tokens=input_tokens, output_tokens=output_tokens)
    provider.estimate_cost.return_value = 0.005
    return provider


# ---------------------------------------------------------------------------
# Unit 2: TestRunClaudeFallback
# ---------------------------------------------------------------------------

class TestRunClaudeFallback:

    # --- Happy paths ---

    def test_happy_3_flagged_pages(self) -> None:
        """3 flagged pages -> helper filters images, builds ONE Claude payload, returns 3 pages."""
        flagged = {35, 68, 108}
        page_images = [
            (1, PNG_FIXTURE),
            (35, PNG_FIXTURE),
            (68, PNG_FIXTURE),
            (108, PNG_FIXTURE),
            (173, PNG_FIXTURE),
        ]
        claude_pages = [
            _make_page(35, score=75, issues=[{"category": "text_integrity", "severity": "moderate",
                                              "description": "Ligature broken", "suggestion": "Check font."}]),
            _make_page(68, score=70, issues=[{"category": "layout", "severity": "minor",
                                              "description": "Margin narrow", "suggestion": "Widen."}]),
            _make_page(108, score=80),
        ]
        mock_provider = _make_mock_claude_provider(claude_pages, input_tokens=600, output_tokens=250)

        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
            pages, in_tok, out_tok = run_claude_fallback(
                flagged, page_images, "rubric text", "claude-sonnet-4-6", "sk-fake-key"
            )

        assert len(pages) == 3
        assert {p["page_number"] for p in pages} == {35, 68, 108}
        assert in_tok == 600
        assert out_tok == 250
        mock_provider.build_request.assert_called_once()
        sent_images = mock_provider.build_request.call_args[0][0]
        assert {n for n, _ in sent_images} == {35, 68, 108}
        assert mock_provider.call.call_count == 1

    def test_happy_single_flagged_page(self) -> None:
        """Batch-size-1 also works: 1 flagged page -> 1 Claude call."""
        flagged = {35}
        page_images = [(1, PNG_FIXTURE), (35, PNG_FIXTURE)]
        claude_pages = [_make_page(35, score=72, issues=[
            {"category": "text_integrity", "severity": "moderate",
             "description": "Rendering artifact on line 3", "suggestion": "Check source PDF."}
        ])]
        mock_provider = _make_mock_claude_provider(claude_pages, input_tokens=300, output_tokens=100)

        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
            pages, in_tok, out_tok = run_claude_fallback(
                flagged, page_images, "rubric", "claude-sonnet-4-6", "sk-fake-key"
            )

        assert len(pages) == 1
        assert pages[0]["page_number"] == 35
        assert in_tok == 300
        assert out_tok == 100

    # --- Edge cases ---

    def test_empty_flagged_set_returns_empty(self) -> None:
        """Empty flagged set -> ([], 0, 0) without touching Claude."""
        with patch("visual_qa.ClaudeVisionProvider") as mock_cls:
            pages, in_tok, out_tok = run_claude_fallback(
                set(), [(1, PNG_FIXTURE)], "rubric", "claude-sonnet-4-6", "sk-fake-key"
            )
        assert pages == []
        assert in_tok == 0
        assert out_tok == 0
        mock_cls.assert_not_called()

    def test_api_key_none_warns_and_returns_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """api_key=None -> warning logged, ([], 0, 0), ClaudeVisionProvider never instantiated."""
        import logging
        with caplog.at_level(logging.WARNING, logger="visual_qa"):
            with patch("visual_qa.ClaudeVisionProvider") as mock_cls:
                pages, in_tok, out_tok = run_claude_fallback(
                    {35}, [(35, PNG_FIXTURE)], "rubric", "claude-sonnet-4-6", None
                )

        assert pages == []
        assert in_tok == 0
        assert out_tok == 0
        mock_cls.assert_not_called()
        assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)

    def test_api_key_empty_string_treated_as_missing(self) -> None:
        """api_key='' (empty string) is treated the same as None."""
        with patch("visual_qa.ClaudeVisionProvider") as mock_cls:
            pages, in_tok, out_tok = run_claude_fallback(
                {35}, [(35, PNG_FIXTURE)], "rubric", "claude-sonnet-4-6", ""
            )
        assert pages == []
        mock_cls.assert_not_called()

    def test_flagged_page_not_in_images_skipped(self) -> None:
        """Flagged page number not present in page_images is silently dropped."""
        flagged = {35, 999}
        page_images = [(35, PNG_FIXTURE)]
        claude_pages = [_make_page(35, score=75)]
        mock_provider = _make_mock_claude_provider(claude_pages)

        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
            pages, in_tok, out_tok = run_claude_fallback(
                flagged, page_images, "rubric", "claude-sonnet-4-6", "sk-fake-key"
            )

        sent_images = mock_provider.build_request.call_args[0][0]
        assert {n for n, _ in sent_images} == {35}
        assert len(pages) == 1

    # --- Error paths ---

    def test_claude_call_raises_returns_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """Claude's call() raises -> logged, returns ([], 0, 0)."""
        import logging
        mock_provider = MagicMock()
        mock_provider.name = "claude"
        mock_provider.build_request.return_value = {"model": "test", "messages": []}
        mock_provider.call.side_effect = RuntimeError("API timeout")

        with caplog.at_level(logging.ERROR, logger="visual_qa"):
            with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
                pages, in_tok, out_tok = run_claude_fallback(
                    {35}, [(35, PNG_FIXTURE)], "rubric", "claude-sonnet-4-6", "sk-fake-key"
                )

        assert pages == []
        assert in_tok == 0
        assert out_tok == 0

    def test_malformed_claude_response_returns_partial_tokens(self) -> None:
        """Malformed JSON -> returns ([], input_tokens, output_tokens) so tokens are tracked."""
        mock_provider = MagicMock()
        mock_provider.name = "claude"
        mock_provider.build_request.return_value = {"model": "test", "messages": []}
        mock_provider.call.return_value = VisionResponse(
            raw_text="not valid json {{{ broken",
            input_tokens=400,
            output_tokens=20,
        )
        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
            pages, in_tok, out_tok = run_claude_fallback(
                {35}, [(35, PNG_FIXTURE)], "rubric", "claude-sonnet-4-6", "sk-fake-key"
            )

        assert pages == []
        assert in_tok == 400
        assert out_tok == 20

    # --- Integration ---

    def test_integration_all_flagged_pages_in_result(self) -> None:
        """All flagged page numbers appear in the returned pages list."""
        flagged = {2, 35, 68}
        page_images = [(n, PNG_FIXTURE) for n in (1, 2, 35, 68, 173)]
        claude_pages = [_make_page(n, score=75) for n in (2, 35, 68)]
        mock_provider = _make_mock_claude_provider(claude_pages)

        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
            pages, in_tok, out_tok = run_claude_fallback(
                flagged, page_images, "rubric", "claude-sonnet-4-6", "sk-test"
            )

        returned_pns = {p["page_number"] for p in pages}
        assert returned_pns == flagged


# ---------------------------------------------------------------------------
# Unit 3 helpers: patch heavy I/O in run_visual_qa
# ---------------------------------------------------------------------------

def _make_vqa_io_patches(input_file: Path, page_images_fixture: list) -> list:
    """Return patches that mock all I/O in run_visual_qa, keeping routing logic real."""
    return [
        patch("visual_qa.convert_to_pdf", return_value=str(input_file)),
        patch("visual_qa.get_pdf_page_count", return_value=200),
        patch("visual_qa.get_pdf_bookmarks", return_value=[]),
        patch("visual_qa.select_sample_pages",
              return_value=[pn for pn, _ in page_images_fixture]),
        patch("visual_qa.find_poppler_path", return_value=""),
        patch("visual_qa.render_pages_to_png", return_value=page_images_fixture),
    ]


def _run_vqa(tmp_path: Path, provider: MagicMock, page_images_fixture: list,
             extra_env: dict | None = None, **extra_kwargs):
    """Run run_visual_qa with all I/O mocked. Returns the report dict."""
    input_file = tmp_path / "book.pdf"
    input_file.write_bytes(b"%PDF-1.4")

    patches = _make_vqa_io_patches(input_file, page_images_fixture)
    if extra_env is not None:
        patches.append(patch.dict(os.environ, extra_env, clear=True))

    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        report = visual_qa.run_visual_qa(
            input_path=str(input_file),
            provider=provider,
            calibre_path="calibre",
            poppler_path=None,
            output_dir=str(tmp_path),
            dpi=100,
            max_pages=8,
            model="test-model",
            rubric_path="",  # agent prompt is loaded automatically
            pass_threshold=70,
            **extra_kwargs,
        )
    return report


# ---------------------------------------------------------------------------
# Unit 3: TestRunVisualQAHybridRouting
# ---------------------------------------------------------------------------

class TestRunVisualQAHybridRouting:

    # --- Characterization: Claude-primary no-op (R4 regression guard) ---

    def test_r4_claude_primary_no_fallback(self, tmp_path: Path) -> None:
        """REGRESSION GUARD (R4): Claude-primary with fallback_enabled=False.
        Report shape matches pre-Unit-3 behavior -- no fallback_* fields."""
        page_images_fixture = [(1, PNG_FIXTURE), (2, PNG_FIXTURE)]
        claude_pages = [_make_page(1, score=90), _make_page(2, score=85)]
        provider = _make_mock_claude_provider(claude_pages, input_tokens=500, output_tokens=200)
        provider.name = "claude"

        report = _run_vqa(tmp_path, provider, page_images_fixture,
                          fallback_enabled=False)

        # Primary called once, no fallback invoked
        assert provider.build_request.call_count == 1
        token_usage = report["token_usage"]
        assert "fallback_input_tokens" not in token_usage
        assert "fallback_output_tokens" not in token_usage
        assert "fallback_estimated_cost_usd" not in token_usage
        assert token_usage["input_tokens"] == 500
        assert token_usage["output_tokens"] == 200

    # --- Happy path: cloud primary, detector flags pages ---

    def test_happy_cloud_primary_detector_fires(self, tmp_path: Path) -> None:
        """Cloud primary, all-empty-issues pages -> Matcher 3 -> Claude called once."""
        page_images_fixture = [(35, PNG_FIXTURE), (68, PNG_FIXTURE)]
        primary_raw = json.dumps({"pages": [
            _make_page(35, score=95),
            _make_page(68, score=90),
        ]})
        cloud_provider = _make_mock_cloud_provider(primary_raw, input_tokens=300, output_tokens=100)

        claude_pages = [
            _make_page(35, score=72, issues=[{
                "category": "text_integrity", "severity": "moderate",
                "description": "Code block unreadable", "suggestion": "Check font."}]),
            _make_page(68, score=68, issues=[{
                "category": "layout", "severity": "minor",
                "description": "Column misaligned", "suggestion": "Adjust."}]),
        ]
        mock_claude = _make_mock_claude_provider(claude_pages, input_tokens=400, output_tokens=180)

        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_claude):
            report = _run_vqa(tmp_path, cloud_provider, page_images_fixture,
                              extra_env={"ANTHROPIC_API_KEY": "sk-fake-key"},
                              fallback_enabled=True,
                              fallback_claude_model="claude-sonnet-4-6",
                              fallback_corpus_path=str(CORPUS_PATH),
                              fallback_empty_issues_score_threshold=80)

        mock_claude.build_request.assert_called_once()
        token_usage = report["token_usage"]
        assert token_usage.get("fallback_input_tokens") == 400
        assert token_usage.get("fallback_output_tokens") == 180
        assert "fallback_estimated_cost_usd" in token_usage
        assert "fallback_model" in token_usage
        # Pages should have Claude's real findings
        issues_total = sum(len(p.get("issues", [])) for p in report.get("pages", []))
        assert issues_total >= 1

    # --- Happy path: cloud primary, detector flags 0 pages ---

    def test_happy_cloud_no_flags_claude_not_called(self, tmp_path: Path) -> None:
        """Cloud primary with real specific issues -> detector flags 0 -> Claude not called."""
        page_images_fixture = [(1, PNG_FIXTURE)]
        primary_raw = json.dumps({"pages": [
            _make_page(1, score=65, issues=[{
                "category": "text_integrity", "severity": "moderate",
                "description": "Ligature fi broken on line 4",
                "suggestion": "Check source font embedding."}])
        ]})
        cloud_provider = _make_mock_cloud_provider(primary_raw, input_tokens=200, output_tokens=60)

        with patch("visual_qa.ClaudeVisionProvider") as mock_claude_cls:
            report = _run_vqa(tmp_path, cloud_provider, page_images_fixture,
                              extra_env={"ANTHROPIC_API_KEY": "sk-fake-key"},
                              fallback_enabled=True,
                              fallback_corpus_path=str(CORPUS_PATH),
                              fallback_empty_issues_score_threshold=80)

        mock_claude_cls.assert_not_called()
        token_usage = report["token_usage"]
        assert "fallback_input_tokens" not in token_usage

    # --- R4: Claude primary short-circuits detector even with fallback_enabled=True ---

    def test_r4_claude_primary_enabled_still_no_self_fallback(self, tmp_path: Path) -> None:
        """R4: provider.name=='claude' -> detector skipped even when fallback_enabled=True."""
        page_images_fixture = [(1, PNG_FIXTURE)]
        claude_pages = [_make_page(1, score=95)]  # would trigger Matcher 1 if detector ran
        provider = _make_mock_claude_provider(claude_pages, input_tokens=300, output_tokens=100)
        provider.name = "claude"

        with patch("visual_qa.ClaudeVisionProvider") as mock_claude_cls:
            report = _run_vqa(tmp_path, provider, page_images_fixture,
                              extra_env={"ANTHROPIC_API_KEY": "sk-fake-key"},
                              fallback_enabled=True,
                              fallback_corpus_path=str(CORPUS_PATH),
                              fallback_empty_issues_score_threshold=80)

        # ClaudeVisionProvider constructor should NOT be called a second time
        mock_claude_cls.assert_not_called()
        assert "fallback_input_tokens" not in report["token_usage"]

    # --- Error path: ANTHROPIC_API_KEY missing -> primary results survive (R5) ---

    def test_r5_missing_api_key_primary_results_survive(self, tmp_path: Path,
                                                         caplog: pytest.LogCaptureFixture) -> None:
        """R5: Missing ANTHROPIC_API_KEY -> warning, primary results shipped intact."""
        import logging
        page_images_fixture = [(35, PNG_FIXTURE)]
        primary_raw = json.dumps({"pages": [_make_page(35, score=95)]})
        cloud_provider = _make_mock_cloud_provider(primary_raw, input_tokens=200, output_tokens=80)

        env_without_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

        with caplog.at_level(logging.WARNING, logger="visual_qa"):
            report = _run_vqa(tmp_path, cloud_provider, page_images_fixture,
                              extra_env=env_without_key,
                              fallback_enabled=True,
                              fallback_corpus_path=str(CORPUS_PATH),
                              fallback_empty_issues_score_threshold=80)

        assert report.get("pages"), "Primary results must survive when API key is missing"
        assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records)

    # --- Error path: detector raises -> primary-only report shipped ---

    def test_detector_failure_primary_results_survive(self, tmp_path: Path,
                                                       caplog: pytest.LogCaptureFixture) -> None:
        """Detector raising unexpectedly -> caught + logged, primary-only report shipped."""
        import logging
        page_images_fixture = [(35, PNG_FIXTURE)]
        primary_raw = json.dumps({"pages": [_make_page(35, score=95)]})
        cloud_provider = _make_mock_cloud_provider(primary_raw, input_tokens=200, output_tokens=80)

        with (
            patch("visual_qa.FallbackFingerprintDetector") as mock_detector_cls,
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-fake-key"}),
            caplog.at_level(logging.ERROR, logger="visual_qa"),
        ):
            mock_detector_cls.from_corpus.side_effect = RuntimeError("Corpus load failed")
            report = _run_vqa(tmp_path, cloud_provider, page_images_fixture,
                              fallback_enabled=True,
                              fallback_corpus_path=str(CORPUS_PATH),
                              fallback_empty_issues_score_threshold=80)

        assert report.get("pages"), "Primary results must survive after detector failure"
        assert "fallback_input_tokens" not in report.get("token_usage", {})

    # --- Integration: merge by page_number ---

    def test_merge_by_page_number_replaces_primary_entries(self, tmp_path: Path) -> None:
        """Claude results for flagged pages replace primary entries; others kept."""
        page_images_fixture = [(2, PNG_FIXTURE), (35, PNG_FIXTURE), (68, PNG_FIXTURE)]
        # All 3 pages have issues==[] + score=95 -> Matcher 3 fires
        primary_raw = json.dumps({"pages": [
            _make_page(2, score=95),
            _make_page(35, score=95),
            _make_page(68, score=95),
        ]})
        cloud_provider = _make_mock_cloud_provider(primary_raw, input_tokens=300, output_tokens=100)

        # Claude returns data for pages 35 and 68 only
        claude_pages = [
            _make_page(35, score=65, issues=[{
                "category": "text_integrity", "severity": "moderate",
                "description": "Code block unreadable", "suggestion": "Fix font."}]),
            _make_page(68, score=70, issues=[{
                "category": "layout", "severity": "minor",
                "description": "Column misaligned", "suggestion": "Adjust."}]),
        ]
        mock_claude = _make_mock_claude_provider(claude_pages, input_tokens=350, output_tokens=150)

        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_claude):
            report = _run_vqa(tmp_path, cloud_provider, page_images_fixture,
                              extra_env={"ANTHROPIC_API_KEY": "sk-fake-key"},
                              fallback_enabled=True,
                              fallback_claude_model="claude-sonnet-4-6",
                              fallback_corpus_path=str(CORPUS_PATH),
                              fallback_empty_issues_score_threshold=80)

        pages_by_num = {p["page_number"]: p for p in report.get("pages", [])}
        assert set(pages_by_num.keys()) == {2, 35, 68}
        assert pages_by_num[35]["issues"], "Page 35 must have Claude's non-empty issues"
        assert pages_by_num[68]["issues"], "Page 68 must have Claude's non-empty issues"
        token_usage = report["token_usage"]
        assert token_usage.get("fallback_input_tokens") == 350
        assert token_usage.get("fallback_output_tokens") == 150


# ---------------------------------------------------------------------------
# Unit 4: TestConfigRoundTrip
# ---------------------------------------------------------------------------

class TestConfigRoundTrip:
    """Verify fallback config flows from settings.json → main() → run_visual_qa().

    Strategy: mock load_settings_json and run_visual_qa, then call main() with
    sys.argv patched. Inspect the kwargs passed to run_visual_qa.
    """

    _BASE_SETTINGS = {
        "paths": {
            "calibre": r"C:\Program Files\Calibre2\ebook-convert.exe",
            "poppler": "",
        },
        "api_models": {"sonnet_latest": "claude-sonnet-4-6"},
        "visual_qa": {
            "dpi": 100,
            "max_pages": 8,
            "pass_threshold": 70,
            "provider": "cloud",
            "cloud_host": "openrouter",
            "cloud_model": "qwen/qwen3-vl-30b-a3b-instruct",
            "local_model": "qwen3.5-35b-a3b-fp8",
            "local_base_url": "http://localhost:8000/v1",
            "rubric_path": "",
            "fallback": {
                "enabled": True,
                "claude_model": "claude-sonnet-4-6",
                "empty_issues_score_threshold": 80,
                "corpus_path": r"tools\visual_qa_fallback_fingerprints.json",
            },
        },
    }

    def _run_main_capture_kwargs(self, tmp_path, settings_override=None,
                                 extra_argv=None, extra_env=None):
        """Call main() and capture kwargs passed to run_visual_qa."""
        import copy
        settings = copy.deepcopy(self._BASE_SETTINGS)
        if settings_override:
            # Shallow merge of visual_qa sub-dict
            vqa = settings_override.get("visual_qa", {})
            settings["visual_qa"].update(vqa)
            if "fallback" in settings_override.get("visual_qa", {}):
                settings["visual_qa"]["fallback"] = settings_override["visual_qa"]["fallback"]

        input_file = tmp_path / "book.kfx"
        input_file.write_bytes(b"dummy")

        captured = {}

        def fake_run_visual_qa(**kwargs):
            captured.update(kwargs)
            return {
                "book": "test", "overall_score": 90, "overall_pass": True,
                "pages_sampled": 1, "pages_total": 100, "summary": "ok",
                "token_usage": {"estimated_cost_usd": 0.001},
            }

        argv = ["visual_qa.py", "--input", str(input_file),
                "--provider", "claude", "--api-key", "sk-fake"]
        if extra_argv:
            argv.extend(extra_argv)

        env = {"ANTHROPIC_API_KEY": "sk-fake"}
        if extra_env:
            env.update(extra_env)

        with (
            patch("visual_qa.load_settings_json", return_value=settings),
            patch("visual_qa.run_visual_qa", side_effect=fake_run_visual_qa),
            patch("visual_qa.ClaudeVisionProvider"),
            patch.object(sys, "argv", argv),
            patch.dict(os.environ, env, clear=True),
        ):
            try:
                visual_qa.main()
            except SystemExit:
                pass

        return captured

    def test_fallback_config_flows_to_run_visual_qa(self, tmp_path):
        """Config values from settings.json reach run_visual_qa as kwargs."""
        captured = self._run_main_capture_kwargs(tmp_path)
        assert captured.get("fallback_enabled") is True
        assert captured.get("fallback_claude_model") == "claude-sonnet-4-6"
        assert captured.get("fallback_corpus_path") == r"tools\visual_qa_fallback_fingerprints.json"

    def test_cli_flag_overrides_config_fallback_enabled(self, tmp_path):
        """--fallback-enabled false disables routing even when config says enabled."""
        captured = self._run_main_capture_kwargs(tmp_path,
                                                 extra_argv=["--fallback-enabled", "false"])
        assert captured.get("fallback_enabled") is False

    def test_cli_flag_overrides_fallback_claude_model(self, tmp_path):
        """--fallback-claude-model overrides config model."""
        captured = self._run_main_capture_kwargs(tmp_path,
                                                 extra_argv=["--fallback-claude-model",
                                                             "claude-haiku-4-5-20251001"])
        assert captured.get("fallback_claude_model") == "claude-haiku-4-5-20251001"

    def test_cli_flag_overrides_corpus_path(self, tmp_path):
        """--fallback-corpus-path overrides config corpus path."""
        captured = self._run_main_capture_kwargs(tmp_path,
                                                 extra_argv=["--fallback-corpus-path",
                                                             r"custom\fingerprints.json"])
        assert captured.get("fallback_corpus_path") == r"custom\fingerprints.json"

    def test_legacy_config_no_fallback_block(self, tmp_path):
        """Settings without a fallback block uses hardcoded defaults (graceful degradation)."""
        settings_override = {"visual_qa": {"fallback": {}}}
        captured = self._run_main_capture_kwargs(tmp_path, settings_override=settings_override)
        assert captured.get("fallback_enabled") is True
        assert captured.get("fallback_claude_model") == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Unit 5: TestRegressionContract
# ---------------------------------------------------------------------------
# Frozen fixtures derived from SCRUM-283 corpus smoke artifacts:
#   - Python Max (scrum283_unit5b): all pages score 85-95, no issues -> Matcher 3
#   - Oil Kings A3B (scrum283_unit3): page 119 has 2 real non-fingerprint issues
#   - Borderline batch: mixed pages, one empty+85 score -> Matcher 1 only
#
# These fixtures lock detector+threshold behavior. Changing the fingerprint corpus
# or the 80-threshold requires deliberate acknowledgment via these assertions.
# ---------------------------------------------------------------------------

_PYTHON_MAX_PAGES_BATCH = [
    # All 8 pages from Python Max smoke: empty issues, scores 85-95
    # Source: scrum283_unit5b_6book_smoke_qwen_vl_max Python report
    {"page_number": 1,   "page_type": "cover",  "score": 95, "pass": True, "issues": []},
    {"page_number": 2,   "page_type": "body",   "score": 95, "pass": True, "issues": []},
    {"page_number": 3,   "page_type": "body",   "score": 85, "pass": True, "issues": []},
    {"page_number": 35,  "page_type": "body",   "score": 95, "pass": True, "issues": []},
    {"page_number": 68,  "page_type": "body",   "score": 95, "pass": True, "issues": []},
    {"page_number": 108, "page_type": "body",   "score": 95, "pass": True, "issues": []},
    {"page_number": 139, "page_type": "body",   "score": 95, "pass": True, "issues": []},
    {"page_number": 173, "page_type": "body",   "score": 95, "pass": True, "issues": []},
]

_OIL_KINGS_A3B_PAGE_119 = {
    # Oil Kings A3B page 119: 2 specific structural issues, no fingerprint phrases
    # Source: scrum283_unit3_6book_smoke_a3b Oil Kings report
    "page_number": 119,
    "page_type": "chapter_start",
    "score": 85,
    "pass": True,
    "issues": [
        {
            "category": "heading_formatting",
            "description": "Chapter heading uses all caps, inconsistent with other chapter headings",
            "severity": "minor",
            "suggestion": "Standardize heading case across all chapters",
        },
        {
            "category": "paragraph_flow",
            "description": "Some paragraphs have inconsistent indentation",
            "severity": "minor",
            "suggestion": "Apply consistent paragraph formatting rules",
        },
    ],
}

_BORDERLINE_BATCH = [
    # Page with real findings (issues non-empty) — Matcher 3 gate stays closed
    {
        "page_number": 10,
        "page_type": "body",
        "score": 80,
        "pass": True,
        "issues": [{"category": "text_integrity", "description": "OCR artifact in footnote",
                    "severity": "minor", "suggestion": "Review OCR"}],
    },
    # Borderline page: empty issues, score exactly at threshold -> Matcher 1 fires
    {
        "page_number": 20,
        "page_type": "body",
        "score": 85,
        "pass": True,
        "issues": [],
    },
]


class TestRegressionContract:
    """Frozen detector behavior against corpus-derived artifacts.

    These tests freeze the threshold+corpus semantics so that future fingerprint
    corpus changes that alter detection must explicitly update these assertions.
    Tests run entirely offline — no API calls.
    """

    def _make_detector_with_real_corpus(self):
        from tools.llm_providers.fingerprint_detector import (
            FallbackFingerprintDetector, FingerprintSettings,
        )
        detector = FallbackFingerprintDetector.from_corpus(CORPUS_PATH)
        settings = FingerprintSettings(
            empty_issues_score_threshold=80,
            substring_corpus=tuple(detector._fingerprints),
            match_category_scores_collapse=True,
        )
        return detector, settings

    def test_fixture1_python_max_all_empty_batch_flags_all(self):
        """Matcher 3 fires on all-empty-issues Python Max batch: all 8 pages flagged."""
        detector, settings = self._make_detector_with_real_corpus()
        flagged = detector.detect(_PYTHON_MAX_PAGES_BATCH, settings)
        expected = {1, 2, 3, 35, 68, 108, 139, 173}
        assert flagged == expected, (
            f"Expected all Python Max pages flagged. Got {flagged}. "
            "If threshold or corpus changed, update this frozen fixture."
        )

    def test_fixture2_oil_kings_real_issues_not_flagged(self):
        """Oil Kings page 119 with 2 real non-fingerprint issues: detector does NOT flag."""
        detector, settings = self._make_detector_with_real_corpus()
        flagged = detector.detect([_OIL_KINGS_A3B_PAGE_119], settings)
        assert flagged == set(), (
            f"Expected Oil Kings page 119 clean. Got {flagged}. "
            "Check if a new fingerprint substring accidentally matches real findings."
        )

    def test_fixture3_borderline_mixed_batch_flags_empty_page(self):
        """Mixed batch: Matcher 3 gate stays closed; Matcher 1 flags the empty-issues page."""
        detector, settings = self._make_detector_with_real_corpus()
        flagged = detector.detect(_BORDERLINE_BATCH, settings)
        # Only page 20 (empty issues, score 85 >= 80) should be flagged
        assert flagged == {20}, (
            f"Expected only page 20 flagged from borderline batch. Got {flagged}. "
            "Threshold or Matcher 3 logic may have changed."
        )

    def test_fixture1_with_collapse_disabled_still_flags_high_score_pages(self):
        """Without Matcher 3, Matcher 1 still flags individual Python pages >= 80."""
        from tools.llm_providers.fingerprint_detector import (
            FallbackFingerprintDetector, FingerprintSettings,
        )
        detector = FallbackFingerprintDetector.from_corpus(CORPUS_PATH)
        settings = FingerprintSettings(
            empty_issues_score_threshold=80,
            substring_corpus=tuple(detector._fingerprints),
            match_category_scores_collapse=False,  # disable Matcher 3
        )
        flagged = detector.detect(_PYTHON_MAX_PAGES_BATCH, settings)
        # page 3 (score=85) and all 95-score pages (>=80) still flagged by Matcher 1
        high_score_pages = {p["page_number"] for p in _PYTHON_MAX_PAGES_BATCH
                            if p["score"] >= 80 and not p["issues"]}
        assert flagged == high_score_pages
