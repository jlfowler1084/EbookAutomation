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
import sys
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
                "enum": ["critical", "major", "moderate", "minor"],
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
                "enum": ["critical", "major", "moderate", "minor"],
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


def _build_detection_schema(page_count: int) -> dict:
    """Pass-1 schema for two-pass VQA: issues only, no score/pass fields.

    SCRUM-280 Unit 4 sub-unit 4b-ii: pass 1 forces issue enumeration before
    scoring.  Omitting score/pass prevents the model from reward-hacking to 100
    while citing zero issues.
    """
    per_issue_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "severity", "description", "suggestion"],
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "text_integrity", "heading_formatting", "paragraph_flow",
                    "toc_navigation", "cover_images", "page_layout",
                ],
            },
            "severity": {"type": "string", "enum": ["critical", "major", "moderate", "minor"]},
            "description": {"type": "string"},
            "suggestion": {"type": "string"},
        },
    }
    per_page_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["page_number", "page_type", "issues"],
        "properties": {
            "page_number": {"type": "integer"},
            "page_type": {
                "type": "string",
                "enum": ["cover", "toc", "front_matter", "chapter_start", "body", "back_matter"],
            },
            "issues": {"type": "array", "items": per_issue_schema},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["pages"],
        "properties": {
            "pages": {
                "type": "array",
                "minItems": page_count,
                "maxItems": page_count,
                "items": per_page_schema,
            },
        },
    }


def _build_scoring_schema(page_count: int) -> dict:
    """Pass-2 schema for two-pass VQA: score/pass only, no issue re-generation.

    SCRUM-280 Unit 4 sub-unit 4b-ii: pass 2 scores against already-committed
    issues.  Text-only payload — no images re-sent.
    """
    per_page_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["page_number", "score", "pass"],
        "properties": {
            "page_number": {"type": "integer"},
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "pass": {"type": "boolean"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["pages"],
        "properties": {
            "pages": {
                "type": "array",
                "minItems": page_count,
                "maxItems": page_count,
                "items": per_page_schema,
            },
        },
    }


class OutputTruncatedError(RuntimeError):
    """Raised when the model's response is cut off mid-generation by the
    max_tokens budget (``finish_reason == "length"``).

    SCRUM-279 P1: guided_json schema enforcement makes the 221-entry
    hallucination cascade structurally impossible, but creates a new leading
    failure mode — the decoder is forced to keep generating toward the closing
    bracket of the required schema; if max_tokens (16384) runs out first, the
    output is truncated JSON.  Surface this explicitly rather than letting it
    fall through as a JSONDecodeError in parse_qa_response.

    Distinct from PageCountMismatchError (wrong count, valid JSON) and
    JSONDecodeError (malformed JSON, any reason).
    """

    def __init__(self, finish_reason: str, output_tokens: int, max_tokens_budget: int):
        self.finish_reason = finish_reason
        self.output_tokens = output_tokens
        self.max_tokens_budget = max_tokens_budget
        super().__init__(
            f"Model output truncated mid-generation: finish_reason={finish_reason!r}, "
            f"output_tokens={output_tokens} (budget={max_tokens_budget}) — "
            f"response is incomplete JSON, report invalid"
        )


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


class PageNumberGroundingError(RuntimeError):
    """Raised when the model's output page_number values don't match the input label set.

    SCRUM-280 P2: RotG, Oil Kings, and Decline of the West smoke confirmed that
    Qwen emits sequential position indices (1, 2, 3, 4, ...) instead of the actual
    --- Page N --- marker values (e.g., [1, 2, 3, 70, 87, 138, 154, 221]).  This is
    a grounding failure distinct from count mismatch or truncation.

    Downstream consumers at tools/pattern_db.py:660 and module/EbookAutomation.psm1:2273
    persist page_number into the issues SQLite table.  Positional output silently poisons
    analytics across all books (all issues cluster at sequential indexes 1-8).  This guard
    makes the failure loud regardless of whether the Unit 2 prompt or Unit 3 schema enum
    lands — same belt-and-suspenders posture as PageCountMismatchError.  Stays in place
    even after both remediations are applied.
    """

    def __init__(self, expected_labels: list[int], actual_page_numbers: list[int]):
        self.expected_labels = expected_labels
        self.actual_page_numbers = actual_page_numbers
        label_set = set(expected_labels)
        ungrounded = [n for n in actual_page_numbers if n not in label_set]
        super().__init__(
            f"Page number grounding failure: output contains page_number values not in "
            f"the input label set. Expected labels: {expected_labels}, "
            f"actual page_numbers: {actual_page_numbers}, "
            f"ungrounded values: {ungrounded}"
        )


class LocalVisionProvider:
    """Vision provider backed by a local OpenAI-compatible endpoint.

    Constructor takes base_url once. No API key is required — sb-chat
    does not enforce authentication.
    """

    name = "local"

    def __init__(self, base_url: str = "http://localhost:8000/v1"):
        # EB-210: sb-chat runs on the primary desktop only.  If this provider
        # is instantiated on Linux (the Hetzner VM), it will never reach the
        # endpoint — fail loudly so the operator fixes config before any
        # silent fallback can mask the mismatch.
        if sys.platform.startswith("linux"):
            raise RuntimeError(
                "LocalVisionProvider is not available on Linux. "
                "Update your config to use provider='openrouter' with "
                "model='qwen/qwen3-vl-30b-a3b-instruct' and set OPENROUTER_API_KEY."
            )
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

        # SCRUM-280 P2 sub-step 2a: grounding clause appended to trailing instruction.
        # RotG + Oil Kings + Decline of West smoke confirmed positional output:
        # model emits page_number 1,2,3,4,... (position) instead of the actual
        # --- Page N --- marker values.  Three required elements: (a) must use the
        # label value, (b) not the position, (c) non-sequential example.
        user_content.append({
            "type": "text",
            "text": (
                "Evaluate all pages above against the rubric. "
                "Return ONLY valid JSON (no markdown fences, no commentary). "
                "Include a 'pages' array with one object per page evaluated, "
                "each containing: page_number, page_type, score (0-100), pass (bool), "
                "and issues (array of objects with category, severity, description, suggestion). "
                "CRITICAL: The `page_number` value for each entry MUST be the integer "
                "in the `--- Page N ---` label above each image, NOT the image's "
                "position in the batch. For example, if the labels are [1, 2, 3, 70], "
                "your `page_number` values must be [1, 2, 3, 70], not [1, 2, 3, 4]."
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
            # SCRUM-279 P1: json_schema (OpenAI-native) replaces json_object so
            # vLLM's guided-decoding backend enforces pages array cardinality at
            # token-masking time.  strict=True prevents silent field masking on
            # optional fields.  Backend auto-selected per vLLM 0.19.0 PR #12210
            # (xgrammar lack of minItems/maxItems support triggers fallback to
            # guidance or outlines, both of which honor array-length bounds).
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "page_extraction_report",
                    "strict": True,
                    "schema": _build_page_extraction_schema(len(page_images)),
                },
            },
            # MANDATORY: disable Qwen3 thinking or sb-chat consumes the entire
            # max_tokens budget on <think> blocks, leaving content empty.
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }

    def build_detection_request(
        self,
        page_images: list[tuple[int, bytes]],
        rubric_text: str,
        model: str,
    ) -> dict:
        """Pass 1 of two-pass VQA: enumerate issues per page, no scoring.

        SCRUM-280 Unit 4 sub-unit 4b-ii.  Sends all images with a detection-only
        trailing instruction and a schema that omits score/pass.  The model is
        forced to commit to an issue list before it ever sees a score prompt.
        """
        user_content: list[dict] = []

        for page_num, png_bytes in page_images:
            b64_data = base64.b64encode(png_bytes).decode("utf-8")
            user_content.append({"type": "text", "text": f"--- Page {page_num} ---"})
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_data}"},
            })

        # Detection-only trailing instruction: list issues, no scoring yet.
        # Grounding clause from Unit 2 retained (same page_number requirement).
        user_content.append({
            "type": "text",
            "text": (
                "Examine each page above against the rubric. For each page, list every "
                "visual quality issue you can see — do NOT assign a score yet. "
                "Return ONLY valid JSON with a 'pages' array where each entry contains: "
                "page_number (the integer from the --- Page N --- label above each image, "
                "NOT its position), page_type, and issues (array with category, severity, "
                "description, suggestion). If a page has no issues, set issues to []. "
                "CRITICAL: page_number must be the label value, not the image's position."
            ),
        })

        page_count = len(page_images)
        schema = _build_detection_schema(page_count)
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": rubric_text},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 16384,
            "temperature": 0.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "vqa_detection_report",
                    "schema": schema,
                    "strict": True,
                },
            },
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }

    def build_scoring_request(
        self,
        detected_pages: list[dict],
        rubric_text: str,
        model: str,
    ) -> dict:
        """Pass 2 of two-pass VQA: score against committed issue list, no images.

        SCRUM-280 Unit 4 sub-unit 4b-ii.  Text-only payload — images are not
        re-sent.  The model receives the issue list from pass 1 and must produce
        a score consistent with it, closing the reward-hacking exit.
        """
        issues_text = json.dumps({"pages": detected_pages}, indent=2)
        user_content = [
            {
                "type": "text",
                "text": (
                    f"The following issues were detected on each page during visual inspection:\n\n"
                    f"{issues_text}\n\n"
                    "Using the rubric, assign a score (0-100) and pass/fail for each page "
                    "based on the issues listed above. A score of 100 requires zero issues. "
                    "Apply these deductions from 100: each critical issue 45-60 points; "
                    "each major 20-30 points; each moderate 12-18 points; each minor 4-6 points. "
                    "Multiple issues compound — a page with two moderate issues and one minor "
                    "issue should score in the 60-72 range, not 80+. "
                    "Return ONLY valid JSON with a 'pages' array where each entry has: "
                    "page_number (use the page_number from the input), score, and pass."
                ),
            }
        ]

        page_count = len(detected_pages)
        schema = _build_scoring_schema(page_count)
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": rubric_text},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "vqa_scoring_report",
                    "schema": schema,
                    "strict": True,
                },
            },
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }

    def two_pass_call(
        self,
        page_images: list[tuple[int, bytes]],
        rubric_text: str,
        model: str,
    ) -> VisionResponse:
        """Orchestrates two-pass detection+scoring.  Transactional — raises on
        either pass failure so visual_qa.py's batch exception handler propagates.

        SCRUM-280 Unit 4 sub-unit 4b-ii.  Approved 2026-04-18 after three failed
        prompt-only variants (4b-i, 2a-i, 2a-4).
        NEW DEPENDENCY: EbookAutomation → sb-chat shared stack throughput (~3× per batch,
        measured 9s vs 3s single-pass; pass-1 issue-enumeration prose is more verbose than
        a combined report).  For SCRUM-275 Phase 3 full-book mode planning, use 3× as the
        base estimate for shared-stack cost — not 2× as initially scoped.
        """
        # Pass 1: detection (image payload, all guards active via call())
        detection_payload = self.build_detection_request(page_images, rubric_text, model)
        logger.info("  Two-pass: pass 1 (detection)...")
        detection_response = self.call(detection_payload)
        detection_data = json.loads(detection_response.raw_text)
        detected_pages = detection_data["pages"]

        # Pass 2: scoring (text-only payload, count guard in call() skipped since image_count==0)
        scoring_payload = self.build_scoring_request(detected_pages, rubric_text, model)
        logger.info("  Two-pass: pass 2 (scoring)...")
        scoring_response = self.call(scoring_payload)
        scoring_data = json.loads(scoring_response.raw_text)
        scored_pages = scoring_data["pages"]

        # Transactional count check: pass 2 must return same number of pages as pass 1
        if len(scored_pages) != len(detected_pages):
            raise PageCountMismatchError(
                expected=len(detected_pages),
                actual=len(scored_pages),
            )

        # Merge: combine pass-1 issues/page_type with pass-2 scores.
        # Positional matching (same rationale as classify_mode: page_number may be
        # ungrounded in pass 1; pass 2's page_number values are just echoed input).
        merged_pages = [
            {
                "page_number": det_pg["page_number"],
                "page_type": det_pg.get("page_type", "body"),
                "score": sco_pg["score"],
                "pass": sco_pg["pass"],
                "issues": det_pg.get("issues", []),
            }
            for det_pg, sco_pg in zip(detected_pages, scored_pages)
        ]
        merged_raw = json.dumps({"pages": merged_pages})

        return VisionResponse(
            raw_text=merged_raw,
            input_tokens=detection_response.input_tokens + scoring_response.input_tokens,
            output_tokens=detection_response.output_tokens + scoring_response.output_tokens,
        )

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

        # Truncation guard — fires BEFORE json.loads / PageCountMismatchError.
        # Under guided_json, the decoder is forced toward the schema's closing
        # bracket; if max_tokens is exhausted first, finish_reason=="length" and
        # raw_text is truncated JSON.  Surface this explicitly (SCRUM-279 P1).
        if choice.finish_reason == "length":
            max_tokens_budget = payload.get("max_tokens", 0)
            logger.error(
                "Output truncated: finish_reason='length', output_tokens=%d, "
                "budget=%d — report invalid",
                output_tokens,
                max_tokens_budget,
            )
            raise OutputTruncatedError(
                finish_reason=choice.finish_reason,
                output_tokens=output_tokens,
                max_tokens_budget=max_tokens_budget,
            )

        # Hallucination guard: model must return exactly one page entry per
        # input image. If JSON is malformed we skip the check here and let
        # parse_qa_response's retry handle it; if JSON parses but the count
        # disagrees, raise loudly rather than let downstream consume
        # ungrounded page_number values.
        parsed = None
        try:
            parsed = json.loads(raw_text)
            actual_count = len(parsed.get("pages", []))
        except (json.JSONDecodeError, AttributeError):
            actual_count = None

        if image_count > 0 and actual_count is not None and actual_count != image_count:
            logger.error(
                "Page count mismatch: sent %d images, got %d page entries "
                "(hallucination suspected — see SCRUM-275 smoke evidence)",
                image_count,
                actual_count,
            )
            raise PageCountMismatchError(expected=image_count, actual=actual_count)

        # SCRUM-280 P2 sub-step 2b: page_number grounding guard.  Fires after JSON
        # parse succeeds and count is confirmed matching, before returning a response.
        # Extracts the expected label set from the --- Page N --- text blocks in the
        # payload and verifies every output page_number is in that set.
        # Downstream: tools/pattern_db.py:660 + EbookAutomation.psm1:2273 persist
        # page_number to SQLite; positional output silently poisons analytics.
        input_labels = [
            int(block["text"][len("--- Page "):-len(" ---")])
            for block in payload["messages"][1]["content"]
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and block.get("text", "").startswith("--- Page ")
                and block.get("text", "").endswith(" ---")
            )
        ]
        if parsed is not None and input_labels:
            actual_page_numbers = [
                p.get("page_number") for p in parsed.get("pages", [])
            ]
            label_set = set(input_labels)
            if any(n not in label_set for n in actual_page_numbers if n is not None):
                logger.error(
                    "Page number grounding failure: expected labels %s, got %s "
                    "(positional output — SCRUM-280 P2 R4 defect)",
                    input_labels,
                    actual_page_numbers,
                )
                raise PageNumberGroundingError(
                    expected_labels=input_labels,
                    actual_page_numbers=actual_page_numbers,
                )

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
