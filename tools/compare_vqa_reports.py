#!/usr/bin/env python3
"""Compare Visual-QA report directories against a baseline.

Computes per-book and corpus-level absolute score delta (|Δ|) between a
candidate VQA run and a baseline run, plus an optional secondary reference
(e.g. a prior local-provider run). Outputs a markdown table to stdout and
an optional JSON summary to a file.

Gate thresholds (SCRUM-280 / SCRUM-283 R2):
    - R2(a): equal-weight corpus mean |Δ| < 15
    - R2(b): no per-book mean |Δ| > 20

Exit codes:
    0 — R2(a) and R2(b) both pass
    1 — R2 gate fails
    2 — page-overlap guard hard-fails (< 50%% overlap on any book;
        Lesson-5 source-format drift fingerprint)

Usage:
    python tools/compare_vqa_reports.py \\
        --candidate data/scrum283_unit3_6book_smoke_a3b/ \\
        --baseline  data/vqa_baseline_post_274/ \\
        [--secondary data/scrum280_unit5_winning_smoke/] \\
        [--json-out  data/scrum283_unit4_gate_result_a3b.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("compare_vqa_reports")

_REPORT_SUFFIX = "_visual_qa_report.json"
_R2_CORPUS_THRESHOLD = 15.0
_R2_PER_BOOK_THRESHOLD = 20.0
_OVERLAP_HARD_FAIL = 0.50  # any book below this fraction fails exit 2


@dataclass
class BookDelta:
    """Per-book comparison result."""

    book_stem: str
    baseline_pages: int
    candidate_pages: int
    overlap_pages: int
    overlap_fraction: float
    mean_abs_delta: float | None        # None if no overlap
    max_page_abs_delta: int | None
    detection_misses: int                # pages candidate=[] and baseline!=[]
    secondary_mean_abs_delta: float | None = None
    note: str = ""


@dataclass
class GateResult:
    per_book: list[BookDelta] = field(default_factory=list)
    corpus_mean_equal_weight: float | None = None
    corpus_mean_page_weighted: float | None = None
    max_per_book_mean: float | None = None
    r2a_pass: bool = False
    r2b_pass: bool = False
    overall_pass: bool = False
    overlap_hard_fail: bool = False


def _load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _index_pages(report: dict) -> dict[int, dict]:
    """Return {page_number: page_dict}. First occurrence wins on duplicates."""
    out: dict[int, dict] = {}
    for page in report.get("pages", []):
        pn = page.get("page_number")
        if isinstance(pn, int) and pn not in out:
            out[pn] = page
    return out


def _discover_books(
    candidate_dir: Path,
    baseline_dir: Path,
) -> list[str]:
    """Return sorted book stems present in BOTH directories.

    A "stem" is the filename with the _visual_qa_report.json suffix stripped.
    """
    def _stems(d: Path) -> set[str]:
        return {
            p.name[: -len(_REPORT_SUFFIX)]
            for p in d.glob(f"*{_REPORT_SUFFIX}")
        }

    cand = _stems(candidate_dir)
    base = _stems(baseline_dir)
    only_cand = cand - base
    only_base = base - cand
    if only_cand:
        logger.warning("Books in candidate but not baseline (skipped): %s", sorted(only_cand))
    if only_base:
        logger.warning("Books in baseline but not candidate (skipped): %s", sorted(only_base))
    return sorted(cand & base)


def _compute_book_delta(
    stem: str,
    candidate_dir: Path,
    baseline_dir: Path,
    secondary_dir: Path | None,
) -> BookDelta:
    cand = _load_report(candidate_dir / f"{stem}{_REPORT_SUFFIX}")
    base = _load_report(baseline_dir / f"{stem}{_REPORT_SUFFIX}")

    cand_pages = _index_pages(cand)
    base_pages = _index_pages(base)

    overlap = sorted(cand_pages.keys() & base_pages.keys())
    overlap_count = len(overlap)
    cand_n = len(cand_pages)
    base_n = len(base_pages)
    frac = overlap_count / max(cand_n, base_n) if max(cand_n, base_n) > 0 else 0.0

    if overlap_count == 0:
        return BookDelta(
            book_stem=stem,
            baseline_pages=base_n,
            candidate_pages=cand_n,
            overlap_pages=0,
            overlap_fraction=0.0,
            mean_abs_delta=None,
            max_page_abs_delta=None,
            detection_misses=0,
            note="no overlapping page_numbers — Lesson-5 drift",
        )

    per_page_deltas: list[int] = []
    misses = 0
    for pn in overlap:
        c_score = cand_pages[pn].get("score")
        b_score = base_pages[pn].get("score")
        if isinstance(c_score, int) and isinstance(b_score, int):
            per_page_deltas.append(abs(c_score - b_score))
        c_issues = cand_pages[pn].get("issues") or []
        b_issues = base_pages[pn].get("issues") or []
        if not c_issues and b_issues:
            misses += 1

    secondary_mean: float | None = None
    if secondary_dir is not None:
        sec_path = secondary_dir / f"{stem}{_REPORT_SUFFIX}"
        if sec_path.exists():
            sec = _load_report(sec_path)
            sec_pages = _index_pages(sec)
            sec_deltas = [
                abs(cand_pages[pn]["score"] - sec_pages[pn]["score"])
                for pn in overlap
                if pn in sec_pages
                and isinstance(cand_pages[pn].get("score"), int)
                and isinstance(sec_pages[pn].get("score"), int)
            ]
            if sec_deltas:
                secondary_mean = statistics.mean(sec_deltas)

    note = ""
    if frac < 1.0:
        note = f"partial overlap — {overlap_count}/{max(cand_n, base_n)} pages"

    return BookDelta(
        book_stem=stem,
        baseline_pages=base_n,
        candidate_pages=cand_n,
        overlap_pages=overlap_count,
        overlap_fraction=frac,
        mean_abs_delta=statistics.mean(per_page_deltas) if per_page_deltas else None,
        max_page_abs_delta=max(per_page_deltas) if per_page_deltas else None,
        detection_misses=misses,
        secondary_mean_abs_delta=secondary_mean,
        note=note,
    )


def _aggregate(per_book: list[BookDelta]) -> GateResult:
    gate = GateResult(per_book=per_book)
    valid = [b for b in per_book if b.mean_abs_delta is not None]
    if not valid:
        return gate

    equal_weight = statistics.mean(b.mean_abs_delta for b in valid)
    # Page-weighted: reconstruct per-page deltas implicit from (mean, count)
    # By (mean × overlap), sum, divide by sum(overlap). Equivalent to true per-page mean.
    total_weighted = sum(b.mean_abs_delta * b.overlap_pages for b in valid)
    total_pages = sum(b.overlap_pages for b in valid)
    page_weighted = total_weighted / total_pages if total_pages else None
    max_per_book = max(b.mean_abs_delta for b in valid)

    gate.corpus_mean_equal_weight = equal_weight
    gate.corpus_mean_page_weighted = page_weighted
    gate.max_per_book_mean = max_per_book
    gate.r2a_pass = equal_weight < _R2_CORPUS_THRESHOLD
    gate.r2b_pass = max_per_book <= _R2_PER_BOOK_THRESHOLD
    gate.overall_pass = gate.r2a_pass and gate.r2b_pass
    gate.overlap_hard_fail = any(b.overlap_fraction < _OVERLAP_HARD_FAIL for b in per_book)
    return gate


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _render_markdown(
    gate: GateResult,
    candidate_dir: Path,
    baseline_dir: Path,
    secondary_dir: Path | None,
) -> str:
    lines: list[str] = []
    lines.append(f"# VQA comparison — {candidate_dir.name} vs {baseline_dir.name}")
    if secondary_dir is not None:
        lines.append(f"Secondary reference: `{secondary_dir.name}`")
    lines.append("")

    header = ["Book", "Pages (c/b)", "Overlap", "mean |Δ|", "max |Δ|", "det-miss"]
    if secondary_dir is not None:
        header.append("|Δ| vs 2ndary")
    header.append("Note")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    for b in gate.per_book:
        row = [
            _truncate(b.book_stem, 48),
            f"{b.candidate_pages}/{b.baseline_pages}",
            f"{b.overlap_pages} ({b.overlap_fraction:.0%})",
            f"{b.mean_abs_delta:.1f}" if b.mean_abs_delta is not None else "—",
            f"{b.max_page_abs_delta}" if b.max_page_abs_delta is not None else "—",
            f"{b.detection_misses}",
        ]
        if secondary_dir is not None:
            row.append(
                f"{b.secondary_mean_abs_delta:.1f}"
                if b.secondary_mean_abs_delta is not None
                else "—"
            )
        row.append(b.note)
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("## Corpus summary")
    if gate.corpus_mean_equal_weight is not None:
        lines.append(f"- Equal-weight mean |Δ|: **{gate.corpus_mean_equal_weight:.2f}**")
        lines.append(f"- Page-weighted mean |Δ|: {gate.corpus_mean_page_weighted:.2f}")
        lines.append(f"- Max per-book mean |Δ|: {gate.max_per_book_mean:.2f}")
        lines.append("")
        lines.append("## R2 gate")
        lines.append(f"- R2(a) equal-weight < {_R2_CORPUS_THRESHOLD}: **{'PASS' if gate.r2a_pass else 'FAIL'}**")
        lines.append(f"- R2(b) no per-book > {_R2_PER_BOOK_THRESHOLD}: **{'PASS' if gate.r2b_pass else 'FAIL'}**")
        lines.append(f"- Overall: **{'PASS' if gate.overall_pass else 'FAIL'}**")
    else:
        lines.append("- No valid per-book deltas — cannot evaluate gate.")
    if gate.overlap_hard_fail:
        lines.append("")
        lines.append(f"**WARNING:** at least one book has < {_OVERLAP_HARD_FAIL:.0%} page overlap — Lesson-5 drift suspected. Exit 2.")
    return "\n".join(lines)


def _render_json(
    gate: GateResult,
    candidate_dir: Path,
    baseline_dir: Path,
    secondary_dir: Path | None,
) -> dict:
    return {
        "candidate_dir": str(candidate_dir),
        "baseline_dir": str(baseline_dir),
        "secondary_dir": str(secondary_dir) if secondary_dir else None,
        "thresholds": {
            "r2a_corpus_mean": _R2_CORPUS_THRESHOLD,
            "r2b_per_book_mean": _R2_PER_BOOK_THRESHOLD,
            "overlap_hard_fail_fraction": _OVERLAP_HARD_FAIL,
        },
        "per_book": [asdict(b) for b in gate.per_book],
        "corpus_mean_equal_weight": gate.corpus_mean_equal_weight,
        "corpus_mean_page_weighted": gate.corpus_mean_page_weighted,
        "max_per_book_mean": gate.max_per_book_mean,
        "r2a_pass": gate.r2a_pass,
        "r2b_pass": gate.r2b_pass,
        "overall_pass": gate.overall_pass,
        "overlap_hard_fail": gate.overlap_hard_fail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare VQA report directories and evaluate R2 gate."
    )
    parser.add_argument("--candidate", required=True, type=Path,
                        help="Directory of candidate *_visual_qa_report.json files")
    parser.add_argument("--baseline", required=True, type=Path,
                        help="Directory of baseline (oracle) reports to compare against")
    parser.add_argument("--secondary", type=Path, default=None,
                        help="Optional second reference (e.g. prior local run)")
    parser.add_argument("--json-out", type=Path, default=None,
                        help="Optional path to write the gate result as JSON")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    for d in (args.candidate, args.baseline):
        if not d.is_dir():
            parser.error(f"Not a directory: {d}")
    if args.secondary is not None and not args.secondary.is_dir():
        parser.error(f"Not a directory: {args.secondary}")

    stems = _discover_books(args.candidate, args.baseline)
    if not stems:
        logger.error("No overlapping book reports between candidate and baseline.")
        return 2

    per_book = [
        _compute_book_delta(stem, args.candidate, args.baseline, args.secondary)
        for stem in stems
    ]
    gate = _aggregate(per_book)

    print(_render_markdown(gate, args.candidate, args.baseline, args.secondary))

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        with args.json_out.open("w", encoding="utf-8") as fh:
            json.dump(_render_json(gate, args.candidate, args.baseline, args.secondary),
                      fh, indent=2)
        logger.info("Wrote gate result to %s", args.json_out)

    if gate.overlap_hard_fail:
        return 2
    return 0 if gate.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
