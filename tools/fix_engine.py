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
# Index detection constants
# ---------------------------------------------------------------------------

_BIBLE_BOOKS = {
    # Old Testament
    'genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy',
    'joshua', 'judges', 'ruth', '1 samuel', '2 samuel',
    '1 kings', '2 kings', '1 chronicles', '2 chronicles',
    'ezra', 'nehemiah', 'esther', 'job', 'psalms', 'psalm',
    'proverbs', 'ecclesiastes', 'song of solomon', 'isaiah',
    'jeremiah', 'lamentations', 'ezekiel', 'daniel', 'hosea',
    'joel', 'amos', 'obadiah', 'jonah', 'micah', 'nahum',
    'habakkuk', 'zephaniah', 'haggai', 'zechariah', 'malachi',
    # New Testament
    'matthew', 'mark', 'luke', 'john', 'acts', 'romans',
    '1 corinthians', '2 corinthians', 'galatians', 'ephesians',
    'philippians', 'colossians', '1 thessalonians', '2 thessalonians',
    '1 timothy', '2 timothy', 'titus', 'philemon', 'hebrews',
    'james', '1 peter', '2 peter', '1 john', '2 john', '3 john',
    'jude', 'revelation',
    # Common abbreviations
    'gen', 'exod', 'lev', 'num', 'deut', 'josh', 'judg',
    'sam', 'kgs', 'chr', 'neh', 'esth', 'ps', 'prov', 'eccl',
    'isa', 'jer', 'lam', 'ezek', 'dan', 'hos', 'mic', 'nah',
    'hab', 'zeph', 'hag', 'zech', 'mal', 'matt', 'mk', 'lk',
    'rom', 'cor', 'gal', 'eph', 'phil', 'col', 'thess', 'tim',
    'heb', 'jas', 'pet', 'rev',
    # Apocryphal / Deuterocanonical
    'tobit', 'judith', 'wisdom', 'sirach', 'baruch',
    '1 maccabees', '2 maccabees', '1 enoch', '2 enoch',
    '2 baruch', '3 baruch', '4 ezra', 'jubilees',
    '1 esdras', '2 esdras', 'susanna', 'bel',
    # Dead Sea Scrolls
    '1qs', '1qm', '1qh', '4qmmt', '11qtemple', 'cd',
    # Ancient authors / sources
    'josephus', 'philo', 'pliny', 'tacitus', 'eusebius',
    'origen', 'jerome', 'augustine', 'tertullian', 'clement',
    'irenaeus', 'athanasius', 'chrysostom',
}

_INDEX_HEADING_RE = re.compile(
    r'(?:index|scripture|biblical|references|sources|concordance)',
    re.IGNORECASE
)

_SUBJECT_HEADING_RE = re.compile(
    r'(?:subject\s+index|general\s+index|author\s+index|name\s+index|'
    r'index\s+of\s+(?:names|subjects|authors|topics|proper\s+names))',
    re.IGNORECASE
)

# Matches verse references like 1:3, 12.14-17, 3:5-6
_VERSE_REF_RE = re.compile(
    r'\d{1,3}[.:]\d{1,3}(?:\s*[-\u2013\u2014]\s*\d{1,3})?'
)

# Matches subject index entries: "Capitalized word(s), page_numbers..."
# Lenient ending — fragmented entries may end with comma, dash, or digit
_SUBJECT_ENTRY_RE = re.compile(
    r'^[A-Z][a-zA-Z\s\'-]{2,},\s*\d'
)


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
            r'(?<!</p>)(<h[1-6][^>]*>)', r'\n\1', text
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


def _has_index_content(paragraphs, start_idx):
    """Check if paragraphs starting at start_idx contain index-like content."""
    sample = paragraphs[start_idx:start_idx + 15]
    if not sample:
        return False

    ref_hits = 0
    book_hits = 0
    subject_hits = 0
    numeric_fragments = 0
    for p in sample:
        stripped = p.strip()
        if not stripped:
            continue
        if _VERSE_REF_RE.search(stripped):
            ref_hits += 1
        # Check if line starts with a bible book name or known source
        lower = stripped.lower()
        first_words = ' '.join(lower.split()[:3])
        if any(first_words.startswith(book) for book in _BIBLE_BOOKS):
            book_hits += 1
        # Check for subject index entries (Capitalized term, page numbers)
        if _SUBJECT_ENTRY_RE.match(stripped):
            subject_hits += 1
        # Short numeric-only fragments indicate fragmented index entries
        if re.match(r'^[\d.\-\u2013\u2014,\s]{1,8}$', stripped):
            numeric_fragments += 1

    non_empty = max(1, sum(1 for p in sample if p.strip()))
    # Scripture index: 30%+ have verse refs OR 20%+ start with book names
    # Subject index: 20%+ match subject entry pattern
    # High numeric fragment density also indicates a fragmented index
    return (ref_hits >= non_empty * 0.3
            or book_hits >= non_empty * 0.2
            or subject_hits >= non_empty * 0.2
            or (subject_hits >= 1 and numeric_fragments >= non_empty * 0.2))


def fix_index_fragments(text, log):
    """Reassemble fragmented index entries (scripture/subject indexes).

    Detects index regions by requiring BOTH an index heading AND reference-dense
    content, then merges:
    1. Lines ending with - or dash followed by numeric continuation
    2. Standalone short numeric fragments into parent entries
    3. Verse reference continuations (short lines starting with digit)

    Only operates within detected index regions to avoid false positives on
    body text.
    """
    # Detect format: HTML uses <p> tags, TXT uses blank-line separation
    is_html = '<p>' in text or '<p ' in text

    if is_html:
        return _fix_index_fragments_html(text, log)
    else:
        return _fix_index_fragments_txt(text, log)


def _fix_index_fragments_txt(text, log):
    """Index fragment reassembly for TXT format (blank-line separated paragraphs)."""
    paragraphs = text.split('\n\n')
    total_paras = len(paragraphs)
    fixes = 0

    # Only look in the last ~60% of the document (indexes are at the end)
    # The heading+content dual check is the primary safeguard against false positives
    search_start = max(0, int(total_paras * 0.4))

    in_index = False
    index_start = -1

    i = search_start
    while i < total_paras:
        stripped = paragraphs[i].strip()

        # Check if we're entering an index region
        if not in_index:
            if (_INDEX_HEADING_RE.search(stripped) or _SUBJECT_HEADING_RE.search(stripped)):
                if i + 1 < total_paras and _has_index_content(paragraphs, i + 1):
                    in_index = True
                    index_start = i + 1
                    log(f"  [fix] index_fragments: detected index region at paragraph {i} "
                        f"({i}/{total_paras})")
            i += 1
            continue

        # Inside an index region — apply reassembly rules

        # Rule 1: Previous paragraph ends with - or dash -> merge with current
        if (i > index_start and paragraphs[i - 1].strip()
                and paragraphs[i - 1].strip()[-1] in '-\u2013\u2014'
                and stripped):
            paragraphs[i - 1] = paragraphs[i - 1].rstrip() + stripped
            paragraphs[i] = ''
            fixes += 1
            i += 1
            continue

        # Rule 2: Current paragraph is just a short number/reference fragment
        # e.g., "25.", "9-", "4-5", "17", "10-"
        if stripped and re.match(r'^[\d.\-\u2013\u2014,\s]{1,8}$', stripped):
            for j in range(i - 1, max(index_start - 1, -1), -1):
                if paragraphs[j].strip():
                    prev = paragraphs[j].rstrip()
                    sep = '' if prev[-1] in '-\u2013\u2014 ' else ' '
                    paragraphs[j] = prev + sep + stripped
                    paragraphs[i] = ''
                    fixes += 1
                    break
            i += 1
            continue

        # Rule 3: Previous paragraph ends with comma and current starts with digit
        # (page number continuation after comma split)
        if (stripped and re.match(r'^\d', stripped) and len(stripped) < 40
                and i > index_start):
            prev_text = ''
            prev_j = -1
            for j in range(i - 1, max(index_start - 1, -1), -1):
                if paragraphs[j].strip():
                    prev_text = paragraphs[j].strip()
                    prev_j = j
                    break
            if prev_text and prev_text[-1] == ',':
                paragraphs[prev_j] = paragraphs[prev_j].rstrip() + ' ' + stripped
                paragraphs[i] = ''
                fixes += 1
                i += 1
                continue

        # Rule 4: Current paragraph is a verse reference continuation
        # (starts with a digit, previous paragraph has verse refs, and it's short)
        if (stripped and re.match(r'^\d', stripped) and len(stripped) < 40
                and i > index_start):
            prev_text = ''
            for j in range(i - 1, max(index_start - 1, -1), -1):
                if paragraphs[j].strip():
                    prev_text = paragraphs[j].strip()
                    break
            if prev_text and _VERSE_REF_RE.search(prev_text):
                for j in range(i - 1, max(index_start - 1, -1), -1):
                    if paragraphs[j].strip():
                        paragraphs[j] = paragraphs[j].rstrip() + ' ' + stripped
                        paragraphs[i] = ''
                        fixes += 1
                        break
                i += 1
                continue

        i += 1

    if fixes:
        log(f"  [fix] index_fragments: {fixes} fragments reassembled")

    result = '\n\n'.join(p for p in paragraphs if p.strip() or p == '')
    # Clean up runs of empty paragraphs that result from merges
    result = re.sub(r'(\n\n){2,}', '\n\n', result)
    return result, fixes


def _fix_index_fragments_html(text, log):
    """Index fragment reassembly for HTML format (<p> elements)."""
    # Split on <p> tags, preserving them
    parts = re.split(r'(<p[^>]*>.*?</p>)', text, flags=re.DOTALL)

    # Extract paragraph contents for analysis
    p_indices = []  # indices into parts[] that are <p> elements
    p_texts = []    # stripped text content of those <p> elements
    for idx, part in enumerate(parts):
        if re.match(r'<p[^>]*>', part):
            # Extract text content (strip tags)
            inner = re.sub(r'<[^>]+>', '', part).strip()
            p_indices.append(idx)
            p_texts.append(inner)

    total_p = len(p_texts)
    if total_p == 0:
        return text, 0

    search_start = max(0, int(total_p * 0.4))
    fixes = 0
    in_index = False
    index_start = -1

    i = search_start
    while i < total_p:
        stripped = p_texts[i]

        if not in_index:
            if (_INDEX_HEADING_RE.search(stripped) or _SUBJECT_HEADING_RE.search(stripped)):
                if i + 1 < total_p and _has_index_content(p_texts, i + 1):
                    in_index = True
                    index_start = i + 1
                    log(f"  [fix] index_fragments: detected HTML index region at <p> {i}")
            i += 1
            continue

        # Rule 1: Previous <p> ends with dash -> merge
        if (i > index_start and p_texts[i - 1]
                and p_texts[i - 1][-1] in '-\u2013\u2014'
                and stripped):
            prev_idx = p_indices[i - 1]
            # Append current text into previous <p> (before </p>)
            parts[prev_idx] = re.sub(
                r'</p>$', stripped + '</p>', parts[prev_idx]
            )
            parts[p_indices[i]] = ''  # Remove current <p>
            p_texts[i - 1] += stripped
            p_texts[i] = ''
            fixes += 1
            i += 1
            continue

        # Rule 2: Short numeric fragment
        if stripped and re.match(r'^[\d.\-\u2013\u2014,\s]{1,8}$', stripped):
            for j in range(i - 1, max(index_start - 1, -1), -1):
                if p_texts[j]:
                    prev_idx = p_indices[j]
                    prev_end = p_texts[j][-1] if p_texts[j] else ''
                    sep = '' if prev_end in '-\u2013\u2014 ' else ' '
                    parts[prev_idx] = re.sub(
                        r'</p>$', sep + stripped + '</p>', parts[prev_idx]
                    )
                    parts[p_indices[i]] = ''
                    p_texts[j] += sep + stripped
                    p_texts[i] = ''
                    fixes += 1
                    break
            i += 1
            continue

        # Rule 3: Previous <p> ends with comma and current starts with digit
        if (stripped and re.match(r'^\d', stripped) and len(stripped) < 40
                and i > index_start):
            prev_text = ''
            prev_j = -1
            for j in range(i - 1, max(index_start - 1, -1), -1):
                if p_texts[j]:
                    prev_text = p_texts[j]
                    prev_j = j
                    break
            if prev_text and prev_text[-1] == ',' and prev_j >= 0:
                prev_idx = p_indices[prev_j]
                parts[prev_idx] = re.sub(
                    r'</p>$', ' ' + stripped + '</p>', parts[prev_idx]
                )
                parts[p_indices[i]] = ''
                p_texts[prev_j] += ' ' + stripped
                p_texts[i] = ''
                fixes += 1
                i += 1
                continue

        # Rule 4: Verse reference continuation
        if (stripped and re.match(r'^\d', stripped) and len(stripped) < 40
                and i > index_start):
            prev_text = ''
            prev_j = -1
            for j in range(i - 1, max(index_start - 1, -1), -1):
                if p_texts[j]:
                    prev_text = p_texts[j]
                    prev_j = j
                    break
            if prev_text and _VERSE_REF_RE.search(prev_text) and prev_j >= 0:
                prev_idx = p_indices[prev_j]
                parts[prev_idx] = re.sub(
                    r'</p>$', ' ' + stripped + '</p>', parts[prev_idx]
                )
                parts[p_indices[i]] = ''
                p_texts[prev_j] += ' ' + stripped
                p_texts[i] = ''
                fixes += 1
            i += 1
            continue

        i += 1

    if fixes:
        log(f"  [fix] index_fragments: {fixes} HTML fragments reassembled")

    result = ''.join(parts)
    return result, fixes


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
    'paragraph_spacing', 'orphan_fragments', 'index_fragments',
    'vqa_targeted',
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

    if 'index_fragments' in categories:
        text, count = fix_index_fragments(text, log)
        if count:
            fixes_by_category['index_fragments'] = count

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
