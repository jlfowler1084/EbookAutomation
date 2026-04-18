"""Claude Vision provider.

Phase 1 of SCRUM-274 — extracts the Anthropic Messages API logic that
previously lived inline in tools/visual_qa.py. The build_request and call
semantics are preserved byte-for-byte so that the refactor produces
bit-identical reports versus the pre-refactor baseline.
"""

from __future__ import annotations

import base64
import logging
import time

import requests

from .base import VisionResponse


logger = logging.getLogger("visual_qa.claude_provider")


# Anthropic API pricing per million tokens. Mirrors the cost model that
# previously lived in visual_qa.build_report so cost reporting stays
# bit-identical.
_CLAUDE_PRICING = {
    "opus":   {"input": 5.00,  "output": 25.00},
    "haiku":  {"input": 1.00,  "output": 5.00},
    "sonnet": {"input": 3.00,  "output": 15.00},
}


def _resolve_pricing_tier(model: str) -> dict:
    """Return the pricing tier for a Claude model name.

    Falls back to Sonnet pricing for unknown model names — matches the
    historical behavior of visual_qa.build_report.
    """
    model_lower = model.lower()
    if "opus" in model_lower:
        return _CLAUDE_PRICING["opus"]
    if "haiku" in model_lower:
        return _CLAUDE_PRICING["haiku"]
    return _CLAUDE_PRICING["sonnet"]


class ClaudeVisionProvider:
    """Vision provider backed by Anthropic's Messages API.

    Constructor takes the API key once so the orchestration layer never
    has to thread it through individual calls.
    """

    name = "claude"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("ClaudeVisionProvider requires a non-empty api_key")
        self._api_key = api_key

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------

    def build_request(
        self,
        page_images: list[tuple[int, bytes]],
        rubric_text: str,
        model: str,
    ) -> dict:
        """Build the Claude API request payload with page images + rubric.

        Output is byte-identical to the pre-refactor build_vision_request
        function in visual_qa.py.
        """
        content: list[dict] = []

        for page_num, png_bytes in page_images:
            b64_data = base64.b64encode(png_bytes).decode("utf-8")
            content.append({
                "type": "text",
                "text": f"--- Page {page_num} ---",
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64_data,
                },
            })

        content.append({
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
            "max_tokens": 8192,
            "system": rubric_text,
            "messages": [
                {"role": "user", "content": content},
            ],
        }

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    def call(self, payload: dict) -> VisionResponse:
        """Send the vision request to the Claude API with retry on overload.

        Mirrors the pre-refactor call_claude_vision behavior: retries once
        each on 429/529 with 10s, 30s, 60s backoff (3 retries total),
        raises RuntimeError on non-retryable failures or exhausted retries.
        """
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }

        image_count = sum(
            1
            for b in payload["messages"][0]["content"]
            if isinstance(b, dict) and b.get("type") == "image"
        )
        logger.info("Sending %d images to Claude Vision API...", image_count)

        max_retries = 3
        backoff_seconds = [10, 30, 60]
        response = None

        for attempt in range(max_retries + 1):
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=300,
            )

            if response.status_code == 200:
                break

            if response.status_code in (429, 529) and attempt < max_retries:
                wait = backoff_seconds[attempt]
                logger.warning(
                    "  API returned %d (attempt %d/%d) — retrying in %ds...",
                    response.status_code, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                continue

            error_body = response.text[:500]
            raise RuntimeError(
                f"Claude API returned {response.status_code}: {error_body}"
            )

        result = response.json()

        usage = result.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        text_blocks = [
            b["text"]
            for b in result.get("content", [])
            if b.get("type") == "text"
        ]
        raw_text = "\n".join(text_blocks).strip()

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
        """Estimate USD cost for a Claude API call.

        Tier resolution matches the pre-refactor visual_qa.build_report
        behavior: substring match against opus/haiku, falling back to
        Sonnet pricing for unknown model names.
        """
        tier = _resolve_pricing_tier(model)
        return (
            (input_tokens / 1_000_000) * tier["input"]
            + (output_tokens / 1_000_000) * tier["output"]
        )
