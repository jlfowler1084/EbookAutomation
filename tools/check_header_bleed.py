#!/usr/bin/env python3
"""EB-370: Running-header weld detector for _kindle.html intermediate artifacts.

Scans post-rejoin _kindle.html files for welded ALL-CAPS running headers.
A "weld" is a short (6-40 char normalized) 2+-word ALL-CAPS phrase that
appears fused into body <p> paragraphs on >=5 distinct pages at >=10% density.

Mirrors the exit-code/JSON/logging conventions of compare_vqa_reports.py:
  - logging  -> stderr
  - JSON report + human summary -> stdout via print()
  - exit codes: 0 clean | 1 nothing scannable | 2 flagged | 3 infra/usage error

Usage:
    python tools/check_header_bleed.py --input output/kindle/.intermediates/
    python tools/check_header_bleed.py --input Book_kindle.html --out report.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

# ── Schema ─────────────────────────────────────────────────────────────────
SCHEMA = "header_bleed_report/v1"

# ── Detection defaults ──────────────────────────────────────────────────────
DEFAULT_MIN_DISTINCT_PAGES = 5
DEFAULT_MIN_DENSITY = 0.10
DEFAULT_LEN_MIN = 6
DEFAULT_LEN_MAX = 40
DEFAULT_GLOB = "*_kindle.html"

# ── Candidate pattern ───────────────────────────────────────────────────────
# ALL-CAPS token: uppercase letters + straight/curly apostrophes + hyphen.
# chr() for all three so the literal can't silently drift (EB-372: the ASCII
# straight apostrophe was previously omitted — "’" is U+2019, not U+0027).
_APOSTROPHES = chr(0x27) + chr(0x2018) + chr(0x2019)   # U+0027 straight, U+2018/U+2019 curly
_CAPS_TOKEN = f"[A-Z][A-Z{_APOSTROPHES}-]*"
# A run of 2+ ALL-CAPS tokens, optionally followed by 1-4 digit page number.
_CANDIDATE_PAT = rf"({_CAPS_TOKEN}(?: {_CAPS_TOKEN})+)(?: (\d{{1,4}}))?"
CANDIDATE_RE = re.compile(_CANDIDATE_PAT)

# Page anchors: only ids matching ^page_N$ count toward total_pages.
_PAGE_ANCHOR_RE = re.compile(r"^page_(\d+)$")

# EB-374: a page-number token (arabic or roman) at a paragraph edge is NOT body
# text. A candidate flanked only by such tokens is a standalone running-header
# repeat, not a body weld. Roman uses a strict grammar, case-insensitive.
_ROMAN_TOKEN = (r"(?i:(?=[mdclxvi])m{0,4}(?:cm|cd|d?c{0,3})"
                r"(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))")
_EDGE_LEAD = re.compile(r"^(?:\d{1,4}|" + _ROMAN_TOKEN + r")\s+")
_EDGE_TRAIL = re.compile(r"\s+(?:\d{1,4}|" + _ROMAN_TOKEN + r")$")


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class Finding:
    normalized: str
    occurrences: int
    distinct_pages: int
    density: float
    glue_positions: list[str]   # per-occurrence: standalone|glued-start|glued-end|mid-paragraph
    samples: list[dict]         # up to 5 windowed context snippets


@dataclass
class BookResult:
    html_path: str
    status: str                          # clean | flagged | error
    weld_total: int                      # count of non-standalone occurrences in findings
    total_pages: int
    findings: list[Finding]              # density-gated candidates with >=1 non-standalone
    standalone_repeats: list[Finding]    # density-gated, all occurrences standalone
    heading_repeats: list[Finding]       # heading-only density-gated candidates
    error: Optional[str] = None


@dataclass
class DetectorParams:
    min_distinct_pages: int = DEFAULT_MIN_DISTINCT_PAGES
    min_density: float = DEFAULT_MIN_DENSITY
    len_min: int = DEFAULT_LEN_MIN
    len_max: int = DEFAULT_LEN_MAX


# ── HTML parser ─────────────────────────────────────────────────────────────

class _BleedParser(HTMLParser):
    """Collect (tag, page, text) triples from a _kindle.html document.

    Tracks the current page number from <a id="page_N"> anchors.
    Only <p> and heading elements are recorded; inline elements (em, sup, a)
    are transparent — their text accumulates into the enclosing block element.
    """

    _BLOCK_TAGS = frozenset(("p", "h1", "h2", "h3", "h4", "h5", "h6"))

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._current_page: int = 0
        self._max_page: int = 0
        self._distinct_pages: set[int] = set()
        self._stack: list[tuple[str, int, list[str]]] = []
        self.elements: list[tuple[str, int, str]] = []   # (tag, page, text)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            attrs_dict = dict(attrs)
            aid = attrs_dict.get("id") or ""
            m = _PAGE_ANCHOR_RE.match(aid)
            if m:
                pg = int(m.group(1))
                self._current_page = pg
                self._distinct_pages.add(pg)
                self._max_page = max(self._max_page, pg)
        if tag in self._BLOCK_TAGS:
            self._stack.append((tag, self._current_page, []))

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1][2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1][0] == tag:
            elem_tag, page, parts = self._stack.pop()
            text = re.sub(r"\s+", " ", "".join(parts)).strip()
            if text:
                self.elements.append((elem_tag, page, text))


# ── Detection core ───────────────────────────────────────────────────────────

def _normalize(raw: str) -> str:
    """Casefold and collapse whitespace; page number already excluded (group 1 only)."""
    return re.sub(r"\s+", " ", raw).strip().casefold()


def _classify_glue(text: str, match: re.Match) -> str:
    """Classify where the candidate sits within the paragraph text.

    Returns: standalone | glued-start | glued-end | mid-paragraph.
    text is already whitespace-normalized (single spaces, stripped).
    match covers the full candidate including optional trailing page number.
    """
    # EB-374: ignore a leading/trailing page-number token (arabic or roman) when
    # deciding standalone vs weld, so "viii HEADER" / "HEADER 73" are standalone.
    core_start = 0
    core_end = len(text)
    lead = _EDGE_LEAD.match(text)
    if lead and lead.end() <= match.start():
        core_start = lead.end()
    trail = _EDGE_TRAIL.search(text)
    if trail and trail.start() >= match.end():
        core_end = trail.start()
    at_start = match.start() <= core_start
    at_end = match.end() >= core_end
    if at_start and at_end:
        return "standalone"
    if at_start:
        return "glued-start"
    if at_end:
        return "glued-end"
    return "mid-paragraph"


def detect(html: str, params: Optional[DetectorParams] = None) -> BookResult:
    """Detect welded ALL-CAPS running headers in a _kindle.html string.

    Pure function — no I/O. Returns a BookResult with html_path set to ''.
    """
    if params is None:
        params = DetectorParams()

    parser = _BleedParser()
    try:
        parser.feed(html)
    except Exception as exc:
        return BookResult(
            html_path="", status="error", weld_total=0, total_pages=0,
            findings=[], standalone_repeats=[], heading_repeats=[],
            error=str(exc),
        )

    total_pages = parser._max_page
    if total_pages == 0:
        total_pages = len(parser._distinct_pages) or 1

    # Accumulate candidates: norm → {pages, count, positions, samples}
    p_acc: dict[str, dict] = {}
    h_acc: dict[str, dict] = {}

    for tag, page, text in parser.elements:
        m = CANDIDATE_RE.search(text)
        if not m:
            continue
        raw = m.group(1)
        norm = _normalize(raw)
        if not (params.len_min <= len(norm) <= params.len_max):
            continue
        glue = _classify_glue(text, m)
        ctx_start = max(0, m.start() - 60)
        ctx_end = min(len(text), m.end() + 60)
        sample = {"page": page, "context": text[ctx_start:ctx_end]}

        bucket = p_acc if tag == "p" else h_acc
        if norm not in bucket:
            bucket[norm] = {"pages": set(), "count": 0, "positions": [], "samples": []}
        entry = bucket[norm]
        entry["pages"].add(page)
        entry["count"] += 1
        entry["positions"].append(glue)
        if len(entry["samples"]) < 5:
            entry["samples"].append(sample)

    def _gate(acc: dict, include_standalone: bool) -> tuple[list[Finding], list[Finding]]:
        flagged: list[Finding] = []
        standalone: list[Finding] = []
        for norm, entry in acc.items():
            distinct = len(entry["pages"])
            density = distinct / total_pages
            if distinct < params.min_distinct_pages or density < params.min_density:
                continue
            f = Finding(
                normalized=norm,
                occurrences=entry["count"],
                distinct_pages=distinct,
                density=round(density, 4),
                glue_positions=list(entry["positions"]),
                samples=entry["samples"],
            )
            if any(g != "standalone" for g in entry["positions"]):
                flagged.append(f)
            elif include_standalone:
                standalone.append(f)
        return flagged, standalone

    findings, standalone_repeats = _gate(p_acc, include_standalone=True)
    # Headings are never welds; collect all density-gated heading candidates
    # (standalone or not) as informational heading_repeats.
    h_flagged, h_standalone = _gate(h_acc, include_standalone=True)
    heading_repeats = h_flagged + h_standalone

    weld_total = sum(
        sum(1 for g in f.glue_positions if g != "standalone")
        for f in findings
    )

    return BookResult(
        html_path="",
        status="flagged" if weld_total > 0 else "clean",
        weld_total=weld_total,
        total_pages=total_pages,
        findings=findings,
        standalone_repeats=standalone_repeats,
        heading_repeats=heading_repeats,
    )


def detect_file(path: Path, params: Optional[DetectorParams] = None) -> BookResult:
    """Run detect() on a single HTML file."""
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return BookResult(
            html_path=str(path), status="error", weld_total=0, total_pages=0,
            findings=[], standalone_repeats=[], heading_repeats=[],
            error=f"Cannot read {path}: {exc}",
        )
    result = detect(html, params)
    result.html_path = str(path)
    return result


def detect_directory(
    directory: Path,
    glob: str = DEFAULT_GLOB,
    params: Optional[DetectorParams] = None,
) -> list[BookResult]:
    """Run detect_file() on all matching HTML files in a directory."""
    files = sorted(directory.glob(glob))
    return [detect_file(f, params) for f in files]


# ── Exit code ────────────────────────────────────────────────────────────────

def _compute_exit_code(books: list[BookResult]) -> int:
    """Compute tiered exit code. Precedence: 3 > 2 > 1 > 0.

    1 — nothing to scan (empty book list)
    2 — >=1 book flagged
    3 — >=1 book errored
    """
    if not books:
        return 1
    code = 0
    for b in books:
        if b.status == "error":
            code = max(code, 3)
        elif b.weld_total > 0:
            code = max(code, 2)
    return code


# ── Helpers ──────────────────────────────────────────────────────────────────

def _git_head_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return "unknown"


def _render_report(
    books: list[BookResult],
    params: DetectorParams,
    exit_code: int,
) -> dict:
    total = len(books)
    flagged = sum(1 for b in books if b.weld_total > 0)
    errors = sum(1 for b in books if b.status == "error")
    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_sha": _git_head_sha(),
        "params": asdict(params),
        "summary": {
            "total_books": total,
            "flagged": flagged,
            "clean": total - flagged - errors,
            "errors": errors,
        },
        "exit_code": exit_code,
        "books": [asdict(b) for b in books],
    }


def _render_human_summary(books: list[BookResult], exit_code: int) -> str:
    lines: list[str] = []
    for b in books:
        name = Path(b.html_path).name if b.html_path else "<unknown>"
        if b.status == "flagged":
            cands = ", ".join(f.normalized for f in b.findings[:3])
            lines.append(f"  FLAGGED  {name}: {b.weld_total} weld(s) — {cands}")
        elif b.status == "error":
            lines.append(f"  ERROR    {name}: {b.error}")
        else:
            lines.append(f"  clean    {name}")
    label = {0: "CLEAN", 1: "NOTHING SCANNABLE", 2: "FLAGGED", 3: "ERROR"}.get(
        exit_code, str(exit_code)
    )
    lines.append(f"\ncheck_header_bleed: {label} (exit {exit_code})")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

class _ExitCodeParser(argparse.ArgumentParser):
    """Override error() to exit 3 instead of argparse's default 2.

    Exit 2 is reserved for 'flagged' books; argument errors must use 3.
    """

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(3, f"{self.prog}: error: {message}\n")


def _build_parser() -> _ExitCodeParser:
    p = _ExitCodeParser(
        prog="check_header_bleed",
        description="Detect welded ALL-CAPS running headers in _kindle.html artifacts.",
    )
    p.add_argument(
        "--input", required=True,
        help="Path to a _kindle.html file or directory to scan.",
    )
    p.add_argument(
        "--glob", default=DEFAULT_GLOB,
        help=f"Glob pattern for directory scan (default: {DEFAULT_GLOB!r}).",
    )
    p.add_argument(
        "--out", default=None,
        help="JSON report output path (default: data/batch_reports/header_bleed/<ts>.json).",
    )
    p.add_argument(
        "--min-distinct-pages", type=int, default=DEFAULT_MIN_DISTINCT_PAGES, metavar="N",
        help=f"Min distinct pages for a candidate to qualify (default: {DEFAULT_MIN_DISTINCT_PAGES}).",
    )
    p.add_argument(
        "--min-density", type=float, default=DEFAULT_MIN_DENSITY, metavar="F",
        help=f"Min page-density ratio for a candidate (default: {DEFAULT_MIN_DENSITY}).",
    )
    p.add_argument(
        "--len-min", type=int, default=DEFAULT_LEN_MIN, metavar="N",
        help=f"Min normalized candidate length in chars (default: {DEFAULT_LEN_MIN}).",
    )
    p.add_argument(
        "--len-max", type=int, default=DEFAULT_LEN_MAX, metavar="N",
        help=f"Max normalized candidate length in chars (default: {DEFAULT_LEN_MAX}).",
    )
    p.add_argument("--quiet", action="store_true", help="Suppress human summary.")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns exit code (caller passes to sys.exit)."""
    p = _build_parser()
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    params = DetectorParams(
        min_distinct_pages=args.min_distinct_pages,
        min_density=args.min_density,
        len_min=args.len_min,
        len_max=args.len_max,
    )

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input path does not exist: %s", input_path)
        return 3

    if input_path.is_dir():
        books = detect_directory(input_path, glob=args.glob, params=params)
    else:
        books = [detect_file(input_path, params=params)]

    exit_code = _compute_exit_code(books)

    if args.out:
        out_path = Path(args.out)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_path = Path("data/batch_reports/header_bleed") / f"{ts}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = _render_report(books, params, exit_code)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Report written to %s", out_path)

    if not args.quiet:
        print(_render_human_summary(books, exit_code))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
