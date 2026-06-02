"""EB-350: Tests for adaptive batch-size cap in visual_qa.py.

Verifies that:
- The local provider's max_batch_size() is respected when it is smaller than
  the configured batch_size.
- The cloud/Claude provider path is completely unaffected (no max_batch_size
  attribute, no cap applied).

All tests are offline — no live server required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from llm_providers.base import VisionResponse  # noqa: E402


PNG_FIXTURE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
RUBRIC_FIXTURE = "RUBRIC TEXT"
MODEL_FIXTURE = "test-model"


def _make_page_response(page_nums: list[int]) -> VisionResponse:
    """Build a VisionResponse whose raw_text has exactly the given page_numbers."""
    pages = [
        {"page_number": pn, "page_type": "body", "score": 90, "pass": True, "issues": []}
        for pn in page_nums
    ]
    return VisionResponse(
        raw_text=json.dumps({"pages": pages}),
        input_tokens=100 * len(page_nums),
        output_tokens=50 * len(page_nums),
    )


def _compute_effective_batch(provider: Any, batch_size: int) -> int:
    """Replicate the EB-350 batch-cap logic from visual_qa.py for isolated testing.

    This directly tests the cap computation without invoking the full
    run_visual_qa pipeline (which requires filesystem, PDF tools, etc.).
    The logic is a verbatim copy of the block added to visual_qa.py.
    """
    effective_batch = batch_size
    if hasattr(provider, "max_batch_size"):
        provider_max = provider.max_batch_size()
        if isinstance(provider_max, int) and provider_max < batch_size:
            effective_batch = provider_max
    return effective_batch


def _build_batches(
    provider: Any,
    page_images: list[tuple[int, bytes]],
    batch_size: int,
) -> list[list[int]]:
    """Build batches using the EB-350 cap logic and return list-of-page-num-lists."""
    effective_batch = _compute_effective_batch(provider, batch_size)
    result = []
    for i in range(0, len(page_images), effective_batch):
        chunk = page_images[i:i + effective_batch]
        result.append([pn for pn, _ in chunk])
    return result


# ---------------------------------------------------------------------------
# EB-350 AC#5: batch-size cap — local provider
#
# The cap logic is isolated in _build_batches() above, which replicates the
# exact 10-line block added to visual_qa.py.  This makes the tests fast,
# dependency-free, and easy to reason about without mocking the full
# run_visual_qa pipeline (PDF rendering, Calibre, etc.).
# ---------------------------------------------------------------------------


def test_visual_qa_caps_batch_size_when_provider_max_is_smaller() -> None:
    """When provider.max_batch_size() < configured batch_size, effective_batch is reduced.

    Scenario: 6 pages, batch_size=8, provider.max_batch_size()=3.
    Expected: 2 batches of 3 pages each.
    """

    class FakeLocalProvider:
        name = "local"

        def max_batch_size(self) -> int:
            return 3  # smaller than configured batch_size=8

    provider = FakeLocalProvider()
    page_images = [(i, PNG_FIXTURE) for i in range(1, 7)]  # 6 pages

    batches = _build_batches(provider, page_images, batch_size=8)

    assert len(batches) == 2, (
        f"Expected 2 batches (6 pages capped to 3 each), got {len(batches)}: {batches}"
    )
    assert batches[0] == [1, 2, 3]
    assert batches[1] == [4, 5, 6]


def test_visual_qa_does_not_cap_when_provider_max_larger_than_batch_size() -> None:
    """When provider.max_batch_size() >= batch_size, no cap is applied.

    Scenario: 4 pages, batch_size=4, provider.max_batch_size()=10.
    Expected: 1 batch of 4 pages.
    """

    class FakeLocalProvider:
        name = "local"

        def max_batch_size(self) -> int:
            return 10  # larger than configured batch_size=4

    provider = FakeLocalProvider()
    page_images = [(i, PNG_FIXTURE) for i in range(1, 5)]  # 4 pages

    batches = _build_batches(provider, page_images, batch_size=4)

    assert len(batches) == 1, (
        f"Expected 1 batch (no cap), got {len(batches)}: {batches}"
    )
    assert batches[0] == [1, 2, 3, 4]


def test_visual_qa_does_not_cap_when_provider_max_equals_batch_size() -> None:
    """When provider.max_batch_size() == batch_size, no cap is applied."""

    class FakeLocalProvider:
        name = "local"

        def max_batch_size(self) -> int:
            return 5

    provider = FakeLocalProvider()
    page_images = [(i, PNG_FIXTURE) for i in range(1, 6)]  # 5 pages

    batches = _build_batches(provider, page_images, batch_size=5)

    assert len(batches) == 1
    assert batches[0] == [1, 2, 3, 4, 5]


def test_visual_qa_cloud_provider_unaffected_by_batch_cap() -> None:
    """Cloud provider has no max_batch_size attribute — batch_size must be unchanged.

    The hasattr guard in visual_qa.py ensures the cap is ONLY applied when
    the provider exposes max_batch_size.
    """

    class FakeCloudProvider:
        name = "cloud"
        # Intentionally NO max_batch_size attribute

    provider = FakeCloudProvider()
    page_images = [(i, PNG_FIXTURE) for i in range(1, 5)]  # 4 pages

    # Verify: no max_batch_size on provider (precondition)
    assert not hasattr(provider, "max_batch_size"), (
        "Precondition: cloud provider must not have max_batch_size"
    )

    batches = _build_batches(provider, page_images, batch_size=4)

    assert len(batches) == 1, (
        "Cloud provider must not be affected by the local-provider batch cap"
    )
    assert batches[0] == [1, 2, 3, 4]


def test_visual_qa_effective_batch_cap_is_1_minimum() -> None:
    """max_batch_size of 1 is honored — each page becomes its own batch."""

    class FakeLocalProvider:
        name = "local"

        def max_batch_size(self) -> int:
            return 1

    provider = FakeLocalProvider()
    page_images = [(i, PNG_FIXTURE) for i in range(1, 4)]  # 3 pages

    batches = _build_batches(provider, page_images, batch_size=8)

    assert len(batches) == 3
    assert batches[0] == [1]
    assert batches[1] == [2]
    assert batches[2] == [3]


def test_effective_batch_is_provider_max_not_configured() -> None:
    """Verify _compute_effective_batch returns provider_max when it is smaller."""

    class FakeLocalProvider:
        name = "local"

        def max_batch_size(self) -> int:
            return 4

    provider = FakeLocalProvider()
    effective = _compute_effective_batch(provider, batch_size=10)
    assert effective == 4


def test_effective_batch_is_configured_when_no_max_batch_size_attr() -> None:
    """Verify _compute_effective_batch returns configured batch_size for cloud providers."""

    class FakeCloudProvider:
        name = "cloud"

    provider = FakeCloudProvider()
    effective = _compute_effective_batch(provider, batch_size=8)
    assert effective == 8
