"""Tests for hybrid routing: run_claude_fallback helper + run_visual_qa integration.

SCRUM-281 Units 2 and 3.

Test classes:
  TestRunClaudeFallback   — Unit 2: the standalone fallback helper
  TestRunVisualQAHybridRouting — Unit 3: detector + helper wired into run_visual_qa
  TestConfigRoundTrip     — Unit 4: config → runtime, CLI override, legacy compat
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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


def _make_mock_claude_provider(pages: list[dict], input_tokens: int = 500,
                                output_tokens: int = 200) -> MagicMock:
    """Return a mock that acts like ClaudeVisionProvider."""
    provider = MagicMock()
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


# ---------------------------------------------------------------------------
# Unit 2: TestRunClaudeFallback
# ---------------------------------------------------------------------------

class TestRunClaudeFallback:

    # --- Happy paths ---

    def test_happy_3_flagged_pages(self) -> None:
        """3 flagged pages → helper filters images, builds ONE Claude payload, returns 3 pages."""
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
        # build_request called exactly ONCE with exactly the 3 flagged images (in any order)
        mock_provider.build_request.assert_called_once()
        call_args = mock_provider.build_request.call_args
        sent_images = call_args[0][0]  # first positional arg
        assert {n for n, _ in sent_images} == {35, 68, 108}
        assert mock_provider.call.call_count == 1

    def test_happy_single_flagged_page(self) -> None:
        """Batch-size-1 also works: 1 flagged page → 1 Claude call."""
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
        """Empty flagged set → ([], 0, 0) without touching Claude."""
        with patch("visual_qa.ClaudeVisionProvider") as mock_cls:
            pages, in_tok, out_tok = run_claude_fallback(
                set(), [(1, PNG_FIXTURE)], "rubric", "claude-sonnet-4-6", "sk-fake-key"
            )
        assert pages == []
        assert in_tok == 0
        assert out_tok == 0
        mock_cls.assert_not_called()

    def test_api_key_none_warns_and_returns_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """api_key=None → warning logged, ([], 0, 0), ClaudeVisionProvider never instantiated."""
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
        assert any("ANTHROPIC_API_KEY" in r.message for r in caplog.records), (
            "Expected ANTHROPIC_API_KEY warning in log"
        )

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
        flagged = {35, 999}  # 999 doesn't exist in page_images
        page_images = [(35, PNG_FIXTURE)]
        claude_pages = [_make_page(35, score=75)]
        mock_provider = _make_mock_claude_provider(claude_pages)

        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
            pages, in_tok, out_tok = run_claude_fallback(
                flagged, page_images, "rubric", "claude-sonnet-4-6", "sk-fake-key"
            )

        # Only page 35 in filtered images; page 999 silently dropped
        sent_images = mock_provider.build_request.call_args[0][0]
        assert {n for n, _ in sent_images} == {35}
        assert len(pages) == 1

    # --- Error paths ---

    def test_claude_call_raises_returns_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """Claude's call() raises → logged, returns ([], 0, 0). run_visual_qa continues."""
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
        assert any("fallback" in r.message.lower() or "error" in r.levelname.lower()
                   for r in caplog.records)

    def test_malformed_claude_response_returns_partial_tokens(self) -> None:
        """Malformed JSON response → returns ([], input_tokens, output_tokens) with actual token counts."""
        mock_provider = MagicMock()
        mock_provider.name = "claude"
        mock_provider.build_request.return_value = {"model": "test", "messages": []}
        mock_provider.call.return_value = VisionResponse(
            raw_text="not valid json {{{ broken",
            input_tokens=400,
            output_tokens=20,
        )
        # parse_qa_response falls through to error dict when JSON is unparseable
        with patch("visual_qa.ClaudeVisionProvider", return_value=mock_provider):
            pages, in_tok, out_tok = run_claude_fallback(
                {35}, [(35, PNG_FIXTURE)], "rubric", "claude-sonnet-4-6", "sk-fake-key"
            )

        # parse_qa_response returns an error dict with pages=[]
        assert pages == []
        # Tokens from the (partial) response should be tracked
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
