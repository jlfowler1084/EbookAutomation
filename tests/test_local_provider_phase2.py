"""Phase 2 tests for the SCRUM-275 LocalVisionProvider.

These tests pin the payload shape, encoding, and critical runtime parameters
(especially enable_thinking=False) for the local sb-chat provider. They run
without a live sb-chat server — all network calls are mocked.

Run with:
    py -3.12 -m pytest tests/test_local_provider_phase2.py -v
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make tools/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from llm_providers import LocalVisionProvider  # noqa: E402
from llm_providers.base import VisionResponse  # noqa: E402


PNG_FIXTURE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
RUBRIC_FIXTURE = "RUBRIC TEXT GOES HERE"
MODEL_FIXTURE = "qwen3.5-35b-a3b-fp8"


@pytest.fixture
def provider() -> LocalVisionProvider:
    return LocalVisionProvider(base_url="http://localhost:8000/v1")


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------


def test_payload_has_messages_key(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert "messages" in payload
    assert "model" in payload
    assert payload["model"] == MODEL_FIXTURE


def test_payload_system_message_carries_rubric(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == RUBRIC_FIXTURE


def test_payload_user_message_is_second(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    messages = payload["messages"]
    assert len(messages) == 2
    assert messages[1]["role"] == "user"


def test_payload_user_content_has_page_text_and_image(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(7, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    user_content = payload["messages"][1]["content"]
    # Per page: one text marker + one image_url block. Plus one trailing instruction.
    assert len(user_content) == 3
    assert user_content[0] == {"type": "text", "text": "--- Page 7 ---"}
    assert user_content[1]["type"] == "image_url"
    assert "url" in user_content[1]["image_url"]
    assert user_content[2]["type"] == "text"


def test_payload_multipage_ordering(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(3, PNG_FIXTURE), (5, PNG_FIXTURE), (8, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    user_content = payload["messages"][1]["content"]
    # 3 pages x 2 blocks + 1 trailing instruction = 7
    assert len(user_content) == 7
    assert user_content[0]["text"] == "--- Page 3 ---"
    assert user_content[2]["text"] == "--- Page 5 ---"
    assert user_content[4]["text"] == "--- Page 8 ---"
    image_blocks = [b for b in user_content if b.get("type") == "image_url"]
    assert len(image_blocks) == 3


# ---------------------------------------------------------------------------
# Base64 encoding
# ---------------------------------------------------------------------------


def test_image_data_is_base64_data_uri(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    user_content = payload["messages"][1]["content"]
    image_block = user_content[1]
    url = image_block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    b64_part = url[len("data:image/png;base64,"):]
    assert base64.b64decode(b64_part) == PNG_FIXTURE


# ---------------------------------------------------------------------------
# Trailing instruction text — must match claude_provider for rubric parity
# ---------------------------------------------------------------------------


def test_trailing_instruction_text_matches_claude_provider(provider: LocalVisionProvider) -> None:
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
    last_block = payload["messages"][1]["content"][-1]
    assert last_block["type"] == "text"
    assert last_block["text"] == expected


# ---------------------------------------------------------------------------
# LOAD-BEARING: enable_thinking=False
# Without this, Qwen3 reasoning parser consumes max_tokens budget on <think>
# blocks, leaving message.content empty. See SCRUM-275 plan amendment.
# ---------------------------------------------------------------------------


def test_enable_thinking_is_false(provider: LocalVisionProvider) -> None:
    """THE critical guard — must never be accidentally removed."""
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert "extra_body" in payload, "extra_body is missing from payload"
    assert "chat_template_kwargs" in payload["extra_body"], (
        "chat_template_kwargs missing from extra_body"
    )
    assert payload["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False, (
        "enable_thinking must be False — if True, Qwen3 reasoning parser will "
        "consume max_tokens budget on <think> blocks and return empty content"
    )


# ---------------------------------------------------------------------------
# Temperature and sampling penalties
# ---------------------------------------------------------------------------


def test_temperature_is_0_1(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["temperature"] == pytest.approx(0.1), (
        "temperature must be 0.1 — temperature=0 triggers repetition loops on visual inputs"
    )


def test_no_frequency_penalty(provider: LocalVisionProvider) -> None:
    """Absence is load-bearing. See SCRUM-275 smoke evidence 2026-04-18:
    frequency_penalty=0.3 penalizes repeated JSON schema tokens across
    multi-page batches, causing mid-generation dropout. Must not be re-added.
    """
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert "frequency_penalty" not in payload, (
        "frequency_penalty must not be set — it breaks multi-page JSON output"
    )


# ---------------------------------------------------------------------------
# response_format
# ---------------------------------------------------------------------------


def test_response_format_is_json_object(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------


def test_estimate_cost_returns_zero(provider: LocalVisionProvider) -> None:
    assert provider.estimate_cost(MODEL_FIXTURE, 0, 0) == 0.0


def test_estimate_cost_returns_zero_regardless_of_tokens(provider: LocalVisionProvider) -> None:
    assert provider.estimate_cost(MODEL_FIXTURE, 1_000_000, 500_000) == 0.0


def test_estimate_cost_is_exactly_float_zero(provider: LocalVisionProvider) -> None:
    result = provider.estimate_cost(MODEL_FIXTURE, 99_999, 12_345)
    assert result == 0.0
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------


def test_provider_name_is_local(provider: LocalVisionProvider) -> None:
    assert provider.name == "local"


def test_default_base_url() -> None:
    p = LocalVisionProvider()
    assert p._base_url == "http://localhost:8000/v1"


def test_custom_base_url() -> None:
    p = LocalVisionProvider(base_url="http://192.168.1.50:9000/v1")
    assert p._base_url == "http://192.168.1.50:9000/v1"


# ---------------------------------------------------------------------------
# parse_qa_response retry on JSONDecodeError
# ---------------------------------------------------------------------------


def test_parse_qa_response_retry_on_json_error() -> None:
    """parse_qa_response must attempt one repair re-prompt on JSONDecodeError.

    The mock provider returns invalid JSON on the first call, then valid JSON
    on the repair call. The function should return the valid result.
    """
    # Import at call time to avoid circular import issues with sys.path
    import visual_qa  # noqa: WPS433

    valid_payload = {
        "overall_score": 88,
        "pages": [{"page_number": 1, "score": 88}],
        "category_scores": {},
        "summary": "repaired",
        "top_issues": [],
    }

    # First call returns bad JSON; second call (repair) returns good JSON
    mock_response_good = VisionResponse(
        raw_text=json.dumps(valid_payload),
        input_tokens=100,
        output_tokens=50,
    )

    mock_provider = MagicMock()
    mock_provider.call.return_value = mock_response_good

    bad_raw_text = "this is not json {"
    # Provide a minimal payload so the repair path can build messages
    original_payload = {
        "messages": [{"role": "user", "content": []}],
        "model": MODEL_FIXTURE,
    }

    result = visual_qa.parse_qa_response(
        raw_text=bad_raw_text,
        provider=mock_provider,
        original_payload=original_payload,
    )

    # The repair call should have been made exactly once
    mock_provider.call.assert_called_once()
    assert result["overall_score"] == 88
    assert result.get("parse_error") is None


def test_parse_qa_response_returns_error_dict_when_both_fail() -> None:
    """If both the initial parse and the repair fail, return the error dict."""
    import visual_qa  # noqa: WPS433

    mock_response_bad = VisionResponse(
        raw_text="still not json {",
        input_tokens=10,
        output_tokens=5,
    )
    mock_provider = MagicMock()
    mock_provider.call.return_value = mock_response_bad

    original_payload = {
        "messages": [{"role": "user", "content": []}],
        "model": MODEL_FIXTURE,
    }

    result = visual_qa.parse_qa_response(
        raw_text="bad json {",
        provider=mock_provider,
        original_payload=original_payload,
    )

    assert result["parse_error"] is True
    assert result["overall_score"] == 0
    assert result["pages"] == []


def test_parse_qa_response_no_retry_without_provider() -> None:
    """When provider is None, no repair is attempted and error dict is returned."""
    import visual_qa  # noqa: WPS433

    result = visual_qa.parse_qa_response(
        raw_text="not valid json {",
        provider=None,
        original_payload=None,
    )

    assert result["parse_error"] is True
    assert result["overall_score"] == 0


def test_parse_qa_response_valid_json_no_retry() -> None:
    """When the first parse succeeds, no retry should happen."""
    import visual_qa  # noqa: WPS433

    valid = {"pages": [{"page_number": 1, "score": 90}], "overall_score": 90}
    mock_provider = MagicMock()

    result = visual_qa.parse_qa_response(
        raw_text=json.dumps(valid),
        provider=mock_provider,
        original_payload={"messages": [], "model": MODEL_FIXTURE},
    )

    mock_provider.call.assert_not_called()
    assert result["overall_score"] == 90
