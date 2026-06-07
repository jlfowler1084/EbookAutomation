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
                 header_out: Path) -> dict:
    src = Path(source)
    stem = src.stem
    staged = staged_dir / src.name
    kfx = kfx_dir / f"{stem}.kfx"
    inter = kfx_dir / ".intermediates" / f"{stem}_kindle.html"
    vqa = kfx_dir / f"{stem}_visual_qa_report.json"
    header_report = header_out / f"{stem}.json"

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
            json.dumps({"stem": stem, "weld_total": weld_total,
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


def build_provenance(manifest: dict, kfx_dir: str, header_out_dir: str) -> dict:
    staged_dir = Path(manifest.get("_staged_dir", "."))
    kfx_dir = Path(kfx_dir)
    header_out = Path(header_out_dir)
    sources = list(manifest.get("anchors", [])) + \
        [f["path"] for f in manifest.get("fresh", [])]

    books = [_book_record(s, staged_dir, kfx_dir, header_out) for s in sources]
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
    ap.add_argument("--kfx-dir", default=r"output\kindle")
    ap.add_argument("--header-out", default=r"data\batch_reports\header_bleed")
    ap.add_argument("--out", default=r"data\batch_reports\EB-377-provenance.json")
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    manifest["_staged_dir"] = args.staged_dir
    index = build_provenance(manifest, args.kfx_dir, args.header_out)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(index, indent=2), encoding="utf-8")
    log.info("Provenance: %s", json.dumps(index["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
