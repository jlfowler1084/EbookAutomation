#!/usr/bin/env python3
"""vqa_determinism_check.py — EB-361 VQA grader determinism self-check.

The local VQA grader is NOT bit-deterministic under concurrent node load. The
client already pins everything it can (``temperature=0``, ``seed=42``, guided
JSON), and the score arithmetic is deterministic (EB-150 fixed-deduction table).
The residual wobble comes from the *server*: the shared llama.cpp Vulkan node
decodes the grading request in a batch alongside other clients' requests, and
batched GPU matmuls reorder floating-point reductions — flipping a borderline
``argmax`` token under greedy decoding, which makes an issue appear/vanish and
swings a page score (e.g. p38 90→70). This is batch-invariance failure; no
client-side request change can fix it (the true cure is server ``--parallel 1``;
see docs/solutions/eb361-*).

This module is the *guard*, not the cure. It encodes the global calibration
rule — run the same input twice; if the two runs disagree per-page, the metric
is non-deterministic and its scores must not be trusted for fine-grained
comparison (converge gating, EB-348/EB-340 rendering-delta measurement).

Layers:
  * ``compare_reports`` — pure comparator over two VQA report dicts. Gate =
    per-page score delta within ``tolerance`` (default strict 0, EB-361) PLUS
    page-set parity. Issue-category drift is surfaced as a secondary diagnostic
    but does NOT fail the score gate.
  * ``run_determinism_check`` — runs an injected ``runner`` N times (strictly
    sequential) and compares run 0 against each later run.
  * ``build_vqa_runner`` / ``main`` — the live CLI path (deferred heavy imports).

Exit codes (CLI):
    0 — deterministic (per-page scores agree within tolerance, page sets match)
    1 — non-deterministic (scores UNRELIABLE — quiesce node and re-run)
    2 — could not assess (a run failed / produced no evaluated pages)

Usage:
    python tools/vqa_determinism_check.py --input "output/kindle/Book.kfx"
    python tools/vqa_determinism_check.py --input book.kfx --runs 3 --tolerance 0 --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("vqa_determinism_check")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class PageDelta:
    """One page that differs between two runs (by score, issues, or presence)."""

    page_number: int
    score_a: int | None
    score_b: int | None
    abs_delta: int | None           # None when a page is missing in one run
    issues_a: list[str]             # sorted issue-category multiset for run A
    issues_b: list[str]
    score_differs: bool             # |score_a - score_b| > tolerance
    issues_differ: bool             # issue-category multisets differ
    missing_in: str | None          # "a" | "b" when the page is absent in that run


@dataclass
class DeterminismVerdict:
    """Aggregate verdict for a determinism self-check.

    ``deterministic`` is the gate: True only when no per-page score delta exceeds
    ``tolerance`` AND no page is missing in either run. Issue-category drift is
    reported via ``n_issue_drift_pages`` but never flips ``deterministic`` on its
    own (EB-361 gates on per-page score, per the approved decision).
    """

    deterministic: bool
    tolerance: int
    pages_compared: int
    n_score_diffs: int
    max_abs_delta: int | None
    overall_score_a: int | None
    overall_score_b: int | None
    overall_abs_delta: int | None
    n_issue_drift_pages: int
    missing_pages: list[int]
    page_deltas: list[PageDelta] = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# Pure comparator
# ---------------------------------------------------------------------------

def _index_pages(report: dict) -> dict[int, dict]:
    """Return {page_number: page_dict}; first occurrence wins on duplicates.

    Mirrors compare_vqa_reports._index_pages so the two tools agree on what a
    "page" is.
    """
    out: dict[int, dict] = {}
    for page in report.get("pages", []):
        pn = page.get("page_number")
        if isinstance(pn, int) and pn not in out:
            out[pn] = page
    return out


def _issue_categories(page: dict) -> list[str]:
    """Sorted multiset of issue categories on a page (counts preserved)."""
    cats = [
        str(issue.get("category", "unknown"))
        for issue in (page.get("issues") or [])
        if isinstance(issue, dict)
    ]
    return sorted(cats)


def _require_evaluable(report: dict, label: str) -> None:
    status = report.get("evaluation_status", "evaluated")
    pages = report.get("pages") or []
    if status != "evaluated" or not pages:
        raise ValueError(
            f"Cannot assess determinism: report {label!r} is not a successful "
            f"evaluation (evaluation_status={status!r}, pages={len(pages)}). "
            f"Re-run until both runs produce evaluated reports with pages."
        )


def compare_reports(
    report_a: dict,
    report_b: dict,
    *,
    tolerance: int = 0,
) -> DeterminismVerdict:
    """Compare two VQA report dicts for grader determinism.

    Args:
        report_a, report_b: VQA report dicts (as written by run_visual_qa).
        tolerance: maximum allowed per-page absolute score delta. Default 0
            (strict bit-determinism, EB-361). A page fails when its delta
            exceeds this.

    Returns:
        DeterminismVerdict.

    Raises:
        ValueError: if either report has no evaluated pages (a failed run can't
            be assessed for determinism).
    """
    _require_evaluable(report_a, "a")
    _require_evaluable(report_b, "b")

    pa = _index_pages(report_a)
    pb = _index_pages(report_b)
    all_pns = sorted(set(pa) | set(pb))

    page_deltas: list[PageDelta] = []
    missing_pages: list[int] = []
    abs_deltas: list[int] = []
    n_score_diffs = 0
    n_issue_drift = 0

    for pn in all_pns:
        in_a, in_b = pn in pa, pn in pb

        if in_a and in_b:
            sa = pa[pn].get("score")
            sb = pb[pn].get("score")
            ca = _issue_categories(pa[pn])
            cb = _issue_categories(pb[pn])
            abs_delta = abs(sa - sb) if isinstance(sa, int) and isinstance(sb, int) else None
            score_differs = abs_delta is not None and abs_delta > tolerance
            issues_differ = ca != cb

            if abs_delta is not None:
                abs_deltas.append(abs_delta)
            if score_differs:
                n_score_diffs += 1
            if issues_differ:
                n_issue_drift += 1
            if score_differs or issues_differ:
                page_deltas.append(PageDelta(
                    page_number=pn, score_a=sa, score_b=sb, abs_delta=abs_delta,
                    issues_a=ca, issues_b=cb,
                    score_differs=score_differs, issues_differ=issues_differ,
                    missing_in=None,
                ))
        else:
            missing_pages.append(pn)
            present = pa[pn] if in_a else pb[pn]
            cats = _issue_categories(present)
            page_deltas.append(PageDelta(
                page_number=pn,
                score_a=present.get("score") if in_a else None,
                score_b=present.get("score") if in_b else None,
                abs_delta=None,
                issues_a=cats if in_a else [],
                issues_b=cats if in_b else [],
                score_differs=False, issues_differ=False,
                missing_in="b" if in_a else "a",
            ))

    max_abs_delta = max(abs_deltas) if abs_deltas else None
    oa = report_a.get("overall_score")
    ob = report_b.get("overall_score")
    overall_abs = abs(oa - ob) if isinstance(oa, int) and isinstance(ob, int) else None
    deterministic = (n_score_diffs == 0) and not missing_pages

    if not deterministic:
        bits = []
        if n_score_diffs:
            bits.append(f"{n_score_diffs} page(s) with score delta > tolerance {tolerance}")
        if missing_pages:
            bits.append(f"{len(missing_pages)} page(s) present in only one run: {missing_pages}")
        note = "; ".join(bits)
    elif n_issue_drift:
        note = (f"score-deterministic, but {n_issue_drift} page(s) show issue-category "
                f"drift (benign for score gating, watch if it grows)")
    else:
        note = "bit-deterministic across the compared runs"

    return DeterminismVerdict(
        deterministic=deterministic,
        tolerance=tolerance,
        pages_compared=len(all_pns),
        n_score_diffs=n_score_diffs,
        max_abs_delta=max_abs_delta,
        overall_score_a=oa,
        overall_score_b=ob,
        overall_abs_delta=overall_abs,
        n_issue_drift_pages=n_issue_drift,
        missing_pages=missing_pages,
        page_deltas=page_deltas,
        note=note,
    )


def _delta_rank(d: PageDelta) -> tuple[int, int]:
    """Severity rank used to keep the worst representative of a page across runs."""
    if d.missing_in is not None:
        return (3, 0)
    if d.score_differs:
        return (2, d.abs_delta or 0)
    if d.issues_differ:
        return (1, 0)
    return (0, 0)


def _merge_verdicts(verdicts: list[DeterminismVerdict], *, tolerance: int) -> DeterminismVerdict:
    """Merge run-0-vs-run-i verdicts (runs > 2) into one aggregate verdict."""
    by_pn: dict[int, PageDelta] = {}
    for v in verdicts:
        for d in v.page_deltas:
            cur = by_pn.get(d.page_number)
            if cur is None or _delta_rank(d) > _delta_rank(cur):
                by_pn[d.page_number] = d
    merged = [by_pn[pn] for pn in sorted(by_pn)]

    deterministic = all(v.deterministic for v in verdicts)
    abs_vals = [v.max_abs_delta for v in verdicts if v.max_abs_delta is not None]
    overall_vals = [v.overall_abs_delta for v in verdicts if v.overall_abs_delta is not None]
    missing = sorted({pn for v in verdicts for pn in v.missing_pages})
    base = verdicts[0]
    note = "" if deterministic else f"non-deterministic across {len(verdicts) + 1} runs"

    return DeterminismVerdict(
        deterministic=deterministic,
        tolerance=tolerance,
        pages_compared=max(v.pages_compared for v in verdicts),
        n_score_diffs=sum(1 for d in merged if d.score_differs),
        max_abs_delta=max(abs_vals) if abs_vals else None,
        overall_score_a=base.overall_score_a,
        overall_score_b=base.overall_score_b,
        overall_abs_delta=max(overall_vals) if overall_vals else None,
        n_issue_drift_pages=sum(1 for d in merged if d.issues_differ),
        missing_pages=missing,
        page_deltas=merged,
        note=note,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_determinism_check(
    runner: Callable[[int], dict],
    *,
    runs: int = 2,
    tolerance: int = 0,
) -> DeterminismVerdict:
    """Run ``runner`` ``runs`` times and compare run 0 against each later run.

    ``runner(i)`` must return the i-th run's VQA report dict. The runs are
    executed strictly sequentially (run i fully completes before run i+1) so the
    two measurement passes never interleave on the node with each other; whether
    *other* clients interleave is what the check is designed to detect.

    Args:
        runner: callable returning a report dict for run index i.
        runs: number of runs (>= 2).
        tolerance: per-page score-delta tolerance passed to compare_reports.

    Raises:
        ValueError: if runs < 2, or if any run produced no evaluated pages.
    """
    if runs < 2:
        raise ValueError(f"runs must be >= 2 to assess determinism (got {runs})")

    reports = [runner(i) for i in range(runs)]
    verdicts = [
        compare_reports(reports[0], reports[i], tolerance=tolerance)
        for i in range(1, runs)
    ]
    return verdicts[0] if len(verdicts) == 1 else _merge_verdicts(verdicts, tolerance=tolerance)


def verdict_to_exit_code(verdict: DeterminismVerdict) -> int:
    """0 when deterministic, 1 otherwise (infra errors map to 2 in main)."""
    return 0 if verdict.deterministic else 1


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_json(verdict: DeterminismVerdict) -> dict:
    """Structured payload for agent / CI consumption (mirrors compare_vqa_reports)."""
    payload = asdict(verdict)
    payload["exit_code"] = verdict_to_exit_code(verdict)
    return payload


def render_markdown(verdict: DeterminismVerdict) -> str:
    lines = ["# VQA grader determinism self-check (EB-361)", ""]
    status = "DETERMINISTIC ✓" if verdict.deterministic else "NON-DETERMINISTIC ✗"
    lines.append(f"- Verdict: **{status}**")
    lines.append(f"- Tolerance (per-page |Δ|): {verdict.tolerance}")
    lines.append(f"- Pages compared: {verdict.pages_compared}")
    lines.append(f"- Pages with score delta > tolerance: {verdict.n_score_diffs}")
    lines.append(f"- Max per-page |Δ|: {verdict.max_abs_delta}")
    lines.append(f"- Overall score: {verdict.overall_score_a} vs {verdict.overall_score_b} "
                 f"(|Δ| {verdict.overall_abs_delta})")
    lines.append(f"- Pages with issue-category drift: {verdict.n_issue_drift_pages}")
    if verdict.missing_pages:
        lines.append(f"- Pages present in only one run: {verdict.missing_pages}")
    if verdict.note:
        lines.append(f"- Note: {verdict.note}")

    if verdict.page_deltas:
        lines += ["", "## Differing pages", "",
                  "| Page | score A | score B | |Δ| | score? | issues? | missing |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for d in verdict.page_deltas:
            lines.append(
                f"| {d.page_number} | {d.score_a} | {d.score_b} | "
                f"{d.abs_delta if d.abs_delta is not None else '—'} | "
                f"{'yes' if d.score_differs else '—'} | "
                f"{'yes' if d.issues_differ else '—'} | "
                f"{d.missing_in or '—'} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Live runner (deferred heavy imports)
# ---------------------------------------------------------------------------

def build_vqa_runner(
    input_path: str,
    *,
    provider_name: str = "local",
    model: str | None = None,
    dpi: int = 150,
    max_pages: int = 50,
    batch_size: int = 8,
    calibre_path: str | None = None,
    poppler_path: str | None = None,
    rubric_path: str | None = None,
    out_dir: str | None = None,
) -> Callable[[int], dict]:
    """Build a ``runner(i) -> report dict`` that runs one full VQA pass.

    Heavy imports (visual_qa, providers, openai) are deferred to here so the pure
    comparator can be imported and unit-tested without them.

    Fallback routing is forced OFF: EB-361 measures the LOCAL grader's
    determinism, and the Claude fallback would inject a second, different
    provider (matches the EB-340 sweep's ``--fallback-enabled false``).
    ``user_supplied_dpi/max_pages`` are True so the large-file auto-reduction
    never silently changes coverage during a measurement run.
    """
    import os
    import shutil

    import visual_qa as vqa
    from llm_providers import ClaudeVisionProvider, CloudVLProvider, LocalVisionProvider

    settings = vqa.load_settings_json()
    vqa_settings = settings.get("visual_qa", {})
    paths = settings.get("paths", {})

    resolved_calibre = calibre_path or paths.get(
        "calibre",
        shutil.which("ebook-convert") or r"C:\Program Files\Calibre2\ebook-convert.exe",
    )
    resolved_poppler = poppler_path or (paths.get("poppler") or None)
    resolved_rubric = rubric_path or str(
        Path(__file__).resolve().parent / "visual_qa_rubric.md"
    )

    # Provider factory (mirrors visual_qa.main).
    if provider_name == "local":
        base_url = (
            os.environ.get("LOCAL_LLM_BASE_URL")
            or vqa_settings.get("local_base_url", "http://localhost:8000/v1")
        )
        provider = LocalVisionProvider(base_url=base_url)
        resolved_model = model or (
            os.environ.get("LOCAL_LLM_VISION_MODEL")
            or vqa_settings.get("local_model", "qwen3.5-35b-a3b-fp8")
        )
    elif provider_name == "cloud":
        host = vqa_settings.get("cloud_host", "openrouter")
        api_key = os.environ.get(f"{host.upper()}_API_KEY")
        if not api_key:
            raise RuntimeError(f"No API key for cloud host '{host}' ({host.upper()}_API_KEY).")
        provider = CloudVLProvider(host=host, api_key=api_key)
        resolved_model = model or (
            os.environ.get("CLOUD_VL_MODEL")
            or vqa_settings.get("cloud_model", "qwen/qwen3-vl-30b-a3b-instruct")
        )
    elif provider_name == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("No ANTHROPIC_API_KEY set for --provider claude.")
        provider = ClaudeVisionProvider(api_key=api_key)
        resolved_model = model or settings.get("api_models", {}).get(
            "sonnet_latest", "claude-sonnet-4-6"
        )
    else:
        raise ValueError(f"Unknown provider: {provider_name!r}")

    def runner(run_index: int) -> dict:
        run_out = str(Path(out_dir) / f"run{run_index + 1}") if out_dir else None
        logger.info("Determinism run %d/%s via %s provider (model=%s)...",
                    run_index + 1, "N", provider_name, resolved_model)
        return vqa.run_visual_qa(
            input_path=input_path,
            provider=provider,
            calibre_path=resolved_calibre,
            poppler_path=resolved_poppler,
            output_dir=run_out,
            dpi=dpi,
            max_pages=max_pages,
            model=resolved_model,
            rubric_path=resolved_rubric,
            batch_size=batch_size,
            user_supplied_dpi=True,
            user_supplied_max_pages=True,
            fallback_enabled=False,
        )

    return runner


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EB-361 VQA grader determinism self-check: run the same input "
                    "twice and refuse to trust the scores unless the runs agree.",
    )
    parser.add_argument("--input", required=True,
                        help="Path to KFX/AZW3/EPUB/PDF to grade twice")
    parser.add_argument("--provider", default="local", choices=["local", "cloud", "claude"],
                        help="Vision provider (default: local — the EB-361 subject)")
    parser.add_argument("--model", default=None,
                        help="Model id (default: resolved from env/settings per provider)")
    parser.add_argument("--dpi", type=int, default=150,
                        help="Render DPI (default: 150 — EB-361 canary)")
    parser.add_argument("--max-pages", type=int, default=50,
                        help="Pages to sample (default: 50 — EB-361 canary)")
    parser.add_argument("--batch-size", type=int, default=8,
                        help="Pages per provider batch (default: 8)")
    parser.add_argument("--runs", type=int, default=2,
                        help="Number of identical runs to compare (default: 2)")
    parser.add_argument("--tolerance", type=int, default=0,
                        help="Max allowed per-page score |Δ| (default: 0 = strict)")
    parser.add_argument("--out-dir", default=None,
                        help="If set, write each run's report under <out-dir>/run{N}/")
    parser.add_argument("--calibre", default=None, help="Path to ebook-convert.exe")
    parser.add_argument("--poppler", default=None, help="Path to poppler bin directory")
    parser.add_argument("--json", action="store_true",
                        help="Emit the verdict as JSON instead of markdown")
    parser.add_argument("--verbose", action="store_true", help="Debug logging to stderr")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    for noisy in ("PIL", "PIL.PngImagePlugin", "urllib3", "urllib3.connectionpool"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        runner = build_vqa_runner(
            args.input,
            provider_name=args.provider,
            model=args.model,
            dpi=args.dpi,
            max_pages=args.max_pages,
            batch_size=args.batch_size,
            calibre_path=args.calibre,
            poppler_path=args.poppler,
            out_dir=args.out_dir,
        )
        verdict = run_determinism_check(runner, runs=args.runs, tolerance=args.tolerance)
    except ValueError as exc:
        logger.error("Determinism check could not run: %s", exc)
        return 2
    except Exception as exc:  # live-run failures (node down, conversion error, etc.)
        logger.error("VQA run failed during determinism check: %s", exc)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 2

    if args.json:
        print(json.dumps(render_json(verdict), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(verdict))

    code = verdict_to_exit_code(verdict)
    if code != 0:
        logger.warning(
            "VQA grader is NON-DETERMINISTIC for this input — scores are UNRELIABLE "
            "for fine-grained comparison (converge gating, EB-348/EB-340 deltas). "
            "Quiesce the node (serve with --parallel 1 / single slot) and re-run "
            "before trusting any score deltas. See docs/solutions/eb361-*."
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
