#!/usr/bin/env python3
"""EB-377: build the per-book artifact provenance index and run the
provenance-SCOPED header-bleed scan (only the manifest's basenames — never a
bare *_kindle.html glob, which would pull stale intermediates into EB-377)."""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_header_bleed as chb  # detect(html, params) -> BookResult

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("build_batch_provenance")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _book_record(source: str, staged_dir: Path, kfx_dir: Path,
                 header_out: Path, diag: dict | None = None) -> dict:
    src = Path(source)
    staged = staged_dir / src.name

    # Convert-ToKindle names output from parsed Title/Author metadata, NOT the
    # source stem (EbookAutomation.psm1). So prefer the real KFX path that
    # batch_qa recorded; fall back to source-stem only when no batch report is
    # available (synthetic tests).
    out_path = diag.get("kindle_conversion", {}).get("output_path") if diag else None
    kfx = Path(out_path) if out_path else kfx_dir / f"{src.stem}.kfx"
    inter = kfx.parent / ".intermediates" / f"{kfx.stem}_kindle.html"
    vqa = kfx.with_name(f"{kfx.stem}_visual_qa_report.json")
    header_report = header_out / f"{kfx.stem}.json"

    coverage = {
        "staged": staged.exists(),
        "kfx": kfx.exists() and kfx.stat().st_size > 0,
        "intermediate_html": inter.exists(),
        "vqa_report": vqa.exists(),
    }

    weld_total = None
    if coverage["intermediate_html"]:
        result = chb.detect(inter.read_text(encoding="utf-8", errors="replace"))
        weld_total = result.weld_total
        header_out.mkdir(parents=True, exist_ok=True)
        header_report.write_text(
            json.dumps({"stem": kfx.stem, "weld_total": weld_total,
                        "findings": [f.__dict__ for f in result.findings]},
                       indent=2, default=str),
            encoding="utf-8",
        )

    if not coverage["kfx"]:
        status = "kfx_failed"
    elif not coverage["intermediate_html"]:
        status = "coverage_gap"
    else:
        status = "complete"

    return {
        "source": str(src), "sha256": _sha256(src) if src.exists() else None,
        "staged": str(staged), "kfx": str(kfx), "intermediate_html": str(inter),
        "vqa_report": str(vqa), "header_report": str(header_report),
        "weld_total": weld_total, "coverage": coverage, "status": status,
    }


def build_provenance(manifest: dict, kfx_dir: str, header_out_dir: str,
                     batch_report: dict | None = None) -> dict:
    staged_dir = Path(manifest.get("_staged_dir", "."))
    kfx_dir = Path(kfx_dir)
    header_out = Path(header_out_dir)
    # Index batch_qa diagnostics by source filename for the real-KFX-path join.
    diags = {d.get("filename"): d
             for d in (batch_report or {}).get("books", [])}
    sources = list(manifest.get("anchors", [])) + \
        [f["path"] for f in manifest.get("fresh", [])]

    books = [_book_record(s, staged_dir, kfx_dir, header_out,
                          diags.get(Path(s).name)) for s in sources]
    flagged = [b for b in books if b["weld_total"]]
    summary = {
        "total": len(books),
        "complete": sum(b["status"] == "complete" for b in books),
        "coverage_gap": sum(b["status"] == "coverage_gap" for b in books),
        "kfx_failed": sum(b["status"] == "kfx_failed" for b in books),
        "weld_books": len(flagged),
        "weld_total_sum": sum(b["weld_total"] or 0 for b in books),
    }
    return {"ticket": "EB-377", "books": books, "summary": summary}


def main(argv=None):
    ap = argparse.ArgumentParser(description="EB-377 provenance + header-bleed")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--staged-dir", required=True)
    ap.add_argument("--batch-qa", default=None,
                    help="batch_qa run JSON; join by filename for the real "
                         "metadata-derived KFX paths (production).")
    ap.add_argument("--kfx-dir", default=r"output\kindle")
    ap.add_argument("--header-out", default=r"data\batch_reports\header_bleed")
    ap.add_argument("--out", default=r"data\batch_reports\EB-377-provenance.json")
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    manifest["_staged_dir"] = args.staged_dir
    batch_report = None
    if args.batch_qa:
        batch_report = json.loads(Path(args.batch_qa).read_text(encoding="utf-8"))
    index = build_provenance(manifest, args.kfx_dir, args.header_out, batch_report)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(index, indent=2), encoding="utf-8")
    log.info("Provenance: %s", json.dumps(index["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
