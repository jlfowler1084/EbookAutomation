#!/usr/bin/env python3
"""EB-377: build the reviewable 11/39 corpus manifest and stage the 50 PDFs.

Anchors come from archive/ (regression confirmation); fresh picks come from a
large pool (default F:\\books), junk/dupe filtered, stratified by size bucket x
subject folder, seeded for reproducibility, with a soft bias toward header-prone
genres. Writes a manifest JSON; optionally copies the 50 PDFs into a staging dir.
"""
from __future__ import annotations
import argparse
import json
import logging
import random
import re
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("select_batch_corpus")

# 11 anchors — each pattern MUST resolve to exactly one file in archive/.
ANCHOR_PATTERNS = [
    "*First Principles*.pdf",
    "*Pilgrim*People*.pdf",
    "*Oil*Kings*.pdf",
    "*Mexico*Illicit*.pdf",
    "*Return*Gods*.pdf",
    "*Python*easy*steps*.pdf",
    "*Atomic*Habits*.pdf",
    "*Decline*West*.pdf",
    "*Dionysius*.pdf",
    "*Genesis*Darwin*.pdf",
    "*Fate*Empires*.pdf",
]

JUNK_RE = re.compile(
    r"(tax[_ ]?return|resume|cv|boarding[_ ]?pass|pasabordo|pasaporte|"
    r"insurance|w-?2|1099|invoice|receipt|statement|itinerary|"
    r"amazon[._ -]*(?:com|order)|\d{3}-\d{7}-\d{7})", re.IGNORECASE,
)
DUPE_RE = re.compile(r"\(\d+\)\.pdf$", re.IGNORECASE)
# EB-377 review: exclude whole non-book / trash FOLDERS by path component —
# filename-only JUNK_RE missed real-pool dirs like _Trash_Pending/ and Non_Books/.
EXCLUDE_DIR_RE = re.compile(
    r"^(?:_?trash(?:[_ ]?pending)?|non[_ ]?books?|_?junk|"
    r"_?recycle(?:[_ ]?bin)?|_?archive[_ ]?junk|pending[_ ]?delete)$",
    re.IGNORECASE,
)
HEADER_PRONE_RE = re.compile(
    r"(history|philosoph|theolog|classic|academ|ancient|empire|"
    r"princip|gods|religion|patristic)", re.IGNORECASE,
)

_SIZE_BUCKETS = [(0, 5), (5, 15), (15, 40), (40, 10_000)]  # MB


def _size_bucket(mb: float) -> str:
    for lo, hi in _SIZE_BUCKETS:
        if lo <= mb < hi:
            return f"{lo}-{hi}MB"
    return "huge"


def _resolve_anchors(archive_dir: Path) -> list[str]:
    anchors = []
    for pat in ANCHOR_PATTERNS:
        matches = sorted(archive_dir.glob(pat))
        if len(matches) != 1:
            raise SystemExit(
                f"Anchor pattern {pat!r} resolved to {len(matches)} files: "
                f"{[m.name for m in matches]} — fix the pattern or archive/."
            )
        anchors.append(str(matches[0]))
    return anchors


def select_corpus(archive_dir: str, fresh_dir: str, n_fresh: int = 39,
                  seed: int = 377, max_per_folder: int = 6) -> dict:
    archive_dir = Path(archive_dir)
    fresh_dir = Path(fresh_dir)
    anchors = _resolve_anchors(archive_dir)
    anchor_stems = {Path(a).stem.lower() for a in anchors}

    candidates = []
    for p in fresh_dir.rglob("*.pdf"):
        name = p.name
        if JUNK_RE.search(name) or DUPE_RE.search(name):
            continue
        # EB-377 review: drop files living under trash / non-book folders.
        rel_dirs = p.relative_to(fresh_dir).parts[:-1]
        if any(EXCLUDE_DIR_RE.match(part) for part in rel_dirs):
            continue
        if p.stem.lower() in anchor_stems:
            continue
        mb = p.stat().st_size / (1024 * 1024)
        subject = p.parent.name if p.parent != fresh_dir else "_root"
        stratum = f"{subject}|{_size_bucket(mb)}"
        weight = 2.0 if HEADER_PRONE_RE.search(str(p)) else 1.0
        candidates.append(
            {"path": str(p), "size_mb": round(mb, 2), "stratum": stratum,
             "subject": subject, "_weight": weight}
        )

    rng = random.Random(seed)
    candidates.sort(key=lambda c: c["path"])  # stable base order before keying
    # EB-377 review: dedupe by basename BEFORE sampling. Task 3 joins artifacts
    # by basename and stage() copies by basename, so two same-named PDFs would
    # collide/overwrite. Keep the first in path-sorted (deterministic) order.
    _seen_names: set[str] = set()
    _deduped = []
    for c in candidates:
        nm = Path(c["path"]).name.lower()
        if nm in _seen_names:
            continue
        _seen_names.add(nm)
        _deduped.append(c)
    candidates = _deduped
    for c in candidates:
        u = rng.random()
        c["_key"] = u ** (1.0 / c["_weight"])
    candidates.sort(key=lambda c: c["_key"], reverse=True)

    # EB-377 review: cap per subject folder so no single folder dominates the
    # fresh set (the weighted sample is global by count, which let _Needs_Review
    # take ~70%). Greedy over the key-sorted list preserves weighted preference.
    fresh = []
    per_folder: dict[str, int] = {}
    for c in candidates:
        if per_folder.get(c["subject"], 0) >= max_per_folder:
            continue
        fresh.append(c)
        per_folder[c["subject"]] = per_folder.get(c["subject"], 0) + 1
        if len(fresh) >= n_fresh:
            break
    # If the cap left us short, top up from the remaining key-ordered candidates,
    # accepting cap overflow rather than an undersized batch.
    if len(fresh) < n_fresh:
        chosen = {c["path"] for c in fresh}
        for c in candidates:
            if c["path"] in chosen:
                continue
            fresh.append(c)
            if len(fresh) >= n_fresh:
                break
        log.warning("per-folder cap %d under-filled; topped up to %d (cap "
                    "overflow) — pool may lack folder diversity",
                    max_per_folder, len(fresh))

    strata_counts: dict[str, int] = {}
    for c in fresh:
        strata_counts[c["stratum"]] = strata_counts.get(c["stratum"], 0) + 1
        del c["_weight"], c["_key"], c["subject"]

    if len(fresh) < n_fresh:
        log.warning("Only %d fresh candidates after filtering (< %d requested)",
                    len(fresh), n_fresh)

    return {"seed": seed, "ticket": "EB-377",
            "anchors": anchors, "fresh": fresh, "strata_counts": strata_counts}


def stage(manifest: dict, staging_dir: str) -> None:
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=True)
    paths = list(manifest["anchors"]) + [f["path"] for f in manifest["fresh"]]
    for src in paths:
        src_p = Path(src)
        dest = staging / src_p.name
        if dest.exists() and dest.stat().st_size == src_p.stat().st_size:
            continue
        shutil.copy2(src_p, dest)
        log.info("staged %s", src_p.name)
    log.info("Staged %d PDFs into %s", len(paths), staging)


def main(argv=None):
    ap = argparse.ArgumentParser(description="EB-377 corpus selection + staging")
    ap.add_argument("--archive", default="archive")
    ap.add_argument("--fresh", default=r"F:\books")
    ap.add_argument("--n-fresh", type=int, default=39)
    ap.add_argument("--seed", type=int, default=377)
    ap.add_argument("--max-per-folder", type=int, default=6,
                    help="Cap fresh picks per subject folder (variety guard).")
    ap.add_argument("--out", default="logs/batch-selection-2026-06-07.json")
    ap.add_argument("--stage", default=None,
                    help="If set, copy the 50 PDFs into this directory.")
    args = ap.parse_args(argv)

    manifest = select_corpus(args.archive, args.fresh, args.n_fresh, args.seed,
                             args.max_per_folder)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Wrote manifest: %s (%d anchors + %d fresh)", out,
             len(manifest["anchors"]), len(manifest["fresh"]))
    log.info("Strata: %s", json.dumps(manifest["strata_counts"]))

    if args.stage:
        stage(manifest, args.stage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
