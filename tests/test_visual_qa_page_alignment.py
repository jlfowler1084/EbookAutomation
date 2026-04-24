"""Tests for SCRUM-291: VQA report page-number alignment.

The VQA report writer used to store the VLM-returned `page_number` field
verbatim, which broke compare_vqa_reports page-overlap when a VLM
renumbered its response sequentially (1..N) instead of echoing our
rendered page indices. _align_pages_to_batch_order overrides VLM page
numbers with the renderer's authoritative numbers by position.

Discovery context: Mexico Illicit returned [1..8] when the renderer had
sampled [1, 2, 3, 33, 93, 147, 166, 234] — see SCRUM-291 description.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import visual_qa as vqa  # noqa: E402

# Mexico Illicit sample from SCRUM-290 A1 quick run
_MEXICO_RENDERED_PAGES = [1, 2, 3, 33, 93, 147, 166, 234]


def _make_response(page_numbers: list[int]) -> list[dict]:
    """Build a response-shaped pages list with the given page_numbers."""
    return [
        {
            "page_number": pn,
            "page_type": "body",
            "score": 90,
            "pass": True,
            "issues": [],
        }
        for pn in page_numbers
    ]


# ---------------------------------------------------------------------------
# Mexico-shaped: VLM renumbers [1..8] when rendered pages are non-sequential
# ---------------------------------------------------------------------------

def test_mexico_renumber_overridden_to_rendered_pages(caplog):
    """The original SCRUM-291 failure case: VLM returns [1..8], we override
    back to [1, 2, 3, 33, 93, 147, 166, 234] without touching other fields."""
    response = _make_response([1, 2, 3, 4, 5, 6, 7, 8])
    # Mark each page so we can prove non-page_number fields survive intact
    for i, p in enumerate(response):
        p["score"] = 70 + i
        p["page_type"] = f"type_{i}"

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        aligned = vqa._align_pages_to_batch_order(response, _MEXICO_RENDERED_PAGES)

    assert [p["page_number"] for p in aligned] == _MEXICO_RENDERED_PAGES, (
        "page_number must be overridden with rendered indices"
    )
    # Non-page_number fields preserved by position
    for i, p in enumerate(aligned):
        assert p["score"] == 70 + i
        assert p["page_type"] == f"type_{i}"
        assert p["pass"] is True
        assert p["issues"] == []

    # Telemetry: warning fires with override count
    msgs = [r.getMessage() for r in caplog.records]
    assert any("renumbered 5/8 page_number(s)" in m for m in msgs), (
        f"expected renumber warning (5 of 8 page numbers differ), got: {msgs}"
    )
    # Pages 1, 2, 3 happen to coincide → only 5 actual changes (33,93,147,166,234)


# ---------------------------------------------------------------------------
# No-op: VLM echoes our page numbers correctly → no override, no warning
# ---------------------------------------------------------------------------

def test_correct_page_numbers_no_override_no_warning(caplog):
    """When the VLM honors our page numbers, the helper is a structural
    no-op and emits no warning. Guards against noisy logs in the happy path."""
    response = _make_response(_MEXICO_RENDERED_PAGES)

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        aligned = vqa._align_pages_to_batch_order(response, _MEXICO_RENDERED_PAGES)

    assert [p["page_number"] for p in aligned] == _MEXICO_RENDERED_PAGES
    msgs = [r.getMessage() for r in caplog.records]
    assert not any("renumbered" in m for m in msgs), (
        f"no warning should fire on correct numbering, got: {msgs}"
    )


# ---------------------------------------------------------------------------
# Original input not mutated (we returned a new dict on override)
# ---------------------------------------------------------------------------

def test_input_pages_not_mutated_on_override():
    """The helper must not mutate caller-owned dicts — it builds new ones."""
    response = _make_response([1, 2, 3])
    original = [dict(p) for p in response]

    vqa._align_pages_to_batch_order(response, [10, 20, 30])

    assert response == original, "input list of dicts must not be mutated"


# ---------------------------------------------------------------------------
# Defensive: response shorter than batch → align prefix, log mismatch warning
# ---------------------------------------------------------------------------

def test_response_shorter_than_batch_aligns_prefix_and_warns(caplog):
    """Provider page-count guards should prevent this, but the helper
    degrades gracefully rather than crash. Aligns what it can."""
    response = _make_response([1, 2, 3])  # only 3
    batch = [10, 20, 30, 40, 50, 60, 70, 80]  # 8 expected

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        aligned = vqa._align_pages_to_batch_order(response, batch)

    assert [p["page_number"] for p in aligned] == [10, 20, 30]
    msgs = [r.getMessage() for r in caplog.records]
    assert any("length mismatch: response=3, batch=8" in m for m in msgs), (
        f"expected length-mismatch warning, got: {msgs}"
    )


# ---------------------------------------------------------------------------
# Defensive: response longer than batch → align prefix, pass tail through
# ---------------------------------------------------------------------------

def test_response_longer_than_batch_passes_tail_through(caplog):
    """If the response has more entries than batch (also a guard violation),
    align the overlap and pass the trailing entries through untouched."""
    response = _make_response([1, 2, 3, 4, 5])
    batch = [10, 20, 30]

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        aligned = vqa._align_pages_to_batch_order(response, batch)

    assert [p["page_number"] for p in aligned] == [10, 20, 30, 4, 5], (
        "trailing entries beyond batch length should pass through unchanged"
    )
    msgs = [r.getMessage() for r in caplog.records]
    assert any("length mismatch: response=5, batch=3" in m for m in msgs)


# ---------------------------------------------------------------------------
# Non-dict entry passes through (defensive against malformed VLM output)
# ---------------------------------------------------------------------------

def test_non_dict_entry_passes_through_untouched():
    """If a response entry is not a dict (e.g., the VLM returned a string),
    the helper must not crash — pass through and let downstream surface it."""
    response = [
        {"page_number": 1, "score": 90},
        "malformed entry from VLM",
        {"page_number": 99, "score": 50},
    ]
    batch = [10, 20, 30]

    aligned = vqa._align_pages_to_batch_order(response, batch)

    assert aligned[0]["page_number"] == 10
    assert aligned[1] == "malformed entry from VLM"  # untouched
    assert aligned[2]["page_number"] == 30


# ---------------------------------------------------------------------------
# Empty inputs — both an empty response and empty batch
# ---------------------------------------------------------------------------

def test_empty_response_and_batch_returns_empty():
    assert vqa._align_pages_to_batch_order([], []) == []


def test_empty_response_with_nonempty_batch_warns_and_returns_empty(caplog):
    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        aligned = vqa._align_pages_to_batch_order([], [1, 2, 3])
    assert aligned == []
    msgs = [r.getMessage() for r in caplog.records]
    assert any("length mismatch: response=0, batch=3" in m for m in msgs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
