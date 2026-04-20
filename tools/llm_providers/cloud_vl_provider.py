"""Cloud VL provider (OpenAI-compatible hosts: OpenRouter, Fireworks, Together).

SCRUM-283 sketch — provides a dedicated cloud-hosted VLM backend after
SCRUM-280 confirmed the local Qwen3.5-35B-A3B grader inflates scores
+11-32 points vs the Claude baseline on Oil Kings / Mexico Illicit pages.
The failure mode is reasoning/calibration (MMMU-shaped), not vision
accuracy (DocVQA-shaped), so jumping to a model with stronger reasoning
at the same param class is the targeted fix.

Target model for R2 gate smoke: Qwen3-VL-30B-A3B on OpenRouter
(~$0.13/M in, $0.52/M out, ~$0.02 for the 48-page smoke corpus).
Full candidate matrix and pricing verification on the SCRUM-283 comment
dated 2026-04-19.

Request shape is intentionally identical to LocalVisionProvider minus the
local-Qwen3 `enable_thinking` kwarg; reuses
`_build_page_extraction_schema()` so the SCRUM-279 P1 cardinality
constraint is preserved across local and cloud backends.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time

import openai

from .base import VisionResponse
from .local_provider import (
    OutputTruncatedError,
    PageCountMismatchError,
    _build_page_extraction_schema,
)


logger = logging.getLogger("visual_qa.cloud_vl_provider")


# Per-(host, model) pricing in USD per 1M tokens. Verified 2026-04-19.
# Update against vendor pricing pages before relying on cost estimates.
_CLOUD_PRICING: dict[tuple[str, str], dict[str, float]] = {
    # OpenRouter
    ("openrouter", "qwen/qwen3-vl-30b-a3b-instruct"):      {"input": 0.13, "output": 0.52},
    ("openrouter", "qwen/qwen3-vl-8b-instruct"):           {"input": 0.08, "output": 0.50},
    ("openrouter", "qwen/qwen-vl-max"):                    {"input": 0.52, "output": 2.08},
    ("openrouter", "qwen/qwen3-vl-235b-a22b-thinking"):    {"input": 0.26, "output": 2.60},
    # Fireworks
    ("fireworks", "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct"): {"input": 0.15, "output": 0.60},
    ("fireworks", "accounts/fireworks/models/qwen3-vl-32b-instruct"):     {"input": 0.50, "output": 0.50},
}


_DEFAULT_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "fireworks":  "https://api.fireworks.ai/inference/v1",
    "together":   "https://api.together.xyz/v1",
}


class CloudVLProvider:
    """Vision provider backed by a cloud-hosted OpenAI-compatible VLM endpoint.

    Tested hosts: OpenRouter (recommended for SCRUM-283 R2 smoke),
    Fireworks, Together. Any host exposing the OpenAI chat.completions
    API with image_url content blocks and json_schema response_format
    works without code changes.

    The request payload mirrors LocalVisionProvider so the rubric text
    and cardinality-enforcing schema flow through unchanged. The only
    intentional divergence is the omission of
    `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` —
    that kwarg is load-bearing for local sb-chat running Qwen3 with the
    qwen3 reasoning parser, but hosted Qwen3-VL endpoints do not expose
    the control and will 400 if it is sent.
    """

    name = "cloud_vl"

    def __init__(
        self,
        host: str = "openrouter",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        if host not in _DEFAULT_BASE_URLS:
            raise ValueError(
                f"Unknown host {host!r}. Known hosts: {sorted(_DEFAULT_BASE_URLS)}"
            )
        if api_key is None:
            env_var = f"{host.upper()}_API_KEY"
            api_key = os.environ.get(env_var)
        if not api_key:
            raise ValueError(
                f"CloudVLProvider requires api_key "
                f"(pass explicitly or set {host.upper()}_API_KEY)"
            )
        self._host = host
        self._api_key = api_key
        self._base_url = base_url or _DEFAULT_BASE_URLS[host]

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------

    def build_request(
        self,
        page_images: list[tuple[int, bytes]],
        rubric_text: str,
        model: str,
    ) -> dict:
        """Build the OpenAI chat-completions payload with images + rubric.

        Uses image_url content blocks (data URI format) per OpenAI spec.
        The `response_format` json_schema carries the full rubric schema
        with minItems == maxItems == len(page_images), identical to the
        local_provider request — this is the SCRUM-279 P1 constraint that
        prevents the 221-entry hallucination cascade seen on Qwen3.5-MoE.
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
                "image_url": {"url": f"data:image/png;base64,{b64_data}"},
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
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "page_extraction_report",
                    "strict": True,
                    "schema": _build_page_extraction_schema(len(page_images)),
                },
            },
        }

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    def call(self, payload: dict) -> VisionResponse:
        """Send the vision request to the configured cloud host.

        Retries 3 times on 429 / transient network errors with 10s/30s/60s
        backoff (mirrors ClaudeVisionProvider). Post-response invariants
        match local_provider: OutputTruncatedError on finish_reason=='length'
        and PageCountMismatchError on pages[] length != image count.
        """
        default_headers: dict[str, str] = {}
        if self._host == "openrouter":
            default_headers = {
                "HTTP-Referer": "https://github.com/jlfowler1084/EbookAutomation",
                "X-Title": "EbookAutomation Visual QA",
            }

        client = openai.OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            default_headers=default_headers or None,
        )

        image_count = sum(
            1
            for block in payload["messages"][1]["content"]
            if isinstance(block, dict) and block.get("type") == "image_url"
        )
        logger.info(
            "Sending %d images to %s (%s) at %s...",
            image_count, self._host, payload.get("model"), self._base_url,
        )

        max_retries = 3
        backoff_seconds = [10, 30, 60]
        response = None

        for attempt in range(max_retries + 1):
            try:
                response = client.chat.completions.create(**payload)
                break
            except openai.RateLimitError as exc:
                if attempt < max_retries:
                    wait = backoff_seconds[attempt]
                    logger.warning(
                        "  Rate-limited (attempt %d/%d) — retrying in %ds...",
                        attempt + 1, max_retries, wait,
                    )
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Cloud VL provider rate-limited after {max_retries} retries: {exc}"
                ) from exc
            except (openai.APIConnectionError, openai.APITimeoutError) as exc:
                if attempt < max_retries:
                    wait = backoff_seconds[attempt]
                    logger.warning(
                        "  Connection error (attempt %d/%d): %s — retrying in %ds...",
                        attempt + 1, max_retries, exc, wait,
                    )
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Cloud VL provider unreachable after {max_retries} retries: {exc}"
                ) from exc

        choice = response.choices[0]
        raw_text = (choice.message.content or "").strip()

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        logger.info(
            "  Cloud VL response: %d input, %d output tokens",
            input_tokens, output_tokens,
        )

        # Truncation guard — guided_json forces the decoder toward the
        # schema's closing bracket; if max_tokens runs out first,
        # raw_text is incomplete JSON. Surface explicitly rather than
        # fall through as a JSONDecodeError downstream.
        if choice.finish_reason == "length":
            max_tokens_budget = payload.get("max_tokens", 0)
            logger.error(
                "Output truncated: finish_reason='length', output_tokens=%d, "
                "budget=%d — report invalid",
                output_tokens, max_tokens_budget,
            )
            raise OutputTruncatedError(
                finish_reason=choice.finish_reason,
                output_tokens=output_tokens,
                max_tokens_budget=max_tokens_budget,
            )

        # Page-count hallucination guard — same invariant as local_provider.
        # Under strict json_schema cardinality this should be unreachable,
        # but kept as belt-and-suspenders since not every host enforces
        # minItems/maxItems at token-masking time.
        try:
            parsed = json.loads(raw_text)
            actual_count = len(parsed.get("pages", []))
        except (json.JSONDecodeError, AttributeError):
            actual_count = None

        if actual_count is not None and actual_count != image_count:
            logger.error(
                "Page count mismatch: sent %d images, got %d page entries",
                image_count, actual_count,
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
        """Return USD cost for a cloud VL call via (host, model) lookup.

        Unknown (host, model) pairs log a warning and return 0.0 rather
        than raise — cost reporting is advisory, the call itself already
        succeeded. Add new entries to _CLOUD_PRICING when introducing a
        new model SKU.
        """
        key = (self._host, model)
        tier = _CLOUD_PRICING.get(key)
        if tier is None:
            logger.warning(
                "No pricing entry for (%s, %s); cost will report as $0.00. "
                "Add to _CLOUD_PRICING in cloud_vl_provider.py.",
                self._host, model,
            )
            return 0.0
        return (
            (input_tokens / 1_000_000) * tier["input"]
            + (output_tokens / 1_000_000) * tier["output"]
        )
