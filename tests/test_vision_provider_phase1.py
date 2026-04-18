"""Phase 1 regression tests for the SCRUM-274 vision provider abstraction.

These tests pin the byte-exact payload shape and cost-model behavior that
the pre-refactor visual_qa.build_vision_request and visual_qa.build_report
produced. If any of these fail after future provider work, the refactor
has stopped being a pure refactor.

Run with:
    py -3.12 -m pytest tests/test_vision_provider_phase1.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make tools/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from llm_providers import ClaudeVisionProvider  # noqa: E402


PNG_FIXTURE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
RUBRIC_FIXTURE = "RUBRIC TEXT GOES HERE"
MODEL_FIXTURE = "claude-sonnet-4-6"


@pytest.fixture
def provider() -> ClaudeVisionProvider:
    return ClaudeVisionProvider(api_key="test-key-not-used")


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------


def test_payload_top_level_keys(provider: ClaudeVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert set(payload.keys()) == {"model", "max_tokens", "system", "messages"}
    assert payload["model"] == MODEL_FIXTURE
    assert payload["max_tokens"] == 8192
    assert payload["system"] == RUBRIC_FIXTURE


def test_payload_messages_structure(provider: ClaudeVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(7, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert len(payload["messages"]) == 1
    user_msg = payload["messages"][0]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    # Per page: one text marker + one image. Plus one trailing instruction.
    assert len(content) == 3
    assert content[0] == {"type": "text", "text": "--- Page 7 ---"}
    assert content[1]["type"] == "image"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["media_type"] == "image/png"
    assert "data" in content[1]["source"]
    assert content[2]["type"] == "text"
    assert "Evaluate all pages above against the rubric." in content[2]["text"]


def test_multipage_payload_ordering(provider: ClaudeVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(3, PNG_FIXTURE), (5, PNG_FIXTURE), (8, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    content = payload["messages"][0]["content"]
    # 3 pages x 2 blocks (text + image) + 1 trailing instruction = 7
    assert len(content) == 7
    assert content[0]["text"] == "--- Page 3 ---"
    assert content[2]["text"] == "--- Page 5 ---"
    assert content[4]["text"] == "--- Page 8 ---"
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 3


def test_image_data_is_base64_encoded(provider: ClaudeVisionProvider) -> None:
    import base64

    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    encoded = payload["messages"][0]["content"][1]["source"]["data"]
    assert base64.b64decode(encoded) == PNG_FIXTURE


def test_trailing_instruction_text_unchanged(provider: ClaudeVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    expected = (
        "Evaluate all pages above against the rubric. "
        "Return ONLY valid JSON (no markdown fences, no commentary). "
        "Include a 'pages' array with one object per page evaluated, "
        "each containing: page_number, page_type, score (0-100), pass (bool), "
        "and issues (array of objects with category, severity, description, suggestion)."
    )
    assert payload["messages"][0]["content"][-1]["text"] == expected


# ---------------------------------------------------------------------------
# Cost model — must mirror the pre-refactor visual_qa.build_report logic
# ---------------------------------------------------------------------------


def test_cost_sonnet_default(provider: ClaudeVisionProvider) -> None:
    cost = provider.estimate_cost("claude-sonnet-4-6", 1_000, 500)
    assert cost == pytest.approx(1_000 / 1_000_000 * 3.00 + 500 / 1_000_000 * 15.00)


def test_cost_opus(provider: ClaudeVisionProvider) -> None:
    cost = provider.estimate_cost("claude-opus-4-6", 1_000, 500)
    assert cost == pytest.approx(1_000 / 1_000_000 * 5.00 + 500 / 1_000_000 * 25.00)


def test_cost_haiku(provider: ClaudeVisionProvider) -> None:
    cost = provider.estimate_cost("claude-haiku-4-5", 1_000, 500)
    assert cost == pytest.approx(1_000 / 1_000_000 * 1.00 + 500 / 1_000_000 * 5.00)


def test_cost_unknown_model_falls_back_to_sonnet(provider: ClaudeVisionProvider) -> None:
    fallback = provider.estimate_cost("totally-fake-model", 1_000, 500)
    sonnet = provider.estimate_cost("claude-sonnet-4-6", 1_000, 500)
    assert fallback == sonnet


def test_cost_zero_tokens(provider: ClaudeVisionProvider) -> None:
    assert provider.estimate_cost("claude-sonnet-4-6", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------


def test_provider_name_is_claude(provider: ClaudeVisionProvider) -> None:
    assert provider.name == "claude"


def test_provider_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError):
        ClaudeVisionProvider(api_key="")


# ---------------------------------------------------------------------------
# Integration with visual_qa.build_report
# ---------------------------------------------------------------------------


def test_build_report_uses_provider_cost(provider: ClaudeVisionProvider) -> None:
    """build_report must produce identical estimated_cost_usd to the pre-refactor
    inline logic, which we verify by comparing against the provider's own
    estimate_cost output."""
    import visual_qa  # noqa: WPS433

    qa_data = {
        "overall_score": 85,
        "pages": [{"page_number": 1, "score": 85}],
        "category_scores": {},
        "summary": "test",
        "top_issues": [],
    }
    report = visual_qa.build_report(
        book_path="/tmp/test.kfx",
        qa_data=qa_data,
        total_pages=100,
        pages_sampled=8,
        dpi=150,
        model="claude-sonnet-4-6",
        input_tokens=10_000,
        output_tokens=2_000,
        provider=provider,
        pass_threshold=70,
    )
    expected_cost = provider.estimate_cost("claude-sonnet-4-6", 10_000, 2_000)
    assert report["token_usage"]["estimated_cost_usd"] == round(expected_cost, 4)
    assert report["overall_score"] == 85
    assert report["overall_pass"] is True
