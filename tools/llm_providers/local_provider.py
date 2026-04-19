"""Local Vision provider (sb-chat / vLLM OpenAI-compatible endpoint).

Phase 2 of SCRUM-275 — adds a local inference backend that speaks the
OpenAI chat-completions API. Designed for sb-chat running Qwen3 with
--reasoning-parser qwen3.

Critical requirement: every request MUST include
    extra_body={"chat_template_kwargs": {"enable_thinking": False}}
Without this flag, Qwen3's reasoning parser routes the entire max_tokens
budget into <think> blocks, leaving message.content empty. In-prompt
/no_think does NOT work — this is load-bearing. See SCRUM-275 plan
amendment 2026-04-17 for full smoke-test evidence.
"""

from __future__ import annotations

import base64
import json
import logging
import time

import openai

from .base import VisionResponse


logger = logging.getLogger("visual_qa.local_provider")


def _build_page_extraction_schema(page_count: int) -> dict:
    """Build a strict JSON schema for a VQA page-extraction report.

    The ``pages`` array is constrained to exactly ``page_count`` items via
    ``minItems`` / ``maxItems``.  This makes it structurally impossible for
    vLLM's guided-decoding backend to emit more (or fewer) page entries than
    images were sent — the decoder masks disallowed tokens at generation time.

    SCRUM-279 P1: direct response to the 2026-04-18 Return-of-the-Gods smoke
    where Qwen3.5-MoE returned 221 sequential page entries for 8 input images
    (10,661 output tokens).  ``minItems == maxItems == len(page_images)`` is
    the load-bearing constraint.  See also ``PageCountMismatchError`` which
    stays in place as belt-and-suspenders post-parse defense.

    Enums mirror ``tools/visual_qa_rubric.md`` verbatim (line 59 for
    page_type; lines 62-63 for category and severity).  Three distinct object
    shapes are declared with ``additionalProperties: false`` throughout, as
    required by OpenAI strict-mode:
      1. per-page objects (items of ``pages[]``)
      2. per-issue objects (items of ``pages[].issues[]``)
      3. top-issue objects (items of ``top_issues[]``) — adds ``affected_pages``
    """
    per_issue_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "severity", "description", "suggestion"],
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "text_integrity",
                    "heading_formatting",
                    "paragraph_flow",
                    "toc_navigation",
                    "cover_images",
                    "page_layout",
                ],
            },
            "severity": {
                "type": "string",
                "enum": ["critical", "moderate", "minor"],
            },
            "description": {"type": "string"},
            "suggestion": {"type": "string"},
        },
    }

    top_issue_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "category",
            "severity",
            "description",
            "affected_pages",
            "suggestion",
        ],
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "text_integrity",
                    "heading_formatting",
                    "paragraph_flow",
                    "toc_navigation",
                    "cover_images",
                    "page_layout",
                ],
            },
            "severity": {
                "type": "string",
                "enum": ["critical", "moderate", "minor"],
            },
            "description": {"type": "string"},
            "affected_pages": {
                "type": "array",
                "items": {"type": "integer"},
            },
            "suggestion": {"type": "string"},
        },
    }

    per_page_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["page_number", "page_type", "score", "pass", "issues"],
        "properties": {
            "page_number": {"type": "integer"},
            "page_type": {
                "type": "string",
                # Order matches tools/visual_qa_rubric.md line 59
                "enum": [
                    "cover",
                    "toc",
                    "front_matter",
                    "chapter_start",
                    "body",
                    "back_matter",
                ],
            },
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "pass": {"type": "boolean"},
            "issues": {
                "type": "array",
                "items": per_issue_schema,
            },
        },
    }

    category_scores_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "text_integrity",
            "heading_formatting",
            "paragraph_flow",
            "toc_navigation",
            "cover_images",
            "page_layout",
        ],
        "properties": {
            "text_integrity": {"type": "integer", "minimum": 0, "maximum": 100},
            "heading_formatting": {"type": "integer", "minimum": 0, "maximum": 100},
            "paragraph_flow": {"type": "integer", "minimum": 0, "maximum": 100},
            "toc_navigation": {"type": "integer", "minimum": 0, "maximum": 100},
            "cover_images": {"type": "integer", "minimum": 0, "maximum": 100},
            "page_layout": {"type": "integer", "minimum": 0, "maximum": 100},
        },
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "pages",
            "overall_score",
            "overall_pass",
            "category_scores",
            "summary",
            "top_issues",
        ],
        "properties": {
            "pages": {
                "type": "array",
                # SCRUM-279 P1 load-bearing constraint: prevents the 221-entry
                # hallucination cascade seen in the 2026-04-18 Return-of-the-Gods
                # smoke.  Both bounds must match exactly — minItems alone still
                # allows over-generation that xgrammar would silently truncate.
                "minItems": page_count,
                "maxItems": page_count,
                "items": per_page_schema,
            },
            "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "overall_pass": {"type": "boolean"},
            "category_scores": category_scores_schema,
            "summary": {"type": "string"},
            "top_issues": {
                "type": "array",
                "items": top_issue_schema,
            },
        },
    }


class PageCountMismatchError(RuntimeError):
    """Raised when the model returns a different number of page evaluations
    than images sent in the request.

    Typically indicates a hallucination cascade — e.g., SCRUM-275 smoke
    2026-04-18 where Qwen3.5-MoE generated 221 sequential page entries for
    8 input images (10,661 output tokens vs typical 400-900). Silent
    truncation to expected length would hide the failure and produce
    plausible-looking but ungrounded page_number values; raising preserves
    the signal so downstream consumers mark the report invalid.
    """

    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Model returned {actual} page entries for {expected} input images "
            f"(hallucination suspected — report invalid, do not trust output)"
        )


class LocalVisionProvider:
    """Vision provider backed by a local OpenAI-compatible endpoint.

    Constructor takes base_url once. No API key is required — sb-chat
    does not enforce authentication.
    """

    name = "local"

    def __init__(self, base_url: str = "http://localhost:8000/v1"):
        self._base_url = base_url

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------

    def build_request(
        self,
        page_images: list[tuple[int, bytes]],
        rubric_text: str,
        model: str,
    ) -> dict:
        """Build the OpenAI chat-completions payload with page images + rubric.

        Uses image_url content blocks (data URI format) rather than
        Anthropic's source-type format. The system message carries the
        rubric; page images + instruction go in the user message.
        """
        user_content: list[dict] = []

        for page_num, png_bytes in page_images:
            b64_data = base64.b64encode(png_bytes).decode("utf-8")
            user_content.append({
                "type": "text",
                "text": f"--- Page {page_num} ---",
            })
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64_data}",
                },
            })

        user_content.append({
            "type": "text",
            "text": (
                "Evaluate all pages above against the rubric. "
                "Return ONLY valid JSON (no markdown fences, no commentary). "
                "Include a 'pages' array with one object per page evaluated, "
                "each containing: page_number, page_type, score (0-100), pass (bool), "
                "and issues (array of objects with category, severity, description, suggestion)."
            ),
        })

        return {
            "model": model,
            "messages": [
                {"role": "system", "content": rubric_text},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 16384,
            "temperature": 0.1,
            # NOTE: frequency_penalty intentionally absent. At 0.3 it penalizes
            # repeated JSON schema tokens (keys, enum values) across multi-page
            # batches, causing the model to emit empty {} entries and stop early.
            # See SCRUM-275 smoke evidence 2026-04-18.
            "response_format": {"type": "json_object"},
            # MANDATORY: disable Qwen3 thinking or sb-chat consumes the entire
            # max_tokens budget on <think> blocks, leaving content empty.
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    def call(self, payload: dict) -> VisionResponse:
        """Send the vision request to the local sb-chat endpoint.

        Retries 3 times with 5-second backoff on connection errors
        (not on 429s — local inference has no rate limiting).
        """
        client = openai.OpenAI(
            base_url=self._base_url,
            api_key="not-needed",
        )

        image_count = sum(
            1
            for block in payload["messages"][1]["content"]
            if isinstance(block, dict) and block.get("type") == "image_url"
        )
        logger.info(
            "Sending %d images to local provider at %s...",
            image_count,
            self._base_url,
        )

        max_retries = 3
        backoff_seconds = 5
        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                # Extract extra_body before passing to the SDK — the openai
                # client accepts it as a keyword argument, not inside the dict.
                extra_body = payload.pop("extra_body", None)
                response = client.chat.completions.create(
                    **{k: v for k, v in payload.items()},
                    extra_body=extra_body,
                )
                # Restore extra_body so the payload dict is not mutated for
                # callers that inspect it after the call.
                if extra_body is not None:
                    payload["extra_body"] = extra_body
                break
            except (openai.APIConnectionError, openai.APITimeoutError) as exc:
                # Restore extra_body in case of retry
                if "extra_body" not in payload and extra_body is not None:
                    payload["extra_body"] = extra_body
                last_exc = exc
                if attempt < max_retries:
                    logger.warning(
                        "  Connection error (attempt %d/%d): %s — retrying in %ds...",
                        attempt + 1,
                        max_retries,
                        exc,
                        backoff_seconds,
                    )
                    time.sleep(backoff_seconds)
                    continue
                raise RuntimeError(
                    f"Local provider unreachable after {max_retries} retries: {exc}"
                ) from exc

        choice = response.choices[0]
        raw_text = (choice.message.content or "").strip()

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        logger.info(
            "  Local provider response: %d input, %d output tokens",
            input_tokens,
            output_tokens,
        )

        # Hallucination guard: model must return exactly one page entry per
        # input image. If JSON is malformed we skip the check here and let
        # parse_qa_response's retry handle it; if JSON parses but the count
        # disagrees, raise loudly rather than let downstream consume
        # ungrounded page_number values.
        try:
            parsed = json.loads(raw_text)
            actual_count = len(parsed.get("pages", []))
        except (json.JSONDecodeError, AttributeError):
            actual_count = None

        if actual_count is not None and actual_count != image_count:
            logger.error(
                "Page count mismatch: sent %d images, got %d page entries "
                "(hallucination suspected — see SCRUM-275 smoke evidence)",
                image_count,
                actual_count,
            )
            raise PageCountMismatchError(expected=image_count, actual=actual_count)

        return VisionResponse(
            raw_text=raw_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # ------------------------------------------------------------------
    # Cost
    # ------------------------------------------------------------------

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Local inference is free — always returns 0.0."""
        return 0.0
