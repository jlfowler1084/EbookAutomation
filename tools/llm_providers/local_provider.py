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
import logging
import time

import openai

from .base import VisionResponse


logger = logging.getLogger("visual_qa.local_provider")


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
            "frequency_penalty": 0.3,
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
