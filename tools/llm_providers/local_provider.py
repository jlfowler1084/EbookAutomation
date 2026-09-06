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
import urllib.request
import urllib.error
from typing import Any, Callable

import openai

from .base import VisionResponse


logger = logging.getLogger("visual_qa.local_provider")


# EB-358: output-token budget for grading requests (batch and single-page retry).
#
# The sweep #2 evidence (docs/solutions/eb340-vqa-sweep2-findings-2026-06-01.md)
# confirmed that dense/scan batches hit finish_reason='length' at the old 16,384
# cap, returning truncated JSON that is discarded → partial coverage.
#
# Server ceiling: the local vLLM/sb-chat node runs Qwen3-VL-30B-A3B with
# n_ctx=32768 (confirmed in sweep #2 run meta: http://192.168.1.33:8080,
# n_ctx=32768).  The total context window (input tokens + output tokens) must
# not exceed n_ctx.  Dense image batches consume up to ~8K input tokens; leaving
# 24576 for output stays within the 32768 ceiling with a safe margin.
#
# ASSUMPTION: this value was chosen conservatively relative to the confirmed
# n_ctx=32768.  If the server is reconfigured with a different n_ctx, this
# constant must be revisited.  Do NOT raise above 32768 - (minimum input
# overhead) without re-verifying the server n_ctx.
GRADING_MAX_OUTPUT_TOKENS: int = 24576

# EB-350: Adaptive context-budget constants.
#
# The probe (get_context_window) is the source of truth for n_ctx; these
# constants are used to size the output budget and batch limit to fit within
# whatever n_ctx the server reports.
#
# EB-392 Unit 1: the EB-350 branch's silent fallback to a hardcoded 32768 on
# any /models probe failure is REMOVED (maintainability review: that removed
# constant, DEFAULT_CONTEXT_WINDOW, was kept importable for a while as a
# historical note despite being read by no code path here -- a foot-gun for a
# future contributor who greps for "the default context window" and
# reintroduces it without realizing CONSERVATIVE_UNKNOWN_N_CTX below now owns
# that role; it has been deleted outright). A server that never answers (or
# answers with sb-vision's real 8192) is not confirmably 32768, and assuming
# it is caused exactly the context overflow this module exists to prevent.
# Probe failure now resolves to CONSERVATIVE_UNKNOWN_N_CTX (below) with an
# explicit, visible n_ctx_source="unknown" instead.

# CONSERVATIVE_UNKNOWN_N_CTX: EB-392 Unit 1 replacement for the silent-32768
# fallback above. When the probe chain (models -> props -> vLLM
# max_model_len) cannot determine a served n_ctx, assuming the SMALLER known
# window (sb-vision's 8192) is the safe direction to be wrong in: it costs
# batch size / output budget, not a context-overflow 400 mid-run. Paired with
# n_ctx_source="unknown" and probe_ok=False so describe() / run_visual_qa can
# surface the degraded regime to callers that never read provenance.
CONSERVATIVE_UNKNOWN_N_CTX: int = 8192

# ABSOLUTE_MIN_OUTPUT_BUDGET: last-resort output budget when even a single
# image does not leave room for MIN_OUTPUT_BUDGET tokens of output (e.g. a
# server n_ctx far below 8192). output_budget_for logs an ERROR naming the
# server n_ctx whenever this floor is the one that actually applied, and the
# caller continues with batch size 1 and this minimum rather than raising
# before the first call.
ABSOLUTE_MIN_OUTPUT_BUDGET: int = 1024

# PROBE_TIMEOUT_SECONDS: per-HTTP-call timeout used by the default probe
# (models, props). Each call gets one retry on failure before that probe step
# is treated as unreachable.
PROBE_TIMEOUT_SECONDS: float = 5.0

# PER_IMAGE_TOKEN_ESTIMATE: approximate input-token cost of one PNG page image
# at the default 150 DPI rendering resolution.  Measured at ~2198 tokens/image
# in the EB-350 sweep.  Rounded to 2200 for a small headroom buffer.
# NOTE: this estimate is calibrated for 150 DPI.  Higher DPI under-estimates
# input tokens (known v1 limitation; a DPI-aware estimate is a future refinement).
PER_IMAGE_TOKEN_ESTIMATE: int = 2200

# RUBRIC_TOKEN_RESERVE: estimated token cost of the system (rubric) message and
# the trailing instruction text block.  A generous 1500-token reserve keeps the
# budget math valid even for long rubrics.
RUBRIC_TOKEN_RESERVE: int = 1500

# CONTEXT_SAFETY_MARGIN: headroom subtracted from n_ctx before any calculation
# to account for tokenizer variance, KV-cache bookkeeping, and rounding.
CONTEXT_SAFETY_MARGIN: int = 1024

# MIN_OUTPUT_BUDGET: floor for the computed output budget.  8192 tokens is
# sufficient for a single-page grading report with multiple issues and ensures
# the model always has a meaningful generation budget even on small n_ctx nodes.
MIN_OUTPUT_BUDGET: int = 8192


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

    Enums mirror the page_type/category/severity lists in the "Scoring
    Instructions" section of ``tools/visual_qa_rubric.md`` verbatim (referenced
    by section, not line number, since rubric edits shift line numbers).  Three distinct object
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
                # Order matches the page_type list in the "Scoring Instructions" section of tools/visual_qa_rubric.md
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
    bracket of the required schema; if max_tokens (GRADING_MAX_OUTPUT_TOKENS) runs out first, the
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


class ContextWindowOverflowError(RuntimeError):
    """Raised when a local provider 400 BadRequestError indicates context overflow.

    llama.cpp / vLLM return HTTP 400 with error code ``context_length_exceeded``
    (or the string "context" in the message body) when the combined image payload
    exceeds the server's KV-cache window.  This is structurally different from a
    connection error (transient, retry with same payload) or a truncation error
    (output ran long) — the correct recovery is to reduce batch size and retry with
    a smaller payload.

    EB-350: Raised by LocalVisionProvider.call() so visual_qa.py's batch exception
    handler can route to single-page retry with a targeted WARNING instead of a
    generic ERROR that says nothing actionable.
    """

    def __init__(self, message: str):
        self.original_message = message
        super().__init__(
            f"Context window overflow (local provider): {message} — "
            f"reduce batch_size or dpi in settings.json"
        )


# ---------------------------------------------------------------------------
# EB-392 Unit 1: probe chain (models -> props -> vLLM max_model_len -> unknown)
#
# Kept as module-level functions (not methods) so LocalVisionProvider can take
# an arbitrary probe *callable* in its constructor -- tests inject a stub here
# instead of patching urllib, and production code gets this real
# implementation by default. Signature: probe(base_url, model, timeout) ->
# dict. Never raises; every HTTP step is independently best-effort.
# ---------------------------------------------------------------------------

_PROBE_RESULT_KEYS = (
    "n_ctx",
    "n_ctx_source",
    "n_ctx_train",
    "model_served",
    "models_listed",
    "server_type",
    "total_slots",
    "model_path",
    "build_info",
    "probe_ok",
)


def _is_positive_int(value: Any) -> bool:
    """True for real positive ints -- excludes bool (a bool is an int subclass)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _unknown_probe_result() -> dict:
    """The conservative result used whenever the probe cannot determine n_ctx."""
    return {
        "n_ctx": CONSERVATIVE_UNKNOWN_N_CTX,
        "n_ctx_source": "unknown",
        "n_ctx_train": None,
        "model_served": None,
        "models_listed": [],
        "server_type": None,
        "total_slots": None,
        "model_path": None,
        "build_info": None,
        "probe_ok": False,
    }


def _normalize_probe_result(result: dict | None) -> dict:
    """Fill in any missing keys and validate n_ctx so a malformed/partial dict
    from a custom injected probe callable can never crash the caller.
    """
    if not isinstance(result, dict):
        return _unknown_probe_result()
    normalized = _unknown_probe_result()
    normalized.update({k: result[k] for k in _PROBE_RESULT_KEYS if k in result})
    if not _is_positive_int(normalized.get("n_ctx")):
        logger.warning(
            "EB-392: probe result has a non-positive/non-integer n_ctx=%r -- "
            "treating server window as unknown",
            normalized.get("n_ctx"),
        )
        salvage_keys = (
            "model_served", "models_listed", "server_type",
            "total_slots", "model_path", "build_info",
        )
        salvaged = _unknown_probe_result()
        salvaged.update({k: normalized[k] for k in salvage_keys if normalized.get(k)})
        return salvaged
    normalized["probe_ok"] = normalized["n_ctx_source"] != "unknown"
    return normalized


def _fetch_json_with_retry(url: str, timeout: float) -> dict | None:
    """GET url and parse JSON, with one retry on any failure. Never raises."""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug(
                "EB-392: probe GET %s failed (attempt %d/2): %s: %s",
                url, attempt + 1, type(exc).__name__, exc,
            )
    return None


def _probe_local_server(base_url: str, model: str | None, timeout: float = PROBE_TIMEOUT_SECONDS) -> dict:
    """Real HTTP probe chain: models -> props -> vLLM max_model_len -> unknown.

    (a) GET {base_url}/models -- find the data[] entry whose id == the
        requested model (fallback: data[0] only when exactly one entry).
        meta.n_ctx is the served window; meta.n_ctx_train is recorded
        separately as weights provenance and is NEVER used as the window.
    (b) GET {host}/props (base_url with a trailing /v1 stripped) -- always
        attempted when reachable, independent of whether (a) already found
        n_ctx, because it is the only source for total_slots / model_path /
        build_info. default_generation_settings.n_ctx fills n_ctx when (a)
        did not.
    (c) vLLM fallback: the matched /v1/models entry's own max_model_len field.
    (d) Unknown: none of the above yielded a positive integer n_ctx.

    Never raises. Each HTTP step gets one retry (see _fetch_json_with_retry).
    """
    result = _unknown_probe_result()
    base_url_clean = base_url.rstrip("/")

    models_data = _fetch_json_with_retry(f"{base_url_clean}/models", timeout)
    max_model_len = None
    if isinstance(models_data, dict):
        entries = [e for e in (models_data.get("data") or []) if isinstance(e, dict)]
        result["models_listed"] = [e.get("id") for e in entries if e.get("id")]
        matched = None
        if model is not None:
            matched = next((e for e in entries if e.get("id") == model), None)
        if matched is None and len(entries) == 1:
            matched = entries[0]
        if matched is not None:
            result["model_served"] = matched.get("id")
            if matched.get("owned_by"):
                result["server_type"] = matched.get("owned_by")
            meta = matched.get("meta") or {}
            result["n_ctx_train"] = meta.get("n_ctx_train")
            n_ctx = meta.get("n_ctx")
            if _is_positive_int(n_ctx):
                result["n_ctx"] = n_ctx
                result["n_ctx_source"] = "models"
            max_model_len = matched.get("max_model_len")
        elif entries and entries[0].get("owned_by"):
            result["server_type"] = entries[0].get("owned_by")

    host = base_url_clean[: -len("/v1")] if base_url_clean.endswith("/v1") else base_url_clean
    props_data = _fetch_json_with_retry(f"{host}/props", timeout)
    if isinstance(props_data, dict):
        result["total_slots"] = props_data.get("total_slots")
        result["model_path"] = props_data.get("model_path")
        result["build_info"] = props_data.get("build_info")
        if result["n_ctx_source"] == "unknown":
            dgs = props_data.get("default_generation_settings") or {}
            n_ctx = dgs.get("n_ctx")
            if _is_positive_int(n_ctx):
                result["n_ctx"] = n_ctx
                result["n_ctx_source"] = "props"

    if result["n_ctx_source"] == "unknown" and _is_positive_int(max_model_len):
        result["n_ctx"] = max_model_len
        result["n_ctx_source"] = "vllm_max_model_len"

    result["probe_ok"] = result["n_ctx_source"] != "unknown"
    if not result["probe_ok"]:
        logger.warning(
            "EB-392: unable to determine server n_ctx for %s (model=%s) via "
            "models/props/vllm probe -- using conservative n_ctx=%d",
            base_url, model, CONSERVATIVE_UNKNOWN_N_CTX,
        )
    return result


class LocalVisionProvider:
    """Vision provider backed by a local OpenAI-compatible endpoint.

    Constructor takes base_url once. No API key is required — sb-chat
    does not enforce authentication.
    """

    name = "local"

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model: str | None = None,
        n_ctx: int | None = None,
        probe: Callable[..., dict] | None = None,
    ):
        # EB-210 / EB-339: the local VQA endpoint lives on a LAN node (the
        # R9700 Qwen3-VL box, DESKTOP-488UQB2) reachable from the primary
        # desktop. The Hetzner VM (Linux) is off-LAN and cannot reach it, so
        # fail loudly here rather than let a node-unreachable error masquerade
        # as a transient fault. Per EB-339 the fallback is explicit, not silent:
        # on the VM the operator switches to the paid OpenRouter path.
        if sys.platform.startswith("linux"):
            raise RuntimeError(
                "LocalVisionProvider is not reachable from Linux (the Hetzner VM "
                "is off-LAN from the R9700 endpoint). Use the cloud provider "
                "instead: set visual_qa.provider='cloud' (cloud_host='openrouter', "
                "cloud_model='qwen/qwen3-vl-30b-a3b-instruct') and set OPENROUTER_API_KEY."
            )
        self._base_url = base_url
        # EB-392 Unit 1: the id of the model this caller asked for (used to
        # pick the matching /v1/models entry during the probe; visual_qa.py
        # passes this once the model is known). None is valid -- the probe
        # falls back to the single-entry case.
        self._model_requested = model
        # EB-392 Unit 1: an explicit n_ctx (--n-ctx / LOCAL_LLM_N_CTX) always
        # wins over probing -- source "cli" in describe(). The probe still
        # runs (lazily, on first describe()/get_context_window() call that
        # needs it) so metadata like models_listed/total_slots is available.
        self._explicit_n_ctx = n_ctx
        self._probe_fn: Callable[..., dict] = probe if probe is not None else _probe_local_server
        self._probe_result: dict | None = None
        # EB-392 Unit 1: fires at most once per instance -- diagnostic only.
        self._per_image_warning_logged = False
        # EB-392 review: fires at most once per instance -- see describe().
        self._n_ctx_mismatch_warning_logged = False
        # EB-392 Unit 1: slots for the caller (run_visual_qa) to record what it
        # actually used for this run, so describe() can surface them for
        # Unit 2's provider_resolved report block. None until set.
        self.batch_size_effective: int | None = None
        self.max_tokens_effective: int | None = None

    # ------------------------------------------------------------------
    # Adaptive context-budget API (EB-350 / EB-392)
    # ------------------------------------------------------------------

    def _ensure_probed(self, refresh: bool = False) -> dict:
        """Run the probe chain at most once per instance, cache the result.

        EB-392 Unit 1: refresh=True forces a new probe call (describe()'s
        refresh parameter). getattr defaults throughout are deliberate: a
        LocalVisionProvider built via __new__() (bypassing __init__, as some
        older tests do) must still behave safely.
        """
        cached = getattr(self, "_probe_result", None)
        if cached is not None and not refresh:
            return cached

        probe_fn = getattr(self, "_probe_fn", None) or _probe_local_server
        base_url = getattr(self, "_base_url", "")
        model_requested = getattr(self, "_model_requested", None)
        try:
            raw = probe_fn(base_url, model_requested, timeout=PROBE_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning(
                "EB-392: probe callable raised %s: %s -- treating server window as unknown",
                type(exc).__name__, exc,
            )
            raw = None
        result = _normalize_probe_result(raw)
        self._probe_result = result
        return result

    def get_context_window(self) -> int:
        """Return the effective n_ctx: an explicit constructor value always
        wins; otherwise the probed value (probing at most once per instance).

        EB-392 Unit 1: on total probe failure this returns
        CONSERVATIVE_UNKNOWN_N_CTX (8192), NOT a silently assumed 32768 --
        see the constants above for why.
        """
        explicit = getattr(self, "_explicit_n_ctx", None)
        if explicit is not None:
            return explicit
        return self._ensure_probed()["n_ctx"]

    def describe(self, refresh: bool = False) -> dict:
        """Return a provenance record for this provider instance.

        EB-392 Unit 1: the source of truth for Unit 2's provider_resolved
        report block. refresh=True forces a new probe call even if one is
        already cached. On total probe failure (and no explicit --n-ctx),
        every field except base_url/model_requested/n_ctx/n_ctx_source/
        probe_ok is None/empty and n_ctx falls back to
        CONSERVATIVE_UNKNOWN_N_CTX with n_ctx_source="unknown".
        """
        probe = self._ensure_probed(refresh=refresh)
        explicit_n_ctx = getattr(self, "_explicit_n_ctx", None)
        if explicit_n_ctx is not None:
            n_ctx = explicit_n_ctx
            n_ctx_source = "cli"
            # Adversarial review: an explicit --n-ctx/LOCAL_LLM_N_CTX always
            # wins over the probe with zero cross-validation, even though the
            # probe still ran and its answer is right here. If the override
            # is stale (e.g. copied from a different server) and overshoots
            # the real window, every batch is sized for the wrong (larger)
            # window and overflows -- including the single-page retry
            # fallback, which recomputes its budget from this same wrong
            # value and has no further fallback. Surface the mismatch before
            # the first overflowing request rather than only after one.
            probed_n_ctx = probe.get("n_ctx") if probe.get("probe_ok") else None
            if (
                probed_n_ctx is not None
                and probed_n_ctx != explicit_n_ctx
                and not getattr(self, "_n_ctx_mismatch_warning_logged", False)
            ):
                logger.warning(
                    "EB-392: explicit n_ctx (%d, source=cli) disagrees with the "
                    "server's probed n_ctx (%d) -- batches/output budget are "
                    "sized for the explicit value, which always wins; if it "
                    "overshoots the real window, requests can overflow with no "
                    "further fallback. Confirm this override is still correct "
                    "for this server.",
                    explicit_n_ctx, probed_n_ctx,
                )
                self._n_ctx_mismatch_warning_logged = True
        else:
            n_ctx = probe["n_ctx"]
            n_ctx_source = probe["n_ctx_source"]
        return {
            "provider": "local",
            "base_url": getattr(self, "_base_url", None),
            "model_requested": getattr(self, "_model_requested", None),
            "model_served": probe.get("model_served"),
            "models_listed": probe.get("models_listed") or [],
            "n_ctx": n_ctx,
            "n_ctx_source": n_ctx_source,
            "n_ctx_train": probe.get("n_ctx_train"),
            "total_slots": probe.get("total_slots"),
            "model_path": probe.get("model_path"),
            "build_info": probe.get("build_info"),
            "server_type": probe.get("server_type"),
            "probe_ok": probe.get("probe_ok", False),
            "batch_size_effective": getattr(self, "batch_size_effective", None),
            "max_tokens_effective": getattr(self, "max_tokens_effective", None),
        }

    def output_budget_for(self, num_images: int, n_ctx: int | None = None) -> int:
        """Compute the max_tokens output budget for a batch of num_images images.

        Formula (EB-392 Unit 1 fix):
            available = n_ctx - CONTEXT_SAFETY_MARGIN - RUBRIC_TOKEN_RESERVE
            raw       = available - num_images * PER_IMAGE_TOKEN_ESTIMATE
            floor     = min(MIN_OUTPUT_BUDGET, raw)
            budget    = clamp(raw, floor, GRADING_MAX_OUTPUT_TOKENS)

        The EB-350 branch floored every batch at MIN_OUTPUT_BUDGET (8192)
        regardless of how much room the batch actually left -- on a server
        with n_ctx=8192 this asked for MORE output tokens than the entire
        window, guaranteeing an overflow. The floor above scales DOWN with
        the batch instead: a single image at n_ctx=8192 lands around 3468
        (well under the window), not a doomed 8192.

        If floor itself would fall below ABSOLUTE_MIN_OUTPUT_BUDGET (i.e. even
        one image does not leave room for a useful response), this logs an
        ERROR naming the server n_ctx and returns ABSOLUTE_MIN_OUTPUT_BUDGET
        instead of raising -- the caller proceeds with batch size 1 and this
        minimum; results on such a server are unreliable but the pipeline
        does not crash before the first request is even sent.

        A single-image batch at n_ctx=32768 resolves to 24576 (ceiling),
        unchanged from before.

        Args:
            num_images: number of page images in the batch.
            n_ctx: server context window; if None, calls get_context_window().
        """
        if n_ctx is None:
            n_ctx = self.get_context_window()
        available = n_ctx - CONTEXT_SAFETY_MARGIN - RUBRIC_TOKEN_RESERVE
        raw = available - num_images * PER_IMAGE_TOKEN_ESTIMATE
        floor = min(MIN_OUTPUT_BUDGET, raw)
        if floor < ABSOLUTE_MIN_OUTPUT_BUDGET:
            logger.error(
                "EB-392: server n_ctx=%d leaves less than the absolute minimum "
                "output budget (%d) for a %d-image batch (available=%d, raw=%d) "
                "-- continuing with batch size 1 and the absolute minimum "
                "budget; results on this server are unreliable until its "
                "context window is raised",
                n_ctx, ABSOLUTE_MIN_OUTPUT_BUDGET, num_images, available, raw,
            )
            floor = ABSOLUTE_MIN_OUTPUT_BUDGET
        return max(floor, min(GRADING_MAX_OUTPUT_TOKENS, raw))

    def max_batch_size(self, n_ctx: int | None = None) -> int:
        """Return the largest batch N that keeps input + MIN_OUTPUT within n_ctx.

        Formula (solved for N):
            N = floor((available - MIN_OUTPUT_BUDGET) / PER_IMAGE_TOKEN_ESTIMATE)
        where available = n_ctx - CONTEXT_SAFETY_MARGIN - RUBRIC_TOKEN_RESERVE.
        Result is at minimum 1.

        At n_ctx=32768 with the chosen constants:
            available = 32768 - 1024 - 1500 = 30244
            N = floor((30244 - 8192) / 2200) = floor(22052 / 2200) = 10

        At n_ctx=8192 (EB-392 Unit 1 -- sb-vision's real served window):
            available = 8192 - 1024 - 1500 = 5668
            N = floor((5668 - 8192) / 2200) = floor(negative) -> clamped to 1

        Args:
            n_ctx: server context window; if None, calls get_context_window().
        """
        if n_ctx is None:
            n_ctx = self.get_context_window()
        available = n_ctx - CONTEXT_SAFETY_MARGIN - RUBRIC_TOKEN_RESERVE
        n = (available - MIN_OUTPUT_BUDGET) // PER_IMAGE_TOKEN_ESTIMATE
        return max(1, n)

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

        # EB-350: adaptive output budget — sized to fit within the server's n_ctx.
        # Single-page batches resolve to GRADING_MAX_OUTPUT_TOKENS (ceiling) at
        # n_ctx=32768; larger batches receive a proportionally smaller budget so
        # that total (input + output) tokens stay within the server window.
        adaptive_budget = self.output_budget_for(len(page_images))

        return {
            "model": model,
            "messages": [
                {"role": "system", "content": rubric_text},
                {"role": "user", "content": user_content},
            ],
            # EB-358: raised from 16384 → GRADING_MAX_OUTPUT_TOKENS to prevent
            # dense-batch output truncation (finish_reason='length' → dropped pages).
            # EB-350: now adaptive — sized by output_budget_for() to fit n_ctx.
            "max_tokens": adaptive_budget,
            "temperature": 0,
            "seed": 42,
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
        # EB-350: adaptive output budget — same logic as build_request.
        # Pass-1 detection enumerates issues verbosely and benefits from the
        # same context-aware sizing so it doesn't overflow the server window.
        adaptive_budget = self.output_budget_for(page_count)
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": rubric_text},
                {"role": "user", "content": user_content},
            ],
            # EB-358: raised from 16384 → GRADING_MAX_OUTPUT_TOKENS (same as
            # build_request).  Pass-1 detection enumerates issues verbosely and
            # can itself hit the 16K cap on dense/scan pages.
            # EB-350: now adaptive — sized by output_budget_for() to fit n_ctx.
            "max_tokens": adaptive_budget,
            "temperature": 0,
            "seed": 42,
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
                    "Apply these FIXED deductions from 100: each critical issue exactly 52 points; "
                    "each major exactly 25 points; each moderate exactly 15 points; "
                    "each minor exactly 5 points. "
                    "Multiple issues compound additively — a page with two moderate issues and "
                    "one minor issue scores 100 - 15 - 15 - 5 = 65. Floor at 0. "
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
            "temperature": 0,
            "seed": 42,
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
            except openai.BadRequestError as exc:
                # Restore extra_body so callers can inspect the payload.
                if "extra_body" not in payload and extra_body is not None:
                    payload["extra_body"] = extra_body
                # EB-350: llama.cpp / vLLM return 400 with code
                # "context_length_exceeded" when the image payload overflows the
                # KV-cache window.  Detect and surface as a named error so the
                # caller can route to single-page retry with a targeted message.
                error_body = str(exc)
                if "context_length_exceeded" in error_body or "context" in error_body.lower():
                    raise ContextWindowOverflowError(error_body) from exc
                # Unrelated 400s (schema violations, invalid model IDs, etc.) — re-raise
                raise
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

        # EB-392 Unit 1: per-image token diagnostic. PER_IMAGE_TOKEN_ESTIMATE
        # (2200) was measured on vLLM at 150 DPI; if the actual per-image cost
        # on this server/DPI combination runs higher, output_budget_for's
        # headroom shrinks silently. Diagnostic only -- logs once per instance,
        # never re-batches or retries.
        if image_count > 0 and not getattr(self, "_per_image_warning_logged", False):
            actual_per_image = input_tokens / image_count
            if actual_per_image > PER_IMAGE_TOKEN_ESTIMATE:
                logger.warning(
                    "EB-392: actual per-image token cost (%.1f) exceeds "
                    "PER_IMAGE_TOKEN_ESTIMATE (%d) -- input_tokens=%d for %d "
                    "images; diagnostic only, no re-batching",
                    actual_per_image, PER_IMAGE_TOKEN_ESTIMATE, input_tokens, image_count,
                )
                self._per_image_warning_logged = True

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
