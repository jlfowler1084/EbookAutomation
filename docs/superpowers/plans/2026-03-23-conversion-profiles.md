# Conversion Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add conversion profile support (`full`, `clean-read`, `text-only`) and individual toggle flags (`--no-footnotes`, `--no-index`, etc.) that let users control which content elements appear in Kindle conversions.

**Architecture:** A standalone Python filter script (`tools/filter_content.py`) processes intermediate HTML/TXT after extraction + fix engine but before Calibre. PowerShell functions gain `-Profile` and `-No*` parameters that invoke the filter. Lean profiles also skip unnecessary upstream processing (footnote linking, AI quality pass) for speed.

**Tech Stack:** Python 3.8+ (BeautifulSoup4 — already installed), PowerShell 5.1+

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| **Create** | `tools/filter_content.py` | Standalone HTML/TXT content filter — reads file, removes elements per profile/flags, writes filtered output, reports JSON summary |
| **Create** | `tools/test_filter_content.py` | Unit tests for the filter script |
| **Modify** | `module/EbookAutomation.psm1` | Add `-Profile` and `-No*` params to `Convert-ToKindle`, `Invoke-EbookPipeline`, `Invoke-ConvergeLoop`; insert filter invocation; add scan recommendation log |
| **Modify** | `tools/pdf_to_balabolka.py` | Add `--skip-footnotes` CLI flag to skip `_link_endnotes()` call when footnotes will be stripped anyway |

---

## Task 1: Create `tools/filter_content.py` — Core Filter Logic

**Files:**
- Create: `tools/filter_content.py`
- Create: `tools/test_filter_content.py`

### Step 1.1: Write test fixtures

- [ ] **Create a minimal HTML fixture string for tests**

```python
# tools/test_filter_content.py
"""Tests for filter_content.py content filtering."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(__file__))

SAMPLE_HTML = """<!DOCTYPE html>
<html><head><title>Test Book</title></head><body>
<h1>Front Matter</h1>
<h2>Endorsements</h2>
<p>Great book! —Famous Person</p>
<h2>Preface</h2>
<p>This is the preface text.</p>

<h1>Chapter 1: Introduction</h1>
<p>Body paragraph one with a footnote<sup><a id="noteref_1" href="#endnote_1">1</a></sup>.</p>
<p>Body paragraph two with a <a href="https://example.com">hyperlink</a>.</p>
<blockquote><p>A quoted passage from another source.</p></blockquote>
<p>More body text.</p>
<img src="figure1.png" alt="Figure 1"/>

<h1>Chapter 2: Analysis</h1>
<p>Analysis paragraph with footnote<sup><a id="noteref_2" href="#endnote_2">2</a></sup>.</p>

<h1>Notes</h1>
<p><a id="endnote_1"></a><a href="#noteref_1">1.</a> First endnote text.</p>
<p><a id="endnote_2"></a><a href="#noteref_2">2.</a> Second endnote text.</p>

<h1>Bibliography</h1>
<p>Author, A. <em>Title</em>. Publisher, 2020.</p>

<h1>Index</h1>
<p>Abraham, 12, 45, 67</p>
<p>Moses, 23, 89</p>
</body></html>"""
```

### Step 1.2: Write failing tests for each filter flag

- [ ] **Write tests for all 7 filter flags + profile presets + TXT filtering**

```python
# tools/test_filter_content.py (continued)
import unittest

class TestFilterNoFootnotes(unittest.TestCase):
    def test_removes_sup_anchors(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_footnotes=True)
        self.assertNotIn('<sup>', result)
        self.assertNotIn('noteref_', result)

    def test_removes_notes_section(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_footnotes=True)
        self.assertNotIn('endnote_1', result)
        self.assertNotIn('First endnote text', result)

    def test_preserves_body_text(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_footnotes=True)
        self.assertIn('Body paragraph one', result)


class TestFilterNoIndex(unittest.TestCase):
    def test_removes_index_section(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_index=True)
        self.assertNotIn('Abraham, 12', result)
        self.assertNotIn('Moses, 23', result)

    def test_preserves_bibliography(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_index=True)
        self.assertIn('Bibliography', result)


class TestFilterNoHyperlinks(unittest.TestCase):
    def test_strips_href_keeps_text(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_hyperlinks=True)
        self.assertNotIn('href="https://example.com"', result)
        self.assertIn('hyperlink', result)

    def test_preserves_anchor_ids(self):
        """<a id="..."> navigation targets should survive."""
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_hyperlinks=True)
        # Anchor IDs used for footnote navigation should be kept
        self.assertIn('id="endnote_1"', result)


class TestFilterNoFrontMatter(unittest.TestCase):
    def test_removes_endorsements_preface(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_front_matter=True)
        self.assertNotIn('Endorsements', result)
        self.assertNotIn('Famous Person', result)
        self.assertNotIn('Preface', result)

    def test_preserves_chapters(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_front_matter=True)
        self.assertIn('Chapter 1', result)
        self.assertIn('Chapter 2', result)


class TestFilterNoBackMatter(unittest.TestCase):
    def test_removes_notes_bibliography_index(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_back_matter=True)
        self.assertNotIn('First endnote text', result)
        self.assertNotIn('Bibliography', result)
        self.assertNotIn('Abraham, 12', result)

    def test_preserves_chapter_content(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_back_matter=True)
        self.assertIn('Analysis paragraph', result)


class TestFilterNoImages(unittest.TestCase):
    def test_removes_img_tags(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_images=True)
        self.assertNotIn('<img', result)
        self.assertNotIn('figure1.png', result)


class TestFilterNoBlockQuotes(unittest.TestCase):
    def test_converts_blockquote_to_p(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, no_block_quotes=True)
        self.assertNotIn('<blockquote>', result)
        self.assertIn('A quoted passage', result)


class TestProfiles(unittest.TestCase):
    def test_full_profile_no_changes(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, profile='full')
        self.assertIn('<sup>', result)
        self.assertIn('Index', result)
        self.assertIn('Bibliography', result)

    def test_clean_read_profile(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, profile='clean-read')
        self.assertNotIn('<sup>', result)          # no footnotes
        self.assertNotIn('Abraham, 12', result)    # no index
        self.assertNotIn('href="https', result)    # no hyperlinks
        self.assertNotIn('Endorsements', result)   # no front matter
        self.assertIn('Bibliography', result)       # back matter kept
        self.assertIn('Chapter 1', result)          # chapters kept

    def test_text_only_profile(self):
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, profile='text-only')
        self.assertNotIn('<sup>', result)
        self.assertNotIn('Abraham, 12', result)
        self.assertNotIn('href="https', result)
        self.assertNotIn('Endorsements', result)
        self.assertNotIn('Bibliography', result)
        self.assertNotIn('<img', result)
        self.assertNotIn('<blockquote>', result)
        self.assertIn('Chapter 1', result)
        self.assertIn('Body paragraph one', result)


class TestFlagOverridesProfile(unittest.TestCase):
    def test_full_with_no_index(self):
        """Individual flag overrides full profile."""
        from filter_content import filter_html
        result = filter_html(SAMPLE_HTML, profile='full', no_index=True)
        self.assertNotIn('Abraham, 12', result)
        self.assertIn('<sup>', result)  # footnotes still present


class TestJsonReport(unittest.TestCase):
    def test_report_structure(self):
        from filter_content import filter_html_with_report
        _, report = filter_html_with_report(SAMPLE_HTML, profile='clean-read')
        self.assertEqual(report['profile'], 'clean-read')
        self.assertIn('removed', report)
        self.assertIn('size_reduction_percent', report)


class TestTxtFiltering(unittest.TestCase):
    """Tests for the legacy TXT/Markdown path."""
    SAMPLE_TXT = """# Preface
Some preface text.

# Chapter 1: Introduction
Body paragraph one.

# Chapter 2: Analysis
Analysis text here.

# Notes
1. First endnote.
2. Second endnote.

# Index
Abraham, 12, 45
Moses, 23, 89
"""

    def test_removes_notes_section(self):
        from filter_content import _filter_txt
        result, removed = _filter_txt(self.SAMPLE_TXT, {'no_footnotes': True})
        self.assertNotIn('First endnote', result)
        self.assertIn('Chapter 1', result)

    def test_removes_index_section(self):
        from filter_content import _filter_txt
        result, removed = _filter_txt(self.SAMPLE_TXT, {'no_index': True})
        self.assertNotIn('Abraham, 12', result)
        self.assertIn('Chapter 1', result)

    def test_removes_front_matter(self):
        from filter_content import _filter_txt
        result, removed = _filter_txt(self.SAMPLE_TXT, {'no_front_matter': True})
        self.assertNotIn('preface text', result)
        self.assertIn('Chapter 1', result)


if __name__ == '__main__':
    unittest.main()
```

### Step 1.3: Run tests to verify they fail

- [ ] **Run tests — all should fail (module not found)**

Run: `python tools/test_filter_content.py 2>&1 | head -20`
Expected: `ModuleNotFoundError: No module named 'filter_content'`

### Step 1.4: Implement `filter_content.py`

- [ ] **Write the filter implementation**

```python
# tools/filter_content.py
"""
Content filter for ebook conversion profiles.

Strips content elements (footnotes, index, hyperlinks, front/back matter,
images, block quotes) from intermediate HTML based on profile presets or
individual flags.

Usage:
    python tools/filter_content.py --input book.html --output filtered.html --profile clean-read
    python tools/filter_content.py --input book.html --output filtered.html --no-footnotes --no-index
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

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("ERROR: BeautifulSoup4 required — run: python -m pip install beautifulsoup4")

# ── Profile presets ──────────────────────────────────────────────────────────

PROFILES = {
    'full': {},
    'clean-read': {
        'no_footnotes': True,
        'no_index': True,
        'no_hyperlinks': True,
        'no_front_matter': True,
    },
    'text-only': {
        'no_footnotes': True,
        'no_index': True,
        'no_hyperlinks': True,
        'no_front_matter': True,
        'no_back_matter': True,
        'no_images': True,
        'no_block_quotes': True,
    },
}

# ── Heading patterns ─────────────────────────────────────────────────────────

FRONT_MATTER_HEADINGS = re.compile(
    r'^(preface|foreword|acknowledge?ments?|dedication|endorsements?|'
    r'epigraph|contributors?|list\s+of\s+(illustrations|abbreviations|maps|tables)|'
    r'translator\'?s?\s+note|editor\'?s?\s+note|introduction\s+to\s+the\s+series)$',
    re.IGNORECASE
)

BACK_MATTER_HEADINGS = re.compile(
    r'^(notes?|endnotes?|footnotes?|bibliography|references?|index|'
    r'works?\s+cited|further\s+reading|selected\s+bibliography|'
    r'acknowledge?ments?|appendix|appendices|glossary|abbreviations?|'
    r'scripture\s+index|subject\s+index|author\s+index|name\s+index|'
    r'search\s+items?\s+of\s+biblical\s+and\s+ancient\s+sources|'
    r'about\s+the\s+authors?)$',
    re.IGNORECASE
)

NOTES_HEADINGS = re.compile(
    r'^(notes?|endnotes?|footnotes?)$', re.IGNORECASE
)

INDEX_HEADINGS = re.compile(
    r'^(index|indices|scripture\s+index|subject\s+index|author\s+index|'
    r'name\s+index|search\s+items?\s+of\s+biblical\s+and\s+ancient\s+sources|'
    r'index\s+of\s+.+)$',
    re.IGNORECASE
)

CHAPTER_HEADING = re.compile(
    r'^(chapter\s+\d|part\s+\d|\d+[\.:]\s|[IVX]+[\.:]\s)',
    re.IGNORECASE
)


# ── Filter functions ─────────────────────────────────────────────────────────

def _remove_section_by_heading(soup, heading_re, heading_tags=('h1', 'h2')):
    """Remove a section from heading match to next same-or-higher heading (or EOF).
    Returns count of removed sections."""
    removed = 0
    for tag_name in heading_tags:
        for heading in soup.find_all(tag_name):
            text = heading.get_text(strip=True)
            if heading_re.match(text):
                # Remove everything from this heading to next h1/h2 or end
                to_remove = [heading]
                sibling = heading.next_sibling
                while sibling:
                    next_sib = sibling.next_sibling
                    if hasattr(sibling, 'name') and sibling.name in ('h1', 'h2'):
                        break
                    to_remove.append(sibling)
                    sibling = next_sib
                for el in to_remove:
                    el.extract()
                removed += 1
    return removed


def _strip_footnotes(soup):
    """Remove <sup> footnote markers and Notes/Endnotes sections. Returns count."""
    count = 0

    # Remove <sup> elements containing footnote anchors (<sup><a href="#...">N</a></sup>)
    for sup in soup.find_all('sup'):
        a_child = sup.find('a')
        if a_child and a_child.get('href', '').startswith('#'):
            sup.decompose()
            count += 1
        elif sup.get_text(strip=True).isdigit():
            # Bare <sup>N</sup> without anchor — also a footnote marker
            sup.decompose()
            count += 1

    # Remove Notes/Endnotes/Footnotes sections
    sections = _remove_section_by_heading(soup, NOTES_HEADINGS)
    count += sections

    # Remove orphaned endnote anchor targets
    for a in soup.find_all('a', id=True):
        aid = a['id']
        if aid.startswith(('endnote_', 'footnote_')):
            # Remove the containing paragraph if it's a note entry
            parent = a.find_parent('p')
            if parent:
                parent.decompose()
                count += 1

    return count


def _strip_index(soup):
    """Remove Index sections. Returns count."""
    return _remove_section_by_heading(soup, INDEX_HEADINGS)


def _strip_hyperlinks(soup):
    """Strip <a href> tags but keep text and <a id> anchors. Returns count."""
    count = 0
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Preserve internal footnote navigation anchors (they have both id and href)
        if a.get('id'):
            # Keep the element but remove the href
            del a['href']
            continue
        # Replace the <a> with its text content
        a.unwrap()
        count += 1
    return count


def _strip_front_matter(soup):
    """Remove front-matter sections that appear BEFORE the first chapter heading. Returns count."""
    count = 0
    # Find the first chapter heading to establish the boundary
    first_chapter = None
    for heading in soup.find_all(['h1', 'h2']):
        text = heading.get_text(strip=True)
        if CHAPTER_HEADING.match(text) or (not FRONT_MATTER_HEADINGS.match(text) and not text.lower().startswith('front matter')):
            first_chapter = heading
            break

    for heading in soup.find_all(['h1', 'h2']):
        # Stop once we've passed the first chapter heading
        if first_chapter and heading == first_chapter:
            break
        text = heading.get_text(strip=True)
        if FRONT_MATTER_HEADINGS.match(text):
            to_remove = [heading]
            sibling = heading.next_sibling
            while sibling:
                next_sib = sibling.next_sibling
                if hasattr(sibling, 'name') and sibling.name in ('h1', 'h2'):
                    break
                to_remove.append(sibling)
                sibling = next_sib
            for el in to_remove:
                el.extract()
            count += 1
    return count


def _strip_back_matter(soup):
    """Remove everything from first back-matter heading to end. Returns count."""
    count = 0
    for heading in soup.find_all(['h1', 'h2']):
        text = heading.get_text(strip=True)
        if BACK_MATTER_HEADINGS.match(text):
            # Check this isn't a chapter heading (e.g. "Appendix" used as chapter title
            # inside the body) — only match if in the last ~40% of the document
            to_remove = [heading]
            sibling = heading.next_sibling
            while sibling:
                next_sib = sibling.next_sibling
                to_remove.append(sibling)
                sibling = next_sib
            for el in to_remove:
                el.extract()
            count += 1
            break  # Everything after is already removed
    return count


def _strip_images(soup):
    """Remove <img> tags and empty <figure>/<figcaption>. Returns count."""
    count = 0
    for img in soup.find_all('img'):
        img.decompose()
        count += 1
    # Clean up empty figure/figcaption
    for tag_name in ('figcaption', 'figure'):
        for el in soup.find_all(tag_name):
            if not el.get_text(strip=True):
                el.decompose()
    return count


def _strip_block_quotes(soup):
    """Convert <blockquote> to <p>, keeping content. Returns count."""
    count = 0
    for bq in soup.find_all('blockquote'):
        # If blockquote contains <p> children, unwrap the blockquote
        if bq.find('p'):
            bq.unwrap()
        else:
            # Replace with a <p>
            new_p = soup.new_tag('p')
            new_p.string = bq.get_text()
            bq.replace_with(new_p)
        count += 1
    return count


# ── TXT filter (for legacy non-HTML path) ────────────────────────────────────

def _filter_txt(text, flags):
    """Filter plain-text/Markdown content by heading pattern matching."""
    lines = text.split('\n')
    result = []
    skip_until_heading = False
    removed = {}

    heading_re = re.compile(r'^#{1,3}\s+(.+)$')  # Markdown headings

    for line in lines:
        m = heading_re.match(line)
        if m:
            heading_text = m.group(1).strip()
            skip_this = False

            if flags.get('no_footnotes') and NOTES_HEADINGS.match(heading_text):
                skip_this = True
                removed['footnotes'] = removed.get('footnotes', 0) + 1
            elif flags.get('no_index') and INDEX_HEADINGS.match(heading_text):
                skip_this = True
                removed['index_sections'] = removed.get('index_sections', 0) + 1
            elif flags.get('no_front_matter') and FRONT_MATTER_HEADINGS.match(heading_text):
                skip_this = True
                removed['front_matter_sections'] = removed.get('front_matter_sections', 0) + 1
            elif flags.get('no_back_matter') and BACK_MATTER_HEADINGS.match(heading_text):
                skip_this = True
                removed['back_matter_sections'] = removed.get('back_matter_sections', 0) + 1

            if skip_this:
                skip_until_heading = True
                continue
            else:
                skip_until_heading = False

        if skip_until_heading:
            continue

        result.append(line)

    return '\n'.join(result), removed


# ── Main API ─────────────────────────────────────────────────────────────────

def _resolve_flags(profile='full', **kwargs):
    """Merge profile preset with individual flag overrides."""
    flags = dict(PROFILES.get(profile, {}))
    for key in ('no_footnotes', 'no_index', 'no_hyperlinks', 'no_front_matter',
                'no_back_matter', 'no_images', 'no_block_quotes'):
        if kwargs.get(key):
            flags[key] = True
    return flags


def filter_html(html_str, profile='full', **kwargs):
    """Filter HTML content. Returns filtered HTML string."""
    filtered, _ = filter_html_with_report(html_str, profile, **kwargs)
    return filtered


def filter_html_with_report(html_str, profile='full', **kwargs):
    """Filter HTML and return (filtered_html, report_dict)."""
    flags = _resolve_flags(profile, **kwargs)

    if not any(flags.values()):
        return html_str, {'profile': profile, 'removed': {}, 'size_reduction_percent': 0}

    original_size = len(html_str)
    soup = BeautifulSoup(html_str, 'html.parser')
    removed = {}

    # Order matters: strip footnotes before back matter (Notes is both)
    if flags.get('no_footnotes'):
        n = _strip_footnotes(soup)
        if n: removed['footnotes'] = n

    if flags.get('no_index'):
        n = _strip_index(soup)
        if n: removed['index_sections'] = n

    if flags.get('no_hyperlinks'):
        n = _strip_hyperlinks(soup)
        if n: removed['hyperlinks'] = n

    if flags.get('no_front_matter'):
        n = _strip_front_matter(soup)
        if n: removed['front_matter_sections'] = n

    if flags.get('no_back_matter'):
        n = _strip_back_matter(soup)
        if n: removed['back_matter_sections'] = n

    if flags.get('no_images'):
        n = _strip_images(soup)
        if n: removed['images'] = n

    if flags.get('no_block_quotes'):
        n = _strip_block_quotes(soup)
        if n: removed['block_quotes'] = n

    result = str(soup)
    new_size = len(result)
    reduction = round((1 - new_size / original_size) * 100, 1) if original_size > 0 else 0

    report = {
        'profile': profile,
        'removed': removed,
        'size_reduction_percent': reduction,
    }

    return result, report


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Filter ebook content by profile/flags.')
    ap.add_argument('--input', required=True, help='Input HTML or TXT file')
    ap.add_argument('--output', required=True, help='Output filtered file')
    ap.add_argument('--profile', default='full',
                    choices=['full', 'clean-read', 'text-only'],
                    help='Conversion profile preset (default: full)')
    ap.add_argument('--no-footnotes', action='store_true')
    ap.add_argument('--no-index', action='store_true')
    ap.add_argument('--no-hyperlinks', action='store_true')
    ap.add_argument('--no-front-matter', action='store_true')
    ap.add_argument('--no-back-matter', action='store_true')
    ap.add_argument('--no-images', action='store_true')
    ap.add_argument('--no-block-quotes', action='store_true')

    args = ap.parse_args()

    if not os.path.isfile(args.input):
        sys.exit(f"ERROR: input file not found: {args.input}")

    with open(args.input, 'r', encoding='utf-8') as f:
        content = f.read()

    is_html = args.input.lower().endswith(('.html', '.htm'))

    flag_kwargs = {
        'no_footnotes': args.no_footnotes,
        'no_index': args.no_index,
        'no_hyperlinks': args.no_hyperlinks,
        'no_front_matter': args.no_front_matter,
        'no_back_matter': args.no_back_matter,
        'no_images': args.no_images,
        'no_block_quotes': args.no_block_quotes,
    }

    if is_html:
        result, report = filter_html_with_report(content, args.profile, **flag_kwargs)
    else:
        flags = _resolve_flags(args.profile, **flag_kwargs)
        result, removed = _filter_txt(content, flags)
        original_size = len(content)
        new_size = len(result)
        reduction = round((1 - new_size / original_size) * 100, 1) if original_size > 0 else 0
        report = {
            'profile': args.profile,
            'removed': removed,
            'size_reduction_percent': reduction,
        }

    report['output_file'] = args.output

    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(result)

    # JSON report to stdout for PowerShell to parse
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
```

### Step 1.5: Run tests — verify they pass

- [ ] **Run the test suite**

Run: `python tools/test_filter_content.py -v`
Expected: All tests PASS

### Step 1.6: Commit Task 1

- [ ] **Commit filter script and tests**

```bash
git add tools/filter_content.py tools/test_filter_content.py
git commit -m "feat: add content filter script with profile support and tests"
```

---

## Task 2: Add `--skip-footnotes` Flag to `pdf_to_balabolka.py`

**Files:**
- Modify: `tools/pdf_to_balabolka.py` — argparse block (~line 8603), `_link_endnotes` call (~line 8014)

When `--skip-footnotes` is passed, the `_link_endnotes()` call at line 8014 is skipped entirely. This avoids doing expensive footnote linking work that will be immediately stripped by `filter_content.py`.

### Step 2.1: Add the argparse flag

- [ ] **Add `--skip-footnotes` argument near other flags**

Find the argparse section (around line 8603 where `--no-ocr` is defined). Add:

```python
ap.add_argument("--skip-footnotes", action="store_true",
                help="Skip footnote/endnote linking (used when profile strips footnotes)")
```

### Step 2.2: Pass flag through to extraction logic

- [ ] **Skip `_link_endnotes()` when flag is set**

At `tools/pdf_to_balabolka.py:8014`, the call is:
```python
html = _link_endnotes(html, log)
```

Wrap it in a conditional. The `args` object needs to be accessible here. Trace how `args` flows to the `process_kindle_html()` function (line 7980, which contains line 8014). The function receives a `skip_footnotes` parameter. Add to its signature and call site.

In the function definition at line 7980 (`def process_kindle_html`), add `skip_footnotes=False` parameter.

At line 8014, change:
```python
# Before:
html = _link_endnotes(html, log)
# After:
if not skip_footnotes:
    html = _link_endnotes(html, log)
else:
    log("  Skipping endnote linking (--skip-footnotes)")
```

In the `main()` function at line 8696 where `process_kindle_html()` is called, pass `skip_footnotes=args.skip_footnotes`:
```python
process_kindle_html(input_path, html_output, log_fn, api_key=args.api_key,
                    force_columns=args.force_columns,
                    apply_ai_fixes=args.apply_ai_fixes,
                    skip_footnotes=args.skip_footnotes)
```

### Step 2.3: Verify no regression

- [ ] **Run the pipeline test suite (default behavior unchanged)**

Run: `python tools/test_pipeline.py --quick`
Expected: All 5 test books pass — the flag is `False` by default, so `_link_endnotes` still runs.

### Step 2.4: Commit Task 2

- [ ] **Commit the Python flag**

```bash
git add tools/pdf_to_balabolka.py
git commit -m "feat: add --skip-footnotes flag to pdf_to_balabolka.py"
```

---

## Task 3: Add Profile Parameters to `Convert-ToKindle`

**Files:**
- Modify: `module/EbookAutomation.psm1:547-583` (param block)
- Modify: `module/EbookAutomation.psm1:1328-1330` (filter insertion point)
- Modify: `module/EbookAutomation.psm1:767-808` (Python arg building — add --skip-footnotes)

### Step 3.1: Add parameters to Convert-ToKindle param block

- [ ] **Add `-Profile` and `-No*` switch parameters**

At `module/EbookAutomation.psm1` line 583 (end of param block, before the closing `)`), add:

```powershell
    [ValidateSet('full','clean-read','text-only')]
    [string]$Profile = 'full',

    [switch]$NoFootnotes,
    [switch]$NoIndex,
    [switch]$NoHyperlinks,
    [switch]$NoFrontMatter,
    [switch]$NoBackMatter,
    [switch]$NoImages,
    [switch]$NoBlockQuotes
```

### Step 3.2: Pass `--skip-footnotes` to Python extraction (both PDF and EPUB paths)

- [ ] **Add --skip-footnotes to Python args when footnotes will be stripped**

**PDF path:** At `module/EbookAutomation.psm1` around line 808 (after the existing arg building), add:

```powershell
# Skip footnote linking if profile/flag will strip them anyway
$effectiveNoFootnotes = $NoFootnotes -or $Profile -in @('clean-read', 'text-only')
if ($effectiveNoFootnotes) {
    $pyArgs += " --skip-footnotes"
}
```

**EPUB path:** At `module/EbookAutomation.psm1` around line 1079 (where `$pyArgs` is built for EPUB extraction), add the same flag:

```powershell
$pyArgs = "$toolPath --input `"$InputFile`" --mode kindle --output-dir `"$tempDir`" --epub-html"
# Skip footnote linking if profile/flag will strip them anyway
$effectiveNoFootnotes = $NoFootnotes -or $Profile -in @('clean-read', 'text-only')
if ($effectiveNoFootnotes) {
    $pyArgs += " --skip-footnotes"
}
```

### Step 3.3: Insert content filter invocation after fix engine

- [ ] **Add filter step between fix engine (line 1328) and Calibre (line 1330)**

At `module/EbookAutomation.psm1` line 1329 (the blank line between fix engine and Calibre), insert:

```powershell
    # ── Apply content profile filter ──────────────────────────────────────────
    $needsFilter = ($Profile -ne 'full') -or $NoFootnotes -or $NoIndex -or $NoHyperlinks -or $NoFrontMatter -or $NoBackMatter -or $NoImages -or $NoBlockQuotes
    # Only filter intermediate files (HTML/TXT), not the original source ebook
    if ($needsFilter -and $convertInput -and ($convertInput -ne $InputFile) -and (Test-Path $convertInput)) {
        try {
            $filterScript = Join-Path $script:ModuleRoot 'tools' 'filter_content.py'
            # Ensure $python is set (it's assigned in PDF/EPUB extraction blocks)
            if (-not $python) { $python = (Get-EbookConfig).paths.python }
            if (Test-Path $filterScript) {
                $filteredPath = [System.IO.Path]::ChangeExtension($convertInput, '.filtered' + [System.IO.Path]::GetExtension($convertInput))

                $filterArgs = "`"$filterScript`" --input `"$convertInput`" --output `"$filteredPath`""
                if ($Profile -ne 'full') { $filterArgs += " --profile $Profile" }
                if ($NoFootnotes)   { $filterArgs += " --no-footnotes" }
                if ($NoIndex)       { $filterArgs += " --no-index" }
                if ($NoHyperlinks)  { $filterArgs += " --no-hyperlinks" }
                if ($NoFrontMatter) { $filterArgs += " --no-front-matter" }
                if ($NoBackMatter)  { $filterArgs += " --no-back-matter" }
                if ($NoImages)      { $filterArgs += " --no-images" }
                if ($NoBlockQuotes) { $filterArgs += " --no-block-quotes" }

                Write-EbookLog "Kindle: filtering content (profile=$Profile)..."

                $filterGuid   = [guid]::NewGuid().ToString('N')
                $filterStdout = Join-Path $env:TEMP "filter_stdout_$filterGuid.txt"
                $filterStderr = Join-Path $env:TEMP "filter_stderr_$filterGuid.txt"

                $filterProc = Start-Process -FilePath $python -ArgumentList $filterArgs `
                                            -NoNewWindow -Wait -PassThru `
                                            -RedirectStandardOutput $filterStdout `
                                            -RedirectStandardError $filterStderr

                if ($filterProc.ExitCode -eq 0 -and (Test-Path $filteredPath)) {
                    # Parse JSON report from stdout
                    if (Test-Path $filterStdout) {
                        $filterReport = Get-Content $filterStdout -Raw -ErrorAction SilentlyContinue
                        Remove-Item $filterStdout -ErrorAction SilentlyContinue
                        if ($filterReport) {
                            try {
                                $filterJson = $filterReport | ConvertFrom-Json
                                $removedItems = ($filterJson.removed.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ', '
                                if ($removedItems) {
                                    Write-EbookLog "Kindle: content filter removed: $removedItems ($($filterJson.size_reduction_percent)% size reduction)" -Level SUCCESS
                                }
                                $stepTimings['ContentFilter'] = "removed $removedItems ($($filterJson.size_reduction_percent)%)"
                            } catch { }
                        }
                    }
                    $convertInput = $filteredPath
                } else {
                    Write-EbookLog "Kindle: content filter failed (non-blocking, using unfiltered)" -Level WARN
                }

                # Clean up stderr
                if (Test-Path $filterStderr) {
                    $stderrContent = Get-Content $filterStderr -Raw -ErrorAction SilentlyContinue
                    if ($stderrContent.Trim()) {
                        Write-EbookLog "  Filter: $($stderrContent.Trim())" -Level WARN
                    }
                    Remove-Item $filterStderr -ErrorAction SilentlyContinue
                }
            }
        } catch {
            Write-EbookLog "Kindle: content filter failed (non-blocking) -- $_" -Level WARN
        }
    }
```

### Step 3.4: Skip AI quality pass for lean profiles

- [ ] **Skip AI quality pass when profile is text-only**

Find where `--api-key` is added to Python args (around line 798-808). Wrap the quality pass enablement:

```powershell
# Skip AI quality pass for text-only profile (less content = less risk)
$skipQualityPass = $Profile -eq 'text-only'
if (-not $skipQualityPass) {
    # ... existing --api-key logic ...
}
```

### Step 3.5: Verify default behavior unchanged

- [ ] **Test with no profile flag (should produce identical output)**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Convert-ToKindle -InputFile 'test_input.pdf' -UseHtmlExtraction -NoCache"`

Then: `python tools/test_pipeline.py --quick`
Expected: All test books pass, no regression.

### Step 3.6: Commit Task 3

- [ ] **Commit PowerShell changes**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: add -Profile and -No* params to Convert-ToKindle with filter integration"
```

---

## Task 4: Add Profile Parameters to `Invoke-EbookPipeline` and `Invoke-ConvergeLoop`

**Files:**
- Modify: `module/EbookAutomation.psm1:2445-2456` (Invoke-EbookPipeline param block)
- Modify: `module/EbookAutomation.psm1:2652` (Invoke-EbookPipeline → Convert-ToKindle call)
- Modify: `module/EbookAutomation.psm1:3914-3924` (Invoke-ConvergeLoop param block)
- Modify: `module/EbookAutomation.psm1:4194-4197` (Invoke-ConvergeLoop → Convert-ToKindle flag passthrough)

### Step 4.1: Add parameters to Invoke-EbookPipeline

- [ ] **Add `-Profile` and `-No*` params to Invoke-EbookPipeline param block**

At `module/EbookAutomation.psm1` line 2456 (end of Invoke-EbookPipeline param block), add the same parameter set as Convert-ToKindle:

```powershell
    [ValidateSet('full','clean-read','text-only')]
    [string]$Profile = 'full',

    [switch]$NoFootnotes,
    [switch]$NoIndex,
    [switch]$NoHyperlinks,
    [switch]$NoFrontMatter,
    [switch]$NoBackMatter,
    [switch]$NoImages,
    [switch]$NoBlockQuotes
```

### Step 4.2: Pass through to Convert-ToKindle call

- [ ] **Update the Convert-ToKindle call at line 2652 to pass profile params**

Change line 2652 to include the new parameters:

```powershell
$kindleOk = Convert-ToKindle -InputFile $workCopy -OutputDir $kindleDir `
    -UseHtmlExtraction:$useHtml `
    -UseClaudeChapters:$UseClaudeChapters `
    -UseOCR:$UseOCR `
    -ForceColumns:$ForceColumns `
    -ValidateVisual:$ValidateVisual `
    -NoCache:$NoCache `
    -ProduceEpub:$emailActive `
    -ApplyAIFixes:$ApplyAIFixes `
    -Profile $Profile `
    -NoFootnotes:$NoFootnotes `
    -NoIndex:$NoIndex `
    -NoHyperlinks:$NoHyperlinks `
    -NoFrontMatter:$NoFrontMatter `
    -NoBackMatter:$NoBackMatter `
    -NoImages:$NoImages `
    -NoBlockQuotes:$NoBlockQuotes
```

### Step 4.3: Add parameters to Invoke-ConvergeLoop

- [ ] **Add `-Profile` and `-No*` params to Invoke-ConvergeLoop param block**

At `module/EbookAutomation.psm1` line 3923 (after `$CostLimit`), add:

```powershell
        [ValidateSet('full','clean-read','text-only')]
        [string]$Profile = 'full',

        [switch]$NoFootnotes,
        [switch]$NoIndex,
        [switch]$NoHyperlinks,
        [switch]$NoFrontMatter,
        [switch]$NoBackMatter,
        [switch]$NoImages,
        [switch]$NoBlockQuotes
```

### Step 4.4: Pass profile flags through converge loop iterations

- [ ] **Add profile flags to `$convertParams` in the converge loop**

At `module/EbookAutomation.psm1` line 4197 (after the `foreach ($flag in $strategy.Flags...)` block), add:

```powershell
        # Pass through profile flags (user preference, not strategy-dependent)
        if ($Profile -ne 'full') { $convertParams['Profile'] = $Profile }
        if ($NoFootnotes)   { $convertParams['NoFootnotes']   = $true }
        if ($NoIndex)       { $convertParams['NoIndex']       = $true }
        if ($NoHyperlinks)  { $convertParams['NoHyperlinks']  = $true }
        if ($NoFrontMatter) { $convertParams['NoFrontMatter'] = $true }
        if ($NoBackMatter)  { $convertParams['NoBackMatter']  = $true }
        if ($NoImages)      { $convertParams['NoImages']      = $true }
        if ($NoBlockQuotes) { $convertParams['NoBlockQuotes'] = $true }
```

### Step 4.5: Add scan recommendation log

- [ ] **Add scan detection warning in Invoke-ConvergeLoop**

At `module/EbookAutomation.psm1` after the classification parsing (~line 3997, after `$classification = $classifyJson | ConvertFrom-Json`), add:

```powershell
            if ($classification.classification -in @('scan_with_text', 'scan_no_text') -and $Profile -eq 'full') {
                Write-EbookLog "ConvergeLoop: scanned PDF detected -- consider using -Profile text-only for best Kindle performance" -Level WARN
            }
```

### Step 4.6: Commit Task 4

- [ ] **Commit pipeline and converge loop changes**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: pass -Profile and -No* params through pipeline and converge loop"
```

---

## Task 5: Update Module Manifest Export

**Files:**
- Check: `module/EbookAutomation.psd1` — verify no manifest changes needed (functions already exported via wildcard or explicit list)

### Step 5.1: Verify exports

- [ ] **Check that the module loads without errors**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force -Verbose 2>&1 | Select-String -Pattern 'Error|WARNING' | head -5"`

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; (Get-Command Convert-ToKindle).Parameters.Keys | Where-Object { $_ -match 'Profile|NoFootnotes|NoIndex' }"`
Expected: `Profile`, `NoFootnotes`, `NoIndex` all visible

### Step 5.2: Commit if needed

- [ ] **Commit manifest changes (if any)**

```bash
git add module/EbookAutomation.psd1
git commit -m "chore: update module manifest for profile parameters"
```

---

## Task 6: Integration Testing

### Step 6.1: Filter unit tests

- [ ] **Run filter unit tests**

Run: `python tools/test_filter_content.py -v`
Expected: All pass

### Step 6.2: Pipeline regression test

- [ ] **Run full pipeline test (default profile = full)**

Run: `python tools/test_pipeline.py --quick`
Expected: All 5 test books pass with no regression

### Step 6.3: Test clean-read profile on a real book

- [ ] **Convert Burge with clean-read profile**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Convert-ToKindle -InputFile (Get-ChildItem 'F:\Books\Bible Study\Burge*' | Select-Object -First 1).FullName -UseHtmlExtraction -NoCache -Profile clean-read"`

Verify in output:
- Log shows "filtering content (profile=clean-read)"
- Log shows removal counts (footnotes, index, hyperlinks, front matter)
- No footnote markers in output HTML
- No index section
- Chapters and body text preserved
- TOC still works

### Step 6.4: Test text-only profile

- [ ] **Convert Burge with text-only profile**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Convert-ToKindle -InputFile (Get-ChildItem 'F:\Books\Bible Study\Burge*' | Select-Object -First 1).FullName -UseHtmlExtraction -NoCache -Profile text-only"`

Verify:
- Only chapter headings and body paragraphs remain
- No back matter
- No front matter
- Smallest file size

### Step 6.5: Test individual flag

- [ ] **Convert with just -NoIndex**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Convert-ToKindle -InputFile (Get-ChildItem 'F:\Books\Bible Study\Burge*' | Select-Object -First 1).FullName -UseHtmlExtraction -NoCache -NoIndex"`

Verify: Index removed, everything else preserved

### Step 6.6: Test scan recommendation

- [ ] **Convert a scanned PDF and check for recommendation log**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Invoke-ConvergeLoop -InputFile (Get-ChildItem 'F:\Books\Bible Study\Fruchtenbaum*' | Select-Object -First 1).FullName -MaxIterations 1"`

Verify: Log shows "scanned PDF detected — consider using -Profile text-only"

### Step 6.7: File size comparison

- [ ] **Compare output sizes across profiles for the same book**

After tasks 6.3-6.5, compare file sizes:
```
Burge full:       X.X MB
Burge clean-read: X.X MB (expected: 10-20% smaller)
Burge text-only:  X.X MB (expected: 20-40% smaller)
```

### Step 6.8: Final regression check

- [ ] **Run full pipeline test one final time**

Run: `python tools/test_pipeline.py --quick`
Expected: All 5 test books pass

### Step 6.9: Commit and push

- [ ] **Final commit and push**

```bash
git add -A
git commit -m "test: verify conversion profiles across all test books"
git push origin feature/conversion-profiles
```
