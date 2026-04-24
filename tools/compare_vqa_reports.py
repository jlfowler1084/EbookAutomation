#!/usr/bin/env python3
"""Compare Visual-QA report directories against a baseline.

Computes per-book and corpus-level absolute score delta (|Δ|) between a
candidate VQA run and a baseline run, plus an optional secondary reference
(e.g. a prior local-provider run). Outputs a markdown table to stdout and
an optional JSON summary to a file.

Gate thresholds (SCRUM-280 / SCRUM-283 R2):
    - R2(a): equal-weight corpus mean |Δ| < 15
    - R2(b): no per-book mean |Δ| > 20

Subcommands:
    compare (default): R2 gate comparison between candidate and baseline dirs.
    audit:             Verify baseline source parity by comparing stored
                       pages[].page_number arrays against a fresh
                       select_sample_pages() run on the current KFX-derived PDF.

Exit codes (compare):
    0 — R2(a) and R2(b) both pass
    1 — R2 gate fails
    2 — page-overlap guard hard-fails (< 50%% overlap on any book;
        Lesson-5 source-format drift fingerprint)

Exit codes (audit):
    0 — all baselines in parity
    1 — one or more baselines skipped (no matching KFX only), no mismatches, no infra errors
    2 — one or more baselines mismatched (real sampled-page drift)
    3 — one or more baselines hit an infrastructure or data error (conversion_error,
        schema_error, or load_error). Operator should investigate before re-capturing.

Skip reasons surfaced per row (audit):
    no_matching_kfx — baseline present, no *.kfx in --kfx-dir with the same stem
    load_error       — baseline JSON unreadable or invalid (OSError, JSONDecodeError)
    schema_error     — baseline JSON valid but missing pages[].page_number
    conversion_error — Calibre/pypdf failure converting KFX or reading the resulting PDF

Usage (compare — default, backward-compatible):
    python tools/compare_vqa_reports.py \\
        --candidate data/scrum283_unit3_6book_smoke_a3b/ \\
        --baseline  data/vqa_baseline_post_274/ \\
        [--secondary data/scrum280_unit5_winning_smoke/] \\
        [--json-out  data/scrum283_unit4_gate_result_a3b.json]

Usage (compare — explicit subcommand):
    python tools/compare_vqa_reports.py compare \\
        --candidate data/scrum283_unit3_6book_smoke_a3b/ \\
        --baseline  data/vqa_baseline_post_274/

Usage (audit):
    python tools/compare_vqa_reports.py audit \\
        [--baseline-dir data/vqa_baseline_post_274/] \\
        [--kfx-dir output/kindle/] \\
        [--json]

When --json is passed, stdout emits a single JSON object with shape
{exit_code, summary{total,parity,skipped,mismatch}, books[]} for agent
consumption. The markdown table is suppressed; logging stays on stderr.
The exit_code field reflects the actual returned exit code (0/1/2/3),
including the SCRUM-287 infra/data-error code 3.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Helpers imported for the audit subcommand.
# Monkeypatch these names in compare_vqa_reports module namespace during unit tests
# to avoid invoking Calibre.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from visual_qa import (  # noqa: E402
    convert_to_pdf,
    get_pdf_page_count,
    get_pdf_bookmarks,
    select_sample_pages,
    load_settings_json,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("compare_vqa_reports")

_REPORT_SUFFIX = "_visual_qa_report.json"
_R2_CORPUS_THRESHOLD = 15.0
_R2_PER_BOOK_THRESHOLD = 20.0
_OVERLAP_HARD_FAIL = 0.50  # any book below this fraction fails exit 2


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_stems(d: Path) -> set[str]:
    """Return set of book stems from *_visual_qa_report.json in d (non-recursive)."""
    return {
        p.name[: -len(_REPORT_SUFFIX)]
        for p in d.glob(f"*{_REPORT_SUFFIX}")
    }


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


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Compare subcommand — dataclasses and logic
# ---------------------------------------------------------------------------

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


def _discover_books(
    candidate_dir: Path,
    baseline_dir: Path,
) -> list[str]:
    """Return sorted book stems present in BOTH directories.

    A "stem" is the filename with the _visual_qa_report.json suffix stripped.
    """
    cand = _get_stems(candidate_dir)
    base = _get_stems(baseline_dir)
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


def _cmd_compare(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Handler for the compare subcommand (and legacy default invocation)."""
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


# ---------------------------------------------------------------------------
# Audit subcommand
# ---------------------------------------------------------------------------

@dataclass
class BookAuditResult:
    """Per-book audit result from the audit subcommand."""
    stem: str
    status: str          # "parity" | "mismatch" | "skipped"
    baseline_pages: list[int]
    expected_pages: list[int] | None   # None when skipped
    note: str = ""
    # One of: None (parity/mismatch), "no_matching_kfx", "load_error",
    # "schema_error", "conversion_error". Drives exit-code taxonomy.
    skip_reason: str | None = None


def _cmd_audit(args: argparse.Namespace) -> int:
    """Handler for the audit subcommand.

    For each baseline JSON in --baseline-dir, find the matching KFX in --kfx-dir
    by exact stem, derive a fresh select_sample_pages() result from that KFX, and
    compare it to the baseline's pages[].page_number array.

    Exit codes:
        0 — all parity
        1 — only no_matching_kfx skips, no mismatches or infra errors
        2 — real sampled-page drift on at least one book
        3 — conversion_error / schema_error / load_error on at least one book
            (operator should investigate before re-capturing)

    Exit 3 takes precedence over 2 (infra/data problems mask real drift signal).
    Exit 2 takes precedence over 1 (real drift beats no-KFX skip).

    Unexpected exceptions (AttributeError, ValueError, etc.) are not caught here
    and will propagate — they signal a programming bug that should fail loudly.
    """
    baseline_dir = Path(args.baseline_dir)
    kfx_dir = Path(args.kfx_dir)
    calibre_path = args.calibre

    if not baseline_dir.is_dir():
        logger.error("Not a directory: %s", baseline_dir)
        return 2

    kfx_by_stem: dict[str, Path] = {}
    if kfx_dir.is_dir():
        kfx_by_stem = {p.stem: p for p in kfx_dir.glob("*.kfx")}
    else:
        logger.warning("kfx-dir not found: %s — all baselines will be skipped", kfx_dir)

    stems = sorted(_get_stems(baseline_dir))
    if not stems:
        logger.error("No baseline reports found in %s", baseline_dir)
        return 2

    results: list[BookAuditResult] = []

    for stem in stems:
        baseline_path = baseline_dir / f"{stem}{_REPORT_SUFFIX}"

        try:
            report = _load_report(baseline_path)
        except (OSError, json.JSONDecodeError) as exc:
            results.append(BookAuditResult(
                stem=stem, status="skipped",
                baseline_pages=[], expected_pages=None,
                note=f"load error: {exc}",
                skip_reason="load_error",
            ))
            logger.warning("Skipping %s: load_error: %s", stem, exc)
            continue

        baseline_page_nums: list[int] = [
            p["page_number"] for p in report.get("pages", [])
            if isinstance(p.get("page_number"), int)
        ]
        if not baseline_page_nums:
            results.append(BookAuditResult(
                stem=stem, status="skipped",
                baseline_pages=[], expected_pages=None,
                note="baseline missing pages[].page_number",
                skip_reason="schema_error",
            ))
            logger.warning("Skipping %s: schema_error: missing pages[].page_number", stem)
            continue

        kfx_path = kfx_by_stem.get(stem)
        if kfx_path is None:
            results.append(BookAuditResult(
                stem=stem, status="skipped",
                baseline_pages=baseline_page_nums, expected_pages=None,
                note="no matching KFX in kfx-dir",
                skip_reason="no_matching_kfx",
            ))
            logger.warning("Skipping %s: no matching KFX found", stem)
            continue

        try:
            pdf_path = convert_to_pdf(kfx_path, calibre_path)
            total_pages = get_pdf_page_count(pdf_path)
            bookmark_pages = get_pdf_bookmarks(pdf_path)
            max_samples = report.get('pages_sampled', 8)
            expected = select_sample_pages(total_pages, max_samples=max_samples,
                                           bookmark_pages=bookmark_pages)
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            results.append(BookAuditResult(
                stem=stem, status="skipped",
                baseline_pages=baseline_page_nums, expected_pages=None,
                note=f"KFX/PDF error: {exc}",
                skip_reason="conversion_error",
            ))
            logger.warning("Skipping %s: conversion_error: %s", stem, exc)
            continue

        if sorted(baseline_page_nums) == sorted(expected):
            results.append(BookAuditResult(
                stem=stem, status="parity",
                baseline_pages=baseline_page_nums, expected_pages=expected,
            ))
        else:
            results.append(BookAuditResult(
                stem=stem, status="mismatch",
                baseline_pages=baseline_page_nums, expected_pages=expected,
                note="sampled-page mismatch",
            ))

    exit_code = _compute_audit_exit_code(results)

    if getattr(args, "json", False):
        print(json.dumps(_render_audit_json(results, exit_code), indent=2))
    else:
        _print_audit_table(results)

    return exit_code


_INFRA_SKIP_REASONS = frozenset({"conversion_error", "schema_error", "load_error"})


def _compute_audit_exit_code(results: list[BookAuditResult]) -> int:
    """Derive the audit exit code from per-book results.

    Priority (highest first): infra/data error (3) > mismatch (2) > no-KFX skip (1) > all parity (0).
    Kept as a separate helper so the --json output and the CLI return value
    are guaranteed to agree.
    """
    any_infra = any(r.skip_reason in _INFRA_SKIP_REASONS for r in results)
    any_mismatch = any(r.status == "mismatch" for r in results)
    any_no_kfx = any(r.skip_reason == "no_matching_kfx" for r in results)
    if any_infra:
        return 3
    if any_mismatch:
        return 2
    if any_no_kfx:
        return 1
    return 0


def _render_audit_json(results: list[BookAuditResult], exit_code: int) -> dict:
    """Build the SCRUM-286 structured-output payload for `audit --json`.

    Field naming follows the ticket AC: `sampled_expected` is the freshly
    computed select_sample_pages() result (the oracle), and `sampled_actual`
    is the page-number array stored in the baseline JSON.
    """
    summary = {
        "total": len(results),
        "parity": sum(1 for r in results if r.status == "parity"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
        "mismatch": sum(1 for r in results if r.status == "mismatch"),
    }
    return {
        "exit_code": exit_code,
        "summary": summary,
        "books": [
            {
                "book": r.stem,
                "status": r.status,
                "sampled_expected": r.expected_pages,
                "sampled_actual": r.baseline_pages,
                "skip_reason": r.skip_reason,
                "note": r.note,
            }
            for r in results
        ],
    }


def _print_audit_table(results: list[BookAuditResult]) -> None:
    print("\n# VQA baseline audit")
    print(f"| {'Book':<50} | {'Status':<9} | {'Skip reason':<16} | Baseline pages | Expected pages | Note |")
    print(f"| {'-'*50} | {'-'*9} | {'-'*16} | {'-'*14} | {'-'*14} | --- |")
    for r in results:
        base_str = str(r.baseline_pages) if r.baseline_pages else "—"
        exp_str = str(r.expected_pages) if r.expected_pages is not None else "—"
        reason_str = r.skip_reason or "—"
        print(f"| {_truncate(r.stem, 50):<50} | {r.status:<9} | {reason_str:<16} | "
              f"{_truncate(base_str, 14):<14} | {_truncate(exp_str, 14):<14} | {r.note} |")
    parity = sum(1 for r in results if r.status == "parity")
    mismatch = sum(1 for r in results if r.status == "mismatch")
    skipped = sum(1 for r in results if r.status == "skipped")
    by_reason: dict[str, int] = {}
    for r in results:
        if r.skip_reason:
            by_reason[r.skip_reason] = by_reason.get(r.skip_reason, 0) + 1
    reason_breakdown = ""
    if by_reason:
        parts = [f"{n} {reason}" for reason, n in sorted(by_reason.items())]
        reason_breakdown = "  (skip reasons: " + ", ".join(parts) + ")"
    print(f"\nSummary: {parity} parity / {mismatch} mismatch / {skipped} skipped{reason_breakdown}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    # Inject "compare" as default subcommand for backward compat:
    # `python compare_vqa_reports.py --candidate X --baseline Y` still works.
    # Top-level flags (--verbose/-v/--help/-h) must NOT trigger the compare injection.
    _known_subcmds = {"compare", "audit", "-h", "--help", "-v", "--verbose"}
    argv = sys.argv[1:]
    if argv and argv[0] not in _known_subcmds:
        argv = ["compare"] + argv

    parser = argparse.ArgumentParser(
        description="Compare VQA report directories (R2 gate) or audit baseline source parity."
    )
    # --verbose hoisted to top-level so it exists regardless of subcommand (or no subcommand).
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    subparsers = parser.add_subparsers(dest="command")

    # --- compare subcommand ---
    compare_p = subparsers.add_parser(
        "compare",
        help="Compare candidate VQA run against baseline (R2 gate). Default when no subcommand given.",
    )
    compare_p.add_argument("--candidate", required=True, type=Path,
                           help="Directory of candidate *_visual_qa_report.json files")
    compare_p.add_argument("--baseline", required=True, type=Path,
                           help="Directory of baseline (oracle) reports to compare against")
    compare_p.add_argument("--secondary", type=Path, default=None,
                           help="Optional second reference (e.g. prior local run)")
    compare_p.add_argument("--json-out", type=Path, default=None,
                           help="Optional path to write the gate result as JSON")

    # --- audit subcommand ---
    audit_p = subparsers.add_parser(
        "audit",
        help="Audit baseline source parity against fresh KFX-derived samples.",
    )
    _settings = load_settings_json()
    _default_calibre = _settings.get("paths", {}).get(
        "calibre", r"C:\Program Files\Calibre2\ebook-convert.exe"
    )
    audit_p.add_argument("--baseline-dir", type=Path,
                         default=Path("data/vqa_baseline_post_274/"),
                         help="Directory of baseline JSON files to audit "
                              "(default: data/vqa_baseline_post_274/)")
    audit_p.add_argument("--kfx-dir", type=Path,
                         default=Path("output/kindle/"),
                         help="Directory containing *.kfx files (default: output/kindle/)")
    audit_p.add_argument("--calibre", default=_default_calibre,
                         help="Path to Calibre ebook-convert.exe")
    audit_p.add_argument("--json", action="store_true",
                         help="Emit a single JSON object on stdout instead of "
                              "the markdown table (for agent / CI consumption). "
                              "Suppresses the markdown summary; logging stays on stderr.")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    if args.command is None:
        parser.print_help()
        return 0
    elif args.command == "compare":
        return _cmd_compare(args, parser)
    elif args.command == "audit":
        return _cmd_audit(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
