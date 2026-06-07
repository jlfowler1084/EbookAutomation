#!/usr/bin/env python3
"""EB-377: merge provenance + batch_qa clusters/observations + determinism into
a findings document. Measurement artifacts are reported SEPARATELY from real
findings (Calibration-Sessions discipline)."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# batch_qa severities: critical > high > medium > low (analyze_patterns).
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _cluster_count(c: dict):
    # batch_qa emits 'book_count'; tolerate 'count' only for forward-compat.
    return c.get("book_count", c.get("count", "?"))


def synthesize(provenance: dict, batch_qa_report: dict, determinism: dict) -> str:
    s = provenance["summary"]
    clusters = sorted(
        batch_qa_report.get("failure_clusters", []),
        key=lambda c: (_SEV_RANK.get(c.get("severity", "low"), 0),
                       c.get("book_count", c.get("count", 0)) or 0),
        reverse=True,
    )
    lines = ["# EB-377 Phase-3 Sweep — Findings", ""]

    lines += ["## Header-bleed verdict", ""]
    if s["weld_total_sum"] == 0:
        lines.append("All scanned books show **0 welds**. The header-bleed "
                     "fixes (EB-367/370/372/374) hold corpus-wide.")
    else:
        lines.append(f"**{s['weld_total_sum']} welds across {s['weld_books']} "
                     f"books.** Spot-check required before escalation.")
    lines.append("")

    lines += ["## New patterns (ranked: severity x book_count)", ""]
    if clusters:
        lines.append("| Pattern | Severity | Count |")
        lines.append("|---|---|---|")
        for c in clusters:
            lines.append(f"| {c['pattern_id']} | {c.get('severity','?')} | "
                         f"{_cluster_count(c)} |")
    else:
        lines.append("No failure clusters detected.")
    lines.append("")
    for obs in batch_qa_report.get("observations", []):
        lines.append(f"- _Observation:_ {obs}")
    lines.append("")

    lines += ["## Prioritized fix list", ""]
    for i, c in enumerate(clusters, 1):
        lines.append(f"{i}. **{c['pattern_id']}** ({c.get('severity','?')}, "
                     f"n={_cluster_count(c)}) → child ticket under EB-377")
    lines.append("")

    lines += ["## Measurement artifacts (NOT findings)", ""]
    lines.append(f"- Coverage: {s['complete']}/{s['total']} complete, "
                 f"{s['coverage_gap']} coverage_gap, {s['kfx_failed']} kfx_failed.")
    if not determinism.get("reproducible", True):
        lines.append(f"- **VQA scores are non-deterministic** "
                     f"(max delta {determinism.get('max_delta','?')}). Treat "
                     f"VQA-derived clusters as provisional until the grader is "
                     f"stabilized (cf. EB-361).")
    else:
        lines.append("- VQA determinism check passed (bit-exact).")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="EB-377 findings synthesis")
    ap.add_argument("--provenance", required=True)
    ap.add_argument("--batch-qa", required=True)
    ap.add_argument("--determinism", required=True)
    ap.add_argument("--out", default=r"data\batch_reports\EB-377-findings-2026-06-07.md")
    args = ap.parse_args(argv)
    md = synthesize(
        json.loads(Path(args.provenance).read_text(encoding="utf-8")),
        json.loads(Path(args.batch_qa).read_text(encoding="utf-8")),
        json.loads(Path(args.determinism).read_text(encoding="utf-8")),
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
