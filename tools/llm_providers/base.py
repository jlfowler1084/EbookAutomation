"""Vision provider interface.

Defines the contract every vision backend must satisfy so visual_qa.py can
treat Claude, local vLLM, or any future provider interchangeably.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class VisionResponse:
    """Normalized response shape returned by every VisionProvider.

    raw_text  — the model's raw text output, expected to be JSON conforming
                to the rubric schema (with or without markdown fences).
    input_tokens  — prompt token count reported by the provider.
    output_tokens — completion token count reported by the provider.
    """

    raw_text: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class VisionProvider(Protocol):
    """Contract for any vision-evaluation backend.

    Implementations build a provider-specific request payload from a list of
    rendered page images and a rubric prompt, send it to their backend, and
    return a normalized VisionResponse. Cost telemetry is computed via
    estimate_cost so the orchestration layer never needs provider-specific
    pricing logic.
    """

    name: str

    def build_request(
        self,
        page_images: list[tuple[int, bytes]],
        rubric_text: str,
        model: str,
    ) -> dict:
        """Construct the provider-native request payload.

        page_images is a list of (page_number, png_bytes) tuples in the
        order they should appear in the prompt. rubric_text becomes the
        system prompt. model is the provider-specific model identifier.
        """
        ...

    def call(self, payload: dict) -> VisionResponse:
        """Send the payload and return a normalized response.

        Implementations are responsible for retries, error handling, and
        translating provider-specific responses into a VisionResponse.
        """
        ...

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Return the dollar cost for the given token usage on this provider.

        Local providers should return 0.0.
        """
        ...
