"""SCRUM-280 Unit 1 — VQA mode classification.

Classifies a post-P1 local VQA corpus into:
  mode 'a' — grading bias: local detects issues but inflates scores
  mode 'b' — detection failure: local misses issues Claude finds
  mixed / dominant-a / dominant-b — intermediate signals

Usage:
    py -3.12 tools/analyze_vqa_mode_classification.py \\
        --local-dir data/scrum275_local_6book \\
        --claude-dir data/vqa_baseline_post_274 \\
        --out data/scrum280_mode_classification/classification.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vqa_mode_classifier")

# Pages where local score >= this threshold are considered "high scoring" for
# grading-bias / detection-failure analysis.  The local model consistently
# scores 80-100; below this band the local score is unreliable for bias diagnosis.
_HIGH_SCORE_THRESHOLD = 80

# Severities (from the rubric + Claude's de-facto 'major' label) that indicate
# a non-trivial issue.  'minor' is excluded intentionally — minor issues on
# high-scoring pages don't distinguish mode (a) from mode (b).
_NONMINOR_SEVERITIES = frozenset({"critical", "moderate", "major"})


def _has_nonminor(issues: list[dict]) -> bool:
    return any(i.get("severity") in _NONMINOR_SEVERITIES for i in issues)


def _determine_book_mode(pct_a: float, pct_b: float) -> str:
    """Translate pct_a / pct_b into a mode verdict."""
    if pct_a >= 0.70:
        return "a"
    if pct_b >= 0.70:
        return "b"
    dominant = max(pct_a, pct_b)
    if dominant >= 0.55:
        return "dominant-a" if pct_a >= pct_b else "dominant-b"
    return "mixed"


def classify_mode(local_report: dict, claude_report: dict) -> dict:
    """Classify one book's VQA output into mode a / b / dominant-x / mixed.

    Raises ValueError when the two reports have different page counts (a
    hard blocker for per-page comparison — mirrors PageCountMismatchError
    style from SCRUM-279 P1).

    Matching is positional, not by page_number.  The local model's
    page_number field may reflect sequential position rather than the actual
    input marker (the R4 grounding defect this plan addresses); using it for
    matching would silently produce wrong cross-page comparisons.  Claude's
    page_number is used as the canonical label in per_page output because
    it reflects the actual sampled page marker.
    """
    local_pages = local_report.get("pages", [])
    claude_pages = claude_report.get("pages", [])

    local_count = len(local_pages)
    claude_count = len(claude_pages)

    if local_count != claude_count:
        raise ValueError(
            f"Page count mismatch: local_report has {local_count} pages, "
            f"claude_report has {claude_count} pages — reports are not comparable "
            f"(check for pre-P1 hallucination cascade in local report)"
        )

    per_page: list[dict] = []
    for local_pg, claude_pg in zip(local_pages, claude_pages):
        local_score: int = local_pg.get("score", 0)
        claude_score: int = claude_pg.get("score", 0)
        local_issues: list[dict] = local_pg.get("issues", [])
        claude_issues: list[dict] = claude_pg.get("issues", [])

        local_has_nonminor = _has_nonminor(local_issues)
        claude_has_cm = _has_nonminor(claude_issues)

        if local_score >= _HIGH_SCORE_THRESHOLD:
            if local_has_nonminor:
                classification = "a"
            elif claude_has_cm:
                classification = "b"
            else:
                classification = "ambiguous"
        else:
            classification = "ambiguous"

        per_page.append({
            # Use claude page_number as canonical label (correct marker);
            # local page_number captured as diagnostic data for grounding audit.
            "page_number": claude_pg.get("page_number"),
            "local_page_number": local_pg.get("page_number"),
            "local_score": local_score,
            "claude_score": claude_score,
            "local_issues_count": len(local_issues),
            "claude_issues_count": len(claude_issues),
            "local_has_nonminor_severity": local_has_nonminor,
            "claude_has_critical_or_moderate": claude_has_cm,
            "per_page_classification": classification,
        })

    total = len(per_page)
    a_count = sum(1 for p in per_page if p["per_page_classification"] == "a")
    b_count = sum(1 for p in per_page if p["per_page_classification"] == "b")
    ambiguous_count = total - a_count - b_count
    high_scoring = sum(1 for p in per_page if p["local_score"] >= _HIGH_SCORE_THRESHOLD)

    pct_a = a_count / total if total else 0.0
    pct_b = b_count / total if total else 0.0
    pct_ambiguous = ambiguous_count / total if total else 0.0

    mode = _determine_book_mode(pct_a, pct_b)

    return {
        "mode": mode,
        "per_page": per_page,
        "aggregate": {
            "pct_mode_a": pct_a,
            "pct_mode_b": pct_b,
            "pct_ambiguous": pct_ambiguous,
            "high_scoring_page_count": high_scoring,
        },
    }


def _determine_overall_mode(book_results: list[dict]) -> str:
    """Aggregate per-book verdicts into an overall corpus verdict.

    Counts books whose mode is in the (a)-family vs (b)-family, then applies
    the same three-tier threshold as the per-book classifier.
    """
    total = len(book_results)
    if total == 0:
        return "mixed"

    a_family = {"a", "dominant-a"}
    b_family = {"b", "dominant-b"}

    a_books = sum(1 for r in book_results if r["mode"] in a_family)
    b_books = sum(1 for r in book_results if r["mode"] in b_family)

    pct_a = a_books / total
    pct_b = b_books / total
    return _determine_book_mode(pct_a, pct_b)


def classify_corpus(local_dir: Path, claude_dir: Path) -> dict:
    """Run classify_mode on every book found in local_dir.

    Returns a dict with 'overall_mode', 'books' (list), and 'errors' (list).
    Books whose page count doesn't match (ValueError) are captured in 'errors'
    so a single broken report doesn't abort the entire corpus run.
    """
    local_files = sorted(local_dir.glob("*_visual_qa_report.json"))
    if not local_files:
        logger.error("No *_visual_qa_report.json files found in %s", local_dir)
        sys.exit(1)

    successful: list[dict] = []
    errors: list[dict] = []

    for local_path in local_files:
        book_name = local_path.stem.replace("_visual_qa_report", "")
        claude_path = claude_dir / local_path.name

        if not claude_path.exists():
            logger.warning("No Claude baseline for %s — skipping", book_name)
            errors.append({"book": book_name, "error": f"Claude file not found: {claude_path}"})
            continue

        with local_path.open(encoding="utf-8") as f:
            local_report = json.load(f)
        with claude_path.open(encoding="utf-8") as f:
            claude_report = json.load(f)

        try:
            result = classify_mode(local_report, claude_report)
            logger.info(
                "  %-45s → %-12s  (a=%.0f%% b=%.0f%% ambig=%.0f%%)",
                book_name[:45],
                result["mode"],
                result["aggregate"]["pct_mode_a"] * 100,
                result["aggregate"]["pct_mode_b"] * 100,
                result["aggregate"]["pct_ambiguous"] * 100,
            )
            successful.append({"book": book_name, **result})
        except ValueError as exc:
            logger.warning("  SKIPPED %s: %s", book_name, exc)
            errors.append({"book": book_name, "error": str(exc)})

    overall_mode = _determine_overall_mode(successful)
    logger.info("Overall corpus classification: %s (%d books, %d errors)", overall_mode, len(successful), len(errors))

    return {
        "overall_mode": overall_mode,
        "books_classified": len(successful),
        "books_errored": len(errors),
        "books": successful,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify post-P1 VQA corpus into mode a (grading bias) / b (detection failure)"
    )
    parser.add_argument(
        "--local-dir",
        required=True,
        type=Path,
        help="Directory containing local provider VQA reports (*_visual_qa_report.json)",
    )
    parser.add_argument(
        "--claude-dir",
        required=True,
        type=Path,
        help="Directory containing Claude baseline VQA reports (*_visual_qa_report.json)",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output path for classification.json",
    )
    args = parser.parse_args()

    if not args.local_dir.is_dir():
        logger.error("--local-dir does not exist: %s", args.local_dir)
        sys.exit(1)
    if not args.claude_dir.is_dir():
        logger.error("--claude-dir does not exist: %s", args.claude_dir)
        sys.exit(1)

    logger.info("Classifying corpus...")
    logger.info("  local-dir:  %s", args.local_dir)
    logger.info("  claude-dir: %s", args.claude_dir)

    result = classify_corpus(args.local_dir, args.claude_dir)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    logger.info("Written to %s", args.out)

    # Exit non-zero if all books errored (no classifiable data)
    if result["books_classified"] == 0:
        logger.error("No books successfully classified — check local-dir contents")
        sys.exit(1)


if __name__ == "__main__":
    main()
