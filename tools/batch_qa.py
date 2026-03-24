#!/usr/bin/env python3
"""
batch_qa.py — Batch Quality Assurance for EbookAutomation

Processes a folder of ebooks through the extraction and conversion pipeline,
collects structured diagnostics per book, detects failure patterns across
the batch, and produces actionable summary reports.

Usage:
    python tools/batch_qa.py <folder>                        # quick mode (HTML only)
    python tools/batch_qa.py <folder> --vqa                  # include visual QA scoring
    python tools/batch_qa.py <folder> --limit 10             # first N books only
    python tools/batch_qa.py <folder> --parallel 3           # concurrent processing
    python tools/batch_qa.py <folder> --format pdf           # filter by format
    python tools/batch_qa.py <folder> --resume <run_id>      # resume interrupted batch
    python tools/batch_qa.py report <run_id>                 # regenerate report from DB
    python tools/batch_qa.py compare <run_id1> <run_id2>     # diff two batch runs
    python tools/batch_qa.py list                            # list past batch runs
"""

import argparse
import glob
import json
import logging
import os
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Import project modules
sys.path.insert(0, str(SCRIPT_DIR))
try:
    from pattern_db import (
        get_db, get_or_create_book, add_conversion, add_issue,
        get_book_by_filename
    )
    HAS_PATTERN_DB = True
except ImportError:
    HAS_PATTERN_DB = False

try:
    from test_pipeline import extract_baseline_from_html, LIGATURE_SPLIT_RE
    HAS_TEST_PIPELINE = True
except ImportError:
    HAS_TEST_PIPELINE = False

logger = logging.getLogger("batch_qa")

# Supported ebook formats
SUPPORTED_FORMATS = {'pdf', 'epub', 'mobi', 'azw', 'azw3', 'txt', 'docx'}

# Default output directory for reports
REPORTS_DIR = PROJECT_ROOT / "data" / "batch_reports"


# ═══════════════════════════════════════════════════════════════════════════
# Schema migration — add batch_runs table
# ═══════════════════════════════════════════════════════════════════════════

_BATCH_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS batch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    folder_path TEXT,
    books_total INTEGER DEFAULT 0,
    books_passed INTEGER DEFAULT 0,
    books_warned INTEGER DEFAULT 0,
    books_failed INTEGER DEFAULT 0,
    books_errored INTEGER DEFAULT 0,
    total_duration_seconds REAL,
    total_api_cost_usd REAL DEFAULT 0,
    avg_vqa_score REAL,
    report_json_path TEXT,
    report_md_path TEXT,
    flags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_BATCH_BOOKS_SQL = """
CREATE TABLE IF NOT EXISTS batch_book_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    book_id INTEGER,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,
    status_reason TEXT,
    diagnostics_json TEXT,
    conversion_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES batch_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_batch_book_results_run
    ON batch_book_results(run_id);
"""


def ensure_batch_tables(db_path=None):
    """Create batch QA tables if they don't exist."""
    if not HAS_PATTERN_DB:
        return
    conn = get_db(db_path)
    try:
        conn.executescript(_BATCH_RUNS_SQL)
        conn.executescript(_BATCH_BOOKS_SQL)
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Failure pattern definitions
# ═══════════════════════════════════════════════════════════════════════════

BACKMATTER_KEYWORDS = {
    'notes', 'bibliography', 'index', 'references', 'appendix', 'appendices',
    'glossary', 'further reading', 'suggested reading', 'about the author',
    'acknowledgments', 'acknowledgements', 'works cited', 'endnotes',
    'select bibliography', 'selected bibliography', 'source notes',
    'permissions', 'credits', 'colophon',
}


def _looks_like_backmatter(heading_labels):
    """Check if all detected headings are back-matter."""
    if not heading_labels:
        return False
    for label in heading_labels:
        lower = label.lower().strip()
        if not any(kw in lower for kw in BACKMATTER_KEYWORDS):
            return False
    return True


FAILURE_PATTERNS = {
    "CHAPTER_DETECTION_ZERO": {
        "condition": lambda d: d["structure"]["chapter_count"] == 0,
        "severity": "high",
        "label": "No chapters detected",
        "description": (
            "Chapter detection found zero real chapters. "
            "May be finding only back-matter headings."
        ),
        "recommendation": (
            "Fix Get-ChapterStructure prompt hierarchy rules "
            "and increase text window size"
        ),
    },
    "CHAPTER_DETECTION_BACKMATTER_ONLY": {
        "condition": lambda d: d["structure"].get(
            "headings_look_like_backmatter", False
        ),
        "severity": "high",
        "label": "Only back-matter headings detected",
        "description": (
            "All detected headings are back-matter "
            "(Notes, Index, Bibliography, etc.)"
        ),
        "recommendation": (
            "Add backmatter exclusion to chapter detection; "
            "prioritize headings appearing in first 80% of document"
        ),
    },
    "LIGATURE_SPLITS_HIGH": {
        "condition": lambda d: d["text_quality"]["ligature_splits"] > 20,
        "severity": "medium",
        "label": "Excessive ligature splits (>20)",
        "description": (
            "More than 20 ligature split artifacts remain after fix pass"
        ),
        "recommendation": (
            "Expand ligature pattern dictionary; check if "
            "source is a specific publisher/font"
        ),
    },
    "FOOTNOTES_UNLINKED": {
        "condition": lambda d: (
            d["text_quality"]["footnotes_unlinked"] > 10
            and d["text_quality"]["footnotes_linked"] == 0
        ),
        "severity": "medium",
        "label": "Footnotes not linked",
        "description": (
            "Superscript footnote numbers present but none "
            "converted to hyperlinks"
        ),
        "recommendation": (
            "Check footnote detection regex; may need "
            "publisher-specific pattern"
        ),
    },
    "VQA_SCORE_LOW": {
        "condition": lambda d: (
            d.get("visual_qa", {}).get("attempted")
            and d.get("visual_qa", {}).get("score", 100) < 65
        ),
        "severity": "high",
        "label": "Visual QA score below 65",
        "description": (
            "Output quality significantly below acceptable threshold"
        ),
        "recommendation": (
            "Review VQA category scores to identify weakest area; "
            "check extraction path selection"
        ),
    },
    "ENCODING_ERRORS": {
        "condition": lambda d: d["text_quality"].get("encoding_errors", 0) > 0,
        "severity": "high",
        "label": "Encoding errors in extracted text",
        "description": "Non-UTF8 content caused garbled characters",
        "recommendation": "Add encoding normalization as pre-processing step",
    },
    "EXTRACTION_FAILED": {
        "condition": lambda d: not d["extraction"]["success"],
        "severity": "critical",
        "label": "Text extraction failed",
        "description": "Could not extract text from source file",
        "recommendation": (
            "Check extraction path; may need OCR fallback "
            "or alternate extraction method"
        ),
    },
    "KFX_FAILED": {
        "condition": lambda d: (
            d.get("kindle_conversion", {}).get("attempted", False)
            and not d.get("kindle_conversion", {}).get("success", True)
        ),
        "severity": "high",
        "label": "KFX conversion failed",
        "description": "Calibre could not produce KFX output",
        "recommendation": (
            "Check Calibre error log; may need HTML cleanup "
            "before conversion"
        ),
    },
    "PAGE_NUMBERS_PRESENT": {
        "condition": lambda d: (
            d["text_quality"].get("standalone_page_numbers", 0) > 5
        ),
        "severity": "low",
        "label": "Standalone page numbers in output",
        "description": "Page numbers from source PDF leaked into body text",
        "recommendation": "Improve page number stripping regex",
    },
    "NO_FORMATTING_PRESERVED": {
        "condition": lambda d: (
            d["text_quality"].get("italic_tags", 0) == 0
            and d["text_quality"].get("bold_tags", 0) == 0
            and d["structure"].get("word_count", 0) > 10000
        ),
        "severity": "medium",
        "label": "No bold/italic formatting preserved",
        "description": (
            "Source likely had formatting but none was preserved "
            "in output"
        ),
        "recommendation": (
            "Check if extraction path supports inline formatting; "
            "may need HTML extraction mode"
        ),
    },
    "DOUBLE_SPACES": {
        "condition": lambda d: d["text_quality"].get("double_spaces", 0) > 20,
        "severity": "low",
        "label": "Excessive double spaces (>20)",
        "description": "Multiple double-space artifacts in output text",
        "recommendation": "Check text normalization pass",
    },
    "LIKELY_SCAN_NO_OCR": {
        "condition": lambda d: (
            d["source_classification"].get("source_type") == "scan"
            and d["structure"]["word_count"] < 100
        ),
        "severity": "medium",
        "label": "Likely scanned PDF without OCR",
        "description": (
            "File size suggests a full book but almost no text extracted. "
            "Likely image-only."
        ),
        "recommendation": (
            "Re-run with OCR enabled, or add auto-OCR fallback "
            "for classified scans"
        ),
    },
    "DRM_ENCRYPTED": {
        "condition": lambda d: any(
            "encrypt" in e.lower() or "password" in e.lower()
            for e in d["extraction"].get("errors", [])
        ),
        "severity": "medium",
        "label": "DRM-encrypted PDF",
        "description": (
            "PDF has encryption. May have empty password "
            "(easily decryptable) or real DRM."
        ),
        "recommendation": (
            "Try empty-password decrypt; if that fails, "
            "manual DRM removal needed"
        ),
    },
    "MULTI_COLUMN_NOT_ROUTED": {
        "condition": lambda d: (
            d["source_classification"].get("column_confidence", 0) >= 0.3
            and d["source_classification"].get("column_confidence", 0) < 0.6
            and d["structure"]["word_count"] > 5000
        ),
        "severity": "low",
        "label": "Possible multi-column PDF not routed to column extractor",
        "description": (
            "Column detection confidence is 30-59% — mixed layout. "
            "May benefit from column-aware extraction on some pages."
        ),
        "recommendation": (
            "Try re-running with --force-columns flag to compare output"
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Folder scanning
# ═══════════════════════════════════════════════════════════════════════════

def scan_folder(folder_path, format_filter=None):
    """Scan a folder for supported ebook files. Returns list of Path objects."""
    folder = Path(folder_path)
    if not folder.is_dir():
        logger.error("Folder not found: %s", folder_path)
        return []

    files = []
    for f in sorted(folder.iterdir()):
        if not f.is_file():
            continue
        ext = f.suffix.lstrip('.').lower()
        if ext not in SUPPORTED_FORMATS:
            continue
        if format_filter and ext != format_filter.lower():
            continue
        files.append(f)

    return files


# ═══════════════════════════════════════════════════════════════════════════
# Per-book extraction and diagnostics
# ═══════════════════════════════════════════════════════════════════════════

def run_extraction_for_book(pdf_path, output_dir, quick=True):
    """
    Run text extraction on a single book.
    Returns (html_path_or_none, txt_path_or_none, stdout, stderr, exit_code).
    """
    cmd = [
        sys.executable, str(SCRIPT_DIR / "pdf_to_balabolka.py"),
        "--input", str(pdf_path),
        "--mode", "kindle",
        "--output-dir", str(output_dir),
        "--html-extraction",
    ]

    # Scale timeout: base 600s + 10s per MB over 20MB
    file_size_mb = os.path.getsize(str(pdf_path)) / (1024 * 1024)
    timeout = max(600, 600 + int((file_size_mb - 20) * 10)) if file_size_mb > 20 else 600

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None, None, "", f"TIMEOUT: extraction exceeded {timeout}s", -1

    # Find the output file (HTML or TXT)
    # Must match pdf_to_balabolka.py's sanitization (line ~8821)
    stem = Path(pdf_path).stem
    safe_stem = re.sub(r"[^\w\s\-]", "", stem).strip().replace(" ", "_")

    html_files = sorted(
        glob.glob(str(Path(output_dir) / f"*{safe_stem[:30]}*.html")),
        key=os.path.getmtime
    )
    txt_files = sorted(
        glob.glob(str(Path(output_dir) / f"*{safe_stem[:30]}*.txt")),
        key=os.path.getmtime
    )

    html_path = html_files[-1] if html_files else None
    txt_path = txt_files[-1] if txt_files else None

    return html_path, txt_path, result.stdout, result.stderr, result.returncode


def run_kfx_conversion_for_book(pdf_path):
    """Run KFX conversion via PowerShell Convert-ToKindle. Returns (success, kfx_path, duration)."""
    module_path = PROJECT_ROOT / "module" / "EbookAutomation.psd1"
    if not module_path.exists():
        module_path = PROJECT_ROOT / "EbookAutomation.psd1"

    ps_cmd = (
        f'Import-Module "{module_path}" -Force; '
        f'Convert-ToKindle -InputFile "{pdf_path}" -UsePdfminer -NoCache'
    )

    # Scale timeout: base 600s + 10s per MB over 20MB
    file_size_mb = os.path.getsize(str(pdf_path)) / (1024 * 1024)
    timeout = max(600, 600 + int((file_size_mb - 20) * 10)) if file_size_mb > 20 else 600

    t0 = time.time()
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout
        )
        duration = time.time() - t0

        kfx_match = re.search(r'done -> (.+\.kfx)', result.stdout + result.stderr)
        kfx_path = kfx_match.group(1) if kfx_match else None
        success = result.returncode == 0 and kfx_path is not None

        return success, kfx_path, duration
    except subprocess.TimeoutExpired:
        return False, None, time.time() - t0


def run_visual_qa_for_book(kfx_path):
    """Run visual QA scoring on a KFX file. Returns (score, category_scores, cost, duration)."""
    qa_script = SCRIPT_DIR / "visual_qa.py"
    if not qa_script.exists():
        return None, {}, 0, 0

    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(qa_script), "--input", str(kfx_path), "--verbose"],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=300
        )
        duration = time.time() - t0

        # Parse the JSON report that visual_qa.py produces
        report_path = str(kfx_path).rsplit('.', 1)[0] + '_visual_qa_report.json'
        if os.path.isfile(report_path):
            with open(report_path, 'r', encoding='utf-8') as f:
                report = json.load(f)
            score = report.get('overall_score', report.get('score'))
            categories = report.get('category_scores', {})
            cost = report.get('cost_usd', report.get('api_cost_usd', 0))
            return score, categories, cost, duration

        return None, {}, 0, duration
    except (subprocess.TimeoutExpired, Exception):
        return None, {}, 0, time.time() - t0


def collect_diagnostics(file_path, output_dir, run_id, quick=True, include_vqa=False):
    """
    Process a single book and collect structured diagnostics.
    Returns a diagnostics dict.
    """
    filename = file_path.name
    ext = file_path.suffix.lstrip('.').lower()
    file_size = file_path.stat().st_size

    diag = {
        "filename": filename,
        "file_size_bytes": file_size,
        "format": ext,
        "batch_run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_classification": {
            "source_type": "unknown",
            "confidence": 0,
            "strategy_selected": "html_extraction" if ext == 'pdf' else "direct",
            "strategy_source": "default",
        },
        "extraction": {
            "success": False,
            "extraction_path": "html_extraction" if ext == 'pdf' else "direct",
            "duration_seconds": 0,
            "html_produced": False,
            "html_size_bytes": 0,
            "errors": [],
            "warnings": [],
        },
        "structure": {
            "chapter_count": 0,
            "h1_count": 0,
            "h2_count": 0,
            "h3_count": 0,
            "heading_labels": [],
            "headings_look_like_backmatter": False,
            "word_count": 0,
            "page_count": 0,
            "has_toc": False,
            "toc_entries": 0,
        },
        "text_quality": {
            "ligature_splits": 0,
            "double_spaces": 0,
            "encoding_errors": 0,
            "standalone_page_numbers": 0,
            "blockquotes_detected": 0,
            "italic_tags": 0,
            "bold_tags": 0,
            "footnotes_linked": 0,
            "footnotes_unlinked": 0,
        },
        "kindle_conversion": {
            "attempted": False,
            "success": False,
            "kfx_size_bytes": 0,
            "duration_seconds": 0,
        },
        "visual_qa": {
            "attempted": False,
            "score": None,
            "pass_threshold": 70,
            "passed": False,
            "category_scores": {},
            "api_cost_usd": 0,
            "duration_seconds": 0,
        },
        "issues": [],
        "overall_status": "ERROR",
        "status_reason": "Not yet processed",
    }

    # ── Phase 1: Text extraction ────────────────────────────────
    t0 = time.time()

    if ext == 'pdf':
        html_path, txt_path, stdout, stderr, exit_code = \
            run_extraction_for_book(file_path, output_dir, quick)
        extraction_duration = time.time() - t0

        diag["extraction"]["duration_seconds"] = round(extraction_duration, 1)

        if exit_code != 0:
            diag["extraction"]["errors"].append(
                f"Extraction exited with code {exit_code}"
            )
            if stderr:
                # Capture last 3 lines of stderr
                err_lines = [l.strip() for l in stderr.strip().split('\n') if l.strip()]
                diag["extraction"]["errors"].extend(err_lines[-3:])
            diag["overall_status"] = "FAIL"
            diag["status_reason"] = "Text extraction failed"
            return diag

        if html_path and os.path.isfile(html_path):
            diag["extraction"]["success"] = True
            diag["extraction"]["html_produced"] = True
            diag["extraction"]["html_size_bytes"] = os.path.getsize(html_path)

            # ── Phase 2: Structural analysis from HTML ──────────
            with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
                html_content = f.read()

            _analyze_html_structure(diag, html_content)

        elif txt_path and os.path.isfile(txt_path):
            diag["extraction"]["success"] = True
            diag["extraction"]["html_produced"] = False
            # Basic analysis from TXT (less rich than HTML)
            with open(txt_path, 'r', encoding='utf-8', errors='replace') as f:
                txt_content = f.read()
            diag["structure"]["word_count"] = len(txt_content.split())
        else:
            diag["extraction"]["errors"].append("No output file produced")
            diag["overall_status"] = "FAIL"
            diag["status_reason"] = "Extraction produced no output"
            return diag

        # Capture warnings from stdout
        if stdout:
            for line in stdout.split('\n'):
                if 'warn' in line.lower() or 'WARNING' in line:
                    diag["extraction"]["warnings"].append(line.strip()[:200])
    else:
        # Non-PDF formats — just record basic metadata
        diag["extraction"]["success"] = True
        diag["extraction"]["extraction_path"] = "direct"
        diag["extraction"]["duration_seconds"] = round(time.time() - t0, 1)

    # ── Phase 2b: Column detection + Scan detection + DRM detection ──
    if ext == 'pdf' and diag["extraction"]["success"]:
        # Probe column layout for diagnostics
        try:
            from pdf_to_balabolka import detect_column_layout
            col_info = detect_column_layout(
                str(file_path), lambda msg: None)
            diag["source_classification"]["is_multicolumn"] = col_info.get(
                "is_multicolumn", False)
            diag["source_classification"]["column_confidence"] = col_info.get(
                "confidence", 0)
            diag["source_classification"]["num_columns"] = col_info.get(
                "num_columns", 1)
            if col_info.get("is_multicolumn"):
                diag["source_classification"]["source_type"] = "multi_column"
        except Exception:
            pass  # non-blocking

        word_count = diag["structure"]["word_count"]
        file_size = diag["file_size_bytes"]
        # Low text yield relative to file size → likely scanned/image-only
        if word_count < 100 and file_size > 5 * 1024 * 1024:
            diag["source_classification"]["source_type"] = "scan"
            diag["source_classification"]["confidence"] = 0.8
            diag["extraction"]["warnings"].append(
                "Very low text yield for file size — likely scanned/image-only PDF. "
                "Consider re-running with --use-ocr flag."
            )

    if ext == 'pdf' and not diag["extraction"]["success"]:
        # Check for DRM/encryption via pypdf
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            if reader.is_encrypted:
                decrypted = False
                try:
                    decrypted = reader.decrypt("") > 0
                except Exception:
                    pass
                if decrypted:
                    diag["extraction"]["warnings"].append(
                        "PDF was encrypted with empty password — decryptable"
                    )
                else:
                    diag["extraction"]["errors"].append(
                        "PDF is encrypted and password-protected"
                    )
        except Exception:
            pass  # Don't let DRM check block the pipeline

    # ── Phase 3: KFX conversion (skip in quick mode) ────────────
    if not quick and ext == 'pdf':
        diag["kindle_conversion"]["attempted"] = True
        kfx_ok, kfx_path, kfx_dur = run_kfx_conversion_for_book(file_path)
        diag["kindle_conversion"]["success"] = kfx_ok
        diag["kindle_conversion"]["duration_seconds"] = round(kfx_dur, 1)
        if kfx_ok and kfx_path and os.path.isfile(kfx_path):
            diag["kindle_conversion"]["kfx_size_bytes"] = os.path.getsize(kfx_path)

            # ── Phase 4: Visual QA (only if requested and KFX exists) ───
            if include_vqa:
                diag["visual_qa"]["attempted"] = True
                vqa_score, vqa_cats, vqa_cost, vqa_dur = \
                    run_visual_qa_for_book(kfx_path)
                diag["visual_qa"]["score"] = vqa_score
                diag["visual_qa"]["category_scores"] = vqa_cats
                diag["visual_qa"]["api_cost_usd"] = round(vqa_cost, 4)
                diag["visual_qa"]["duration_seconds"] = round(vqa_dur, 1)
                diag["visual_qa"]["passed"] = (
                    vqa_score is not None
                    and vqa_score >= diag["visual_qa"]["pass_threshold"]
                )

    # ── Phase 5: Issue detection ────────────────────────────────
    _detect_issues(diag)

    # ── Phase 6: Status classification ──────────────────────────
    _classify_status(diag)

    return diag


def _analyze_html_structure(diag, html_content):
    """Extract structural and text quality metrics from HTML output."""
    # Use test_pipeline's baseline extractor if available
    if HAS_TEST_PIPELINE:
        baseline = extract_baseline_from_html(html_content)
        diag["structure"]["h1_count"] = baseline.get("h1_count", 0)
        diag["structure"]["h2_count"] = baseline.get("h2_count", 0)
        diag["structure"]["h3_count"] = baseline.get("h3_count", 0)
        diag["structure"]["heading_labels"] = (
            baseline.get("h1_headings", [])
            + baseline.get("h2_headings", [])
        )
        diag["text_quality"]["ligature_splits"] = baseline.get(
            "ligature_splits_remaining", 0
        )
        diag["text_quality"]["double_spaces"] = baseline.get("double_spaces", 0)
        diag["text_quality"]["standalone_page_numbers"] = baseline.get(
            "standalone_page_numbers", 0
        )
        diag["text_quality"]["blockquotes_detected"] = baseline.get(
            "blockquotes", 0
        )
        diag["text_quality"]["italic_tags"] = baseline.get("em_tags", 0)
        diag["text_quality"]["footnotes_linked"] = baseline.get(
            "linked_footnotes", 0
        )
        diag["text_quality"]["footnotes_unlinked"] = baseline.get(
            "unlinked_footnotes", 0
        )
    else:
        # Manual fallback
        all_headings = re.findall(r'<(h[123])>(.*?)</\1>', html_content)
        diag["structure"]["h1_count"] = sum(
            1 for tag, _ in all_headings if tag == 'h1'
        )
        diag["structure"]["h2_count"] = sum(
            1 for tag, _ in all_headings if tag == 'h2'
        )
        diag["structure"]["h3_count"] = sum(
            1 for tag, _ in all_headings if tag == 'h3'
        )
        diag["structure"]["heading_labels"] = [
            text for _, text in all_headings
        ]

    # Chapter count = h1 + h2 (h3 are sub-sections, not chapters)
    diag["structure"]["chapter_count"] = (
        diag["structure"]["h1_count"] + diag["structure"]["h2_count"]
    )

    # Check if headings look like back-matter
    diag["structure"]["headings_look_like_backmatter"] = _looks_like_backmatter(
        diag["structure"]["heading_labels"]
    )

    # Word count from body text
    body_text = re.sub(r'<[^>]+>', ' ', html_content)
    diag["structure"]["word_count"] = len(body_text.split())

    # Bold tag count
    diag["text_quality"]["bold_tags"] = len(
        re.findall(r'<(?:strong|b)>', html_content)
    )

    # Encoding error heuristic: count replacement characters
    diag["text_quality"]["encoding_errors"] = body_text.count('\ufffd')


def _detect_issues(diag):
    """Run failure pattern detection and populate issues list."""
    for pattern_id, pattern in FAILURE_PATTERNS.items():
        try:
            if pattern["condition"](diag):
                diag["issues"].append({
                    "category": pattern_id.lower(),
                    "severity": pattern["severity"],
                    "description": pattern["description"],
                })
        except (KeyError, TypeError):
            continue


def _classify_status(diag):
    """Set overall_status and status_reason based on diagnostics."""
    if not diag["extraction"]["success"]:
        diag["overall_status"] = "ERROR"
        diag["status_reason"] = "Extraction failed"
        return

    has_critical = any(i["severity"] == "critical" for i in diag["issues"])
    has_high = any(i["severity"] == "high" for i in diag["issues"])

    vqa = diag.get("visual_qa", {})
    vqa_attempted = vqa.get("attempted", False)
    vqa_score = vqa.get("score")
    vqa_threshold = vqa.get("pass_threshold", 70)

    if has_critical:
        diag["overall_status"] = "FAIL"
        diag["status_reason"] = "Critical issue detected"
    elif (vqa_attempted and vqa_score is not None
          and vqa_score < vqa_threshold - 10):
        diag["overall_status"] = "FAIL"
        diag["status_reason"] = f"VQA score {vqa_score} well below threshold"
    elif has_high:
        diag["overall_status"] = "WARN"
        high_issues = [i["description"][:60] for i in diag["issues"]
                       if i["severity"] == "high"]
        diag["status_reason"] = "; ".join(high_issues[:2])
    elif (vqa_attempted and vqa_score is not None
          and vqa_score < vqa_threshold):
        diag["overall_status"] = "WARN"
        diag["status_reason"] = f"VQA score {vqa_score} below threshold {vqa_threshold}"
    else:
        diag["overall_status"] = "PASS"
        diag["status_reason"] = "All checks passed"


# ═══════════════════════════════════════════════════════════════════════════
# Pattern analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_patterns(diagnostics_list):
    """
    Cluster failure patterns across all books in the batch.
    Returns sorted list of (pattern_id, cluster_info) tuples.
    """
    clusters = {}

    for diag in diagnostics_list:
        for pattern_id, pattern in FAILURE_PATTERNS.items():
            try:
                if pattern["condition"](diag):
                    if pattern_id not in clusters:
                        clusters[pattern_id] = {
                            "pattern": pattern,
                            "books": [],
                            "source_types": Counter(),
                            "formats": Counter(),
                        }
                    clusters[pattern_id]["books"].append(diag["filename"])
                    src = diag["source_classification"]["source_type"]
                    clusters[pattern_id]["source_types"][src] += 1
                    clusters[pattern_id]["formats"][diag["format"]] += 1
            except (KeyError, TypeError):
                continue

    # Sort by severity then by book count descending
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_clusters = sorted(
        clusters.items(),
        key=lambda x: (
            severity_order.get(x[1]["pattern"]["severity"], 9),
            -len(x[1]["books"]),
        ),
    )

    return sorted_clusters


def detect_correlations(diagnostics_list, clusters):
    """Find cross-cutting correlations in the batch data."""
    observations = []
    total = len(diagnostics_list)
    if total == 0:
        return observations

    # Source type correlation for failures
    failed = [d for d in diagnostics_list if d["overall_status"] in ("FAIL", "ERROR")]
    if failed:
        src_counts = Counter(d["source_classification"]["source_type"] for d in failed)
        for src, count in src_counts.most_common(3):
            if src != "unknown" and count >= 2:
                pct = count / len(failed) * 100
                if pct >= 75:
                    observations.append(
                        f"{pct:.0f}% of failures are '{src}' source type "
                        f"({count}/{len(failed)} failed books)"
                    )

    # Chapter detection is the dominant issue
    if "CHAPTER_DETECTION_ZERO" in dict(clusters):
        ch_count = len(dict(clusters)["CHAPTER_DETECTION_ZERO"]["books"])
        pct = ch_count / total * 100
        if pct >= 15:
            # Estimate impact of fixing
            pass_count = sum(
                1 for d in diagnostics_list if d["overall_status"] == "PASS"
            )
            potential_pass = pass_count + ch_count
            observations.append(
                f"Chapter detection affects {pct:.0f}% of all books "
                f"({ch_count}/{total}). "
                f"Fixing this could improve batch pass rate from "
                f"{pass_count/total*100:.0f}% to ~{potential_pass/total*100:.0f}%."
            )

    # File size correlation
    large_fail = [
        d for d in failed if d["file_size_bytes"] > 10 * 1024 * 1024
    ]
    if len(large_fail) >= 2 and len(large_fail) / max(len(failed), 1) >= 0.5:
        observations.append(
            f"{len(large_fail)} of {len(failed)} failures are files >10MB. "
            f"Large files may need special handling."
        )

    # VQA score distribution
    vqa_scores = [
        d["visual_qa"]["score"]
        for d in diagnostics_list
        if d["visual_qa"].get("attempted") and d["visual_qa"].get("score") is not None
    ]
    if vqa_scores:
        below_60 = sum(1 for s in vqa_scores if s < 60)
        if below_60 >= 2:
            observations.append(
                f"{below_60} books scored below 60 in VQA. "
                f"These may need alternate extraction strategies."
            )

    return observations


# ═══════════════════════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_json_report(run_id, diagnostics_list, clusters, observations,
                         duration, flags):
    """Write the full machine-readable JSON report."""
    report = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "books_total": len(diagnostics_list),
            "books_passed": sum(
                1 for d in diagnostics_list if d["overall_status"] == "PASS"
            ),
            "books_warned": sum(
                1 for d in diagnostics_list if d["overall_status"] == "WARN"
            ),
            "books_failed": sum(
                1 for d in diagnostics_list if d["overall_status"] == "FAIL"
            ),
            "books_errored": sum(
                1 for d in diagnostics_list if d["overall_status"] == "ERROR"
            ),
            "total_duration_seconds": round(duration, 1),
            "total_api_cost_usd": round(sum(
                d.get("visual_qa", {}).get("api_cost_usd", 0)
                for d in diagnostics_list
            ), 4),
            "flags": flags,
        },
        "failure_clusters": [
            {
                "pattern_id": pid,
                "severity": cluster["pattern"]["severity"],
                "label": cluster["pattern"]["label"],
                "description": cluster["pattern"]["description"],
                "recommendation": cluster["pattern"]["recommendation"],
                "book_count": len(cluster["books"]),
                "books": cluster["books"],
                "source_types": dict(cluster["source_types"]),
                "formats": dict(cluster["formats"]),
            }
            for pid, cluster in clusters
        ],
        "observations": observations,
        "books": diagnostics_list,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"{run_id}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return str(json_path)


def generate_md_report(run_id, diagnostics_list, clusters, observations,
                       duration, flags):
    """Write the human-readable Markdown summary report."""
    total = len(diagnostics_list)
    passed = sum(1 for d in diagnostics_list if d["overall_status"] == "PASS")
    warned = sum(1 for d in diagnostics_list if d["overall_status"] == "WARN")
    failed = sum(1 for d in diagnostics_list if d["overall_status"] == "FAIL")
    errored = sum(1 for d in diagnostics_list if d["overall_status"] == "ERROR")
    api_cost = sum(
        d.get("visual_qa", {}).get("api_cost_usd", 0) for d in diagnostics_list
    )
    dur_min = int(duration // 60)
    dur_sec = int(duration % 60)

    vqa_scores = [
        d["visual_qa"]["score"]
        for d in diagnostics_list
        if d["visual_qa"].get("attempted") and d["visual_qa"].get("score") is not None
    ]

    lines = []
    lines.append(f"# Batch QA Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"**Run ID:** {run_id}  ")
    lines.append(
        f"**Books processed:** {total} | "
        f"**Passed:** {passed} | **Warnings:** {warned} | "
        f"**Failed:** {failed} | **Errors:** {errored}  "
    )
    lines.append(
        f"**Duration:** {dur_min}m {dur_sec}s | "
        f"**API cost:** ${api_cost:.2f}  "
    )
    if vqa_scores:
        avg_vqa = sum(vqa_scores) / len(vqa_scores)
        lines.append(
            f"**Visual QA:** {len(vqa_scores)} scored | "
            f"avg {avg_vqa:.1f} | "
            f"range {min(vqa_scores)}–{max(vqa_scores)}  "
        )
    mode = "Quick (HTML only)" if flags.get("quick") else "Full"
    if flags.get("vqa"):
        mode += " + VQA"
    lines.append(f"**Mode:** {mode}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Failure clusters ────────────────────────────────────────
    if clusters:
        lines.append("## Failure clusters (sorted by impact)")
        lines.append("")

        cluster_dict = dict(clusters)
        for pid, cluster in clusters:
            sev = cluster["pattern"]["severity"].upper()
            label = cluster["pattern"]["label"]
            book_count = len(cluster["books"])
            lines.append(f"### {sev} — {label} ({book_count} books)")

            # Show first 5 filenames, summarize the rest
            shown = cluster["books"][:5]
            lines.append(f"**Affected:** {', '.join(shown)}")
            if book_count > 5:
                lines.append(f"(+{book_count - 5} more — see JSON report)")

            # Source type breakdown
            src_parts = [
                f"{src} ({cnt})"
                for src, cnt in cluster["source_types"].most_common()
            ]
            if src_parts and not all(s.startswith("unknown") for s in src_parts):
                lines.append(f"**Source types:** {', '.join(src_parts)}")

            lines.append(
                f"**Recommendation:** {cluster['pattern']['recommendation']}"
            )

            # Check overlap with other clusters
            for other_pid, other_cluster in clusters:
                if other_pid == pid:
                    continue
                overlap = set(cluster["books"]) & set(other_cluster["books"])
                if len(overlap) >= 2 and len(overlap) == len(cluster["books"]):
                    lines.append(
                        f"**Overlap:** All {len(overlap)} also in "
                        f"\"{other_cluster['pattern']['label']}\""
                    )

            # Impact note for high-volume clusters
            if book_count >= total * 0.15:
                pct = book_count / total * 100
                lines.append(
                    f"**Impact:** Affects {pct:.0f}% of all books in this batch."
                )

            lines.append("")
    else:
        lines.append("## No failure patterns detected")
        lines.append("")
        lines.append("All books passed without triggering any known failure patterns.")
        lines.append("")

    # ── Observations ────────────────────────────────────────────
    if observations:
        lines.append("---")
        lines.append("")
        lines.append("## Observations")
        lines.append("")
        for obs in observations:
            lines.append(f"- {obs}")
        lines.append("")

    # ── Score distribution ──────────────────────────────────────
    if vqa_scores:
        lines.append("---")
        lines.append("")
        lines.append("## VQA score distribution")
        lines.append("")
        lines.append("| Range | Count |")
        lines.append("|-------|-------|")

        buckets = [(90, 100), (80, 89), (70, 79), (60, 69), (0, 59)]
        for lo, hi in buckets:
            count = sum(1 for s in vqa_scores if lo <= s <= hi)
            if count > 0:
                lines.append(f"| {lo}–{hi} | {count} |")
        no_vqa = total - len(vqa_scores)
        if no_vqa > 0:
            lines.append(f"| No VQA | {no_vqa} |")
        lines.append("")

    # ── Per-book summary table ──────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Per-book summary")
    lines.append("")
    lines.append("| # | Book | Status | Chapters | Issues | Time |")
    lines.append("|---|------|--------|----------|--------|------|")

    for i, diag in enumerate(diagnostics_list, 1):
        name = diag["filename"]
        if len(name) > 45:
            name = name[:42] + "..."
        status = diag["overall_status"]
        ch = diag["structure"]["chapter_count"]
        ch_str = str(ch) if diag["extraction"]["success"] else "—"
        issues = len(diag["issues"])
        ext_dur = diag["extraction"]["duration_seconds"]
        kfx_dur = diag.get("kindle_conversion", {}).get("duration_seconds", 0)
        vqa_dur = diag.get("visual_qa", {}).get("duration_seconds", 0)
        total_dur = ext_dur + kfx_dur + vqa_dur
        time_str = f"{total_dur:.0f}s" if total_dur > 0 else "—"

        lines.append(
            f"| {i} | {name} | {status} | {ch_str} | {issues} | {time_str} |"
        )

    lines.append("")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"{run_id}.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return str(md_path)


# ═══════════════════════════════════════════════════════════════════════════
# Database recording
# ═══════════════════════════════════════════════════════════════════════════

def record_batch_to_db(run_id, diagnostics_list, duration, flags,
                       json_path, md_path, db_path=None):
    """Write batch results to pattern_db."""
    if not HAS_PATTERN_DB:
        logger.warning("pattern_db not available; skipping database recording")
        return

    ensure_batch_tables(db_path)
    conn = get_db(db_path)

    try:
        total = len(diagnostics_list)
        passed = sum(1 for d in diagnostics_list if d["overall_status"] == "PASS")
        warned = sum(1 for d in diagnostics_list if d["overall_status"] == "WARN")
        failed = sum(1 for d in diagnostics_list if d["overall_status"] == "FAIL")
        errored = sum(1 for d in diagnostics_list if d["overall_status"] == "ERROR")
        api_cost = sum(
            d.get("visual_qa", {}).get("api_cost_usd", 0) for d in diagnostics_list
        )
        vqa_scores = [
            d["visual_qa"]["score"]
            for d in diagnostics_list
            if d["visual_qa"].get("attempted") and d["visual_qa"]["score"] is not None
        ]
        avg_vqa = sum(vqa_scores) / len(vqa_scores) if vqa_scores else None

        # Insert batch run record
        conn.execute(
            """INSERT OR REPLACE INTO batch_runs
               (run_id, folder_path, books_total, books_passed, books_warned,
                books_failed, books_errored, total_duration_seconds,
                total_api_cost_usd, avg_vqa_score, report_json_path,
                report_md_path, flags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, flags.get("folder_path", ""), total, passed, warned,
             failed, errored, round(duration, 1), round(api_cost, 4),
             avg_vqa, json_path, md_path, json.dumps(flags)),
        )

        # Insert per-book results
        for diag in diagnostics_list:
            # Get or create book record
            book_id = None
            try:
                book_id = get_or_create_book(
                    diag["filename"],
                    format=diag["format"],
                    file_size_bytes=diag["file_size_bytes"],
                    source_type=diag["source_classification"]["source_type"],
                    chapter_count=diag["structure"]["chapter_count"],
                    word_count=diag["structure"]["word_count"],
                    db_path=db_path,
                )
            except Exception as e:
                logger.debug("Could not create book record: %s", e)

            # Record conversion
            conversion_id = None
            if book_id and diag["extraction"]["success"]:
                try:
                    conversion_id = add_conversion(
                        book_id=book_id,
                        extraction_path=diag["extraction"]["extraction_path"],
                        vqa_score=diag.get("visual_qa", {}).get("score"),
                        duration_seconds=diag["extraction"]["duration_seconds"],
                        api_input_tokens=0,
                        api_output_tokens=0,
                        cost_usd=diag.get("visual_qa", {}).get("api_cost_usd", 0),
                        category_scores=diag.get("visual_qa", {}).get(
                            "category_scores"
                        ),
                        db_path=db_path,
                    )
                except Exception as e:
                    logger.debug("Could not record conversion: %s", e)

            # Record issues
            if book_id and conversion_id:
                for issue in diag["issues"]:
                    try:
                        add_issue(
                            conversion_id=conversion_id,
                            book_id=book_id,
                            category=issue["category"],
                            severity=issue["severity"],
                            description=issue.get("description", ""),
                            db_path=db_path,
                        )
                    except Exception as e:
                        logger.debug("Could not record issue: %s", e)

            # Insert batch_book_results
            conn.execute(
                """INSERT INTO batch_book_results
                   (run_id, book_id, filename, status, status_reason,
                    diagnostics_json, conversion_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, book_id, diag["filename"], diag["overall_status"],
                 diag["status_reason"], json.dumps(diag), conversion_id),
            )

        conn.commit()
        logger.info("Batch results recorded to database")

    except Exception as e:
        logger.error("Database recording failed: %s", e)
        conn.rollback()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Resume support
# ═══════════════════════════════════════════════════════════════════════════

def get_completed_books(run_id, db_path=None):
    """Get list of filenames already processed in an interrupted batch."""
    if not HAS_PATTERN_DB:
        return set()
    ensure_batch_tables(db_path)
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            "SELECT filename FROM batch_book_results WHERE run_id = ?",
            (run_id,),
        )
        return {row["filename"] for row in cursor.fetchall()}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Compare two batch runs
# ═══════════════════════════════════════════════════════════════════════════

def compare_runs(run_id1, run_id2, db_path=None):
    """Compare two batch runs and print a delta summary."""
    json1 = REPORTS_DIR / f"{run_id1}.json"
    json2 = REPORTS_DIR / f"{run_id2}.json"

    if not json1.exists():
        print(f"Report not found: {json1}")
        return
    if not json2.exists():
        print(f"Report not found: {json2}")
        return

    with open(json1, 'r', encoding='utf-8') as f:
        report1 = json.load(f)
    with open(json2, 'r', encoding='utf-8') as f:
        report2 = json.load(f)

    s1 = report1["summary"]
    s2 = report2["summary"]

    print(f"\n{'=' * 60}")
    print(f"  Batch QA Comparison")
    print(f"  Run A: {run_id1}")
    print(f"  Run B: {run_id2}")
    print(f"{'=' * 60}\n")

    def _delta(label, v1, v2, higher_is_better=True):
        diff = v2 - v1
        if diff == 0:
            arrow = "  "
        elif (diff > 0) == higher_is_better:
            arrow = " ↑"
        else:
            arrow = " ↓"
        print(f"  {label:<25} {v1:>6}  →  {v2:>6}  ({diff:+d}{arrow})")

    _delta("Books total", s1["books_total"], s2["books_total"], True)
    _delta("Passed", s1["books_passed"], s2["books_passed"], True)
    _delta("Warnings", s1["books_warned"], s2["books_warned"], False)
    _delta("Failed", s1["books_failed"], s2["books_failed"], False)
    _delta("Errors", s1["books_errored"], s2["books_errored"], False)

    # Pass rate
    rate1 = (s1["books_passed"] / s1["books_total"] * 100
             if s1["books_total"] else 0)
    rate2 = (s2["books_passed"] / s2["books_total"] * 100
             if s2["books_total"] else 0)
    diff = rate2 - rate1
    arrow = " ↑" if diff > 0 else (" ↓" if diff < 0 else "  ")
    print(f"  {'Pass rate':<25} {rate1:>5.1f}%  →  {rate2:>5.1f}%  ({diff:+.1f}%{arrow})")

    # Cluster comparison
    clusters1 = {c["pattern_id"]: c for c in report1.get("failure_clusters", [])}
    clusters2 = {c["pattern_id"]: c for c in report2.get("failure_clusters", [])}
    all_patterns = set(list(clusters1.keys()) + list(clusters2.keys()))

    if all_patterns:
        print(f"\n  {'Failure Pattern':<35} {'Run A':>6}  →  {'Run B':>6}")
        print(f"  {'-' * 55}")
        for pid in sorted(all_patterns):
            c1 = clusters1.get(pid, {}).get("book_count", 0)
            c2 = clusters2.get(pid, {}).get("book_count", 0)
            label = (clusters1.get(pid) or clusters2.get(pid, {})).get("label", pid)
            if len(label) > 33:
                label = label[:30] + "..."
            diff = c2 - c1
            arrow = " ↓" if diff < 0 else (" ↑" if diff > 0 else "  ")
            print(f"  {label:<35} {c1:>6}  →  {c2:>6}  ({diff:+d}{arrow})")

    # Per-book deltas (for books in both runs)
    books1 = {b["filename"]: b for b in report1.get("books", [])}
    books2 = {b["filename"]: b for b in report2.get("books", [])}
    common = set(books1.keys()) & set(books2.keys())

    status_changes = []
    for fn in sorted(common):
        s_old = books1[fn]["overall_status"]
        s_new = books2[fn]["overall_status"]
        if s_old != s_new:
            status_changes.append((fn, s_old, s_new))

    if status_changes:
        print(f"\n  Status changes ({len(status_changes)} books):")
        for fn, old, new in status_changes[:15]:
            short = fn[:40] + "..." if len(fn) > 40 else fn
            print(f"    {short:<45} {old:>5} → {new}")
        if len(status_changes) > 15:
            print(f"    ... and {len(status_changes) - 15} more")

    print(f"\n{'=' * 60}\n")


# ═══════════════════════════════════════════════════════════════════════════
# List past runs
# ═══════════════════════════════════════════════════════════════════════════

def list_past_runs(db_path=None):
    """List all past batch runs from the database."""
    if not HAS_PATTERN_DB:
        # Fallback: list JSON files in reports dir
        if REPORTS_DIR.exists():
            for f in sorted(REPORTS_DIR.glob("batch_*.json"), reverse=True):
                print(f"  {f.stem}")
        return

    ensure_batch_tables(db_path)
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """SELECT run_id, books_total, books_passed, books_warned,
                      books_failed, books_errored, total_duration_seconds,
                      total_api_cost_usd, created_at
               FROM batch_runs ORDER BY created_at DESC LIMIT 20"""
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        print("No batch runs found.")
        return

    print(f"\n{'Run ID':<30} {'Total':>5} {'Pass':>5} {'Warn':>5} "
          f"{'Fail':>5} {'Err':>4} {'Time':>8} {'Cost':>7} {'Date'}")
    print("-" * 100)

    for r in rows:
        dur = r["total_duration_seconds"] or 0
        dur_str = f"{int(dur//60)}m{int(dur%60):02d}s"
        cost = r["total_api_cost_usd"] or 0
        date = (r["created_at"] or "")[:16]
        print(
            f"{r['run_id']:<30} {r['books_total']:>5} {r['books_passed']:>5} "
            f"{r['books_warned']:>5} {r['books_failed']:>5} {r['books_errored']:>4} "
            f"{dur_str:>8} ${cost:>6.2f} {date}"
        )

    print()


# ═══════════════════════════════════════════════════════════════════════════
# Main orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def run_batch(folder_path, quick=True, include_vqa=False, limit=None,
              format_filter=None, parallel=1, resume_run_id=None,
              db_path=None, no_db=False):
    """
    Main batch QA entry point.
    Scans folder, processes each book, analyzes patterns, generates reports.
    """
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        print(f"Error: folder not found: {folder}")
        return None

    # Generate run ID
    if resume_run_id:
        run_id = resume_run_id
        print(f"\nResuming batch run: {run_id}")
    else:
        run_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Create temp output directory for this batch
    batch_output = PROJECT_ROOT / "processing" / "batch_qa" / run_id
    batch_output.mkdir(parents=True, exist_ok=True)

    # Scan folder
    files = scan_folder(folder, format_filter)
    if not files:
        print(f"No supported ebook files found in: {folder}")
        return None

    # Resume: skip already-completed books
    completed = set()
    if resume_run_id:
        completed = get_completed_books(resume_run_id, db_path)
        files = [f for f in files if f.name not in completed]
        print(f"  Already completed: {len(completed)} books")
        print(f"  Remaining: {len(files)} books")

    if limit:
        files = files[:limit]

    total_files = len(files) + len(completed)
    flags = {
        "quick": quick,
        "vqa": include_vqa,
        "limit": limit,
        "format_filter": format_filter,
        "parallel": parallel,
        "folder_path": str(folder),
    }

    print(f"\n{'=' * 60}")
    print(f"  EbookAutomation — Batch QA")
    print(f"  Run ID:  {run_id}")
    print(f"  Folder:  {folder}")
    print(f"  Books:   {len(files)} to process"
          f"{f' ({len(completed)} already done)' if completed else ''}")
    mode = "Quick (HTML extraction only)"
    if not quick:
        mode = "Full (HTML + KFX)"
    if include_vqa:
        mode += " + Visual QA"
    print(f"  Mode:    {mode}")
    if parallel > 1:
        print(f"  Workers: {parallel}")
    print(f"{'=' * 60}\n")

    batch_start = time.time()
    diagnostics_list = []

    # Load any previously completed diagnostics for resume
    if resume_run_id and completed:
        prev_json = REPORTS_DIR / f"{resume_run_id}.json"
        if prev_json.exists():
            with open(prev_json, 'r', encoding='utf-8') as f:
                prev_report = json.load(f)
            diagnostics_list = prev_report.get("books", [])

    def _process_one(idx_file):
        idx, file_path = idx_file
        book_num = idx + len(completed) + 1
        print(f"  [{book_num}/{total_files}] {file_path.name}...",
              flush=True)
        try:
            diag = collect_diagnostics(
                file_path, str(batch_output), run_id,
                quick=quick, include_vqa=include_vqa,
            )
            status = diag["overall_status"]
            ch = diag["structure"]["chapter_count"]
            dur = diag["extraction"]["duration_seconds"]
            issues = len(diag["issues"])
            print(
                f"  [{book_num}/{total_files}] {status}: {file_path.name} "
                f"(ch={ch}, issues={issues}, {dur:.0f}s)"
            )
            return diag
        except Exception as e:
            print(f"  [{book_num}/{total_files}] ERROR: {file_path.name} — {e}")
            return {
                "filename": file_path.name,
                "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
                "format": file_path.suffix.lstrip('.').lower(),
                "batch_run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_classification": {"source_type": "unknown", "confidence": 0,
                                          "strategy_selected": "unknown",
                                          "strategy_source": "error"},
                "extraction": {"success": False, "extraction_path": "error",
                               "duration_seconds": 0, "html_produced": False,
                               "html_size_bytes": 0,
                               "errors": [str(e)], "warnings": []},
                "structure": {"chapter_count": 0, "h1_count": 0, "h2_count": 0,
                              "h3_count": 0, "heading_labels": [],
                              "headings_look_like_backmatter": False,
                              "word_count": 0, "page_count": 0,
                              "has_toc": False, "toc_entries": 0},
                "text_quality": {"ligature_splits": 0, "double_spaces": 0,
                                 "encoding_errors": 0, "standalone_page_numbers": 0,
                                 "blockquotes_detected": 0, "italic_tags": 0,
                                 "bold_tags": 0, "footnotes_linked": 0,
                                 "footnotes_unlinked": 0},
                "kindle_conversion": {"attempted": False, "success": False,
                                      "kfx_size_bytes": 0, "duration_seconds": 0},
                "visual_qa": {"attempted": False, "score": None, "pass_threshold": 70,
                              "passed": False, "category_scores": {},
                              "api_cost_usd": 0, "duration_seconds": 0},
                "issues": [{"category": "uncaught_exception", "severity": "critical",
                            "description": str(e)}],
                "overall_status": "ERROR",
                "status_reason": f"Uncaught exception: {e}",
            }

    # Process books (sequential or parallel)
    indexed_files = list(enumerate(files))

    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(_process_one, item): item
                for item in indexed_files
            }
            for future in as_completed(futures):
                result = future.result()
                diagnostics_list.append(result)
    else:
        for item in indexed_files:
            result = _process_one(item)
            diagnostics_list.append(result)

    # Sort by filename for consistent report ordering
    diagnostics_list.sort(key=lambda d: d["filename"])

    batch_duration = time.time() - batch_start

    # ── Pattern analysis ────────────────────────────────────────
    print(f"\n  Analyzing patterns across {len(diagnostics_list)} books...")
    clusters = analyze_patterns(diagnostics_list)
    observations = detect_correlations(diagnostics_list, clusters)

    # ── Generate reports ────────────────────────────────────────
    json_path = generate_json_report(
        run_id, diagnostics_list, clusters, observations,
        batch_duration, flags,
    )
    md_path = generate_md_report(
        run_id, diagnostics_list, clusters, observations,
        batch_duration, flags,
    )

    # ── Record to database ──────────────────────────────────────
    if not no_db:
        record_batch_to_db(
            run_id, diagnostics_list, batch_duration, flags,
            json_path, md_path, db_path,
        )

    # ── Print summary ───────────────────────────────────────────
    total_count = len(diagnostics_list)
    passed = sum(1 for d in diagnostics_list if d["overall_status"] == "PASS")
    warned = sum(1 for d in diagnostics_list if d["overall_status"] == "WARN")
    failed = sum(1 for d in diagnostics_list if d["overall_status"] == "FAIL")
    errored = sum(1 for d in diagnostics_list if d["overall_status"] == "ERROR")
    dur_min = int(batch_duration // 60)
    dur_sec = int(batch_duration % 60)

    print(f"\n{'=' * 60}")
    print(f"  Batch QA Complete — {run_id}")
    print(f"  Results: {passed} passed, {warned} warnings, "
          f"{failed} failed, {errored} errors  ({total_count} total)")
    rate = passed / total_count * 100 if total_count else 0
    print(f"  Pass rate: {rate:.0f}%")
    print(f"  Duration: {dur_min}m {dur_sec}s")
    if clusters:
        print(f"  Top issue: {clusters[0][1]['pattern']['label']} "
              f"({len(clusters[0][1]['books'])} books)")
    print(f"  Reports:")
    print(f"    JSON: {json_path}")
    print(f"    MD:   {md_path}")
    print(f"{'=' * 60}\n")

    return run_id


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="EbookAutomation — Batch Quality Assurance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/batch_qa.py F:\\TestBooks                     Quick scan
  python tools/batch_qa.py F:\\TestBooks --vqa               Include Visual QA
  python tools/batch_qa.py F:\\TestBooks --limit 10          First 10 books
  python tools/batch_qa.py F:\\TestBooks --parallel 3        3 concurrent workers
  python tools/batch_qa.py list                             List past runs
  python tools/batch_qa.py compare <run1> <run2>            Compare two runs
        """,
    )

    subparsers = parser.add_subparsers(dest="command")

    # ── run (default) ───────────────────────────────────────────
    run_parser = subparsers.add_parser("run", help="Run batch QA on a folder")
    run_parser.add_argument("folder", help="Path to folder containing ebooks")
    run_parser.add_argument(
        "--vqa", action="store_true",
        help="Include Visual QA scoring (requires --vqa approval, ~$0.04/book)"
    )
    run_parser.add_argument(
        "--full", action="store_true",
        help="Full mode: include KFX conversion (default is quick/HTML-only)"
    )
    run_parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of books to process"
    )
    run_parser.add_argument(
        "--format", dest="format_filter", default=None,
        help="Filter by file format (e.g., pdf, epub)"
    )
    run_parser.add_argument(
        "--parallel", type=int, default=1,
        help="Number of concurrent workers (default: 1)"
    )
    run_parser.add_argument(
        "--resume", metavar="RUN_ID", default=None,
        help="Resume an interrupted batch run"
    )
    run_parser.add_argument(
        "--no-db", action="store_true",
        help="Skip writing results to database"
    )
    run_parser.add_argument(
        "--db-path", default=None,
        help="Override database path"
    )

    # ── compare ─────────────────────────────────────────────────
    cmp_parser = subparsers.add_parser(
        "compare", help="Compare two batch runs"
    )
    cmp_parser.add_argument("run_id1", help="First run ID")
    cmp_parser.add_argument("run_id2", help="Second run ID")
    cmp_parser.add_argument("--db-path", default=None)

    # ── list ────────────────────────────────────────────────────
    list_parser = subparsers.add_parser("list", help="List past batch runs")
    list_parser.add_argument("--db-path", default=None)

    # ── report ──────────────────────────────────────────────────
    rpt_parser = subparsers.add_parser(
        "report", help="Regenerate report from saved JSON"
    )
    rpt_parser.add_argument("run_id", help="Run ID to regenerate report for")

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Handle no subcommand — check if first positional looks like a folder
    if args.command is None:
        # Check if there's a positional argument that's a folder path
        remaining = sys.argv[1:]
        if remaining and not remaining[0].startswith('-'):
            potential_folder = remaining[0]
            if os.path.isdir(potential_folder):
                # Treat as: batch_qa.py run <folder> [flags]
                sys.argv.insert(1, "run")
                args = parser.parse_args()
            else:
                parser.print_help()
                return
        else:
            parser.print_help()
            return

    if args.command == "run":
        quick = not args.full
        run_batch(
            folder_path=args.folder,
            quick=quick,
            include_vqa=args.vqa,
            limit=args.limit,
            format_filter=args.format_filter,
            parallel=args.parallel,
            resume_run_id=args.resume,
            db_path=args.db_path,
            no_db=args.no_db,
        )
    elif args.command == "compare":
        compare_runs(args.run_id1, args.run_id2, args.db_path)
    elif args.command == "list":
        list_past_runs(args.db_path)
    elif args.command == "report":
        # Regenerate MD report from existing JSON
        json_path = REPORTS_DIR / f"{args.run_id}.json"
        if not json_path.exists():
            print(f"JSON report not found: {json_path}")
            return
        with open(json_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
        diagnostics_list = report.get("books", [])
        clusters = analyze_patterns(diagnostics_list)
        observations = detect_correlations(diagnostics_list, clusters)
        md_path = generate_md_report(
            args.run_id, diagnostics_list, clusters, observations,
            report["summary"].get("total_duration_seconds", 0),
            report["summary"].get("flags", {}),
        )
        print(f"Report regenerated: {md_path}")


if __name__ == "__main__":
    main()
