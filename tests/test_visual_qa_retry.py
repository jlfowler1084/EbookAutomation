"""EB-350: Tests for adaptive batch-size cap in visual_qa.py.

EB-392 review (testing): this file previously re-implemented the EB-350
batch-cap block (``_compute_effective_batch``/``_build_batches``) as local
test helpers and asserted against that COPY, not the real code in
``visual_qa.py`` -- the old docstring admitted as much ("a verbatim copy of
the block added to visual_qa.py"). If the production block diverged from the
copy (an off-by-one, an inverted comparison, a broken ``hasattr`` guard),
those tests would keep passing while the real cap silently broke -- the exact
anti-pattern of asserting against re-implemented logic instead of the real
code path.

Rewritten to call ``visual_qa.run_visual_qa`` directly (all heavy I/O mocked,
same pattern as ``tests/test_local_provider_phase2.py``'s own real-path
integration tests) with fake providers. Those integration tests already cover
``max_batch_size() == 1`` (N single-page batches) and "no ``max_batch_size``
attribute at all" (cloud/Claude providers, untouched); this file covers the
remaining, distinct scenarios: a cap strictly between 1 and the configured
batch size, and a cap equal to / larger than the configured batch size
(both no-ops).

All tests are offline -- no live server required.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from llm_providers.base import VisionResponse  # noqa: E402

PNG_FIXTURE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _report_page(page_number: int) -> dict:
    return {"page_number": page_number, "page_type": "body", "score": 90, "pass": True, "issues": []}


def _run_vqa(tmp_path: Path, provider, page_images: list, **extra_kwargs) -> dict:
    """Run run_visual_qa with all heavy I/O mocked; returns the report dict.

    Mirrors tests/test_local_provider_phase2.py's own ``_run_vqa_integration``
    helper -- kept local to this file to avoid a cross-test-file import
    dependency.
    """
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
        return visual_qa.run_visual_qa(
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


def _fake_local_provider(max_batch_size_value: int, per_call_page_groups: list[list[int]]) -> MagicMock:
    """A MagicMock local provider whose ``call()`` returns one response per
    batch (grouped by ``per_call_page_groups``) and whose ``max_batch_size()``
    returns a fixed value -- a real-path stand-in for
    ``LocalVisionProvider.max_batch_size()``.
    """
    provider = MagicMock(spec=["name", "build_request", "call", "estimate_cost", "max_batch_size"])
    provider.name = "local"
    provider.build_request.return_value = {
        "model": "test-model", "messages": [{"role": "user", "content": []}],
    }
    provider.estimate_cost.return_value = 0.0
    provider.max_batch_size.return_value = max_batch_size_value
    provider.call.side_effect = [
        VisionResponse(
            raw_text=json.dumps({"pages": [_report_page(pn) for pn in group]}),
            input_tokens=100 * len(group), output_tokens=50 * len(group),
        )
        for group in per_call_page_groups
    ]
    return provider


def test_run_visual_qa_caps_batch_size_when_provider_max_is_smaller(tmp_path: Path) -> None:
    """6 pages, batch_size=8, provider.max_batch_size()=3 -> 2 batches of 3
    (a cap strictly between 1 and the configured batch size -- not covered by
    test_local_provider_phase2.py's max_batch_size()==1 integration test).
    """
    page_images = [(i, PNG_FIXTURE) for i in range(1, 7)]
    provider = _fake_local_provider(3, [[1, 2, 3], [4, 5, 6]])

    report = _run_vqa(tmp_path, provider, page_images, batch_size=8)

    assert provider.call.call_count == 2
    assert report["pages_evaluated"] == 6


def test_run_visual_qa_does_not_cap_when_provider_max_equals_batch_size(tmp_path: Path) -> None:
    """5 pages, batch_size=5, provider.max_batch_size()=5 -> 1 batch of 5 (no cap)."""
    page_images = [(i, PNG_FIXTURE) for i in range(1, 6)]
    provider = _fake_local_provider(5, [[1, 2, 3, 4, 5]])

    report = _run_vqa(tmp_path, provider, page_images, batch_size=5)

    assert provider.call.call_count == 1
    assert report["pages_evaluated"] == 5


def test_run_visual_qa_does_not_cap_when_provider_max_larger_than_batch_size(tmp_path: Path) -> None:
    """4 pages, batch_size=4, provider.max_batch_size()=10 -> 1 batch of 4 (no cap)."""
    page_images = [(i, PNG_FIXTURE) for i in range(1, 5)]
    provider = _fake_local_provider(10, [[1, 2, 3, 4]])

    report = _run_vqa(tmp_path, provider, page_images, batch_size=4)

    assert provider.call.call_count == 1
    assert report["pages_evaluated"] == 4
