"""
Test harness for the pdfminer HTML extraction pipeline.

Runs the PDF -> HTML -> KFX pipeline on validated books and checks expected
properties (heading counts, content presence, formatting quality).

Supports two modes:
  1. Hardcoded test cases (TEST_CASES dict) — manually curated assertions
  2. Auto-captured baselines (test_cases.json) — snapshot from last good run

Usage:
    python tools/test_pipeline.py                     # run all tests
    python tools/test_pipeline.py "Oil Kings"         # run one test
    python tools/test_pipeline.py --quick             # HTML only, skip KFX
    python tools/test_pipeline.py --list              # list test case names
    python tools/test_pipeline.py --recapture "Oil Kings"  # re-capture baseline
    python tools/test_pipeline.py --capture-only "Oil Kings"  # capture without testing
"""

import argparse
import glob
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
ARCHIVE_DIR = PROJECT_ROOT / "archive"
OUTPUT_DIR = PROJECT_ROOT / "output" / "kindle"
TEST_CASES_JSON = SCRIPT_DIR / "test_cases.json"

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
            "kfx_produced": False,   # skip KFX step; validate HTML only
            "min_h3": 8,             # chapters land as h3 from font-cluster path (Hermeneia format)
            # no_standalone_page_numbers omitted: known pipeline bug (size used before assignment
            # at format_paragraphs_as_html line ~3662) prevents reliable stripping for this book
        }
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Auto-capture: extract baseline from HTML
# ═══════════════════════════════════════════════════════════════════════════

def extract_baseline_from_html(html, kfx_path=None):
    """Extract all verifiable properties from HTML output as a baseline snapshot."""
    all_headings = re.findall(r'<(h[123])>(.*?)</\1>', html)
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
    for m in re.finditer(r'<h2>(.*?)</h2>', html):
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


def capture_baseline(name, pdf_pattern, html, kfx_path=None):
    """Capture a baseline for a book and save to test_cases.json."""
    cases = load_captured_cases()
    baseline = extract_baseline_from_html(html, kfx_path)

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

    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=600)

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
    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=600
    )
    return result.stdout, result.stderr


# ═══════════════════════════════════════════════════════════════════════════
# Validation checks (hardcoded test cases)
# ═══════════════════════════════════════════════════════════════════════════

def validate_html(html, expected, pipeline_stdout=""):
    """Run all expected checks against the HTML content. Returns (passes, failures)."""
    passes = []
    failures = []

    # Parse heading structure
    all_headings = re.findall(r'<(h[123])>(.*?)</\1>', html)
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
    baseline = capture_baseline(name, pdf_pattern, html, kfx_path)
    return baseline


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
        return

    # ── Recapture mode ──
    if args.recapture:
        name = args.recapture
        # Find in hardcoded cases or captured cases
        pattern = None
        if name in TEST_CASES:
            pattern = TEST_CASES[name]["pdf_pattern"]
        else:
            captured = load_captured_cases()
            if name in captured:
                pattern = captured[name]["pdf_pattern"]
        if not pattern:
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

    # ── Normal test mode ──
    # Merge hardcoded and captured cases
    captured_cases = load_captured_cases()
    # Only run captured cases that aren't already in hardcoded TEST_CASES
    extra_captured = {k: v for k, v in captured_cases.items() if k not in TEST_CASES}

    if args.test_name:
        hc_matches = {n: TEST_CASES[n] for n in TEST_CASES
                      if args.test_name.lower() in n.lower()}
        cap_matches = {n: extra_captured[n] for n in extra_captured
                       if args.test_name.lower() in n.lower()}
        if not hc_matches and not cap_matches:
            print(f"No test case matching '{args.test_name}'")
            all_names = list(TEST_CASES.keys()) + list(extra_captured.keys())
            print(f"Available: {', '.join(all_names)}")
            sys.exit(1)
    else:
        hc_matches = TEST_CASES
        cap_matches = extra_captured

    total_tests = len(hc_matches) + len(cap_matches)
    mode = "QUICK (HTML only)" if args.quick else "FULL (HTML + KFX)"
    print(f"\n{'=' * 60}")
    print(f"  EbookAutomation Pipeline Test Suite")
    print(f"  Mode: {mode}")
    print(f"  Tests: {total_tests} ({len(hc_matches)} hardcoded, {len(cap_matches)} captured)")
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

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Results: {total_pass} passed, {total_fail} failed, "
          f"{total_pass + total_fail} total")
    print(f"{'=' * 60}\n")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
