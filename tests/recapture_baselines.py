"""
Re-capture baselines from CURRENT pipeline output.

Runs each book through the HTML extraction pipeline, captures actual metrics,
and overwrites tests/expected_baselines.json with those real values.

Usage:
    python tests/recapture_baselines.py
    python tests/recapture_baselines.py "Oil Kings"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
BASELINES_FILE = TESTS_DIR / "expected_baselines.json"

sys.path.insert(0, str(TOOLS_DIR))
import test_pipeline as _tp  # noqa: E402


# Books to recapture (pdf_pattern matches archive/ glob).
# Corpus policy (SCRUM-303): five books with available source PDFs from the
# CLAUDE.md regression corpus, plus Dionysius retained as the SCRUM-299
# running-header regression anchor. Atomic Habits and Decline of the West
# are CLAUDE.md corpus members but exist only as KFX artifacts; PDF
# acquisition is tracked in SCRUM-304.
BOOK_PATTERNS = {
    "Oil Kings":             "*Oil*Kings*",
    "Mexico":                "*Mexico*Illicit*",
    "Return of the Gods":    "*Return*Gods*",
    "Python in Easy Steps":  "*Python*easy*steps*",
    "Dionysius":             "*Dionysius*",
}


def baseline_from_actual(raw: dict) -> dict:
    """Convert extract_baseline_from_html() output to expected_baselines.json format."""
    h1 = raw["h1_count"]
    h2 = raw["h2_count"]
    h3 = raw["h3_count"]
    toc_depth = 3 if h3 > 0 else (2 if h2 > 0 else 1)
    return {
        "headings": {"h1": h1, "h2": h2, "h3": h3},
        "toc_entries": h1 + h2 + h3,
        "toc_max_depth": toc_depth,
        "footnote_linked_pairs": raw["linked_footnotes"],
        "footnote_unlinked": raw["unlinked_footnotes"],
        "h2_headings": raw["h2_headings"],
        "blockquotes": raw["blockquotes"],
        "em_tags": raw["em_tags"],
        "attributions": raw["attributions"],
        "ligature_splits": raw["ligature_splits_remaining"],
        "double_spaces": raw["double_spaces"],
        "standalone_page_numbers": raw["standalone_page_numbers"],
        "has_front_matter_h1": raw["has_front_matter_h1"],
        "chapter_openings": raw["chapter_openings"],
    }


def _git_head_sha() -> str:
    """Return the short SHA of the current git HEAD, or 'unknown'."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
        )
        return out.decode("ascii", "replace").strip() or "unknown"
    except Exception:
        return "unknown"


def recapture(books_filter: list[str] | None = None) -> int:
    # Load existing baselines so we can keep kfx_size_kb (captured separately
    # from KFX builds) when re-capturing.
    existing: dict = {}
    if BASELINES_FILE.is_file():
        with open(BASELINES_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)

    to_capture = {
        name: pat
        for name, pat in BOOK_PATTERNS.items()
        if not books_filter or any(f.lower() in name.lower() for f in books_filter)
    }

    if not to_capture:
        print(f"ERROR: no book matched {books_filter!r}", file=sys.stderr)
        return 2

    # Full recapture (no filter): start from an empty baseline so books no
    # longer in BOOK_PATTERNS are pruned. Single-book recapture: preserve
    # existing entries for other books.
    if books_filter:
        new_baselines: dict = dict(existing)
    else:
        new_baselines = {}

    total = len(to_capture)
    ok = 0
    failed = 0

    print(f"\n{'=' * 62}")
    print(f"  EbookAutomation — Baseline Recapture ({total} book(s))")
    print(f"{'=' * 62}\n")

    for book_name, pdf_pattern in to_capture.items():
        print(f"  [{ok + failed + 1}/{total}] {book_name} ...", flush=True)

        pdf_path = _tp.find_pdf(pdf_pattern)
        if not pdf_path:
            print(f"  SKIP: PDF not found for pattern {pdf_pattern!r}")
            failed += 1
            continue

        html_path, stdout, stderr = _tp.run_extraction(pdf_path, use_pdfminer=True, test_name=book_name)
        if not html_path or not os.path.isfile(html_path):
            print(f"  FAIL: extraction produced no HTML file")
            if stderr.strip():
                print(f"    stderr: {stderr.strip()[:300]}")
            failed += 1
            continue

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        raw = _tp.extract_baseline_from_html(html)
        entry = baseline_from_actual(raw)

        # Preserve kfx_size_kb from the existing baseline if present (we're not re-running KFX)
        existing_entry = existing.get(book_name, {})
        if "kfx_size_kb" in existing_entry:
            entry["kfx_size_kb"] = existing_entry["kfx_size_kb"]

        entry["pdf_pattern"] = pdf_pattern
        entry["captured_at"] = datetime.now(timezone.utc).isoformat()

        new_baselines[book_name] = entry

        h = entry["headings"]
        print(
            f"  OK: h1={h['h1']} h2={h['h2']} h3={h['h3']} "
            f"linked={entry['footnote_linked_pairs']} "
            f"unlinked={entry['footnote_unlinked']}"
        )
        ok += 1

    if ok == 0:
        print("\nNo books recaptured — aborting write.")
        return 1

    # Build the known-issues comment block as a JSON comment workaround:
    # JSON doesn't support comments; we add a "__known_issues__" key instead.
    known_issues: list[str] = [
        # SCRUM-304: two CLAUDE.md corpus books are KFX-only (no source PDF
        # in archive/), so they cannot be baselined by this script.
        "Atomic Habits: KFX-only in output/kindle/, no source PDF — text-extraction baseline N/A (SCRUM-304)",
        "Decline of the West: KFX-only in output/kindle/, no source PDF — text-extraction baseline N/A (SCRUM-304)",
    ]

    # Check for suspicious Mexico h2 headings (running headers / body promoted to heading)
    mexico = new_baselines.get("Mexico", {})
    mexico_h2 = mexico.get("h2_headings", [])
    suspicious_mexico = [h for h in mexico_h2 if len(h) > 80 or h.islower() or h[0].islower() if h]
    if suspicious_mexico:
        known_issues.append(
            "Mexico: misclassified h2 headings (body text promoted to heading) — "
            f"e.g. {suspicious_mexico[0][:80]!r}"
        )

    # Check for Dionysius high unlinked
    dionysius = new_baselines.get("Dionysius", {})
    if dionysius.get("footnote_unlinked", 0) > 500:
        known_issues.append(
            f"Dionysius: {dionysius['footnote_unlinked']} unlinked footnotes — "
            "known limitation of footnote linking on this book's PDF layout"
        )

    new_baselines["__known_issues__"] = known_issues

    # Capture metadata header so future readers can see when this baseline
    # was taken and against which pipeline commit.
    new_baselines["__metadata__"] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_head_sha": _git_head_sha(),
        "corpus_policy": (
            "5 books with available source PDFs from CLAUDE.md regression "
            "corpus (Oil Kings, Mexico, Return of the Gods, Python in Easy "
            "Steps) plus Dionysius (SCRUM-299 running-header regression "
            "anchor). Atomic Habits and Decline of the West are deferred "
            "to SCRUM-304 pending PDF acquisition."
        ),
        "scrum_ticket": "SCRUM-303",
    }

    with open(BASELINES_FILE, "w", encoding="utf-8") as f:
        json.dump(new_baselines, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 62}")
    print(f"  Recaptured: {ok}/{total}  |  Saved to: {BASELINES_FILE.name}")
    if known_issues:
        print(f"  Known issues recorded ({len(known_issues)}):")
        for issue in known_issues:
            print(f"    - {issue[:90]}")
    print(f"{'=' * 62}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Re-capture baselines from actual pipeline output")
    ap.add_argument("book", nargs="*", metavar="BOOK", help="Book name(s) to recapture (default: all)")
    args = ap.parse_args()
    sys.exit(recapture(args.book or None))
