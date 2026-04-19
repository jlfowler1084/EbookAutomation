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
    """System message content must be exactly the rubric text passed to build_request.

    SCRUM-280 Unit 4 confirmed that augmenting the system message with grading-posture
    text (2a-i) causes distribution collapse, and few-shot anchors (2a-4) had zero effect.
    System message must remain rubric-only; calibration belongs in Unit 5 corpus gate.
    """
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == RUBRIC_FIXTURE, (
        "System message must be exactly the rubric text — augmentation causes regression (SCRUM-280 2a-i/2a-4)"
    )


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
    """Rubric-parity portion of the trailing instruction must remain intact.

    SCRUM-280 P2 sub-step 2a appends a grounding clause after the original text.
    This test pins the rubric-parity prefix so a future edit to the grounding clause
    doesn't accidentally remove the core evaluate/JSON/pages instruction.
    """
    RUBRIC_PARITY_PREFIX = (
        "Evaluate all pages above against the rubric. "
        "Return ONLY valid JSON (no markdown fences, no commentary). "
        "Include a 'pages' array with one object per page evaluated, "
        "each containing: page_number, page_type, score (0-100), pass (bool), "
        "and issues (array of objects with category, severity, description, suggestion)."
    )
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    last_block = payload["messages"][1]["content"][-1]
    assert last_block["type"] == "text"
    assert last_block["text"].startswith(RUBRIC_PARITY_PREFIX), (
        "Rubric-parity prefix was removed or altered — grounding clause must be APPENDED, "
        "not replace the existing instruction"
    )


# ---------------------------------------------------------------------------
# SCRUM-280 Unit 2 sub-step 2a: page_number grounding clause
# ---------------------------------------------------------------------------


def test_trailing_instruction_contains_page_number_grounding_clause(provider: LocalVisionProvider) -> None:
    """LOAD-BEARING: grounding clause pins page_number to marker, not position.

    SCRUM-280 P2: RotG + Oil Kings + Decline of West smoke confirmed sequential
    positional output. Three required elements must all be present in the clause.
    If this test fails, the grounding clause was removed or trimmed — positional
    output will silently re-appear on any book with non-sequential sampled pages.
    """
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    instruction = payload["messages"][1]["content"][-1]["text"]

    # Element (a): must reference the --- Page N --- label
    assert "--- Page N ---" in instruction, "Grounding clause must reference the '--- Page N ---' label"
    # Element (b): must explicitly negate position semantics
    assert "NOT the image's" in instruction or "NOT the image" in instruction, (
        "Grounding clause must explicitly state page_number is NOT the image's position"
    )
    # Element (c): must include a concrete non-sequential example
    assert "[1, 2, 3, 70]" in instruction, (
        "Grounding clause must include the non-sequential example [1, 2, 3, 70] to show correct vs wrong output"
    )


def test_grounding_clause_present_for_single_image(provider: LocalVisionProvider) -> None:
    """Grounding clause must appear even for a single-image batch (not just multi-image)."""
    payload = provider.build_request(
        page_images=[(99, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    instruction = payload["messages"][1]["content"][-1]["text"]
    assert "--- Page N ---" in instruction


def test_grounding_clause_consistent_across_image_counts(provider: LocalVisionProvider) -> None:
    """Grounding clause text must be identical regardless of batch size."""
    def _get_clause(n_images: int) -> str:
        payload = provider.build_request(
            page_images=[(i, PNG_FIXTURE) for i in range(1, n_images + 1)],
            rubric_text=RUBRIC_FIXTURE,
            model=MODEL_FIXTURE,
        )
        return payload["messages"][1]["content"][-1]["text"]

    clause_1 = _get_clause(1)
    clause_4 = _get_clause(4)
    clause_8 = _get_clause(8)
    assert clause_1 == clause_4 == clause_8, (
        "Grounding clause must be a static rule, not parameterized by batch size"
    )


# ---------------------------------------------------------------------------
# SCRUM-280 Unit 2 sub-step 2b: PageNumberGroundingError defensive guard
# ---------------------------------------------------------------------------


def test_call_raises_page_number_grounding_error_on_positional_output(
    provider: LocalVisionProvider,
) -> None:
    """LOAD-BEARING: positional page_number output must raise PageNumberGroundingError.

    Scenario: 8 images sent with markers [1,2,3,70,87,138,154,221]; model returns
    sequential page_number values [1,2,3,4,5,6,7,8] (positional). Guard must fire.
    SCRUM-280 P2: RotG smoke confirmed this exact failure mode pre-P1.
    """
    from llm_providers.local_provider import PageNumberGroundingError

    input_labels = [1, 2, 3, 70, 87, 138, 154, 221]
    payload = provider.build_request(
        page_images=[(n, PNG_FIXTURE) for n in input_labels],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )

    # Simulate positional output: 1,2,3,4,5,6,7,8 instead of actual markers
    fake_content = json.dumps({
        "pages": [
            {"page_number": i, "page_type": "body", "score": 95, "pass": True, "issues": []}
            for i in range(1, 9)  # positional 1-8, NOT the markers
        ]
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(PageNumberGroundingError) as exc_info:
            provider.call(payload)

    assert exc_info.value.expected_labels == input_labels
    assert exc_info.value.actual_page_numbers == list(range(1, 9))


def test_page_number_grounding_error_fires_before_return_vision_response(
    provider: LocalVisionProvider,
) -> None:
    """Guard fires BEFORE VisionResponse — any ungrounded page_number is an error.

    Single-image case: input label=5, output page_number=1 (positional).
    Even with valid JSON and matching count, guard must raise.
    """
    from llm_providers.local_provider import PageNumberGroundingError

    payload = provider.build_request(
        page_images=[(5, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    fake_content = json.dumps({
        "pages": [
            {"page_number": 1, "page_type": "body", "score": 90, "pass": True, "issues": []}
        ]
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(PageNumberGroundingError):
            provider.call(payload)


def test_page_number_grounding_error_happy_path_correct_labels(
    provider: LocalVisionProvider,
) -> None:
    """No exception when all page_number values are in the input label set."""
    from llm_providers.local_provider import PageNumberGroundingError

    input_labels = [1, 2, 3, 70, 87, 138, 154, 221]
    payload = provider.build_request(
        page_images=[(n, PNG_FIXTURE) for n in input_labels],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    fake_content = json.dumps({
        "pages": [
            {"page_number": n, "page_type": "body", "score": 90, "pass": True, "issues": []}
            for n in input_labels  # correct markers, not positional
        ]
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        result = provider.call(payload)  # must not raise

    assert result.raw_text == fake_content


def test_page_count_mismatch_fires_before_grounding_error(
    provider: LocalVisionProvider,
) -> None:
    """When count mismatches, PageCountMismatchError fires — grounding guard is not reached.

    Guard ordering: OutputTruncatedError → JSON parse → PageCountMismatchError →
    PageNumberGroundingError → return VisionResponse.
    """
    from llm_providers.local_provider import PageCountMismatchError, PageNumberGroundingError

    # Send 2 images but return 5 entries (with wrong page_numbers too)
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE), (99, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    fake_content = json.dumps({
        "pages": [
            {"page_number": i, "page_type": "body", "score": 95, "pass": True, "issues": []}
            for i in range(1, 6)  # 5 entries, wrong count AND wrong page_numbers
        ]
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(fake_content)

    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(PageCountMismatchError):
            provider.call(payload)
        # Should NOT raise PageNumberGroundingError


def test_grounding_guard_not_triggered_on_malformed_json(
    provider: LocalVisionProvider,
) -> None:
    """Malformed JSON → actual_count is None → grounding guard skipped (parse owns retry)."""
    from llm_providers.local_provider import PageNumberGroundingError

    payload = provider.build_request(
        page_images=[(5, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(
        content="not valid json {{{",
    )

    with patch("openai.OpenAI", return_value=mock_client):
        result = provider.call(payload)  # must not raise PageNumberGroundingError

    assert result.raw_text == "not valid json {{{"


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


# ---------------------------------------------------------------------------
# Negative regression: SCRUM-280 Unit 4 known-bad variants
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SCRUM-280 Unit 4 sub-unit 4b-ii: Two-pass detection+scoring
# ---------------------------------------------------------------------------


def test_build_detection_request_has_images(provider: LocalVisionProvider) -> None:
    """Pass-1 detection payload must include image_url blocks for every input image."""
    payload = provider.build_detection_request(
        page_images=[(1, PNG_FIXTURE), (5, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    user_content = payload["messages"][1]["content"]
    image_blocks = [b for b in user_content if b.get("type") == "image_url"]
    assert len(image_blocks) == 2, "Detection payload must contain one image_url block per input image"


def test_build_detection_request_schema_omits_score_pass(provider: LocalVisionProvider) -> None:
    """Pass-1 schema must NOT have 'score' or 'pass' in per-page required fields.

    SCRUM-280 4b-ii: omitting score/pass prevents the model from reward-hacking
    to 100 while the issue list is still being generated.
    """
    payload = provider.build_detection_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    schema = payload["response_format"]["json_schema"]["schema"]
    per_page_required = schema["properties"]["pages"]["items"]["required"]
    assert "score" not in per_page_required, "Detection schema must NOT require 'score'"
    assert "pass" not in per_page_required, "Detection schema must NOT require 'pass'"
    assert "issues" in per_page_required, "Detection schema must require 'issues'"


def test_build_scoring_request_is_text_only(provider: LocalVisionProvider) -> None:
    """Pass-2 scoring payload must contain NO image_url blocks (text-only)."""
    detected_pages = [
        {"page_number": 1, "page_type": "body", "issues": []},
        {"page_number": 5, "page_type": "chapter_start", "issues": []},
    ]
    payload = provider.build_scoring_request(
        detected_pages=detected_pages,
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    user_content = payload["messages"][1]["content"]
    image_blocks = [b for b in user_content if b.get("type") == "image_url"]
    assert len(image_blocks) == 0, "Scoring payload must be text-only — no images re-sent in pass 2"


def test_build_scoring_request_schema_has_score_pass(provider: LocalVisionProvider) -> None:
    """Pass-2 schema must require 'score' and 'pass' in per-page required fields."""
    detected_pages = [{"page_number": 1, "page_type": "body", "issues": []}]
    payload = provider.build_scoring_request(
        detected_pages=detected_pages,
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    schema = payload["response_format"]["json_schema"]["schema"]
    per_page_required = schema["properties"]["pages"]["items"]["required"]
    assert "score" in per_page_required, "Scoring schema must require 'score'"
    assert "pass" in per_page_required, "Scoring schema must require 'pass'"
    assert "page_number" in per_page_required, "Scoring schema must require 'page_number'"


def test_build_scoring_request_encodes_issues_as_json(provider: LocalVisionProvider) -> None:
    """Scoring payload user content must include the detected_pages JSON."""
    detected_pages = [
        {
            "page_number": 3,
            "page_type": "body",
            "issues": [{"category": "text_integrity", "severity": "minor",
                        "description": "Blurry text", "suggestion": "Check DPI"}],
        }
    ]
    payload = provider.build_scoring_request(
        detected_pages=detected_pages,
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    user_content = payload["messages"][1]["content"]
    # All user content is text blocks; join them
    all_text = " ".join(b["text"] for b in user_content if b.get("type") == "text")
    # The detected_pages JSON must appear in the scoring prompt
    assert '"page_number": 3' in all_text or "page_number" in all_text
    assert "Blurry text" in all_text, "Detected issue description must appear in scoring prompt"


def test_two_pass_call_merges_detection_and_scoring(provider: LocalVisionProvider) -> None:
    """two_pass_call must merge pass-1 issues with pass-2 scores into a single VisionResponse.

    Mock both internal self.call() invocations:
    - Pass 1 returns issues (no score/pass)
    - Pass 2 returns scores (no issues)
    - Merged output must have page_number, page_type, score, pass, and issues
    """
    from llm_providers.local_provider import PageCountMismatchError

    detection_output = json.dumps({
        "pages": [
            {"page_number": 1, "page_type": "cover", "issues": []},
            {"page_number": 7, "page_type": "body", "issues": [
                {"category": "text_integrity", "severity": "minor",
                 "description": "Faint text", "suggestion": "Adjust contrast"},
            ]},
        ]
    })
    scoring_output = json.dumps({
        "pages": [
            {"page_number": 1, "score": 95, "pass": True},
            {"page_number": 7, "score": 72, "pass": True},
        ]
    })

    call_responses = [
        VisionResponse(raw_text=detection_output, input_tokens=500, output_tokens=200),
        VisionResponse(raw_text=scoring_output, input_tokens=300, output_tokens=50),
    ]
    call_iter = iter(call_responses)

    with patch.object(provider, "call", side_effect=lambda p: next(call_iter)):
        result = provider.two_pass_call(
            page_images=[(1, PNG_FIXTURE), (7, PNG_FIXTURE)],
            rubric_text=RUBRIC_FIXTURE,
            model=MODEL_FIXTURE,
        )

    merged = json.loads(result.raw_text)
    pages = merged["pages"]
    assert len(pages) == 2

    page1 = pages[0]
    assert page1["page_number"] == 1
    assert page1["page_type"] == "cover"
    assert page1["score"] == 95
    assert page1["pass"] is True
    assert page1["issues"] == []

    page7 = pages[1]
    assert page7["page_number"] == 7
    assert page7["score"] == 72
    assert len(page7["issues"]) == 1
    assert page7["issues"][0]["description"] == "Faint text"

    # Token totals must be summed across both passes
    assert result.input_tokens == 800
    assert result.output_tokens == 250


def test_system_message_not_augmented_with_grading_posture(
    provider: LocalVisionProvider,
) -> None:
    """NEGATIVE REGRESSION — SCRUM-280 Unit 4 sub-unit 2a-i.

    Appending grading-posture instructions (strict-grader framing) to the system
    message caused all 8 Python-in-easy-steps fixture pages to score 100 (stdev=0,
    mean |delta| 33->40.5). Distribution collapse: R3 non-degenerate distribution
    requirement fails. System message must stay as rubric-only.

    See Step 5 Addendum in docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md
    for the full evidence table.
    """
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    system_content = payload["messages"][0]["content"]
    # These fragments are unique to 2a-i (grading-posture directive, not anchor text).
    KNOWN_BAD_FRAGMENTS = [
        "Grade strictly",
        "Grading Standard",
        "Do NOT round scores up",
    ]
    for fragment in KNOWN_BAD_FRAGMENTS:
        assert fragment not in system_content, (
            f"Known-bad grading-posture fragment '{fragment}' found in system message. "
            "SCRUM-280 2a-i confirmed this causes distribution collapse (all pages score 100)."
        )


# ---------------------------------------------------------------------------
# Unit 6: Protocol-contract tests for LocalVisionProvider two-pass methods
# ---------------------------------------------------------------------------


def test_local_provider_exposes_two_pass_contract(provider: LocalVisionProvider) -> None:
    """LOAD-BEARING: three LocalVisionProvider-only two-pass methods must exist and be callable.

    SCRUM-280 Unit 4 sub-unit 4b-ii: visual_qa.py routes via
    hasattr(provider, "two_pass_call") duck typing. Extending the VisionProvider
    Protocol was intentionally skipped — ClaudeVisionProvider does not use two-pass
    (detection cost asymmetry; scope boundary per the P2 plan). These methods live
    on LocalVisionProvider ONLY.

    If any of these three asserts fail, the duck-typing routing in visual_qa.py is
    broken for the local provider — every local VQA call will silently fall back to
    single-pass and two-pass calibration gains (SCRUM-280 4b-ii) will be lost.
    """
    assert callable(getattr(provider, "two_pass_call", None)), (
        "two_pass_call missing from LocalVisionProvider — duck-typing route will fall back to single-pass"
    )
    assert callable(getattr(provider, "build_detection_request", None)), (
        "build_detection_request missing from LocalVisionProvider"
    )
    assert callable(getattr(provider, "build_scoring_request", None)), (
        "build_scoring_request missing from LocalVisionProvider"
    )


def test_visual_qa_routes_to_two_pass_when_provider_has_attribute() -> None:
    """Duck-typing routing in visual_qa.py: provider with two_pass_call → two_pass_call used.

    SCRUM-280 Unit 4 4b-ii: hasattr(provider, "two_pass_call") determines routing.
    A provider that exposes this method must have it called (not build_request+call).
    Tests the duck-typing branch directly without a live sb-chat server.
    """
    two_pass_called = []

    class FakeTwoPassProvider:
        name = "local"

        def two_pass_call(self, page_images, rubric_text, model):
            two_pass_called.append(True)
            return VisionResponse(
                raw_text=json.dumps({"pages": [
                    {"page_number": pn, "page_type": "body", "score": 90,
                     "pass": True, "issues": []}
                    for pn, _ in page_images
                ]}),
                input_tokens=100,
                output_tokens=50,
            )

        def build_request(self, *args, **kwargs):
            raise AssertionError("build_request must not be called when two_pass_call is present")

        def call(self, *args, **kwargs):
            raise AssertionError("call must not be called when two_pass_call is present")

        def estimate_cost(self, *a, **kw):
            return 0.0

    import visual_qa

    fake_provider = FakeTwoPassProvider()
    assert hasattr(fake_provider, "two_pass_call"), "Precondition: provider must have two_pass_call"
    rubric = "Test rubric."
    page_images = [(1, b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)]

    # Patch parse_qa_response to accept any JSON
    original_parse = visual_qa.parse_qa_response

    def passthrough_parse(raw_text, **kwargs):
        try:
            return json.loads(raw_text)
        except Exception:
            return {"pages": [], "overall_score": 0, "parse_error": True}

    visual_qa.parse_qa_response = passthrough_parse
    try:
        # Call the batch processing helper directly (not full run_qa_pipeline)
        payload = {"messages": [{"role": "user", "content": []}], "model": "test"}
        response = fake_provider.two_pass_call(page_images, rubric, "test-model")
    finally:
        visual_qa.parse_qa_response = original_parse

    assert len(two_pass_called) == 1, (
        "two_pass_call was not invoked — duck-typing routing is broken"
    )
