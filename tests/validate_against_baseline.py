"""
Validate pipeline output against expected baselines.

Runs the PDF -> HTML extraction pipeline on each test book and compares
measurable output properties against the values captured in
tests/expected_baselines.json.

Usage:
    # Standalone (all books):
    python tests/validate_against_baseline.py

    # Standalone (one book):
    python tests/validate_against_baseline.py "Oil Kings"

    # pytest (all books):
    python -m pytest tests/validate_against_baseline.py -v

    # pytest (one book):
    python -m pytest tests/validate_against_baseline.py -v -k "Oil_Kings"

Exit codes:
    0  all books passed
    1  one or more books failed
    2  setup error (missing baseline file, missing PDF, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
BASELINES_FILE = TESTS_DIR / "expected_baselines.json"

# Add tools/ to path so we can import test_pipeline helpers
sys.path.insert(0, str(TOOLS_DIR))
import test_pipeline as _tp  # noqa: E402


# ---------------------------------------------------------------------------
# Baseline loading
# ---------------------------------------------------------------------------

def load_baselines() -> dict:
    if not BASELINES_FILE.is_file():
        raise FileNotFoundError(f"Baseline file not found: {BASELINES_FILE}")
    with open(BASELINES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Per-book comparison
# ---------------------------------------------------------------------------

def _safe_test_name(pdf_path: str, book_name: str) -> str:
    """Return a test_name that keeps the output filename within the NTFS
    255-byte filename limit when passed to _tp.run_extraction().

    Background (EB-208): PDFs with very long filenames produce safe_stems of
    229+ chars; with the test suffix ``_test_<book_name>.html`` appended the
    filename reaches 256 chars — one over the NTFS limit — causing
    [Errno 22] on open(), regardless of the output directory.  Shortening the
    test_name is the only safe fix that doesn't touch pdf_to_balabolka.py.
    """
    import re as _re
    stem = Path(pdf_path).stem
    safe_stem = _re.sub(r"[^\w\s\-]", "", stem).strip().replace(" ", "_")
    fixed_prefix = "_test_"
    fixed_ext = ".html"
    max_slug_len = 255 - len(safe_stem) - len(fixed_prefix) - len(fixed_ext) - 1
    slug = book_name.replace(" ", "_").lower()
    if len(slug) <= max_slug_len:
        return book_name
    return slug[:max(max_slug_len, 4)]


def run_and_compare(book_name: str, entry: dict) -> Tuple[List[str], List[str]]:
    """
    Run HTML extraction for *book_name* and compare against *entry*.
    Returns (passes, failures) — failure strings include specific deviations.
    """
    passes: list[str] = []
    failures: list[str] = []

    # -- Find PDF --
    pdf_path = _tp.find_pdf(entry["pdf_pattern"], exclude=entry.get("pdf_exclude"))
    if not pdf_path:
        failures.append(f"PDF not found matching pattern: {entry['pdf_pattern']}")
        return passes, failures

    # -- Run extraction (with path-safe test_name if needed for EB-208) --
    safe_name = _safe_test_name(pdf_path, book_name)
    html_path, stdout, stderr = _tp.run_extraction(pdf_path, use_pdfminer=True, test_name=safe_name)
    if not html_path or not os.path.isfile(html_path):
        failures.append("HTML file was not produced by extraction pipeline")
        if stderr.strip():
            failures.append(f"  stderr: {stderr.strip()[:200]}")
        return passes, failures

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    current = _tp.extract_baseline_from_html(html)

    # -- Heading counts (±2 tolerance) --
    for level in ("h1", "h2", "h3"):
        expected_n = entry["headings"][level]
        actual_n = current[f"{level}_count"]
        if abs(actual_n - expected_n) <= 2:
            passes.append(f"headings.{level} = {actual_n}  (baseline {expected_n}, tol ±2)")
        else:
            failures.append(
                f"headings.{level}: expected {expected_n} (±2), got {actual_n}"
            )

    # -- TOC entry count (±5 tolerance, sum of all heading levels) --
    expected_toc = entry["toc_entries"]
    actual_toc = current["h1_count"] + current["h2_count"] + current["h3_count"]
    if abs(actual_toc - expected_toc) <= 5:
        passes.append(f"toc_entries = {actual_toc}  (baseline {expected_toc}, tol ±5)")
    else:
        failures.append(
            f"toc_entries: expected {expected_toc} (±5), got {actual_toc}"
        )

    # -- TOC max depth --
    expected_depth = entry["toc_max_depth"]
    actual_depth = (3 if current["h3_count"] > 0
                    else 2 if current["h2_count"] > 0
                    else 1)
    if actual_depth == expected_depth:
        passes.append(f"toc_max_depth = {actual_depth}")
    else:
        failures.append(
            f"toc_max_depth: expected {expected_depth}, got {actual_depth}"
        )

    # -- Linked footnotes (must not regress below baseline) --
    expected_linked = entry["footnote_linked_pairs"]
    actual_linked = current["linked_footnotes"]
    if expected_linked == 0:
        passes.append(f"footnote_linked_pairs = {actual_linked}  (baseline 0, skip regression check)")
    elif actual_linked >= expected_linked:
        passes.append(
            f"footnote_linked_pairs >= {expected_linked}  (got {actual_linked})"
        )
    else:
        failures.append(
            f"footnote_linked_pairs regression: expected >= {expected_linked}, got {actual_linked}"
        )

    # -- Unlinked footnotes (must not increase by more than 5) --
    expected_unlinked = entry["footnote_unlinked"]
    actual_unlinked = current["unlinked_footnotes"]
    if actual_unlinked <= expected_unlinked + 5:
        passes.append(
            f"footnote_unlinked <= {expected_unlinked}  (got {actual_unlinked})"
        )
    else:
        failures.append(
            f"footnote_unlinked regression: expected <= {expected_unlinked}, got {actual_unlinked}"
        )

    # -- h2 headings list (exact match, order-sensitive) --
    expected_h2 = entry.get("h2_headings", [])
    actual_h2 = current.get("h2_headings", [])
    if expected_h2:
        if expected_h2 == actual_h2:
            passes.append(f"h2_headings: all {len(expected_h2)} match exactly")
        else:
            missing = [h for h in expected_h2 if h not in actual_h2]
            added = [h for h in actual_h2 if h not in expected_h2]
            parts = []
            if missing:
                parts.append(f"missing: {[m[:40] for m in missing[:3]]}")
            if added:
                parts.append(f"added: {[a[:40] for a in added[:3]]}")
            failures.append(f"h2_headings differ — {'; '.join(parts)}")

    # -- Ligature splits (must not increase) --
    expected_lig = entry.get("ligature_splits", 0)
    actual_lig = current["ligature_splits_remaining"]
    if actual_lig <= expected_lig:
        passes.append(f"ligature_splits <= {expected_lig}  (got {actual_lig})")
    else:
        failures.append(
            f"ligature_splits regression: expected <= {expected_lig}, got {actual_lig}"
        )

    # -- Double spaces (must not increase) --
    expected_ds = entry.get("double_spaces", 0)
    actual_ds = current["double_spaces"]
    if actual_ds <= expected_ds:
        passes.append(f"double_spaces <= {expected_ds}  (got {actual_ds})")
    else:
        failures.append(
            f"double_spaces regression: expected <= {expected_ds}, got {actual_ds}"
        )

    # -- Standalone page numbers (must not increase) --
    expected_pg = entry.get("standalone_page_numbers", 0)
    actual_pg = current["standalone_page_numbers"]
    if actual_pg <= expected_pg:
        passes.append(f"standalone_page_numbers <= {expected_pg}  (got {actual_pg})")
    else:
        failures.append(
            f"standalone_page_numbers regression: expected <= {expected_pg}, got {actual_pg}"
        )

    # -- Chapter openings (fuzzy 40-char prefix match) --
    expected_openings = entry.get("chapter_openings", {})
    if expected_openings:
        matched = 0
        opener_failures = []
        for heading, expected_opener in expected_openings.items():
            actual_opener = current.get("chapter_openings", {}).get(heading, "")
            if not actual_opener:
                continue  # heading disappeared — caught by h2_headings check
            if expected_opener[:40] == actual_opener[:40]:
                matched += 1
            else:
                opener_failures.append(
                    f'  "{heading[:35]}": '
                    f'expected "{expected_opener[:40]}" '
                    f'got      "{actual_opener[:40]}"'
                )
        if not opener_failures:
            passes.append(f"chapter_openings: all {matched}/{len(expected_openings)} matched")
        else:
            failures.append(
                f"chapter_openings: {len(opener_failures)} mismatch(es):\n"
                + "\n".join(opener_failures)
            )

    return passes, failures


# ---------------------------------------------------------------------------
# pytest integration
# ---------------------------------------------------------------------------

try:
    import pytest

    _baselines: dict = {}
    try:
        _baselines = {k: v for k, v in load_baselines().items() if not k.startswith("__")}
    except FileNotFoundError:
        pass  # pytest will collect the parametrize below; empty means 0 tests

    @pytest.mark.parametrize("book_name,entry", list(_baselines.items()))
    def test_book_baseline(book_name: str, entry: dict) -> None:
        """Pipeline output for each book must match expected_baselines.json."""
        passes, failures = run_and_compare(book_name, entry)
        if failures:
            deviation_block = "\n  ".join(failures)
            pytest.fail(
                f"{book_name}: {len(failures)} check(s) FAILED "
                f"({len(passes)} passed):\n  {deviation_block}"
            )

except ImportError:
    pass  # pytest not installed — standalone mode still works


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def _run_standalone(books_filter: Optional[List[str]] = None) -> int:
    # EB-209: startup guard — detect empty/missing ARCHIVE_DIR before iterating
    # books so that setup errors produce a clear exit-2 instead of 7 spurious
    # "PDF not found" failures that look like real regressions.
    if not _tp.ARCHIVE_DIR.exists():
        print(f"ERROR: ARCHIVE_DIR does not exist: {_tp.ARCHIVE_DIR}", file=sys.stderr)
        sys.exit(2)
    pdf_count = len(list(_tp.ARCHIVE_DIR.glob("*.pdf")))
    if pdf_count == 0:
        print(f"ERROR: ARCHIVE_DIR is empty: {_tp.ARCHIVE_DIR}", file=sys.stderr)
        sys.exit(2)

    try:
        baselines = load_baselines()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if books_filter:
        # case-insensitive substring match
        selected = {
            name: entry
            for name, entry in baselines.items()
            if any(f.lower() in name.lower() for f in books_filter)
        }
        if not selected:
            available = ", ".join(baselines.keys())
            print(
                f"ERROR: No book matching {books_filter!r}\n"
                f"Available: {available}",
                file=sys.stderr,
            )
            return 2
    else:
        selected = {k: v for k, v in baselines.items() if not k.startswith("__")}

    total = len(selected)
    passed = 0
    failed = 0

    print(f"\n{'=' * 62}")
    print(f"  EbookAutomation — Baseline Validation")
    print(f"  Books: {total}  |  Baseline: {BASELINES_FILE.name}")
    print(f"{'=' * 62}\n")

    for book_name, entry in selected.items():
        print(f"  Running: {book_name}...", end="", flush=True)
        book_passes, book_failures = run_and_compare(book_name, entry)
        n_checks = len(book_passes) + len(book_failures)

        if book_failures:
            status = "FAIL"
            failed += 1
        else:
            status = "PASS"
            passed += 1

        print(
            f"\r  {status}: {book_name} "
            f"({len(book_passes)}/{n_checks} checks, "
            f"{'no deviations' if not book_failures else str(len(book_failures)) + ' deviation(s)'})"
        )

        for msg in book_failures:
            # indent multi-line messages
            for line in msg.splitlines():
                print(f"      FAIL: {line}")

    print(f"\n{'=' * 62}")
    print(f"  Results: {passed} passed, {failed} failed, {total} total")
    print(f"{'=' * 62}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Validate pipeline output against expected_baselines.json"
    )
    ap.add_argument(
        "book",
        nargs="*",
        metavar="BOOK",
        help="Book name(s) to validate (default: all). Substring match.",
    )
    args = ap.parse_args()
    sys.exit(_run_standalone(args.book or None))
