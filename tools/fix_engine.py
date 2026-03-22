#!/usr/bin/env python3
"""fix_engine.py -- Rule-based text fixes for ebook conversion pipeline.

Applies deterministic corrections to intermediate TXT/HTML files between
text extraction and Calibre conversion. Each fix is logged and can be
recorded in the pattern database for learning.

Usage:
    # Apply all applicable fixes to an intermediate file
    python tools/fix_engine.py --input temp_kindle.txt --vqa-report report.json

    # Apply specific fix categories only
    python tools/fix_engine.py --input temp_kindle.txt --fixes whitespace,punctuation

    # Dry run -- show what would be fixed without modifying the file
    python tools/fix_engine.py --input temp_kindle.txt --dry-run

    # Called from PowerShell (typical):
    python tools/fix_engine.py --input "$tempTxt" --vqa-report "$vqaReport" --output "$fixedTxt"
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ---------------------------------------------------------------------------
# Fix passes -- each returns (modified_text, fix_count)
# ---------------------------------------------------------------------------

def fix_whitespace(text, log):
    """Whitespace normalization."""
    fixes = 0

    # Collapse runs of 3+ spaces to single space
    text, n = re.subn(r' {3,}', ' ', text)
    fixes += n

    # Remove spaces immediately before punctuation: . , ; : ! ?
    text, n = re.subn(r' +([.,;:!?])', r'\1', text)
    fixes += n

    # Collapse runs of 3+ blank lines to 2 blank lines
    text, n = re.subn(r'\n{4,}', '\n\n\n', text)
    fixes += n

    # Strip trailing whitespace from each line
    lines = text.split('\n')
    stripped_count = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped != line:
            lines[i] = stripped
            stripped_count += 1
    if stripped_count:
        text = '\n'.join(lines)
        fixes += stripped_count

    # Replace tabs with single space
    text, n = re.subn(r'\t', ' ', text)
    fixes += n

    if fixes:
        log(f"  [fix] whitespace: {fixes} corrections")
    return text, fixes


def fix_smart_quotes(text, log):
    """ASCII to Unicode quote conversion for TXT intermediates."""
    fixes = 0

    # Opening double quotes: after whitespace/line-start/paren, before word char
    # Use non-lookbehind approach for Python 3.8 compat (variable-width lookbehind unsupported)
    text, n = re.subn(
        r'(^|[\s(])"(?=\w)', lambda m: m.group(1) + '\u201c', text,
        flags=re.MULTILINE
    )
    fixes += n

    # Closing double quotes: after word char/punctuation, before whitespace/line-end/paren
    text, n = re.subn(
        r'(?<=[\w.,;:!?])"(?=[\s.,;:!?)]|$)', '\u201d', text,
        flags=re.MULTILINE
    )
    fixes += n

    # Remaining unmatched quotes at start of line (opening)
    text, n = re.subn(r'^"(?=\w)', '\u201c', text, flags=re.MULTILINE)
    fixes += n

    # Apostrophes inside words: word char + ' + word char
    text, n = re.subn(r"(?<=\w)'(?=\w)", '\u2019', text)
    fixes += n

    # Opening single quotes: after whitespace/paren, before word
    text, n = re.subn(
        r"(^|[\s(])'(?=\w)", lambda m: m.group(1) + '\u2018', text,
        flags=re.MULTILINE
    )
    fixes += n

    # Closing single quotes: after word, before whitespace/punct
    text, n = re.subn(
        r"(?<=\w)'(?=[\s.,;:!?]|$)", '\u2019', text, flags=re.MULTILINE
    )
    fixes += n

    if fixes:
        log(f"  [fix] smart_quotes: {fixes} replacements")
    return text, fixes


_HEADING_PATTERNS = re.compile(
    r'^(CHAPTER|PART|INTRODUCTION|CONCLUSION|APPENDIX|EPILOGUE|PROLOGUE|'
    r'PREFACE|FOREWORD|AFTERWORD|ACKNOWLEDGMENT|BIBLIOGRAPHY|GLOSSARY|INDEX)'
    r'(\s+[IVXLCDM\d]+)?(\s*[.:\-].*)?$',
    re.IGNORECASE
)


def fix_heading_formatting(text, log, file_type='txt'):
    """Heading tag normalization."""
    fixes = 0

    if file_type == 'txt':
        lines = text.split('\n')
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # Strip duplicate headings: same heading text appears twice consecutively
            if (i + 1 < len(lines)
                    and line.strip()
                    and line.strip() == lines[i + 1].strip()
                    and (line.strip().startswith('#') or line.strip().isupper())):
                new_lines.append(line)
                i += 2  # skip the duplicate
                fixes += 1
                continue

            # Ensure # and ## headings have blank line before and after
            if line.strip().startswith('#'):
                # Blank line before (if previous line is non-empty and not blank)
                if new_lines and new_lines[-1].strip():
                    new_lines.append('')
                    fixes += 1
                new_lines.append(line)
                # Blank line after (if next line is non-empty)
                if i + 1 < len(lines) and lines[i + 1].strip():
                    new_lines.append('')
                    fixes += 1
                i += 1
                continue

            # Fix headings that lost their # prefix: ALL CAPS, short, between
            # blank lines, matching common heading patterns
            stripped = line.strip()
            if (stripped
                    and stripped.isupper()
                    and len(stripped) < 80
                    and _HEADING_PATTERNS.match(stripped)):
                prev_blank = (not new_lines or not new_lines[-1].strip())
                next_blank = (i + 1 >= len(lines) or not lines[i + 1].strip())
                if prev_blank and next_blank:
                    new_lines.append(f'## {stripped}')
                    fixes += 1
                    i += 1
                    continue

            new_lines.append(line)
            i += 1

        text = '\n'.join(new_lines)
    else:
        # HTML: ensure <h1>/<h2> tags have paragraph breaks around them
        text, n = re.subn(
            r'(?<!</p>\s*)(<h[1-6][^>]*>)', r'\n\1', text
        )
        fixes += n
        text, n = re.subn(
            r'(</h[1-6]>)(?!\s*<)', r'\1\n', text
        )
        fixes += n

    if fixes:
        log(f"  [fix] heading_formatting: {fixes} corrections")
    return text, fixes


def fix_paragraph_spacing(text, log, file_type='txt'):
    """Paragraph structure cleanup."""
    fixes = 0

    if file_type == 'txt':
        # Merge lines that are clearly continuations: start with lowercase,
        # previous line doesn't end with terminal punctuation or heading marker
        lines = text.split('\n')
        merged_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Check if this line should be merged with previous
            if (merged_lines
                    and line.strip()
                    and line.strip()[0].islower()
                    and merged_lines[-1].strip()
                    and not merged_lines[-1].strip().startswith('#')
                    and merged_lines[-1].strip()[-1] not in '.!?:;"\u201d'):
                # Merge with previous line
                merged_lines[-1] = merged_lines[-1].rstrip() + ' ' + line.strip()
                fixes += 1
            else:
                merged_lines.append(line)
            i += 1

        # Normalize paragraph spacing: collapse 3+ blank lines to 1 blank line
        # (whitespace pass already handles 4+; this handles exactly 3 blank lines
        # between paragraphs -> 1 blank line)
        text = '\n'.join(merged_lines)
    else:
        # HTML: remove empty <p></p> tags
        text, n = re.subn(r'<p>\s*</p>', '', text)
        fixes += n

    if fixes:
        log(f"  [fix] paragraph_spacing: {fixes} corrections")
    return text, fixes


def fix_orphan_fragments(text, log):
    """Remove extraction artifacts."""
    fixes = 0
    lines = text.split('\n')
    cleaned = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Strip standalone single-character artifact lines
        if stripped in (')', ']', ',', '.', '-', '\u2013', '\u2014', '(', '['):
            # Check that it's isolated (prev and next lines are blank or content)
            prev_blank = (i == 0 or not lines[i - 1].strip())
            next_blank = (i + 1 >= len(lines) or not lines[i + 1].strip())
            if prev_blank or next_blank:
                fixes += 1
                continue

        # Merge orphaned short fragments (< 5 chars) into previous paragraph
        if (stripped
                and len(stripped) < 5
                and cleaned
                and cleaned[-1].strip()
                and not stripped.startswith('#')
                and not stripped[0].isupper()
                and i > 0
                and lines[i - 1].strip()):
            # Looks like a fragment of the previous line
            cleaned[-1] = cleaned[-1].rstrip() + ' ' + stripped
            fixes += 1
            continue

        cleaned.append(line)

    text = '\n'.join(cleaned)

    if fixes:
        log(f"  [fix] orphan_fragments: {fixes} removals/merges")
    return text, fixes


def fix_vqa_targeted(text, log, vqa_report):
    """VQA-guided fixes based on top_issues from a previous VQA report."""
    if not vqa_report:
        return text, 0

    fixes = 0
    top_issues = vqa_report.get('top_issues', [])
    category_scores = vqa_report.get('category_scores', {})

    for issue in top_issues:
        cat = issue.get('category', '')
        desc = (issue.get('description', '') or '').lower()

        # text_integrity + spaces before punctuation -> already handled by whitespace
        if cat == 'text_integrity' and 'space' in desc and 'punctuation' in desc:
            log(f"  [fix] vqa_targeted: text_integrity/spacing handled by whitespace pass")
            fixes += 1

        # heading_formatting + unstyled -> scan for heading patterns and inject ##
        if cat == 'heading_formatting' and ('unstyled' in desc or 'missing' in desc):
            lines = text.split('\n')
            heading_fixes = 0
            for j, line in enumerate(lines):
                stripped = line.strip()
                if (stripped
                        and not stripped.startswith('#')
                        and stripped.isupper()
                        and len(stripped) < 80
                        and _HEADING_PATTERNS.match(stripped)):
                    lines[j] = f'## {stripped}'
                    heading_fixes += 1
            if heading_fixes:
                text = '\n'.join(lines)
                fixes += heading_fixes
                log(f"  [fix] vqa_targeted: injected {heading_fixes} heading markers")

        # paragraph_flow + split mid-sentence -> merge broken paragraphs
        if cat == 'paragraph_flow' and ('split' in desc or 'break' in desc):
            lines = text.split('\n')
            merged = []
            merge_count = 0
            for j, line in enumerate(lines):
                if (merged
                        and line.strip()
                        and line.strip()[0].islower()
                        and merged[-1].strip()
                        and not merged[-1].strip().startswith('#')
                        and merged[-1].strip()[-1] not in '.!?:;"\u201d'):
                    merged[-1] = merged[-1].rstrip() + ' ' + line.strip()
                    merge_count += 1
                else:
                    merged.append(line)
            if merge_count:
                text = '\n'.join(merged)
                fixes += merge_count
                log(f"  [fix] vqa_targeted: merged {merge_count} split paragraphs")

        # toc_navigation + missing anchors -> inject anchors for endnote patterns
        if cat == 'toc_navigation' and 'anchor' in desc:
            # Only for HTML files
            anchor_count = 0
            for m in re.finditer(r'(?<!\bid=["\'])(\bnote\s*(\d+))', text, re.IGNORECASE):
                note_num = m.group(2)
                anchor = f'<a id="note{note_num}"></a>'
                if anchor not in text:
                    text = text.replace(m.group(0), anchor + m.group(0), 1)
                    anchor_count += 1
                    if anchor_count >= 50:  # safety cap
                        break
            if anchor_count:
                fixes += anchor_count
                log(f"  [fix] vqa_targeted: injected {anchor_count} note anchors")

    if fixes:
        log(f"  [fix] vqa_targeted: {fixes} total targeted fixes")
    return text, fixes


# ---------------------------------------------------------------------------
# Main interface
# ---------------------------------------------------------------------------

ALL_FIX_CATEGORIES = [
    'whitespace', 'smart_quotes', 'heading_formatting',
    'paragraph_spacing', 'orphan_fragments', 'vqa_targeted',
]


def apply_fixes(input_path, output_path=None, vqa_report_path=None,
                fix_categories=None, dry_run=False, log=None):
    """Apply all applicable fixes to an intermediate text/HTML file.

    Args:
        input_path: Path to the intermediate TXT or HTML file
        output_path: Where to write the fixed file (default: overwrite input)
        vqa_report_path: Path to _visual_qa_report.json from previous iteration
        fix_categories: List of specific categories to run (default: all)
        dry_run: If True, report what would be fixed without modifying
        log: Logging function (default: print to stderr)

    Returns:
        dict with:
            total_fixes: int
            fixes_by_category: dict
            issues_addressed: list
            file_modified: bool
    """
    if log is None:
        log = lambda msg: print(msg, file=sys.stderr)

    input_path = Path(input_path)
    if not input_path.exists():
        log(f"  [fix] ERROR: input file not found: {input_path}")
        return {
            'total_fixes': 0,
            'fixes_by_category': {},
            'issues_addressed': [],
            'file_modified': False,
        }

    # Determine file type
    file_type = 'html' if input_path.suffix.lower() == '.html' else 'txt'

    # Read the file
    text = input_path.read_text(encoding='utf-8', errors='replace')
    original_text = text

    # Load VQA report if provided
    vqa_report = None
    issues_addressed = []
    if vqa_report_path:
        vqa_path = Path(vqa_report_path)
        if vqa_path.exists():
            try:
                vqa_report = json.loads(vqa_path.read_text(encoding='utf-8'))
                issues_addressed = [
                    i.get('category', 'unknown')
                    for i in vqa_report.get('top_issues', [])
                ]
                log(f"  [fix] Loaded VQA report with {len(issues_addressed)} top issues")
            except (json.JSONDecodeError, KeyError) as e:
                log(f"  [fix] Could not parse VQA report: {e}")
        else:
            log(f"  [fix] VQA report not found: {vqa_path}")

    # Determine which categories to run
    if fix_categories:
        categories = [c.strip() for c in fix_categories if c.strip() in ALL_FIX_CATEGORIES]
    else:
        categories = list(ALL_FIX_CATEGORIES)

    # Run fix passes
    fixes_by_category = {}

    if 'whitespace' in categories:
        text, count = fix_whitespace(text, log)
        if count:
            fixes_by_category['whitespace'] = count

    if 'smart_quotes' in categories and file_type == 'txt':
        text, count = fix_smart_quotes(text, log)
        if count:
            fixes_by_category['smart_quotes'] = count

    if 'heading_formatting' in categories:
        text, count = fix_heading_formatting(text, log, file_type)
        if count:
            fixes_by_category['heading_formatting'] = count

    if 'paragraph_spacing' in categories:
        text, count = fix_paragraph_spacing(text, log, file_type)
        if count:
            fixes_by_category['paragraph_spacing'] = count

    if 'orphan_fragments' in categories:
        text, count = fix_orphan_fragments(text, log)
        if count:
            fixes_by_category['orphan_fragments'] = count

    if 'vqa_targeted' in categories and vqa_report:
        text, count = fix_vqa_targeted(text, log, vqa_report)
        if count:
            fixes_by_category['vqa_targeted'] = count

    total_fixes = sum(fixes_by_category.values())
    file_modified = text != original_text

    if dry_run:
        log(f"  [fix] DRY RUN: would apply {total_fixes} fixes across {len(fixes_by_category)} categories")
    elif file_modified:
        out = Path(output_path) if output_path else input_path
        out.write_text(text, encoding='utf-8')
        log(f"  [fix] Written {total_fixes} fixes to {out}")
    else:
        log(f"  [fix] No changes needed")

    return {
        'total_fixes': total_fixes,
        'fixes_by_category': fixes_by_category,
        'issues_addressed': issues_addressed,
        'file_modified': file_modified and not dry_run,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Rule-based text fixes for ebook conversion"
    )
    parser.add_argument("--input", required=True,
                        help="Path to intermediate TXT/HTML file")
    parser.add_argument("--output", default=None,
                        help="Output path (default: overwrite input)")
    parser.add_argument("--vqa-report", default=None,
                        help="Path to VQA report JSON from previous iteration")
    parser.add_argument("--fixes", default=None,
                        help="Comma-separated list of fix categories to apply")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fixed without modifying")
    parser.add_argument("--verbose", action="store_true",
                        help="Detailed logging")

    args = parser.parse_args()

    fix_categories = None
    if args.fixes:
        fix_categories = [c.strip() for c in args.fixes.split(',')]

    def log(msg):
        print(msg, file=sys.stderr)

    result = apply_fixes(
        input_path=args.input,
        output_path=args.output,
        vqa_report_path=args.vqa_report,
        fix_categories=fix_categories,
        dry_run=args.dry_run,
        log=log,
    )

    # JSON summary to stdout (for PowerShell to parse)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
