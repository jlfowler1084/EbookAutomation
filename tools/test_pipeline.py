"""
Test harness for the pdfminer HTML extraction pipeline.

Runs the PDF -> HTML -> KFX pipeline on validated books and checks expected
properties (heading counts, content presence, formatting quality).

Supports three test sources:
  1. Hardcoded test cases (TEST_CASES dict) — manually curated assertions
  2. Auto-captured baselines (test_cases.json) — snapshot from last good run
  3. Test corpus hot folder (test-corpus/) — drop books for auto-discovery

Usage:
    python tools/test_pipeline.py                     # run all tests
    python tools/test_pipeline.py "Oil Kings"         # run one test
    python tools/test_pipeline.py --quick             # HTML only, skip KFX
    python tools/test_pipeline.py --list              # list test case names
    python tools/test_pipeline.py --recapture "Oil Kings"  # re-capture baseline
    python tools/test_pipeline.py --capture-only "Oil Kings"  # capture without testing
    python tools/test_pipeline.py --corpus            # run ONLY corpus tests
    python tools/test_pipeline.py --corpus "Burge"    # run single corpus book
    python tools/test_pipeline.py --corpus --recapture "Burge"  # re-capture corpus baseline
"""

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
# Allow env-override so worktree sessions can point at the main repo's data dirs
# without creating filesystem junctions (CLAUDE.md 2026-04-22 incident).
ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", PROJECT_ROOT / "archive"))

# Import chapter alignment (non-fatal if unavailable)
try:
    from chapter_alignment import verify_chapter_alignment
    HAS_CHAPTER_ALIGNMENT = True
except ImportError:
    HAS_CHAPTER_ALIGNMENT = False
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "output" / "kindle"))
TEST_CASES_JSON = SCRIPT_DIR / "test_cases.json"
CORPUS_DIR = PROJECT_ROOT / "test-corpus"
CORPUS_EXTENSIONS = {'.pdf', '.epub', '.mobi', '.azw', '.azw3'}
# Formats the harness can currently process (others get SKIP)
SUPPORTED_CORPUS_FORMATS = {'.pdf', '.epub'}

# ── Ligature split patterns (same as _fix_ligature_splits) ──────────────
LIGATURE_SPLIT_RE = re.compile(
    r'\b(?:'
    r'[Tt]h e\b|[Tt]h is\b|[Tt]h at\b|[Tt]h ey\b|[Tt]h en\b|[Tt]h ere\b|'
    r'[Tt]h ose\b|[Tt]h us\b|[Tt]h an\b|[Tt]h eir\b|[Tt]h em\b|[Tt]h ese\b|'
    r'fi [a-z]|fl [a-z]|ffi [a-z]|ffl [a-z]'
    r')'
)

# ═══════════════════════════════════════════════════════════════════════════
# Hardcoded test case definitions
# ═══════════════════════════════════════════════════════════════════════════

TEST_CASES = {
    "Oil Kings": {
        "pdf_pattern": "*Oil*Kings*",
        "pdf_exclude": None,
        "use_pdfminer": True,
        "expected": {
            "kfx_produced": True,
            "min_h1": 5,
            "max_h1": 9,
            "min_h2": 13,
            "min_h3": 50,
            "h1_must_contain": ["GLADIATOR", "SHOWDOWN"],
            "h2_must_contain": ["Introduction", "A KIND OF SUPER MAN"],
            "no_duplicate_h1": True,
            "body_must_contain": ["They came to bury Caesar"],
            "has_front_matter_h1": True,
            "max_ligature_splits": 10,
            "max_double_spaces": 0,
            "min_blockquotes": 2,
            "min_em": 100,
        }
    },
    "Genesis": {
        "pdf_pattern": "*Genesis*",
        "pdf_exclude": None,
        "use_pdfminer": True,
        "expected": {
            "kfx_produced": True,
            "min_h2": 13,
            "h2_must_contain": ["How Should One Read the Early Chapters"],
            "heading_must_not_contain": ["Modem"],
            "body_must_contain": ["Modern"],
            "max_ligature_splits": 5,
            "max_double_spaces": 0,
        }
    },
    "Mexico": {
        "pdf_pattern": "*Mexico*Illicit*",
        "pdf_exclude": None,
        "use_pdfminer": True,
        "expected": {
            "kfx_produced": True,
            "min_h2": 8,
            "h2_must_contain": ["Introduction", "1 The State Reaction"],
            "min_linked_footnotes": 230,
            "max_ligature_splits": 30,
            "max_double_spaces": 0,
            "no_standalone_page_numbers": True,
        }
    },
    "Brother of Jesus": {
        "pdf_pattern": "*Brother*Jesus*",
        "pdf_exclude": None,
        "use_pdfminer": True,
        "expected": {
            "kfx_produced": True,
            "min_h1": 25,
            "max_ligature_splits": 20,
            "min_blockquotes": 5,
        }
    },
    "Dionysius": {
        "pdf_pattern": "*Dionysius*",
        "pdf_exclude": None,
        "use_pdfminer": True,
        "expected": {
            "kfx_produced": True,
            "min_h2": 20,
            "min_blockquotes": 10,
            "min_h3": 20,
        }
    },
    "Ezekiel II": {
        "pdf_pattern": "*Ezekiel*II*",
        "pdf_exclude": None,
        "use_pdfminer": True,   # --html-extraction → routes to PyMuPDF for multi-column
        "expected": {
            "min_h3": 15,            # commentary section headings via font-cluster path
        }
    },
    "Bain Dangerous Book": {
        "pdf_pattern": "*Bain*Dangerous*",
        "pdf_exclude": None,
        "use_pdfminer": True,
        "expected": {
            "kfx_produced": False,   # HTML-only validation, skip KFX for speed
            "min_h2": 10,            # actual=76; conservative floor to catch catastrophic regression
        }
    },
    "Codex Magica": {
        "pdf_pattern": "*Codex*Magica*",
        "pdf_exclude": None,
        "use_pdfminer": True,
        "expected": {
            "kfx_produced": False,   # HTML-only validation, skip KFX for speed
            "min_h2": 8,             # actual=18; conservative floor to catch pattern promotion regression
        }
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Auto-capture: extract baseline from HTML
# ═══════════════════════════════════════════════════════════════════════════

def extract_baseline_from_html(html, kfx_path=None):
    """Extract all verifiable properties from HTML output as a baseline snapshot."""
    all_headings = re.findall(r'<(h[123])(?:\s[^>]*)?>(.+?)</\1>', html)
    h1_list = [text for tag, text in all_headings if tag == 'h1']
    h2_list = [text for tag, text in all_headings if tag == 'h2']
    h3_list = [text for tag, text in all_headings if tag == 'h3']

    body_text = re.sub(r'<[^>]+>', ' ', html)
    body_text = re.sub(r'\s+', ' ', body_text)

    linked = len(re.findall(r'<sup><a\s+id="noteref_', html))
    unlinked = len(re.findall(r'<sup>\d+</sup>', html))
    blockquotes = len(re.findall(r'<blockquote>', html))
    em_count = len(re.findall(r'<em>', html))
    attributions = len(re.findall(r'class="attribution"', html))
    ligature_splits = len(LIGATURE_SPLIT_RE.findall(body_text))
    text_only = re.sub(r'<[^>]+>', '', html)
    double_spaces = len(re.findall(r'  ', text_only))
    standalone_pages = len(re.findall(r'<p>\d{1,3}</p>', html))
    has_front_matter = any("front matter" in h.lower() for h in h1_list)

    # Chapter openings: first 60 chars of body text after each h2
    chapter_openings = {}
    for m in re.finditer(r'<h2(?:\s[^>]*)?>(.*?)</h2>', html):
        heading_text = m.group(1)
        after = html[m.end():]
        # Find first <p> after this heading
        p_match = re.search(r'<p>(.*?)</p>', after)
        if p_match:
            opener = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()[:60]
            if opener:
                chapter_openings[heading_text] = opener

    baseline = {
        "h1_count": len(h1_list),
        "h2_count": len(h2_list),
        "h3_count": len(h3_list),
        "h1_headings": h1_list,
        "h2_headings": h2_list,
        "linked_footnotes": linked,
        "unlinked_footnotes": unlinked,
        "blockquotes": blockquotes,
        "em_tags": em_count,
        "attributions": attributions,
        "ligature_splits_remaining": ligature_splits,
        "double_spaces": double_spaces,
        "standalone_page_numbers": standalone_pages,
        "has_front_matter_h1": has_front_matter,
        "chapter_openings": chapter_openings,
    }

    if kfx_path and os.path.isfile(kfx_path):
        baseline["kfx_size_kb"] = int(os.path.getsize(kfx_path) / 1024)

    return baseline


def load_captured_cases():
    """Load auto-captured test cases from test_cases.json."""
    if TEST_CASES_JSON.is_file():
        with open(TEST_CASES_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_captured_cases(cases):
    """Save auto-captured test cases to test_cases.json."""
    with open(TEST_CASES_JSON, 'w', encoding='utf-8') as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)


def capture_baseline(name, pdf_pattern, html, kfx_path=None, pdf_path=None, html_path=None):
    """Capture a baseline for a book and save to test_cases.json."""
    cases = load_captured_cases()
    baseline = extract_baseline_from_html(html, kfx_path)

    # Capture alignment data if source PDF is available
    if HAS_CHAPTER_ALIGNMENT and pdf_path and html_path:
        try:
            alignment = verify_chapter_alignment(
                pdf_path, html_path, log=lambda msg: None
            )
            if alignment.get('alignment_score') is not None:
                baseline['alignment_score'] = alignment['alignment_score']
                baseline['aligned_chapters'] = alignment['summary']['aligned']
                baseline['total_bookmarks'] = alignment['total_bookmarks']
        except Exception:
            pass

    cases[name] = {
        "pdf_pattern": pdf_pattern,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "baseline": baseline,
    }

    save_captured_cases(cases)
    b = baseline
    print(f"  Test case auto-captured for '{name}' "
          f"({b['h2_count']} h2, {b['linked_footnotes']} footnotes, {b['h3_count']} h3)")
    return baseline


def validate_against_baseline(html, baseline, kfx_path=None):
    """Compare current HTML output against a saved baseline. Returns (passes, failures)."""
    passes = []
    failures = []
    current = extract_baseline_from_html(html, kfx_path)

    # Heading counts within tolerance of +/- 2
    for key in ['h1_count', 'h2_count', 'h3_count']:
        expected = baseline[key]
        actual = current[key]
        if abs(actual - expected) <= 2:
            passes.append(f"{key} = {actual} (baseline {expected}, +/-2)")
        else:
            failures.append(f"{key} = {actual} -- baseline {expected} (tolerance +/-2)")

    # h2_headings list should be identical
    if baseline.get('h2_headings') and current.get('h2_headings'):
        if baseline['h2_headings'] == current['h2_headings']:
            passes.append(f"h2_headings identical ({len(current['h2_headings'])} entries)")
        else:
            # Show diff
            expected_set = set(baseline['h2_headings'])
            actual_set = set(current['h2_headings'])
            missing = expected_set - actual_set
            added = actual_set - expected_set
            parts = []
            if missing:
                parts.append(f"missing: {list(missing)[:3]}")
            if added:
                parts.append(f"added: {list(added)[:3]}")
            failures.append(f"h2_headings differ -- {'; '.join(parts)}")

    # Linked footnotes should be >= baseline (fixes improve, not regress)
    if baseline.get('linked_footnotes', 0) > 0:
        if current['linked_footnotes'] >= baseline['linked_footnotes']:
            passes.append(f"linked_footnotes >= {baseline['linked_footnotes']} "
                         f"(got {current['linked_footnotes']})")
        else:
            failures.append(f"linked_footnotes regression: {current['linked_footnotes']} "
                          f"< baseline {baseline['linked_footnotes']}")

    # Ligature splits should be <= baseline
    if current['ligature_splits_remaining'] <= baseline.get('ligature_splits_remaining', 999):
        passes.append(f"ligature_splits <= {baseline.get('ligature_splits_remaining', 'N/A')} "
                     f"(got {current['ligature_splits_remaining']})")
    else:
        failures.append(f"ligature_splits regression: {current['ligature_splits_remaining']} "
                      f"> baseline {baseline.get('ligature_splits_remaining')}")

    # Double spaces should be <= baseline
    if current['double_spaces'] <= baseline.get('double_spaces', 0):
        passes.append(f"double_spaces <= {baseline.get('double_spaces', 0)} "
                     f"(got {current['double_spaces']})")
    else:
        failures.append(f"double_spaces regression: {current['double_spaces']} "
                      f"> baseline {baseline.get('double_spaces')}")

    # Chapter openings must match (content alignment)
    if baseline.get('chapter_openings'):
        matched = 0
        total = 0
        for heading, expected_opener in baseline['chapter_openings'].items():
            actual_opener = current.get('chapter_openings', {}).get(heading, '')
            if actual_opener:
                total += 1
                # Compare first 40 chars for fuzzy match
                if expected_opener[:40] == actual_opener[:40]:
                    matched += 1
                else:
                    failures.append(f'chapter opening "{heading[:30]}": '
                                  f'expected "{expected_opener[:40]}" '
                                  f'got "{actual_opener[:40]}"')
        if total > 0 and matched == total:
            passes.append(f"chapter_openings: all {matched} matched")
        elif matched > 0:
            passes.append(f"chapter_openings: {matched}/{total} matched")

    # KFX size within 10% of baseline
    if baseline.get('kfx_size_kb') and kfx_path and os.path.isfile(kfx_path):
        actual_kb = int(os.path.getsize(kfx_path) / 1024)
        expected_kb = baseline['kfx_size_kb']
        pct = abs(actual_kb - expected_kb) / max(expected_kb, 1) * 100
        if pct <= 10:
            passes.append(f"kfx_size within 10% ({actual_kb} KB vs baseline {expected_kb} KB)")
        else:
            failures.append(f"kfx_size off by {pct:.0f}%: {actual_kb} KB vs baseline {expected_kb} KB")

    return passes, failures


# ═══════════════════════════════════════════════════════════════════════════
# Test corpus (hot folder) discovery
# ═══════════════════════════════════════════════════════════════════════════

def file_sha256(path):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def discover_corpus_books():
    """Scan test-corpus/ for supported ebook files. Returns list of Path objects."""
    if not CORPUS_DIR.is_dir():
        return []
    books = []
    for ext in CORPUS_EXTENSIONS:
        books.extend(CORPUS_DIR.glob(f"*{ext}"))
    # Deduplicate and sort by stem
    books = sorted(set(books), key=lambda p: p.stem.lower())
    return books


def load_corpus_baseline(book_path):
    """Load the baseline sidecar for a corpus book, or None if missing."""
    baseline_path = book_path.with_suffix('.baseline.json')
    if baseline_path.is_file():
        with open(baseline_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_corpus_baseline(book_path, baseline_data):
    """Save baseline sidecar JSON next to the corpus book."""
    baseline_path = book_path.with_suffix('.baseline.json')
    with open(baseline_path, 'w', encoding='utf-8') as f:
        json.dump(baseline_data, f, indent=2, ensure_ascii=False)


def load_corpus_expectations(book_path):
    """Load manual override expectations from <stem>.expect.json, or None."""
    expect_path = book_path.with_suffix('.expect.json')
    if expect_path.is_file():
        with open(expect_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def detect_extraction_path(stdout, stderr):
    """Detect which extraction path was used from pipeline output."""
    combined = (stdout or '') + '\n' + (stderr or '')
    if 'column' in combined.lower() and 'pymupdf' in combined.lower():
        return 'pymupdf'
    if 'pdfminer' in combined.lower() or 'html-extraction' in combined.lower():
        return 'pdfminer'
    if 'pypdf' in combined.lower():
        return 'pypdf'
    return 'unknown'


def run_corpus_extraction(book_path, test_name="corpus"):
    """Run extraction for a corpus book. Supports PDF and EPUB."""
    ext = book_path.suffix.lower()
    if ext == '.pdf':
        return run_extraction(str(book_path), use_pdfminer=True, test_name=test_name)
    elif ext == '.epub':
        return run_extraction(str(book_path), use_pdfminer=True, test_name=test_name)
    else:
        return None, "", f"Unsupported format: {ext}"


def capture_corpus_baseline(book_path, quick=False):
    """Run extraction on a corpus book and capture its baseline sidecar."""
    stem = book_path.stem
    ext = book_path.suffix.lower()

    print(f"  Extracting: {stem}...", end="", flush=True)
    html_path, stdout, stderr = run_corpus_extraction(book_path, test_name=stem)
    if not html_path or not os.path.isfile(html_path):
        print(f"\r  ERROR: HTML not produced for {stem}")
        return None

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    kfx_path = None
    if not quick and ext == '.pdf':
        ps_stdout, ps_stderr = run_kfx_conversion(str(book_path))
        kfx_match = re.search(r'done -> (.+\.kfx)', ps_stdout + ps_stderr)
        if kfx_match:
            kfx_path = kfx_match.group(1)

    baseline = extract_baseline_from_html(html, kfx_path)
    extraction_path = detect_extraction_path(stdout, stderr)

    sidecar = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_file": book_path.name,
        "source_format": ext.lstrip('.'),
        "extraction_path": extraction_path,
        "file_size_bytes": book_path.stat().st_size,
        "file_hash_sha256": file_sha256(book_path),
        "baseline": baseline,
    }

    save_corpus_baseline(book_path, sidecar)
    b = baseline
    print(f"\r  NEW BASELINE CAPTURED: {stem} "
          f"(h2={b['h2_count']}, fn={b['linked_footnotes']}, h3={b['h3_count']}, "
          f"path={extraction_path})")
    return sidecar


def run_corpus_test(book_path, quick=False):
    """Run a corpus book against its baseline or expectations. Returns (passed, passes, failures, elapsed)."""
    t0 = time.time()
    stem = book_path.stem
    ext = book_path.suffix.lower()

    if ext not in SUPPORTED_CORPUS_FORMATS:
        msg = f"SKIP: {stem} -- {ext} conversion not yet supported in test harness"
        return None, [], [msg], time.time() - t0

    # Check for manual expectations
    expectations = load_corpus_expectations(book_path)

    # Check for existing baseline
    sidecar = load_corpus_baseline(book_path)

    # Warn if source file changed since baseline was captured
    if sidecar:
        current_hash = file_sha256(book_path)
        if current_hash != sidecar.get('file_hash_sha256'):
            print(f"  WARNING: {stem} source file has changed since baseline was captured!")

    # Run extraction
    html_path, stdout, stderr = run_corpus_extraction(book_path, test_name=stem)
    if not html_path or not os.path.isfile(html_path):
        return False, [], ["HTML file not produced"], time.time() - t0

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    kfx_path = None
    if not quick and ext == '.pdf':
        ps_stdout, ps_stderr = run_kfx_conversion(str(book_path))
        kfx_match = re.search(r'done -> (.+\.kfx)', ps_stdout + ps_stderr)
        if kfx_match:
            kfx_path = kfx_match.group(1)

    all_passes = []
    all_failures = []

    # If manual expectations exist, validate against them (like hardcoded tests)
    if expectations:
        passes, failures = validate_html(html, expectations, stdout)
        all_passes.extend(passes)
        all_failures.extend(failures)

    # If baseline exists, also validate against baseline
    if sidecar and sidecar.get('baseline'):
        passes, failures = validate_against_baseline(html, sidecar['baseline'], kfx_path)
        all_passes.extend(passes)
        all_failures.extend(failures)

    # If neither exists, this is first run — capture baseline
    if not sidecar and not expectations:
        capture_corpus_baseline(book_path, quick)
        elapsed = time.time() - t0
        return True, ["baseline captured"], [], elapsed

    elapsed = time.time() - t0
    passed = len(all_failures) == 0
    return passed, all_passes, all_failures, elapsed


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline runner
# ═══════════════════════════════════════════════════════════════════════════

def find_pdf(pattern, exclude=None):
    """Find a PDF in the archive matching the glob pattern."""
    matches = list(ARCHIVE_DIR.glob(pattern + ".pdf"))
    if not matches:
        matches = list(ARCHIVE_DIR.glob(pattern))
    if exclude:
        matches = [m for m in matches if exclude not in m.name]
    if not matches:
        return None
    return str(matches[0])


def run_extraction(pdf_path, use_pdfminer=True, test_name="test"):
    """Run the Python extraction pipeline and return the HTML output path."""
    suffix = f"_test_{test_name.replace(' ', '_').lower()}.txt"
    cmd = [
        sys.executable, str(SCRIPT_DIR / "pdf_to_balabolka.py"),
        "--input", pdf_path,
        "--mode", "kindle",
        "--output-dir", str(OUTPUT_DIR),
        "--suffix", suffix,
    ]
    if use_pdfminer:
        cmd.append("--html-extraction")

    # Scale timeout based on file size (matches batch_qa.py pattern from EB-83)
    # Base 900s (generous for post-processing) + 15s per MB over 20MB
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    timeout = max(900, 900 + int((file_size_mb - 20) * 15)) if file_size_mb > 20 else 900

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "", f"TIMEOUT: extraction exceeded {timeout}s for {Path(pdf_path).name}"

    # Find the HTML file that was produced
    base = Path(pdf_path).stem
    safe = re.sub(r'[^\w\-.]', '_', base)
    html_pattern = str(OUTPUT_DIR / f"*{safe[:40]}*test*.html")
    html_files = sorted(glob.glob(html_pattern), key=os.path.getmtime)
    if not html_files:
        # Broader search
        html_files = sorted(
            [f for f in glob.glob(str(OUTPUT_DIR / "*.html"))
             if "test_" + test_name.replace(' ', '_').lower() in f.lower()],
            key=os.path.getmtime
        )
    html_path = html_files[-1] if html_files else None
    return html_path, result.stdout, result.stderr


def run_kfx_conversion(pdf_path):
    """Run the full Convert-ToKindle PowerShell pipeline including KFX."""
    ps_cmd = (
        f'Import-Module "{PROJECT_ROOT / "module" / "EbookAutomation.psd1"}" -Force; '
        f'Convert-ToKindle -InputFile "{pdf_path}" -UsePdfminer'
    )
    # Scale timeout based on file size (matches batch_qa.py pattern from EB-83)
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    timeout = max(900, 900 + int((file_size_mb - 20) * 15)) if file_size_mb > 20 else 900

    try:
        # pwsh (PS 7): PS 5.1 default execution policy blocks Import-Module
        result = subprocess.run(
            ["pwsh", "-Command", ps_cmd],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return "", f"TIMEOUT: KFX conversion exceeded {timeout}s for {Path(pdf_path).name}"

    return result.stdout, result.stderr


# ═══════════════════════════════════════════════════════════════════════════
# TTS output validation (EB-81)
# ═══════════════════════════════════════════════════════════════════════════

def check_no_standalone_silence_tags(txt_content):
    """Validate that no line in TTS output is a standalone silence tag.

    Balcon.exe only processes SAPI XML when inline with speakable text.
    Standalone silence/pause tags on their own line produce zero audio.
    """
    issues = []
    for i, line in enumerate(txt_content.split('\n')):
        stripped = line.strip()
        if re.match(r'^<silence\s+msec="\d+"\s*/>\s*$', stripped):
            issues.append(f"Line {i+1}: standalone silence tag: {stripped}")
        if re.match(r'^\{\{Pause=\d+\}\}\s*$', stripped):
            issues.append(f"Line {i+1}: standalone pause tag: {stripped}")
    return issues


# ═══════════════════════════════════════════════════════════════════════════
# Validation checks (hardcoded test cases)
# ═══════════════════════════════════════════════════════════════════════════

def validate_html(html, expected, pipeline_stdout=""):
    """Run all expected checks against the HTML content. Returns (passes, failures)."""
    passes = []
    failures = []

    # Parse heading structure
    all_headings = re.findall(r'<(h[123])(?:\s[^>]*)?>(.+?)</\1>', html)
    h1_list = [text for tag, text in all_headings if tag == 'h1']
    h2_list = [text for tag, text in all_headings if tag == 'h2']
    h3_list = [text for tag, text in all_headings if tag == 'h3']

    # Strip HTML from body for content checks
    body_text = re.sub(r'<[^>]+>', ' ', html)
    body_text = re.sub(r'\s+', ' ', body_text)

    # ── Heading count checks ──
    for level, hlist, label in [('h1', h1_list, 'h1'), ('h2', h2_list, 'h2'),
                                 ('h3', h3_list, 'h3')]:
        min_key = f"min_{label}"
        max_key = f"max_{label}"
        if min_key in expected:
            if len(hlist) >= expected[min_key]:
                passes.append(f"{min_key} >= {expected[min_key]} (got {len(hlist)})")
            else:
                failures.append(f"{min_key} >= {expected[min_key]} -- got {len(hlist)}")
        if max_key in expected:
            if len(hlist) <= expected[max_key]:
                passes.append(f"{max_key} <= {expected[max_key]} (got {len(hlist)})")
            else:
                failures.append(f"{max_key} <= {expected[max_key]} -- got {len(hlist)}")

    # ── h1_must_contain / h2_must_contain ──
    for level_key, hlist in [("h1_must_contain", h1_list), ("h2_must_contain", h2_list)]:
        if level_key in expected:
            for required in expected[level_key]:
                found = any(required.lower() in h.lower() for h in hlist)
                if found:
                    passes.append(f'{level_key} "{required}"')
                else:
                    failures.append(f'{level_key} "{required}" -- not found in {level_key.split("_")[0]} list')

    # ── heading_must_not_contain ──
    if "heading_must_not_contain" in expected:
        all_heading_text = ' '.join(text for _, text in all_headings)
        for banned in expected["heading_must_not_contain"]:
            if banned in all_heading_text:
                failures.append(f'heading_must_not_contain "{banned}" -- found in headings')
            else:
                passes.append(f'heading_must_not_contain "{banned}"')

    # ── no_duplicate_h1 / no_duplicate_h2 ──
    for dup_key, dup_list in [("no_duplicate_h1", h1_list), ("no_duplicate_h2", h2_list)]:
        if expected.get(dup_key):
            normalized = [re.sub(r'\s+', ' ', h.strip().lower()) for h in dup_list]
            dupes = [h for h in set(normalized) if normalized.count(h) > 1]
            if not dupes:
                passes.append(dup_key)
            else:
                failures.append(f"{dup_key} -- duplicates: {dupes[:3]}")

    # ── body_must_contain ──
    if "body_must_contain" in expected:
        for phrase in expected["body_must_contain"]:
            if phrase in body_text:
                passes.append(f'body_must_contain "{phrase[:40]}"')
            else:
                failures.append(f'body_must_contain "{phrase[:40]}" -- not found')

    # ── start_reading_contains ──
    if "start_reading_contains" in expected:
        target = expected["start_reading_contains"]
        if re.search(r'start.reading.at.*' + re.escape(target), pipeline_stdout, re.I):
            passes.append(f'start_reading_contains "{target}"')
        else:
            if any(target.lower() in h.lower() for h in h2_list):
                passes.append(f'start_reading_contains "{target}" (in h2 list)')
            else:
                failures.append(f'start_reading_contains "{target}" -- not in pipeline output')

    # ── Front matter h1 ──
    if expected.get("no_front_matter_h1"):
        if not any("front matter" in h.lower() for h in h1_list):
            passes.append("no_front_matter_h1")
        else:
            failures.append("no_front_matter_h1 -- 'Front Matter' h1 found")
    if expected.get("has_front_matter_h1"):
        if any("front matter" in h.lower() for h in h1_list):
            passes.append("has_front_matter_h1")
        else:
            failures.append("has_front_matter_h1 -- 'Front Matter' h1 not found")

    # ── Ligature splits ──
    if "max_ligature_splits" in expected:
        splits = LIGATURE_SPLIT_RE.findall(body_text)
        max_allowed = expected["max_ligature_splits"]
        if len(splits) <= max_allowed:
            passes.append(f"max_ligature_splits <= {max_allowed} (got {len(splits)})")
        else:
            samples = splits[:5]
            failures.append(f"max_ligature_splits <= {max_allowed} -- got {len(splits)}: {samples}")

    # ── Double spaces ──
    if "max_double_spaces" in expected:
        text_only = re.sub(r'<[^>]+>', '', html)
        double_count = len(re.findall(r'  ', text_only))
        max_allowed = expected["max_double_spaces"]
        if double_count <= max_allowed:
            passes.append(f"max_double_spaces <= {max_allowed} (got {double_count})")
        else:
            failures.append(f"max_double_spaces <= {max_allowed} -- got {double_count}")

    # ── Blockquotes ──
    if "min_blockquotes" in expected:
        bq_count = len(re.findall(r'<blockquote>', html))
        if bq_count >= expected["min_blockquotes"]:
            passes.append(f"min_blockquotes >= {expected['min_blockquotes']} (got {bq_count})")
        else:
            failures.append(f"min_blockquotes >= {expected['min_blockquotes']} -- got {bq_count}")

    # ── Em tags ──
    if "min_em" in expected:
        em_count = len(re.findall(r'<em>', html))
        if em_count >= expected["min_em"]:
            passes.append(f"min_em >= {expected['min_em']} (got {em_count})")
        else:
            failures.append(f"min_em >= {expected['min_em']} -- got {em_count}")

    # ── Linked footnotes ──
    if "min_linked_footnotes" in expected:
        linked = len(re.findall(r'<sup><a\s+id="noteref_', html))
        if linked >= expected["min_linked_footnotes"]:
            passes.append(f"min_linked_footnotes >= {expected['min_linked_footnotes']} (got {linked})")
        else:
            failures.append(
                f"min_linked_footnotes >= {expected['min_linked_footnotes']} -- got {linked}")

    # ── No standalone page numbers ──
    if expected.get("no_standalone_page_numbers"):
        standalone = re.findall(r'<p>\d{1,3}</p>', html)
        if not standalone:
            passes.append("no_standalone_page_numbers")
        else:
            failures.append(
                f"no_standalone_page_numbers -- found {len(standalone)}: {standalone[:3]}")

    return passes, failures


# ═══════════════════════════════════════════════════════════════════════════
# Chapter alignment check (appends to existing passes/failures)
# ═══════════════════════════════════════════════════════════════════════════

def run_alignment_check(pdf_path, html_path, passes, failures):
    """Run chapter alignment verification if available. Appends to passes/failures.

    Alignment is warn-only (never causes a test failure) because many books have
    deeply nested bookmarks that don't map to output headings. The data is
    informational — regressions are caught by the baseline's chapter_openings check.
    """
    if not HAS_CHAPTER_ALIGNMENT:
        return
    if not pdf_path or not html_path:
        return
    try:
        alignment = verify_chapter_alignment(
            pdf_path, html_path,
            log=lambda msg: None,  # silent
        )
        if alignment.get('skipped') or alignment.get('error'):
            reason = alignment.get('reason') or alignment.get('error', 'unknown')
            passes.append(f"chapter_alignment: skipped ({reason})")
            return
        score = alignment.get('alignment_score')
        if score is None:
            passes.append(f"chapter_alignment: skipped (no bookmarks)")
            return
        summary = alignment.get('summary', {})
        aligned = summary.get('aligned', 0)
        total = alignment.get('total_bookmarks', 0)
        if score >= 70:
            passes.append(f"chapter_alignment: {score}% ({aligned}/{total} aligned)")
        else:
            detail_parts = []
            if summary.get('misaligned'):
                detail_parts.append(f"{summary['misaligned']} misaligned")
            if summary.get('unmatched'):
                detail_parts.append(f"{summary['unmatched']} unmatched")
            # Warn-only: low alignment is informational, not a test failure
            passes.append(
                f"chapter_alignment: {score}% ({aligned}/{total}) — "
                f"warn: {', '.join(detail_parts)}"
            )
    except Exception as e:
        passes.append(f"chapter_alignment: skipped ({e})")


# ═══════════════════════════════════════════════════════════════════════════
# Test runner
# ═══════════════════════════════════════════════════════════════════════════

def run_test(name, case, quick=False):
    """Run a single test case. Returns (passed, passes, failures, elapsed)."""
    t0 = time.time()
    pdf_path = find_pdf(case["pdf_pattern"], case.get("pdf_exclude"))
    if not pdf_path:
        return False, [], [f"PDF not found: {case['pdf_pattern']}"], time.time() - t0

    expected = case["expected"]

    if quick:
        html_path, stdout, stderr = run_extraction(
            pdf_path, case.get("use_pdfminer", True), name
        )
        if not html_path or not os.path.isfile(html_path):
            return False, [], ["HTML file not produced"], time.time() - t0

        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        passes, failures = validate_html(html, expected, stdout)

        if "kfx_produced" in expected:
            passes.append("kfx_produced (skipped in --quick mode)")

    else:
        stdout, stderr = run_kfx_conversion(pdf_path)
        pipeline_output = stdout + "\n" + stderr

        html_path, py_stdout, py_stderr = run_extraction(
            pdf_path, case.get("use_pdfminer", True), name
        )
        if not html_path or not os.path.isfile(html_path):
            return False, [], ["HTML file not produced"], time.time() - t0

        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        passes, failures = validate_html(html, expected, pipeline_output)

        if expected.get("kfx_produced"):
            if "SUCCESS" in pipeline_output and ".kfx" in pipeline_output:
                kfx_match = re.search(r'done -> (.+\.kfx)', pipeline_output)
                if kfx_match and os.path.isfile(kfx_match.group(1)):
                    size_mb = os.path.getsize(kfx_match.group(1)) / (1024 * 1024)
                    passes.append(f"kfx_produced ({size_mb:.1f} MB)")
                else:
                    failures.append("kfx_produced -- SUCCESS logged but KFX file not found")
            else:
                failures.append("kfx_produced -- no SUCCESS in pipeline output")

    # Chapter alignment check (non-blocking)
    run_alignment_check(pdf_path, html_path, passes, failures)

    elapsed = time.time() - t0
    passed = len(failures) == 0
    return passed, passes, failures, elapsed


def run_baseline_test(name, captured_case, quick=False):
    """Run a test against an auto-captured baseline. Returns (passed, passes, failures, elapsed)."""
    t0 = time.time()
    pdf_path = find_pdf(captured_case["pdf_pattern"])
    if not pdf_path:
        return False, [], [f"PDF not found: {captured_case['pdf_pattern']}"], time.time() - t0

    html_path, stdout, stderr = run_extraction(pdf_path, True, name)
    if not html_path or not os.path.isfile(html_path):
        return False, [], ["HTML file not produced"], time.time() - t0

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    kfx_path = None
    if not quick:
        ps_stdout, ps_stderr = run_kfx_conversion(pdf_path)
        kfx_match = re.search(r'done -> (.+\.kfx)', ps_stdout + ps_stderr)
        if kfx_match:
            kfx_path = kfx_match.group(1)

    passes, failures = validate_against_baseline(html, captured_case["baseline"], kfx_path)

    # Chapter alignment check (non-blocking)
    run_alignment_check(pdf_path, html_path, passes, failures)

    elapsed = time.time() - t0
    passed = len(failures) == 0
    return passed, passes, failures, elapsed


def do_capture(name, pdf_pattern, quick=False):
    """Run extraction and capture a baseline for the given book."""
    pdf_path = find_pdf(pdf_pattern)
    if not pdf_path:
        print(f"  ERROR: PDF not found for pattern: {pdf_pattern}")
        return None

    print(f"  Extracting: {name}...", end="", flush=True)
    html_path, stdout, stderr = run_extraction(pdf_path, True, name)
    if not html_path or not os.path.isfile(html_path):
        print(f"\r  ERROR: HTML not produced for {name}")
        return None

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    kfx_path = None
    if not quick:
        ps_stdout, ps_stderr = run_kfx_conversion(pdf_path)
        kfx_match = re.search(r'done -> (.+\.kfx)', ps_stdout + ps_stderr)
        if kfx_match:
            kfx_path = kfx_match.group(1)

    print(f"\r  Capturing baseline for {name}...")
    baseline = capture_baseline(name, pdf_pattern, html, kfx_path,
                                pdf_path=pdf_path, html_path=html_path)
    return baseline


# ═══════════════════════════════════════════════════════════════════════════
# Filter content tests (unit + integration)
# ═══════════════════════════════════════════════════════════════════════════

TEST_FILTER_HTML = (
    '<html><body>'
    '<h1>Foreword</h1>'
    '<p>This is the foreword text.</p>'
    '<h1>Chapter 1: The Beginning</h1>'
    '<p>Body text with a footnote<sup><a href="#endnote_1">1</a></sup> reference.</p>'
    '<p>More body text with <a href="http://example.com">a hyperlink</a>.</p>'
    '<blockquote><p>A quoted passage.</p></blockquote>'
    '<figure><img src="figure1.png" alt="Figure 1"/><figcaption>Figure 1</figcaption></figure>'
    '<h1>Chapter 2: The Middle</h1>'
    '<p>More chapter content here.</p>'
    '<h2>Notes</h2>'
    '<p><a id="endnote_1">1.</a> This is a footnote.</p>'
    '<h2>Bibliography</h2>'
    '<p>Author, A. (2020). Book Title. Publisher.</p>'
    '<h2>Index</h2>'
    '<p>Abraham, 12, 45, 67</p>'
    '<p>Moses, 23, 89, 112</p>'
    '</body></html>'
)


def run_filter_tests(quick=False):
    """Run unit tests for filter_content.py profiles and individual filters.

    Returns list of (name, passed, passes, failures, elapsed).
    """
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from filter_content import filter_html_with_report

    results = []

    def _run(name, fn):
        t0 = time.time()
        passes, failures = [], []
        try:
            fn(passes, failures)
        except Exception as e:
            failures.append(f"Exception: {e}")
        elapsed = round(time.time() - t0, 3)
        results.append((name, len(failures) == 0, passes, failures, elapsed))

    # ── Profile tests ───────────────────────────────────────────────────

    def test_full_profile(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, profile='full')
        (P if result == TEST_FILTER_HTML else F).append(
            "full profile: output == input (no changes)")
        (P if report['size_reduction_percent'] == 0 else F).append(
            "full profile: 0% size reduction")
        (P if not report['removed'] else F).append(
            "full profile: empty removed dict")

    def test_clean_read_profile(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, profile='clean-read')
        (P if 'Chapter 1' in result else F).append("clean-read: Chapter 1 preserved")
        (P if 'Body text' in result else F).append("clean-read: body text preserved")
        (P if 'Foreword' not in result else F).append("clean-read: Foreword stripped")
        (P if '<a href=' not in result else F).append("clean-read: hyperlinks stripped")
        (P if 'a hyperlink' in result else F).append("clean-read: link text preserved")
        (P if '<sup>' not in result else F).append("clean-read: footnote <sup> stripped")
        (P if 'Abraham' not in result else F).append("clean-read: index entries stripped")
        (P if 'Bibliography' not in result else F).append("clean-read: Bibliography stripped")
        (P if '<blockquote' in result else F).append("clean-read: blockquotes preserved")
        (P if '<img' in result else F).append("clean-read: images preserved")
        (P if report['size_reduction_percent'] > 0 else F).append(
            f"clean-read: size reduced ({report['size_reduction_percent']}%)")

    def test_text_only_profile(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, profile='text-only')
        (P if 'Chapter 1' in result else F).append("text-only: Chapter 1 preserved")
        (P if 'Body text' in result else F).append("text-only: body text preserved")
        (P if 'Foreword' not in result else F).append("text-only: Foreword stripped")
        (P if '<blockquote' not in result else F).append("text-only: blockquotes stripped")
        (P if '<img' not in result else F).append("text-only: images stripped")
        (P if 'Bibliography' not in result else F).append("text-only: Bibliography stripped")
        _, cr_report = filter_html_with_report(TEST_FILTER_HTML, profile='clean-read')
        (P if report['size_reduction_percent'] > cr_report['size_reduction_percent'] else F).append(
            "text-only: strips more than clean-read")

    # ── Individual filter tests ─────────────────────────────────────────

    def test_no_footnotes(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_footnotes=True)
        (P if '<sup>' not in result else F).append("no_footnotes: <sup> markers removed")
        (P if 'endnote_1' not in result else F).append("no_footnotes: endnote section removed")
        (P if 'Chapter 1' in result else F).append("no_footnotes: chapters preserved")
        (P if report['removed'].get('footnotes', 0) > 0 else F).append(
            f"no_footnotes: report count = {report['removed'].get('footnotes', 0)}")

    def test_no_index(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_index=True)
        (P if 'Abraham' not in result else F).append("no_index: Abraham entry removed")
        (P if 'Moses' not in result else F).append("no_index: Moses entry removed")
        (P if 'Chapter 1' in result else F).append("no_index: chapters preserved")
        (P if report['removed'].get('index_sections', 0) > 0 else F).append(
            "no_index: report shows sections removed")

    def test_no_hyperlinks(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_hyperlinks=True)
        (P if '<a href=' not in result else F).append("no_hyperlinks: <a href> removed")
        (P if 'a hyperlink' in result else F).append("no_hyperlinks: link text preserved")
        (P if report['removed'].get('hyperlinks', 0) > 0 else F).append(
            "no_hyperlinks: report shows links removed")

    def test_no_front_matter(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_front_matter=True)
        (P if 'Foreword' not in result else F).append("no_front_matter: Foreword removed")
        (P if 'foreword text' not in result else F).append("no_front_matter: Foreword body removed")
        (P if 'Chapter 1' in result else F).append("no_front_matter: chapters preserved")
        (P if report['removed'].get('front_matter_sections', 0) > 0 else F).append(
            "no_front_matter: report shows sections removed")

    def test_no_back_matter(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_back_matter=True)
        # Notes is first back-matter heading → everything from Notes onward removed
        (P if 'Bibliography' not in result else F).append("no_back_matter: Bibliography removed")
        (P if 'Abraham' not in result else F).append("no_back_matter: Index removed")
        (P if 'Chapter 1' in result else F).append("no_back_matter: chapters preserved")

    def test_no_images(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_images=True)
        (P if '<img' not in result else F).append("no_images: <img> tags removed")
        (P if 'Chapter 1' in result else F).append("no_images: chapters preserved")
        (P if report['removed'].get('images', 0) > 0 else F).append(
            "no_images: report shows images removed")

    def test_no_block_quotes(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_block_quotes=True)
        (P if '<blockquote' not in result else F).append("no_block_quotes: tag removed")
        (P if 'quoted passage' in result else F).append("no_block_quotes: text preserved")
        (P if report['removed'].get('block_quotes', 0) > 0 else F).append(
            "no_block_quotes: report shows quotes removed")

    def test_no_bibliography(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, no_bibliography=True)
        (P if 'Book Title' not in result else F).append("no_bibliography: bibliography content removed")
        (P if 'Chapter 1' in result else F).append("no_bibliography: chapters preserved")
        (P if report['removed'].get('bibliography_sections', 0) > 0 else F).append(
            "no_bibliography: report shows sections removed")

    def test_works_cited_variant(P, F):
        html = (
            '<html><body>'
            '<h1>Chapter 1</h1><p>Body text.</p>'
            '<h2>Works Cited</h2><p>Smith, J. (2020). Title.</p>'
            '</body></html>'
        )
        result, report = filter_html_with_report(html, no_bibliography=True)
        (P if 'Smith' not in result else F).append("works_cited: Works Cited heading matched")
        (P if 'Chapter 1' in result else F).append("works_cited: chapters preserved")

    # ── Edge case tests ─────────────────────────────────────────────────

    def test_profile_plus_override(P, F):
        result, report = filter_html_with_report(TEST_FILTER_HTML, profile='full', no_index=True)
        (P if 'Abraham' not in result else F).append("full+no_index: index stripped")
        (P if 'Foreword' in result else F).append("full+no_index: Foreword preserved")
        (P if '<a href=' in result else F).append("full+no_index: hyperlinks preserved")
        (P if '<sup>' in result else F).append("full+no_index: footnotes preserved")

    def test_empty_input(P, F):
        result, report = filter_html_with_report('', profile='clean-read')
        (P if result == '' else F).append("empty input: returns empty string")
        P.append("empty input: no crash")

    def test_no_match_input(P, F):
        html = '<html><body><h1>Chapter 1</h1><p>Just body text.</p></body></html>'
        result, report = filter_html_with_report(html, profile='clean-read')
        (P if 'Chapter 1' in result else F).append("no_match: Chapter 1 preserved")
        (P if 'Just body text' in result else F).append("no_match: body text preserved")

    # ── Integration test: real book HTML through clean-read ─────────────

    def test_integration_clean_read(P, F):
        case = TEST_CASES.get("Dionysius")
        if not case:
            P.append("integration: skipped (no Dionysius test case)")
            return
        pdf = find_pdf(case["pdf_pattern"], case.get("pdf_exclude"))
        if not pdf:
            P.append("integration: skipped (Dionysius PDF not found)")
            return

        html_path, stdout, stderr = run_extraction(pdf, use_pdfminer=True, test_name="filter_integ")
        if not html_path or not os.path.isfile(html_path):
            F.append("integration: extraction failed (no output HTML)")
            return

        with open(html_path, 'r', encoding='utf-8') as fh:
            full_html = fh.read()

        P.append("integration: extraction succeeded")

        filtered, report = filter_html_with_report(full_html, profile='clean-read')

        (P if len(filtered) < len(full_html) else F).append(
            f"integration: clean-read smaller ({report['size_reduction_percent']}% reduction)")
        (P if report['removed'] else F).append(
            f"integration: content stripped ({', '.join(f'{k}={v}' for k, v in report['removed'].items())})")

    # ── Register and run ────────────────────────────────────────────────

    _run("filter: full profile", test_full_profile)
    _run("filter: clean-read profile", test_clean_read_profile)
    _run("filter: text-only profile", test_text_only_profile)
    _run("filter: --no-footnotes", test_no_footnotes)
    _run("filter: --no-index", test_no_index)
    _run("filter: --no-hyperlinks", test_no_hyperlinks)
    _run("filter: --no-front-matter", test_no_front_matter)
    _run("filter: --no-back-matter", test_no_back_matter)
    _run("filter: --no-images", test_no_images)
    _run("filter: --no-block-quotes", test_no_block_quotes)
    _run("filter: --no-bibliography", test_no_bibliography)
    _run("filter: --no-bibliography (Works Cited)", test_works_cited_variant)
    _run("filter: full + --no-index override", test_profile_plus_override)
    _run("filter: empty input", test_empty_input)
    _run("filter: no-match input", test_no_match_input)
    _run("filter: integration clean-read", test_integration_clean_read)

    return results


def run_spaced_letter_tests():
    """Run unit tests for Phase 8 character spacing collapse in fix_ocr_artifacts().

    Returns list of (name, passed, passes, failures, elapsed).
    """
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from pdf_to_balabolka import fix_ocr_artifacts

    results = []
    log_messages = []

    def _log(msg):
        log_messages.append(msg)

    def _run(name, fn):
        t0 = time.time()
        passes, failures = [], []
        try:
            fn(passes, failures)
        except Exception as e:
            failures.append(f"Exception: {e}")
        elapsed = round(time.time() - t0, 3)
        results.append((name, len(failures) == 0, passes, failures, elapsed))

    def _collapse(text):
        """Run a single paragraph through fix_ocr_artifacts and return result."""
        log_messages.clear()
        paras = [text]
        fix_ocr_artifacts(paras, _log)
        return paras[0]

    # ── Fully-spaced word collapse (Phase 8 core behavior) ─────────

    def test_fully_spaced_wilson(P, F):
        """Single fully-spaced word collapses to dictionary word."""
        result = _collapse("W i l s o n")
        result_lower = result.lower()
        (P if "wilson" in result_lower else F).append(
            f"Wilson collapsed: got '{result}'")
        (P if "W i l" not in result else F).append(
            f"spaced letters gone: got '{result}'")

    def test_fully_spaced_manhattan(P, F):
        """Fully-spaced 'Manhattan' with all 9 chars."""
        result = _collapse("M a n h a t t a n")
        result_lower = result.lower()
        (P if "manhattan" in result_lower else F).append(
            f"manhattan collapsed: got '{result}'")
        (P if "a n h" not in result else F).append(
            f"spaced letters gone: got '{result}'")

    def test_fully_spaced_phrase(P, F):
        """Multiple fully-spaced words in a phrase with normal words between."""
        result = _collapse("W i l s o n in P a r i s")
        result_lower = result.lower()
        (P if "wilson" in result_lower else F).append(
            f"Wilson collapsed: got '{result}'")
        (P if "paris" in result_lower else F).append(
            f"Paris collapsed: got '{result}'")
        (P if "W i l" not in result and "P a r" not in result else F).append(
            f"all spaced runs collapsed: got '{result}'")

    def test_fully_spaced_dominion(P, F):
        """Doctrinal text: 'exact harmony of dominion'."""
        result = _collapse("e x a c t h a r m o n y o f d o m i n i o n")
        result_lower = result.lower()
        (P if "exact" in result_lower else F).append(
            f"'exact' found: got '{result}'")
        (P if "dominion" in result_lower else F).append(
            f"'dominion' found: got '{result}'")
        (P if "e x a" not in result else F).append(
            f"spaced letters gone: got '{result}'")

    # ── Mixed spaced/fused from real pdfminer output ─────────────────

    def test_mixed_paris_collapses(P, F):
        """Real pdfminer: 'W i ls on in P a r i s' — only 'P a r i s' is fully spaced."""
        result = _collapse("W i ls on in P a r i s")
        # 'P a r i s' is fully spaced (5 single chars) → collapses to 'Paris'
        # 'W i ls on' has fused pairs → regex doesn't match → stays as-is
        (P if "Paris" in result else F).append(
            f"fully-spaced 'Paris' collapsed: got '{result}'")
        (P if "W i ls on" in result else F).append(
            f"fused 'W i ls on' unchanged (expected): got '{result}'")

    def test_mixed_normal_prefix(P, F):
        """Normal text prefix followed by fully-spaced word."""
        result = _collapse("He visited W i l s o n in Paris")
        result_lower = result.lower()
        (P if "he visited" in result_lower else F).append(
            f"normal prefix preserved: got '{result}'")
        (P if "wilson" in result_lower else F).append(
            f"Wilson collapsed: got '{result}'")

    # ── Edge cases ────────────────────────────────────────────────────

    def test_normal_text_unchanged(P, F):
        original = "The quick brown fox"
        result = _collapse(original)
        (P if result == original else F).append(
            f"normal text unchanged: got '{result}'")

    def test_toc_dot_leaders_unchanged(P, F):
        original = ". . . . . . ."
        result = _collapse(original)
        (P if result == original else F).append(
            f"TOC dots unchanged: got '{result}'")

    def test_short_sequence_unchanged(P, F):
        """2-char sequence below the 3+ threshold — should not trigger."""
        original = "a b"
        result = _collapse(original)
        (P if result == original else F).append(
            f"2-char sequence unchanged: got '{result}'")

    def test_short_acronym_unchanged(P, F):
        """'U S A' = 3 chars but only 2 repetitions of (char space) — below regex {3,}."""
        original = "U S A"
        result = _collapse(original)
        (P if result == original else F).append(
            f"short acronym unchanged: got '{result}'")

    def test_punctuation_apostrophe(P, F):
        """Spaced word with trailing apostrophe-s."""
        result = _collapse("d o m i n i o n ' s")
        result_lower = result.lower()
        (P if "dominion" in result_lower else F).append(
            f"dominion collapsed: got '{result}'")
        (P if "d o m" not in result else F).append(
            f"spaced letters gone: got '{result}'")

    # ── Register and run ──────────────────────────────────────────────

    _run("spaced: fully-spaced Wilson", test_fully_spaced_wilson)
    _run("spaced: fully-spaced Manhattan", test_fully_spaced_manhattan)
    _run("spaced: fully-spaced phrase", test_fully_spaced_phrase)
    _run("spaced: fully-spaced dominion phrase", test_fully_spaced_dominion)
    _run("spaced: mixed Paris collapses", test_mixed_paris_collapses)
    _run("spaced: mixed normal prefix", test_mixed_normal_prefix)
    _run("spaced: normal text unchanged", test_normal_text_unchanged)
    _run("spaced: TOC dot leaders", test_toc_dot_leaders_unchanged)
    _run("spaced: short sequence (2 chars)", test_short_sequence_unchanged)
    _run("spaced: short acronym (U S A)", test_short_acronym_unchanged)
    _run("spaced: apostrophe punctuation", test_punctuation_apostrophe)

    return results


def main():
    ap = argparse.ArgumentParser(description="Test harness for pdfminer HTML extraction pipeline")
    ap.add_argument("test_name", nargs="?", default=None,
                    help="Name of a specific test to run (default: all)")
    ap.add_argument("--quick", action="store_true",
                    help="Skip KFX conversion, only validate HTML output")
    ap.add_argument("--list", action="store_true",
                    help="List available test case names and exit")
    ap.add_argument("--recapture", metavar="NAME",
                    help="Re-capture baseline for a book (overwrites saved baseline)")
    ap.add_argument("--capture-only", metavar="NAME",
                    help="Capture baseline without running tests")
    ap.add_argument("--corpus", nargs="?", const=True, default=None, metavar="NAME",
                    help="Run only test-corpus/ books (optionally filter by name)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Show all passing checks")
    args = ap.parse_args()

    if args.list:
        print("Hardcoded test cases:")
        for name in TEST_CASES:
            pdf = find_pdf(TEST_CASES[name]["pdf_pattern"],
                          TEST_CASES[name].get("pdf_exclude"))
            status = "FOUND" if pdf else "MISSING"
            print(f"  {name:20s}  [{status}]  {TEST_CASES[name]['pdf_pattern']}")

        captured = load_captured_cases()
        if captured:
            print("\nAuto-captured baselines (test_cases.json):")
            for name, case in captured.items():
                pdf = find_pdf(case["pdf_pattern"])
                status = "FOUND" if pdf else "MISSING"
                captured_at = case.get("captured_at", "unknown")[:10]
                b = case.get("baseline", {})
                print(f"  {name:20s}  [{status}]  captured {captured_at}  "
                      f"h2={b.get('h2_count', '?')} fn={b.get('linked_footnotes', '?')}")

        corpus_books = discover_corpus_books()
        print(f"\nTest corpus (test-corpus/):")
        if not corpus_books:
            print("  (empty — drop ebook files into test-corpus/ to add tests)")
        for book in corpus_books:
            sidecar = load_corpus_baseline(book)
            has_expect = book.with_suffix('.expect.json').is_file()
            if sidecar:
                captured_at = sidecar.get("captured_at", "unknown")[:10]
                b = sidecar.get("baseline", {})
                status = f"baselined {captured_at}"
                details = f"h2={b.get('h2_count', '?')} fn={b.get('linked_footnotes', '?')} path={sidecar.get('extraction_path', '?')}"
            else:
                status = "NEW (no baseline)"
                details = ""
            expect_tag = " +expect" if has_expect else ""
            print(f"  {book.stem:20s}  [{status}]{expect_tag}  {book.suffix}  {details}")
        return

    # ── Recapture mode ──
    if args.recapture:
        name = args.recapture

        # Check corpus first if --corpus flag is set
        if args.corpus is not None:
            corpus_books = discover_corpus_books()
            matches = [b for b in corpus_books if name.lower() in b.stem.lower()]
            if matches:
                for book in matches:
                    capture_corpus_baseline(book, args.quick)
                return
            print(f"No corpus book matching '{name}'")
            sys.exit(1)

        # Find in hardcoded cases or captured cases
        pattern = None
        if name in TEST_CASES:
            pattern = TEST_CASES[name]["pdf_pattern"]
        else:
            captured = load_captured_cases()
            if name in captured:
                pattern = captured[name]["pdf_pattern"]
        if not pattern:
            # Also check corpus books as fallback
            corpus_books = discover_corpus_books()
            matches = [b for b in corpus_books if name.lower() in b.stem.lower()]
            if matches:
                for book in matches:
                    capture_corpus_baseline(book, args.quick)
                return
            print(f"Unknown test case: '{name}'")
            sys.exit(1)
        do_capture(name, pattern, args.quick)
        return

    # ── Capture-only mode ──
    if args.capture_only:
        name = args.capture_only
        pattern = None
        if name in TEST_CASES:
            pattern = TEST_CASES[name]["pdf_pattern"]
        else:
            captured = load_captured_cases()
            if name in captured:
                pattern = captured[name]["pdf_pattern"]
        if not pattern:
            print(f"Unknown test case: '{name}'. Provide a --pdf-pattern for new books.")
            sys.exit(1)
        do_capture(name, pattern, args.quick)
        return

    # ── Corpus-only mode ──
    if args.corpus is not None:
        corpus_books = discover_corpus_books()
        if isinstance(args.corpus, str):
            corpus_books = [b for b in corpus_books if args.corpus.lower() in b.stem.lower()]
            if not corpus_books:
                print(f"No corpus book matching '{args.corpus}'")
                all_stems = [b.stem for b in discover_corpus_books()]
                if all_stems:
                    print(f"Available: {', '.join(all_stems)}")
                else:
                    print("test-corpus/ is empty — drop ebook files there to add tests")
                sys.exit(1)

        mode = "QUICK (HTML only)" if args.quick else "FULL (HTML + KFX)"
        print(f"\n{'=' * 60}")
        print(f"  EbookAutomation Corpus Test Suite")
        print(f"  Mode: {mode}")
        print(f"  Books: {len(corpus_books)}")
        print(f"{'=' * 60}\n")

        total_pass = 0
        total_fail = 0
        total_skip = 0

        for book in corpus_books:
            print(f"  Running: {book.stem} [corpus]...", end="", flush=True)
            passed, passes, failures, elapsed = run_corpus_test(book, args.quick)

            if passed is None:
                # Skipped (unsupported format)
                print(f"\r  {failures[0]}")
                total_skip += 1
                continue

            status = "PASS" if passed else "FAIL"
            check_count = len(passes) + len(failures)
            print(f"\r  {status}: {book.stem} [corpus] "
                  f"({len(passes)}/{check_count} checks, {elapsed:.1f}s)")

            if failures:
                for f in failures:
                    print(f"    FAIL: {f}")
            elif args.verbose:
                for p in passes:
                    print(f"    PASS: {p}")

            if passed:
                total_pass += 1
            else:
                total_fail += 1

        print(f"\n{'=' * 60}")
        parts = [f"{total_pass} passed", f"{total_fail} failed"]
        if total_skip:
            parts.append(f"{total_skip} skipped")
        print(f"  Results: {', '.join(parts)}, {total_pass + total_fail + total_skip} total")
        print(f"{'=' * 60}\n")
        sys.exit(0 if total_fail == 0 else 1)

    # ── Normal test mode ──
    # Merge hardcoded and captured cases
    captured_cases = load_captured_cases()
    # Only run captured cases that aren't already in hardcoded TEST_CASES
    extra_captured = {k: v for k, v in captured_cases.items() if k not in TEST_CASES}

    # Discover corpus books
    corpus_books = discover_corpus_books()

    if args.test_name:
        hc_matches = {n: TEST_CASES[n] for n in TEST_CASES
                      if args.test_name.lower() in n.lower()}
        cap_matches = {n: extra_captured[n] for n in extra_captured
                       if args.test_name.lower() in n.lower()}
        corpus_matches = [b for b in corpus_books
                          if args.test_name.lower() in b.stem.lower()]
        run_filters = 'filter' in args.test_name.lower()
        run_spaced = 'spaced' in args.test_name.lower()
        if not hc_matches and not cap_matches and not corpus_matches and not run_filters and not run_spaced:
            print(f"No test case matching '{args.test_name}'")
            all_names = list(TEST_CASES.keys()) + list(extra_captured.keys()) + [b.stem for b in corpus_books]
            all_names.append("filter (16 unit + integration tests)")
            all_names.append("spaced (11 character spacing collapse tests)")
            print(f"Available: {', '.join(all_names)}")
            sys.exit(1)
    else:
        hc_matches = TEST_CASES
        cap_matches = extra_captured
        corpus_matches = corpus_books
        run_filters = True
        run_spaced = True

    n_filter = 16 if run_filters else 0
    n_spaced = 11 if run_spaced else 0
    total_tests = len(hc_matches) + len(cap_matches) + len(corpus_matches) + n_filter + n_spaced
    mode = "QUICK (HTML only)" if args.quick else "FULL (HTML + KFX)"
    print(f"\n{'=' * 60}")
    print(f"  EbookAutomation Pipeline Test Suite")
    print(f"  Mode: {mode}")
    corpus_note = f", {len(corpus_matches)} corpus" if corpus_matches else ""
    filter_note = f", {n_filter} filter" if n_filter else ""
    spaced_note = f", {n_spaced} spaced" if n_spaced else ""
    print(f"  Tests: {total_tests} ({len(hc_matches)} hardcoded, "
          f"{len(cap_matches)} captured{corpus_note}{filter_note}{spaced_note})")
    print(f"{'=' * 60}\n")

    results = {}
    total_pass = 0
    total_fail = 0

    # Run hardcoded tests
    for name, case in hc_matches.items():
        print(f"  Running: {name}...", end="", flush=True)
        passed, passes, failures, elapsed = run_test(name, case, args.quick)
        results[name] = (passed, passes, failures, elapsed)

        status = "PASS" if passed else "FAIL"
        check_count = len(passes) + len(failures)
        print(f"\r  {status}: {name} ({len(passes)}/{check_count} checks passed, {elapsed:.1f}s)")

        if failures:
            for f in failures:
                print(f"    FAIL: {f}")
        elif args.verbose:
            for p in passes:
                print(f"    PASS: {p}")

        if passed:
            total_pass += 1
        else:
            total_fail += 1

    # Run captured baseline tests
    for name, case in cap_matches.items():
        print(f"  Running: {name} [baseline]...", end="", flush=True)
        passed, passes, failures, elapsed = run_baseline_test(name, case, args.quick)
        results[name] = (passed, passes, failures, elapsed)

        status = "PASS" if passed else "FAIL"
        check_count = len(passes) + len(failures)
        print(f"\r  {status}: {name} [baseline] "
              f"({len(passes)}/{check_count} checks, {elapsed:.1f}s)")

        if failures:
            for f in failures:
                print(f"    FAIL: {f}")
        elif args.verbose:
            for p in passes:
                print(f"    PASS: {p}")

        if passed:
            total_pass += 1
        else:
            total_fail += 1

    # Run corpus tests
    total_skip = 0
    if corpus_matches:
        for book in corpus_matches:
            print(f"  Running: {book.stem} [corpus]...", end="", flush=True)
            passed, passes, failures, elapsed = run_corpus_test(book, args.quick)

            if passed is None:
                print(f"\r  {failures[0]}")
                total_skip += 1
                continue

            status = "PASS" if passed else "FAIL"
            check_count = len(passes) + len(failures)
            print(f"\r  {status}: {book.stem} [corpus] "
                  f"({len(passes)}/{check_count} checks, {elapsed:.1f}s)")

            if failures:
                for f in failures:
                    print(f"    FAIL: {f}")
            elif args.verbose:
                for p in passes:
                    print(f"    PASS: {p}")

            if passed:
                total_pass += 1
            else:
                total_fail += 1

    # Run filter content tests
    if run_filters:
        filter_results = run_filter_tests(args.quick)
        for name, passed, passes, failures, elapsed in filter_results:
            check_count = len(passes) + len(failures)
            status = "PASS" if passed else "FAIL"
            print(f"  {status}: {name} ({len(passes)}/{check_count} checks, {elapsed:.1f}s)")

            if failures:
                for f in failures:
                    print(f"    FAIL: {f}")
            elif args.verbose:
                for p in passes:
                    print(f"    PASS: {p}")

            if passed:
                total_pass += 1
            else:
                total_fail += 1

    # Run spaced-letter collapse tests
    if run_spaced:
        spaced_results = run_spaced_letter_tests()
        for name, passed, passes, failures, elapsed in spaced_results:
            check_count = len(passes) + len(failures)
            status = "PASS" if passed else "FAIL"
            print(f"  {status}: {name} ({len(passes)}/{check_count} checks, {elapsed:.1f}s)")

            if failures:
                for f in failures:
                    print(f"    FAIL: {f}")
            elif args.verbose:
                for p in passes:
                    print(f"    PASS: {p}")

            if passed:
                total_pass += 1
            else:
                total_fail += 1

    # Summary
    print(f"\n{'=' * 60}")
    parts = [f"{total_pass} passed", f"{total_fail} failed"]
    if total_skip:
        parts.append(f"{total_skip} skipped")
    print(f"  Results: {', '.join(parts)}, {total_pass + total_fail + total_skip} total")
    print(f"{'=' * 60}\n")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
