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
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make tools/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from llm_providers import LocalVisionProvider  # noqa: E402
from llm_providers.base import VisionResponse  # noqa: E402
from llm_providers.local_provider import (  # noqa: E402
    ABSOLUTE_MIN_OUTPUT_BUDGET,
    CONSERVATIVE_UNKNOWN_N_CTX,
    CONTEXT_SAFETY_MARGIN,
    GRADING_MAX_OUTPUT_TOKENS,
    MIN_OUTPUT_BUDGET,
    PER_IMAGE_TOKEN_ESTIMATE,
    RUBRIC_TOKEN_RESERVE,
    _build_page_extraction_schema,
)


PNG_FIXTURE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
RUBRIC_FIXTURE = "RUBRIC TEXT GOES HERE"
MODEL_FIXTURE = "qwen3.5-35b-a3b-fp8"


def _stub_probe_32768(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
    """Default network-free probe stub for the shared `provider` fixture.

    EB-392: on Joe's machine http://localhost:8000/v1/models is live (it now
    answers as the text-only Flash gateway, listing several models with no
    n_ctx match) and http://192.168.1.33:8080/v1/models (sb-vision) is also
    live reporting n_ctx=8192 -- every test in this file must be independent
    of whichever server happens to be reachable. This stub is injected as the
    `provider` fixture's default `probe` callable so ordinary payload/budget
    tests never touch urllib at all.

    Tests that exercise the REAL HTTP probe chain (get_context_window's
    models/props/vllm/unknown behavior) construct their own un-stubbed
    LocalVisionProvider instance (probe=None -> the real _probe_local_server)
    and patch urllib.request.urlopen directly instead of using this fixture.
    """
    return {
        "n_ctx": 32768,
        "n_ctx_source": "models",
        "n_ctx_train": 262144,
        "model_served": model or "stub-model",
        "models_listed": [model or "stub-model"],
        "server_type": "llamacpp",
        "total_slots": 1,
        "model_path": None,
        "build_info": None,
        "probe_ok": True,
    }


@pytest.fixture
def provider() -> LocalVisionProvider:
    return LocalVisionProvider(base_url="http://localhost:8000/v1", probe=_stub_probe_32768)


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


def test_temperature_is_0(provider: LocalVisionProvider) -> None:
    # EB-150: temperature changed from 0.1 to 0 for grader determinism.
    # The repetition-loop concern cited in the original assertion was not
    # observed in practice (guided-json schema enforcement prevents repetition
    # at the token-masking level). seed=42 provides additional reproducibility.
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["temperature"] == 0, (
        "temperature must be 0 (EB-150: deterministic grader)"
    )
    assert payload.get("seed") == 42, (
        "seed must be 42 (EB-150: deterministic grader)"
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
    assert severity_enum == ["critical", "major", "moderate", "minor"]  # EB-219


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
        completion_tokens=GRADING_MAX_OUTPUT_TOKENS,
    )
    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(OutputTruncatedError) as exc_info:
            provider.call(payload)

    assert exc_info.value.finish_reason == "length"
    assert exc_info.value.output_tokens == GRADING_MAX_OUTPUT_TOKENS
    # Truncation guard reads budget from payload; must match the raised constant (EB-358).
    assert exc_info.value.max_tokens_budget == GRADING_MAX_OUTPUT_TOKENS


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


# ---------------------------------------------------------------------------
# EB-358: output-token budget tests
# ---------------------------------------------------------------------------


def test_grading_max_output_tokens_constant_value() -> None:
    """GRADING_MAX_OUTPUT_TOKENS must be greater than the old 16,384 cap.

    EB-358: the old cap caused dense/scan batches to hit finish_reason='length',
    returning truncated JSON that was discarded → partial coverage.  The new
    value must exceed 16384 to actually unblock those batches.
    """
    assert GRADING_MAX_OUTPUT_TOKENS > 16384, (
        f"GRADING_MAX_OUTPUT_TOKENS ({GRADING_MAX_OUTPUT_TOKENS}) must exceed the old 16384 cap "
        "(EB-358: old cap truncated dense-batch output)"
    )


def test_grading_max_output_tokens_within_server_ceiling() -> None:
    """GRADING_MAX_OUTPUT_TOKENS must not exceed the confirmed server n_ctx ceiling.

    Server n_ctx=32768 (Qwen3-VL-30B-A3B on R9700, documented in sweep #2 meta).
    The output budget must leave room for input tokens — chosen conservatively.
    """
    SERVER_N_CTX = 32768
    assert GRADING_MAX_OUTPUT_TOKENS <= SERVER_N_CTX, (
        f"GRADING_MAX_OUTPUT_TOKENS ({GRADING_MAX_OUTPUT_TOKENS}) exceeds confirmed server "
        f"n_ctx={SERVER_N_CTX} — this would cause context-window overflow on the server"
    )


def test_build_request_uses_grading_max_output_tokens(provider: LocalVisionProvider) -> None:
    """build_request() must carry GRADING_MAX_OUTPUT_TOKENS, not a hardcoded 16384.

    EB-358: batch grading (and single-page retry, which also calls build_request)
    need the raised budget to complete dense/scan pages without truncation.
    """
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["max_tokens"] == GRADING_MAX_OUTPUT_TOKENS, (
        f"build_request max_tokens must equal GRADING_MAX_OUTPUT_TOKENS "
        f"({GRADING_MAX_OUTPUT_TOKENS}), got {payload['max_tokens']} — "
        "EB-358: old 16384 cap truncated dense-batch output"
    )


def test_build_detection_request_uses_grading_max_output_tokens(
    provider: LocalVisionProvider,
) -> None:
    """build_detection_request() (two-pass Pass 1) must also use GRADING_MAX_OUTPUT_TOKENS.

    EB-358: Pass-1 detection enumerates issues verbosely and can itself hit
    the old 16K cap on dense/scan pages.  The retry path via build_request
    uses GRADING_MAX_OUTPUT_TOKENS too; detection budget should be >= batch budget.
    """
    payload = provider.build_detection_request(
        page_images=[(1, PNG_FIXTURE), (2, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["max_tokens"] == GRADING_MAX_OUTPUT_TOKENS, (
        f"build_detection_request max_tokens must equal GRADING_MAX_OUTPUT_TOKENS "
        f"({GRADING_MAX_OUTPUT_TOKENS}), got {payload['max_tokens']}"
    )


def test_build_scoring_request_keeps_small_budget(provider: LocalVisionProvider) -> None:
    """build_scoring_request() (two-pass Pass 2) must NOT use GRADING_MAX_OUTPUT_TOKENS.

    Pass 2 is text-only (no images) and just assigns a numeric score per page
    from the already-computed issue list.  It only needs a small budget (1024).
    Raising it would be wasteful and is not part of EB-358 scope.
    """
    detected_pages = [{"page_number": 1, "page_type": "body", "issues": []}]
    payload = provider.build_scoring_request(
        detected_pages=detected_pages,
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["max_tokens"] < GRADING_MAX_OUTPUT_TOKENS, (
        "build_scoring_request (Pass 2, text-only) must use a small budget, "
        f"not GRADING_MAX_OUTPUT_TOKENS ({GRADING_MAX_OUTPUT_TOKENS})"
    )


def test_grading_budget_exceeds_single_page_retry_budget(provider: LocalVisionProvider) -> None:
    """Single-page retry uses build_request — budget must be >= batch budget.

    EB-358 task notes: 'The single-page retry path should use a budget >= the
    batch budget'.  Since both paths call build_request(), the same constant
    applies to both.  This test pins that relationship explicitly.
    """
    batch_payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE), (2, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    single_payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)],
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert single_payload["max_tokens"] >= batch_payload["max_tokens"], (
        "Single-page retry budget must be >= batch budget (both use build_request/GRADING_MAX_OUTPUT_TOKENS)"
    )


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


# ---------------------------------------------------------------------------
# EB-350: Adaptive context-budget manager
# ---------------------------------------------------------------------------

# Helper: minimal /models JSON response as bytes.
def _models_response(n_ctx: int) -> bytes:
    payload = {
        "data": [{"id": "test-model", "meta": {"n_ctx": n_ctx}}],
        "object": "list",
    }
    return json.dumps(payload).encode("utf-8")


class _FakeHTTPResponse:
    """Minimal stand-in for urllib.request.urlopen context manager."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# EB-350 AC#1: get_context_window — parse, cache, fallback
# ---------------------------------------------------------------------------


def _raw_provider() -> LocalVisionProvider:
    """A LocalVisionProvider with the REAL probe (probe=None), for tests that
    exercise the HTTP probe chain itself via a patched urllib.request.urlopen.
    Must NOT use the shared `provider` fixture -- its injected stub bypasses
    urllib entirely and would make any urlopen patch inert (EB-392).
    """
    return LocalVisionProvider(base_url="http://localhost:8000/v1")


def test_get_context_window_parses_n_ctx() -> None:
    """get_context_window() returns data[0].meta.n_ctx from /models response."""
    provider = _raw_provider()
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeHTTPResponse(_models_response(49152)),
    ):
        result = provider.get_context_window()
    assert result == 49152


def test_get_context_window_caches_result() -> None:
    """Second call must NOT make any additional network requests (cached)."""
    provider = _raw_provider()
    call_count = []

    def fake_urlopen(url, timeout=None):
        call_count.append(1)
        return _FakeHTTPResponse(_models_response(32768))

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        first = provider.get_context_window()
        calls_after_first_probe = len(call_count)
        second = provider.get_context_window()

    assert first == second == 32768
    assert calls_after_first_probe > 0, "First probe must have made at least one HTTP call"
    assert len(call_count) == calls_after_first_probe, (
        f"urlopen called {len(call_count)} times total (vs {calls_after_first_probe} "
        "after the first probe) — the second get_context_window() call must not "
        "issue any additional network requests"
    )


def test_get_context_window_returns_conservative_unknown_on_network_error() -> None:
    """On total network failure, get_context_window() returns CONSERVATIVE_UNKNOWN_N_CTX.

    EB-392: the EB-350 branch silently fell back to DEFAULT_CONTEXT_WINDOW
    (32768) here — exactly the assumption that causes context overflow on a
    server that is actually smaller (sb-vision's real 8192). That silent
    fallback is removed; an unreachable server now resolves to the smaller,
    safer CONSERVATIVE_UNKNOWN_N_CTX (8192) instead.
    """
    import urllib.error

    provider = _raw_provider()
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        result = provider.get_context_window()

    assert result == CONSERVATIVE_UNKNOWN_N_CTX


def test_get_context_window_returns_conservative_unknown_on_missing_field() -> None:
    """If /models response is missing meta.n_ctx (and /props has none either),
    return CONSERVATIVE_UNKNOWN_N_CTX (EB-392 -- not the old 32768 default)."""
    provider = _raw_provider()
    bad_response = json.dumps({"data": [{"id": "test", "meta": {}}], "object": "list"}).encode()
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(bad_response)):
        result = provider.get_context_window()
    assert result == CONSERVATIVE_UNKNOWN_N_CTX


def test_get_context_window_returns_conservative_unknown_on_malformed_json() -> None:
    """If /models response is malformed JSON, return CONSERVATIVE_UNKNOWN_N_CTX
    (EB-392 -- not the old 32768 default)."""
    provider = _raw_provider()
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeHTTPResponse(b"not json {{{"),
    ):
        result = provider.get_context_window()
    assert result == CONSERVATIVE_UNKNOWN_N_CTX


def test_get_context_window_unknown_fallback_is_also_cached() -> None:
    """Even the conservative-unknown result is cached — no repeated probe
    attempts on every call once the server has been found unreachable."""
    provider = _raw_provider()
    call_count = []

    def fake_urlopen(url, timeout=None):
        call_count.append(1)
        raise ConnectionError("host unreachable")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        r1 = provider.get_context_window()
        calls_after_first_probe = len(call_count)
        r2 = provider.get_context_window()

    assert r1 == r2 == CONSERVATIVE_UNKNOWN_N_CTX
    assert calls_after_first_probe > 0, "First probe must have made at least one HTTP call"
    assert len(call_count) == calls_after_first_probe, (
        "Probe must not be retried after the unknown result is cached"
    )


# ---------------------------------------------------------------------------
# EB-350 AC#2: output_budget_for — single page, large batch, clamps
# ---------------------------------------------------------------------------


def test_output_budget_for_single_page_returns_ceiling_at_32768(
    provider: LocalVisionProvider,
) -> None:
    """Single-image batch at n_ctx=32768 must resolve to GRADING_MAX_OUTPUT_TOKENS (24576)."""
    budget = provider.output_budget_for(num_images=1, n_ctx=32768)
    assert budget == GRADING_MAX_OUTPUT_TOKENS, (
        f"Single-page budget at n_ctx=32768 must be {GRADING_MAX_OUTPUT_TOKENS}, got {budget}"
    )


def test_output_budget_for_large_batch_is_reduced(
    provider: LocalVisionProvider,
) -> None:
    """A large batch must produce a budget smaller than GRADING_MAX_OUTPUT_TOKENS."""
    budget_8 = provider.output_budget_for(num_images=8, n_ctx=32768)
    assert budget_8 < GRADING_MAX_OUTPUT_TOKENS, (
        f"8-image batch budget ({budget_8}) should be below the 24576 ceiling at n_ctx=32768"
    )
    assert budget_8 >= MIN_OUTPUT_BUDGET, (
        f"8-image batch budget ({budget_8}) must not drop below MIN_OUTPUT_BUDGET={MIN_OUTPUT_BUDGET}"
    )


def test_output_budget_for_never_below_absolute_minimum(
    provider: LocalVisionProvider,
) -> None:
    """A pathologically large batch must clamp to ABSOLUTE_MIN_OUTPUT_BUDGET.

    EB-392: the EB-350 branch floored EVERY batch at MIN_OUTPUT_BUDGET (8192)
    regardless of how little room the batch left -- for a batch this large the
    raw budget is deeply negative, so flooring it at 8192 would ask the server
    for far more output tokens than the entire window has room for. The fixed
    floor scales down with the batch and only stops at the smaller
    ABSOLUTE_MIN_OUTPUT_BUDGET (1024), logging an ERROR rather than silently
    requesting an impossible amount.
    """
    # 100 images at n_ctx=32768 would give a huge negative raw value.
    budget = provider.output_budget_for(num_images=100, n_ctx=32768)
    assert budget == ABSOLUTE_MIN_OUTPUT_BUDGET


def test_output_budget_for_tiny_n_ctx_logs_error_and_uses_absolute_minimum(
    provider: LocalVisionProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Edge case: n_ctx so small even one image does not fit.

    Must log an ERROR naming the server n_ctx, return
    ABSOLUTE_MIN_OUTPUT_BUDGET, and never raise before the first call.
    """
    with caplog.at_level("ERROR", logger="visual_qa.local_provider"):
        budget = provider.output_budget_for(num_images=1, n_ctx=1000)
    assert budget == ABSOLUTE_MIN_OUTPUT_BUDGET
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    assert "1000" in error_records[0].getMessage(), (
        "ERROR log must name the server n_ctx that triggered the absolute minimum"
    )


def test_output_budget_for_never_above_grading_max(
    provider: LocalVisionProvider,
) -> None:
    """Even num_images=0 (edge case) must not exceed GRADING_MAX_OUTPUT_TOKENS."""
    budget = provider.output_budget_for(num_images=0, n_ctx=32768)
    assert budget <= GRADING_MAX_OUTPUT_TOKENS


def test_output_budget_for_math_correctness(
    provider: LocalVisionProvider,
) -> None:
    """Verify the formula at a mid-range batch size (not clamped)."""
    n_ctx = 32768
    num_images = 8
    available = n_ctx - CONTEXT_SAFETY_MARGIN - RUBRIC_TOKEN_RESERVE
    expected_raw = available - num_images * PER_IMAGE_TOKEN_ESTIMATE
    expected = max(MIN_OUTPUT_BUDGET, min(GRADING_MAX_OUTPUT_TOKENS, expected_raw))
    assert provider.output_budget_for(num_images=num_images, n_ctx=n_ctx) == expected


def test_output_budget_for_uses_probe_when_n_ctx_not_supplied(
    provider: LocalVisionProvider,
) -> None:
    """When n_ctx is not passed, output_budget_for calls get_context_window()."""
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeHTTPResponse(_models_response(32768)),
    ):
        budget = provider.output_budget_for(num_images=1)
    assert budget == GRADING_MAX_OUTPUT_TOKENS


# ---------------------------------------------------------------------------
# EB-350 AC#3: max_batch_size — computed value at n_ctx=32768
# ---------------------------------------------------------------------------


def test_max_batch_size_at_32768(provider: LocalVisionProvider) -> None:
    """max_batch_size at n_ctx=32768 with chosen constants must be 10.

    available = 32768 - 1024 - 1500 = 30244
    N = floor((30244 - 8192) / 2200) = floor(22052 / 2200) = 10
    """
    result = provider.max_batch_size(n_ctx=32768)
    assert result == 10, (
        f"max_batch_size at n_ctx=32768 expected 10, got {result}. "
        "If constants changed, re-verify the math and update this assertion."
    )


def test_max_batch_size_at_least_one(provider: LocalVisionProvider) -> None:
    """max_batch_size is always at least 1, even for a tiny n_ctx."""
    result = provider.max_batch_size(n_ctx=4096)
    assert result >= 1


def test_max_batch_size_uses_probe_when_n_ctx_not_supplied(
    provider: LocalVisionProvider,
) -> None:
    """When n_ctx is not passed, max_batch_size calls get_context_window()."""
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeHTTPResponse(_models_response(32768)),
    ):
        result = provider.max_batch_size()
    assert result == 10


# ---------------------------------------------------------------------------
# EB-350 AC#4: build_request / build_detection_request carry adaptive budget
# ---------------------------------------------------------------------------


def test_build_request_falls_back_to_conservative_window_on_probe_failure() -> None:
    """build_request for 1 image with a fully unreachable server uses the
    EB-392 conservative-unknown budget, NOT the old silent 32768 fallback
    (removed -- see CONSERVATIVE_UNKNOWN_N_CTX).

    Uses a fresh un-stubbed provider (not the shared fixture) so the forced
    urlopen failure actually exercises the real probe chain.
    """
    fresh = _raw_provider()
    with patch("urllib.request.urlopen", side_effect=ConnectionError("no server")):
        payload = fresh.build_request(
            page_images=[(1, PNG_FIXTURE)],
            rubric_text=RUBRIC_FIXTURE,
            model=MODEL_FIXTURE,
        )
    assert fresh.get_context_window() == CONSERVATIVE_UNKNOWN_N_CTX
    expected = fresh.output_budget_for(1, n_ctx=CONSERVATIVE_UNKNOWN_N_CTX)
    assert payload["max_tokens"] == expected
    assert payload["max_tokens"] != GRADING_MAX_OUTPUT_TOKENS, (
        "A fully unreachable server must NOT silently produce the 32768-window "
        "budget (EB-350's removed silent fallback)"
    )


def test_build_request_carries_adaptive_budget_mocked_small_n_ctx() -> None:
    """build_request reflects the server n_ctx when the probe succeeds.

    Uses a fresh un-stubbed provider (not the shared fixture) so the mocked
    /models response actually drives get_context_window().
    """
    fresh = _raw_provider()
    small_n_ctx = 16384
    # available = 16384 - 1024 - 1500 = 13860
    # raw = 13860 - 1*2200 = 11660; floor = min(8192, 11660) = 8192
    # budget = max(8192, min(24576, 11660)) = 11660
    expected = 11660
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeHTTPResponse(_models_response(small_n_ctx)),
    ):
        payload = fresh.build_request(
            page_images=[(1, PNG_FIXTURE)],
            rubric_text=RUBRIC_FIXTURE,
            model=MODEL_FIXTURE,
        )
    assert payload["max_tokens"] == expected


def test_build_detection_request_carries_adaptive_budget(
    provider: LocalVisionProvider,
) -> None:
    """build_detection_request carries the same adaptive budget as build_request."""
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeHTTPResponse(_models_response(32768)),
    ):
        det_payload = provider.build_detection_request(
            page_images=[(1, PNG_FIXTURE), (2, PNG_FIXTURE)],
            rubric_text=RUBRIC_FIXTURE,
            model=MODEL_FIXTURE,
        )
        req_payload = provider.build_request(
            page_images=[(1, PNG_FIXTURE), (2, PNG_FIXTURE)],
            rubric_text=RUBRIC_FIXTURE,
            model=MODEL_FIXTURE,
        )
    assert det_payload["max_tokens"] == req_payload["max_tokens"], (
        "Detection and extraction requests for the same image count must "
        "carry the same adaptive budget"
    )


def test_build_request_adaptive_budget_large_batch_below_ceiling(
    provider: LocalVisionProvider,
) -> None:
    """A large batch (>10 images) at n_ctx=32768 produces a budget below 24576.

    EB-392: 11 images at n_ctx=32768 leaves less room than MIN_OUTPUT_BUDGET
    (8192) -- available=30244, raw=30244-11*2200=6044 -- so the fixed floor
    scales down to 6044 rather than clamping up to 8192 (which would ask for
    more output than the window has room for). Only the ABSOLUTE_MIN_OUTPUT_BUDGET
    floor is a hard guarantee.
    """
    # `provider` fixture stubs the probe at n_ctx=32768 (EB-392) -- no network call.
    payload = provider.build_request(
        page_images=[(i, PNG_FIXTURE) for i in range(1, 12)],  # 11 images
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["max_tokens"] < GRADING_MAX_OUTPUT_TOKENS, (
        "11-image batch budget must be below the 24576 ceiling at n_ctx=32768"
    )
    assert payload["max_tokens"] >= ABSOLUTE_MIN_OUTPUT_BUDGET


def test_build_scoring_request_unchanged_at_1024(
    provider: LocalVisionProvider,
) -> None:
    """build_scoring_request (Pass 2, text-only) must stay at max_tokens=1024.

    EB-350 hard constraint: text-only pass budget is NOT adaptive.
    """
    detected_pages = [{"page_number": 1, "page_type": "body", "issues": []}]
    payload = provider.build_scoring_request(
        detected_pages=detected_pages,
        rubric_text=RUBRIC_FIXTURE,
        model=MODEL_FIXTURE,
    )
    assert payload["max_tokens"] == 1024, (
        "build_scoring_request must stay at 1024 (text-only pass, EB-350 hard constraint)"
    )


# ---------------------------------------------------------------------------
# EB-392 Unit 1: explicit n_ctx (--n-ctx / LOCAL_LLM_N_CTX) wins over probing
# ---------------------------------------------------------------------------


def test_explicit_n_ctx_wins_over_probe_source_is_cli() -> None:
    """Constructor n_ctx always wins over probing; n_ctx_source == 'cli'.

    The probe still runs (lazily, for describe() metadata) even though its
    answer is never used for n_ctx itself.
    """
    probe_calls: list[int] = []

    def fake_probe(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
        probe_calls.append(1)
        return {
            "n_ctx": 8192,  # would be used if the explicit override didn't win
            "n_ctx_source": "models",
            "n_ctx_train": None,
            "model_served": "sb-vision",
            "models_listed": ["sb-vision"],
            "server_type": "llamacpp",
            "total_slots": 1,
            "model_path": None,
            "build_info": None,
            "probe_ok": True,
        }

    fresh = LocalVisionProvider(base_url="http://x/v1", n_ctx=32768, probe=fake_probe)
    assert fresh.get_context_window() == 32768, "explicit n_ctx must not require a probe call"
    assert len(probe_calls) == 0

    info = fresh.describe()
    assert info["n_ctx"] == 32768
    assert info["n_ctx_source"] == "cli"
    assert info["model_served"] == "sb-vision", "probe metadata still surfaces via describe()"
    assert len(probe_calls) == 1, "describe() must still run the probe for other metadata"


def test_describe_warns_once_when_explicit_n_ctx_disagrees_with_probe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Adversarial review: an explicit --n-ctx that disagrees with the real
    probed window silently defeated the adaptive context-budget safety net
    (it always wins, with zero cross-validation). describe() must log ONE
    WARNING naming both values."""
    def fake_probe(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
        return {
            "n_ctx": 8192, "n_ctx_source": "models", "n_ctx_train": None,
            "model_served": "m", "models_listed": ["m"], "server_type": "llamacpp",
            "total_slots": 1, "model_path": None, "build_info": None, "probe_ok": True,
        }

    provider = LocalVisionProvider(base_url="http://x/v1", n_ctx=32768, probe=fake_probe)
    with caplog.at_level("WARNING", logger="visual_qa.local_provider"):
        provider.describe()
        provider.describe(refresh=True)  # second call must NOT log a second warning

    matches = [r for r in caplog.records if "disagrees with" in r.getMessage()]
    assert len(matches) == 1
    assert "32768" in matches[0].getMessage()
    assert "8192" in matches[0].getMessage()


def test_describe_no_warning_when_explicit_n_ctx_matches_probe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_probe(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
        return {
            "n_ctx": 32768, "n_ctx_source": "models", "n_ctx_train": None,
            "model_served": "m", "models_listed": ["m"], "server_type": "llamacpp",
            "total_slots": 1, "model_path": None, "build_info": None, "probe_ok": True,
        }

    provider = LocalVisionProvider(base_url="http://x/v1", n_ctx=32768, probe=fake_probe)
    with caplog.at_level("WARNING", logger="visual_qa.local_provider"):
        provider.describe()

    assert not any("disagrees with" in r.getMessage() for r in caplog.records)


def test_describe_no_warning_when_probe_failed(caplog: pytest.LogCaptureFixture) -> None:
    """A total probe failure (probe_ok False) must not be treated as a
    disagreement -- there is no trustworthy probed value to compare against."""
    def fake_probe(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
        return None

    provider = LocalVisionProvider(base_url="http://x/v1", n_ctx=32768, probe=fake_probe)
    with caplog.at_level("WARNING", logger="visual_qa.local_provider"):
        provider.describe()

    assert not any("disagrees with" in r.getMessage() for r in caplog.records)


def test_max_batch_size_and_output_budget_use_explicit_n_ctx_too() -> None:
    """Explicit n_ctx flows through to the batch-size/output-budget math as well."""
    fresh = LocalVisionProvider(
        base_url="http://x/v1", n_ctx=8192,
        probe=lambda base_url, model, timeout=5.0: (_ for _ in ()).throw(
            AssertionError("probe must not be called when computing budgets from an explicit n_ctx")
        ),
    )
    assert fresh.max_batch_size() == 1
    budget = fresh.output_budget_for(1)
    assert budget == fresh.output_budget_for(1, n_ctx=8192)


# ---------------------------------------------------------------------------
# EB-392 Unit 1: probe caching + describe(refresh=True)
# ---------------------------------------------------------------------------


def test_describe_refresh_true_reprobes_and_can_return_different_n_ctx() -> None:
    """Probe is cached after the first call; describe(refresh=True) forces a
    new probe call and can surface a changed server n_ctx.
    """
    responses = iter([
        {
            "n_ctx": 8192, "n_ctx_source": "models", "n_ctx_train": None,
            "model_served": "m", "models_listed": ["m"], "server_type": "llamacpp",
            "total_slots": 1, "model_path": None, "build_info": None, "probe_ok": True,
        },
        {
            "n_ctx": 32768, "n_ctx_source": "models", "n_ctx_train": None,
            "model_served": "m", "models_listed": ["m"], "server_type": "llamacpp",
            "total_slots": 1, "model_path": None, "build_info": None, "probe_ok": True,
        },
    ])
    call_count: list[int] = []

    def fake_probe(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
        call_count.append(1)
        return next(responses)

    fresh = LocalVisionProvider(base_url="http://x/v1", probe=fake_probe)

    first = fresh.describe()
    assert first["n_ctx"] == 8192
    assert len(call_count) == 1

    second = fresh.describe()  # cached -- no new probe call
    assert second["n_ctx"] == 8192
    assert len(call_count) == 1

    third = fresh.describe(refresh=True)
    assert third["n_ctx"] == 32768
    assert len(call_count) == 2


# ---------------------------------------------------------------------------
# EB-392 Unit 1: real HTTP probe chain (models -> props -> vllm -> unknown)
# ---------------------------------------------------------------------------


def _make_dual_urlopen(
    models_data: dict | None = None,
    models_raise: Exception | None = None,
    props_data: dict | None = None,
    props_raise: Exception | None = None,
):
    """Return a urlopen stand-in that answers differently for /models vs /props,
    so probe-chain tests can control each endpoint independently.
    """

    def fake_urlopen(url: str, timeout: float | None = None):
        if url.rstrip("/").endswith("/props"):
            if props_raise is not None:
                raise props_raise
            return _FakeHTTPResponse(json.dumps(props_data or {}).encode("utf-8"))
        if models_raise is not None:
            raise models_raise
        return _FakeHTTPResponse(json.dumps(models_data or {}).encode("utf-8"))

    return fake_urlopen


def test_probe_chain_models_lacks_n_ctx_but_props_supplies_it() -> None:
    """models entry has no meta.n_ctx; /props.default_generation_settings.n_ctx
    fills it in -- n_ctx_source == 'props'."""
    fresh = _raw_provider()
    models_response = {"data": [{"id": "test-model", "meta": {}}], "object": "list"}
    props_response = {"default_generation_settings": {"n_ctx": 9000}, "total_slots": 1}
    fake = _make_dual_urlopen(models_data=models_response, props_data=props_response)
    with patch("urllib.request.urlopen", side_effect=fake):
        result = fresh.describe()
    assert result["n_ctx"] == 9000
    assert result["n_ctx_source"] == "props"
    assert result["probe_ok"] is True


def test_probe_chain_vllm_max_model_len_fallback() -> None:
    """Neither models.meta.n_ctx nor /props supply a window, but the matched
    models entry has a vLLM-style max_model_len -- n_ctx_source == 'vllm_max_model_len'.
    """
    fresh = _raw_provider()
    models_response = {
        "data": [{"id": "test-model", "meta": {}, "max_model_len": 40000}],
        "object": "list",
    }
    fake = _make_dual_urlopen(models_data=models_response, props_raise=ConnectionError("no props"))
    with patch("urllib.request.urlopen", side_effect=fake):
        result = fresh.describe()
    assert result["n_ctx"] == 40000
    assert result["n_ctx_source"] == "vllm_max_model_len"
    assert result["probe_ok"] is True


def test_probe_chain_all_endpoints_fail_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """models AND props both unreachable -> unknown/8192/probe_ok False, one WARNING."""
    fresh = _raw_provider()

    def fake_urlopen(url: str, timeout: float | None = None):
        raise ConnectionError("down")

    with caplog.at_level("WARNING", logger="visual_qa.local_provider"):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = fresh.describe()

    assert result["n_ctx"] == CONSERVATIVE_UNKNOWN_N_CTX
    assert result["n_ctx_source"] == "unknown"
    assert result["probe_ok"] is False
    warning_messages = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("unable to determine server n_ctx" in m for m in warning_messages), (
        "Probe failure must log a WARNING naming the reason"
    )


def test_probe_non_integer_n_ctx_treated_as_unknown_no_exception() -> None:
    """A non-integer meta.n_ctx value must not crash the probe -- treated as unknown."""
    fresh = _raw_provider()
    models_response = {"data": [{"id": "test-model", "meta": {"n_ctx": "not-a-number"}}], "object": "list"}
    fake = _make_dual_urlopen(models_data=models_response, props_data={})
    with patch("urllib.request.urlopen", side_effect=fake):
        result = fresh.get_context_window()  # must not raise
    assert result == CONSERVATIVE_UNKNOWN_N_CTX


def test_probe_multi_model_listing_matches_requested_id() -> None:
    """/v1/models lists two entries; the one matching the requested id is used."""
    fresh = LocalVisionProvider(base_url="http://x/v1", model="sb-vision")
    models_response = {
        "data": [
            {"id": "sb-chat", "meta": {"n_ctx": 32768}},
            {"id": "sb-vision", "meta": {"n_ctx": 8192}},
        ],
        "object": "list",
    }
    fake = _make_dual_urlopen(models_data=models_response, props_data={})
    with patch("urllib.request.urlopen", side_effect=fake):
        result = fresh.describe()
    assert result["model_served"] == "sb-vision"
    assert result["n_ctx"] == 8192
    assert set(result["models_listed"]) == {"sb-chat", "sb-vision"}


def test_probe_multi_model_listing_requested_id_absent_probe_ok_true() -> None:
    """Requested id is not among the listed models -> model_served None, but
    probe_ok stays True when /props still supplies a usable n_ctx.
    """
    fresh = LocalVisionProvider(base_url="http://x/v1", model="sb-vision-v2")
    models_response = {
        "data": [
            {"id": "sb-chat", "meta": {"n_ctx": 32768}},
            {"id": "sb-vision", "meta": {"n_ctx": 8192}},
        ],
        "object": "list",
    }
    props_response = {"default_generation_settings": {"n_ctx": 8192}, "total_slots": 1}
    fake = _make_dual_urlopen(models_data=models_response, props_data=props_response)
    with patch("urllib.request.urlopen", side_effect=fake):
        result = fresh.describe()
    assert result["model_served"] is None
    assert result["probe_ok"] is True
    assert result["n_ctx"] == 8192
    assert result["n_ctx_source"] == "props"


def test_probe_props_present_records_total_slots_model_path_build_info() -> None:
    fresh = _raw_provider()
    models_response = {"data": [{"id": "test-model", "meta": {"n_ctx": 8192}}], "object": "list"}
    props_response = {
        "default_generation_settings": {"n_ctx": 8192},
        "total_slots": 1,
        "model_path": "/models/sb-vision.gguf",
        "build_info": "b9384-abc123",
    }
    fake = _make_dual_urlopen(models_data=models_response, props_data=props_response)
    with patch("urllib.request.urlopen", side_effect=fake):
        result = fresh.describe()
    assert result["total_slots"] == 1
    assert result["model_path"] == "/models/sb-vision.gguf"
    assert result["build_info"] == "b9384-abc123"


def test_probe_props_unreachable_leaves_fields_none_no_exception() -> None:
    """/props 404 (or any failure) leaves total_slots/model_path/build_info None
    without raising, and does not disturb an n_ctx already found via /models.
    """
    fresh = _raw_provider()
    models_response = {"data": [{"id": "test-model", "meta": {"n_ctx": 32768}}], "object": "list"}
    fake = _make_dual_urlopen(models_data=models_response, props_raise=Exception("404 Not Found"))
    with patch("urllib.request.urlopen", side_effect=fake):
        result = fresh.describe()  # must not raise
    assert result["n_ctx"] == 32768
    assert result["n_ctx_source"] == "models"
    assert result["total_slots"] is None
    assert result["model_path"] is None
    assert result["build_info"] is None


# ---------------------------------------------------------------------------
# EB-392 Unit 1: describe() dict shape
# ---------------------------------------------------------------------------

_DESCRIBE_KEYS = {
    "provider", "base_url", "model_requested", "model_served", "models_listed",
    "n_ctx", "n_ctx_source", "n_ctx_train", "total_slots", "model_path",
    "build_info", "server_type", "probe_ok", "batch_size_effective",
    "max_tokens_effective",
}


def test_describe_happy_path_shape_and_values() -> None:
    fresh = LocalVisionProvider(
        base_url="http://localhost:8000/v1", model="sb-vision", probe=_stub_probe_32768,
    )
    info = fresh.describe()
    assert set(info.keys()) == _DESCRIBE_KEYS
    assert info["provider"] == "local"
    assert info["base_url"] == "http://localhost:8000/v1"
    assert info["model_requested"] == "sb-vision"
    assert info["n_ctx"] == 32768
    assert info["n_ctx_source"] == "models"
    assert info["probe_ok"] is True
    assert info["batch_size_effective"] is None
    assert info["max_tokens_effective"] is None


def test_describe_on_total_probe_failure_all_other_fields_are_empty() -> None:
    """On total probe failure: base_url/model_requested set, n_ctx/n_ctx_source/
    probe_ok reflect the unknown path, everything else None/empty/False.
    """

    def failing_probe(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
        raise ConnectionError("down")

    fresh = LocalVisionProvider(base_url="http://x/v1", model="m", probe=failing_probe)
    info = fresh.describe()
    assert info["base_url"] == "http://x/v1"
    assert info["model_requested"] == "m"
    assert info["n_ctx"] == CONSERVATIVE_UNKNOWN_N_CTX
    assert info["n_ctx_source"] == "unknown"
    assert info["probe_ok"] is False
    assert info["model_served"] is None
    assert info["models_listed"] == []
    assert info["n_ctx_train"] is None
    assert info["total_slots"] is None
    assert info["model_path"] is None
    assert info["build_info"] is None
    assert info["server_type"] is None


# ---------------------------------------------------------------------------
# EB-392 Unit 1: per-image token diagnostic (call())
# ---------------------------------------------------------------------------


def test_call_logs_per_image_token_warning_once_when_actual_exceeds_estimate(
    provider: LocalVisionProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A response implying ~3000 tokens/image (over PER_IMAGE_TOKEN_ESTIMATE=2200)
    logs one WARNING; a second call on the same instance does not repeat it.
    Diagnostic only -- no re-batching, no exception.
    """
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)], rubric_text=RUBRIC_FIXTURE, model=MODEL_FIXTURE,
    )
    fake_content = json.dumps({
        "pages": [{"page_number": 1, "page_type": "body", "score": 90, "pass": True, "issues": []}],
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(
        fake_content, prompt_tokens=3000, completion_tokens=50,
    )
    with caplog.at_level("WARNING", logger="visual_qa.local_provider"):
        with patch("openai.OpenAI", return_value=mock_client):
            provider.call(payload)
            provider.call(payload)

    matches = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "per-image token cost" in r.getMessage()
    ]
    assert len(matches) == 1, (
        f"Expected exactly one per-image diagnostic WARNING, got {len(matches)}"
    )


def test_call_does_not_log_per_image_warning_when_within_estimate(
    provider: LocalVisionProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A response within PER_IMAGE_TOKEN_ESTIMATE must not log the diagnostic."""
    payload = provider.build_request(
        page_images=[(1, PNG_FIXTURE)], rubric_text=RUBRIC_FIXTURE, model=MODEL_FIXTURE,
    )
    fake_content = json.dumps({
        "pages": [{"page_number": 1, "page_type": "body", "score": 90, "pass": True, "issues": []}],
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_fake_completion(
        fake_content, prompt_tokens=2000, completion_tokens=50,
    )
    with caplog.at_level("WARNING", logger="visual_qa.local_provider"):
        with patch("openai.OpenAI", return_value=mock_client):
            provider.call(payload)

    matches = [r for r in caplog.records if "per-image token cost" in r.getMessage()]
    assert matches == []


# ---------------------------------------------------------------------------
# EB-392 Unit 1: run_visual_qa integration
# ---------------------------------------------------------------------------


def _make_report_page(page_number: int, score: int = 90) -> dict:
    return {
        "page_number": page_number,
        "page_type": "body",
        "score": score,
        "pass": score >= 70,
        "issues": [],
    }


def _run_vqa_integration(tmp_path: Path, provider, page_images: list, **extra_kwargs) -> dict:
    """Run run_visual_qa with all heavy I/O mocked; returns the report dict.

    Mirrors tests/test_visual_qa_hybrid_routing.py's _run_vqa helper -- kept
    local to this file to avoid a cross-test-file import dependency.
    """
    import contextlib
    import visual_qa

    input_file = tmp_path / "book.pdf"
    input_file.write_bytes(b"%PDF-1.4")

    patches = [
        patch("visual_qa.convert_to_pdf", return_value=str(input_file)),
        patch("visual_qa.get_pdf_page_count", return_value=200),
        patch("visual_qa.get_pdf_bookmarks", return_value=[]),
        patch("visual_qa.select_sample_pages", return_value=[pn for pn, _ in page_images]),
        patch("visual_qa.find_poppler_path", return_value=""),
        patch("visual_qa.render_pages_to_png", return_value=page_images),
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=True),
    ]
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
            rubric_path="",
            pass_threshold=70,
            fallback_enabled=False,
            **extra_kwargs,
        )
    return report


def test_run_visual_qa_integration_max_batch_size_one_splits_into_three_batches(
    tmp_path: Path,
) -> None:
    """A provider whose max_batch_size() returns 1 with 3 page images issues
    3 separate batches (EB-350/EB-392 integration)."""
    provider = MagicMock(spec=["name", "build_request", "call", "estimate_cost", "max_batch_size"])
    provider.name = "local"
    provider.build_request.return_value = {
        "model": "test-model", "messages": [{"role": "user", "content": []}],
    }
    provider.estimate_cost.return_value = 0.0
    provider.max_batch_size.return_value = 1
    provider.call.side_effect = [
        VisionResponse(raw_text=json.dumps({"pages": [_make_report_page(1)]}), input_tokens=100, output_tokens=50),
        VisionResponse(raw_text=json.dumps({"pages": [_make_report_page(2)]}), input_tokens=100, output_tokens=50),
        VisionResponse(raw_text=json.dumps({"pages": [_make_report_page(3)]}), input_tokens=100, output_tokens=50),
    ]

    page_images = [(1, PNG_FIXTURE), (2, PNG_FIXTURE), (3, PNG_FIXTURE)]
    report = _run_vqa_integration(tmp_path, provider, page_images, batch_size=8)

    assert provider.call.call_count == 3
    assert report["pages_evaluated"] == 3


def test_run_visual_qa_integration_provider_without_max_batch_size_untouched(
    tmp_path: Path,
) -> None:
    """A provider with no max_batch_size (Claude/cloud) is not batch-capped --
    3 pages at configured batch_size=8 stay in a single batch."""
    provider = MagicMock(spec=["name", "build_request", "call", "estimate_cost"])
    provider.name = "cloud"
    provider.build_request.return_value = {
        "model": "m", "messages": [{"role": "user", "content": []}],
    }
    provider.estimate_cost.return_value = 0.0
    provider.call.return_value = VisionResponse(
        raw_text=json.dumps({"pages": [_make_report_page(n) for n in (1, 2, 3)]}),
        input_tokens=300, output_tokens=100,
    )
    assert not hasattr(provider, "max_batch_size"), "Precondition: no max_batch_size attribute"

    page_images = [(1, PNG_FIXTURE), (2, PNG_FIXTURE), (3, PNG_FIXTURE)]
    report = _run_vqa_integration(tmp_path, provider, page_images, batch_size=8)

    assert provider.call.call_count == 1, "Uncapped provider must not be split into extra batches"
    assert report["pages_evaluated"] == 3


def test_run_visual_qa_integration_unknown_probe_sets_coverage_reason_and_degrades_status(
    tmp_path: Path,
) -> None:
    """A provider reporting n_ctx_source == 'unknown' via describe() yields a
    report with coverage_reason == 'probe_failed_conservative_window' and a
    degraded evaluation_status -- while still preserving the score.
    """
    provider = MagicMock(spec=["name", "build_request", "call", "estimate_cost", "describe"])
    provider.name = "local"
    provider.build_request.return_value = {
        "model": "m", "messages": [{"role": "user", "content": []}],
    }
    provider.estimate_cost.return_value = 0.0
    provider.call.return_value = VisionResponse(
        raw_text=json.dumps({"pages": [_make_report_page(1)]}), input_tokens=100, output_tokens=50,
    )
    provider.describe.return_value = {
        "provider": "local", "base_url": "http://x/v1", "model_requested": "m",
        "model_served": None, "models_listed": [], "n_ctx": CONSERVATIVE_UNKNOWN_N_CTX,
        "n_ctx_source": "unknown", "n_ctx_train": None, "total_slots": None,
        "model_path": None, "build_info": None, "server_type": None,
        "probe_ok": False, "batch_size_effective": None, "max_tokens_effective": None,
    }

    page_images = [(1, PNG_FIXTURE)]
    report = _run_vqa_integration(tmp_path, provider, page_images, batch_size=8)

    assert report["coverage_reason"] == "probe_failed_conservative_window"
    assert report["evaluation_status"] == "evaluated_degraded"
    assert report["overall_score"] is not None, (
        "The score must be preserved (not blanked to None) -- the model did respond, "
        "only the window it responded under is unconfirmed"
    )


def test_run_visual_qa_integration_known_window_does_not_set_degraded_reason(
    tmp_path: Path,
) -> None:
    """Sanity check: a provider whose describe() reports a confirmed n_ctx_source
    (not 'unknown') must NOT trigger the degraded coverage_reason."""
    provider = MagicMock(spec=["name", "build_request", "call", "estimate_cost", "describe"])
    provider.name = "local"
    provider.build_request.return_value = {
        "model": "m", "messages": [{"role": "user", "content": []}],
    }
    provider.estimate_cost.return_value = 0.0
    provider.call.return_value = VisionResponse(
        raw_text=json.dumps({"pages": [_make_report_page(1)]}), input_tokens=100, output_tokens=50,
    )
    provider.describe.return_value = {
        "provider": "local", "base_url": "http://x/v1", "model_requested": "m",
        "model_served": "m", "models_listed": ["m"], "n_ctx": 32768,
        "n_ctx_source": "models", "n_ctx_train": None, "total_slots": 1,
        "model_path": None, "build_info": None, "server_type": "llamacpp",
        "probe_ok": True, "batch_size_effective": None, "max_tokens_effective": None,
    }

    page_images = [(1, PNG_FIXTURE)]
    report = _run_vqa_integration(tmp_path, provider, page_images, batch_size=8)

    assert report["coverage_reason"] is None
    assert report["evaluation_status"] == "evaluated"
