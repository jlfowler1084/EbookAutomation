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
from llm_providers.local_provider import _build_page_extraction_schema  # noqa: E402


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


# test_response_format_is_json_object renamed to test_response_format_is_json_schema
# in Unit 2 (SCRUM-279 P1) — see Unit 2 block below.


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
# Unit 1: _build_page_extraction_schema helper
# ---------------------------------------------------------------------------


def _collect_objects(node: dict) -> list[dict]:
    """Recursively collect all sub-dicts with type == 'object'."""
    results = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            results.append(node)
        for v in node.values():
            results.extend(_collect_objects(v))
    elif isinstance(node, list):
        for item in node:
            results.extend(_collect_objects(item))
    return results


def test_schema_pages_minItems_equals_page_count() -> None:
    schema = _build_page_extraction_schema(8)
    assert schema["properties"]["pages"]["minItems"] == 8


def test_schema_pages_maxItems_equals_page_count() -> None:
    schema = _build_page_extraction_schema(8)
    assert schema["properties"]["pages"]["maxItems"] == 8


def test_schema_top_level_type_and_required() -> None:
    schema = _build_page_extraction_schema(8)
    assert schema["type"] == "object"
    required = schema["required"]
    for key in ("pages", "overall_score", "overall_pass", "category_scores", "summary", "top_issues"):
        assert key in required, f"'{key}' missing from top-level required"
    assert schema["properties"]["pages"]["type"] == "array"


def test_schema_all_objects_have_additionalProperties_false() -> None:
    schema = _build_page_extraction_schema(8)
    objects = _collect_objects(schema)
    assert len(objects) > 0, "No objects found — schema is malformed"
    for obj in objects:
        assert obj.get("additionalProperties") is False, (
            f"Object missing additionalProperties:false — properties: {list(obj.get('properties', {}).keys())}"
        )


def test_schema_per_page_properties_and_required() -> None:
    schema = _build_page_extraction_schema(8)
    page_items = schema["properties"]["pages"]["items"]
    props = page_items["properties"]
    for key in ("page_number", "page_type", "score", "pass", "issues"):
        assert key in props, f"'{key}' missing from per-page properties"
    required = page_items["required"]
    for key in ("page_number", "page_type", "score", "pass", "issues"):
        assert key in required, f"'{key}' missing from per-page required"


def test_schema_page_type_enum_matches_rubric() -> None:
    schema = _build_page_extraction_schema(8)
    page_type_enum = schema["properties"]["pages"]["items"]["properties"]["page_type"]["enum"]
    assert page_type_enum == ["cover", "toc", "front_matter", "chapter_start", "body", "back_matter"]


def test_schema_issue_severity_enum() -> None:
    schema = _build_page_extraction_schema(8)
    issues_items = schema["properties"]["pages"]["items"]["properties"]["issues"]["items"]
    severity_enum = issues_items["properties"]["severity"]["enum"]
    assert severity_enum == ["critical", "moderate", "minor"]


def test_schema_category_scores_has_six_keys_with_bounds() -> None:
    schema = _build_page_extraction_schema(8)
    cat_scores = schema["properties"]["category_scores"]
    expected_keys = {
        "text_integrity", "heading_formatting", "paragraph_flow",
        "toc_navigation", "cover_images", "page_layout",
    }
    assert set(cat_scores["required"]) == expected_keys
    for key in expected_keys:
        prop = cat_scores["properties"][key]
        assert prop == {"type": "integer", "minimum": 0, "maximum": 100}, (
            f"category_scores.{key} has unexpected schema: {prop}"
        )
    assert cat_scores["additionalProperties"] is False


def test_schema_top_issues_shape_has_affected_pages() -> None:
    schema = _build_page_extraction_schema(8)
    top_issue_items = schema["properties"]["top_issues"]["items"]
    assert "affected_pages" in top_issue_items["properties"]
    assert top_issue_items["properties"]["affected_pages"] == {
        "type": "array",
        "items": {"type": "integer"},
    }
    # per-page issues must NOT have affected_pages
    per_page_issue_items = schema["properties"]["pages"]["items"]["properties"]["issues"]["items"]
    assert "affected_pages" not in per_page_issue_items["properties"]


def test_schema_boundary_single_image() -> None:
    schema = _build_page_extraction_schema(1)
    pages = schema["properties"]["pages"]
    assert pages["minItems"] == 1
    assert pages["maxItems"] == 1


def test_schema_boundary_sixteen_images() -> None:
    schema = _build_page_extraction_schema(16)
    pages = schema["properties"]["pages"]
    assert pages["minItems"] == 16
    assert pages["maxItems"] == 16


def test_schema_round_trips_json_dumps() -> None:
    schema = _build_page_extraction_schema(8)
    serialized = json.dumps(schema)
    assert json.loads(serialized) == schema


# ---------------------------------------------------------------------------
# Unit 2: json_schema response_format wiring + OutputTruncatedError
# ---------------------------------------------------------------------------


def test_response_format_is_json_schema(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    rf = payload["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "page_extraction_report"


def test_response_format_strict_true(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize("n_images", [1, 2, 8, 16])
def test_response_format_schema_bounds_match_image_count(
    provider: LocalVisionProvider, n_images: int
) -> None:
    payload = provider.build_request(
        page_images=[(i, PNG_FIXTURE) for i in range(1, n_images + 1)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    schema = payload["response_format"]["json_schema"]["schema"]
    pages = schema["properties"]["pages"]
    assert pages["minItems"] == n_images
    assert pages["maxItems"] == n_images


def test_build_request_single_image_schema_bounds(provider: LocalVisionProvider) -> None:
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    schema = payload["response_format"]["json_schema"]["schema"]
    pages = schema["properties"]["pages"]
    assert pages["minItems"] == 1
    assert pages["maxItems"] == 1


def test_frequency_penalty_still_absent_after_schema_change(provider: LocalVisionProvider) -> None:
    """Schema change must not reintroduce frequency_penalty."""
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert "frequency_penalty" not in payload


def test_enable_thinking_still_present_after_schema_change(provider: LocalVisionProvider) -> None:
    """Schema change must not disturb the enable_thinking=False guard."""
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


def test_call_raises_output_truncated_error_on_finish_reason_length(
    provider: LocalVisionProvider,
) -> None:
    from llm_providers.local_provider import OutputTruncatedError

    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(
        content='{"pages": [',  # truncated JSON
        finish_reason="length",
        completion_tokens=16384,
    )
    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(OutputTruncatedError) as exc_info:
            provider.call(payload)

    assert exc_info.value.finish_reason == "length"
    assert exc_info.value.output_tokens == 16384
    assert exc_info.value.max_tokens_budget == 16384


def test_call_does_not_raise_output_truncated_on_stop(provider: LocalVisionProvider) -> None:
    """finish_reason='stop' must not raise OutputTruncatedError."""
    from llm_providers.local_provider import OutputTruncatedError

    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    fake_content = json.dumps({
        "pages": [
            {"page_number": 1, "page_type": "body", "score": 85, "pass": True, "issues": []},
        ]
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(
        content=fake_content,
        finish_reason="stop",
    )
    with patch("openai.OpenAI", return_value=mock_client):
        result = provider.call(payload)

    assert result.raw_text == fake_content


def test_output_truncated_fires_before_json_loads(provider: LocalVisionProvider) -> None:
    """Truncated JSON + finish_reason='length' must raise OutputTruncatedError,
    not JSONDecodeError — truncation guard runs before any parsing.
    """
    from llm_providers.local_provider import OutputTruncatedError

    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(
        content="this is not json {{{",
        finish_reason="length",
    )
    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(OutputTruncatedError):
            provider.call(payload)


def test_repair_payload_strips_response_format() -> None:
    """parse_qa_response must pop response_format from the repair payload.

    Verifies sub-step 2c: if guided_json is active, the repair call has no
    images and a strict N-page schema would force fabricated entries.
    """
    import visual_qa

    captured_repair_payloads: list[dict] = []

    def capturing_call(p: dict) -> VisionResponse:
        captured_repair_payloads.append(dict(p))
        return VisionResponse(
            raw_text=json.dumps({
                "overall_score": 80,
                "pages": [{"page_number": 1, "score": 80}],
                "category_scores": {},
                "summary": "ok",
                "top_issues": [],
            }),
            input_tokens=10,
            output_tokens=20,
        )

    mock_provider = MagicMock()
    mock_provider.call.side_effect = capturing_call

    original_payload = {
        "messages": [{"role": "user", "content": []}],
        "model": MODEL_FIXTURE,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "page_extraction_report", "strict": True, "schema": {}},
        },
    }

    visual_qa.parse_qa_response(
        raw_text="not valid json {",
        provider=mock_provider,
        original_payload=original_payload,
    )

    assert len(captured_repair_payloads) == 1
    assert "response_format" not in captured_repair_payloads[0], (
        "response_format must be stripped from repair payload before the repair call"
    )


# ---------------------------------------------------------------------------
# LOAD-BEARING: page-count hallucination guard
# SCRUM-275 smoke 2026-04-18 — Return of the Gods produced 221 sequential
# page entries for 8 input images. Silent truncation would hide this and
# yield ungrounded page_number values to downstream consumers. The guard
# must raise PageCountMismatchError, not truncate.
# ---------------------------------------------------------------------------


def _make_fake_completion(
    content: str,
    prompt_tokens: int = 100,
    completion_tokens: int = 500,
    finish_reason: str = "stop",
) -> MagicMock:
    """Helper: build a mock OpenAI ChatCompletion response."""
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = content
    fake.choices[0].finish_reason = finish_reason
    fake.usage = MagicMock()
    fake.usage.prompt_tokens = prompt_tokens
    fake.usage.completion_tokens = completion_tokens
    return fake


def test_call_raises_on_page_count_hallucination(provider: LocalVisionProvider) -> None:
    """Model returns MORE page entries than images sent — guard must raise."""
    from llm_providers.local_provider import PageCountMismatchError

    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE), (2, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )

    # Simulate Return-of-the-Gods-style hallucination: 5 entries for 2 images.
    fake_content = json.dumps({
        "pages": [
            {"page_number": i, "page_type": "body", "score": 95, "pass": True, "issues": []}
            for i in range(1, 6)
        ]
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(PageCountMismatchError) as exc_info:
            provider.call(payload)

    assert exc_info.value.expected == 2
    assert exc_info.value.actual == 5


def test_call_raises_on_page_count_undercount(provider: LocalVisionProvider) -> None:
    """Model returns FEWER page entries than images sent — guard must raise.

    Covers the complementary failure mode (e.g., model drops pages mid-generation).
    Same guard, same exception — the caller should not guess which pages are missing.
    """
    from llm_providers.local_provider import PageCountMismatchError

    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE), (2, PNG_FIXTURE), (3, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )

    fake_content = json.dumps({
        "pages": [
            {"page_number": 1, "page_type": "body", "score": 95, "pass": True, "issues": []},
        ]
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(PageCountMismatchError) as exc_info:
            provider.call(payload)

    assert exc_info.value.expected == 3
    assert exc_info.value.actual == 1


def test_call_passes_through_on_matching_count(provider: LocalVisionProvider) -> None:
    """Happy path: model returns exactly the expected page count — no exception."""
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE), (2, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )

    fake_content = json.dumps({
        "pages": [
            {"page_number": 1, "page_type": "body", "score": 85, "pass": True, "issues": []},
            {"page_number": 2, "page_type": "body", "score": 90, "pass": True, "issues": []},
        ]
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        result = provider.call(payload)

    assert result.raw_text == fake_content
    assert result.input_tokens == 100
    assert result.output_tokens == 500


def test_call_skips_guard_on_malformed_json(provider: LocalVisionProvider) -> None:
    """If JSON is malformed, call() must NOT raise PageCountMismatchError.

    parse_qa_response owns the retry-on-JSON-error path. The guard is for
    semantic mismatch on syntactically-valid output.
    """
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )

    # Malformed JSON — the guard must pass this through for downstream retry.
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(
        content="not valid json {{{",
    )

    with patch("openai.OpenAI", return_value=mock_client):
        result = provider.call(payload)

    assert result.raw_text == "not valid json {{{"


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
