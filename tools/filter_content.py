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
from typing import Any

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
        'no_bibliography': True,
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
    r"translator'?s?\s+note|editor'?s?\s+note|introduction\s+to\s+the\s+series)$",
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

BIBLIOGRAPHY_HEADINGS = re.compile(
    r'^(bibliography|references?|works?\s+cited|sources?\s+cited|'
    r'selected\s+bibliography|annotated\s+bibliography|'
    r'further\s+reading|suggested\s+reading|recommended\s+reading|'
    r'list\s+of\s+(?:works|references|sources)\s+cited)$',
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

    # Remove <sup> elements containing footnote anchors
    for sup in soup.find_all('sup'):
        a_child = sup.find('a')
        if a_child and a_child.get('href', '').startswith('#'):
            sup.decompose()
            count += 1
        elif sup.get_text(strip=True).isdigit():
            sup.decompose()
            count += 1

    # Remove Notes/Endnotes/Footnotes sections
    sections = _remove_section_by_heading(soup, NOTES_HEADINGS)
    count += sections

    # Remove orphaned endnote anchor targets
    for a in soup.find_all('a', id=True):
        aid = a['id']
        if aid.startswith(('endnote_', 'footnote_')):
            parent = a.find_parent('p')
            if parent:
                parent.decompose()
                count += 1

    return count


def _strip_index(soup):
    """Remove Index sections. Returns count."""
    return _remove_section_by_heading(soup, INDEX_HEADINGS)


def _strip_bibliography(soup):
    """Remove Bibliography/References sections. Returns count."""
    return _remove_section_by_heading(soup, BIBLIOGRAPHY_HEADINGS)


def _strip_hyperlinks(soup):
    """Strip <a href> tags but keep text and <a id> anchors. Returns count."""
    count = 0
    for a in soup.find_all('a', href=True):
        if a.get('id'):
            del a['href']
            continue
        a.unwrap()
        count += 1
    return count


def _strip_front_matter(soup):
    """Remove front-matter sections that appear BEFORE the first chapter heading. Returns count."""
    count = 0
    first_chapter = None
    for heading in soup.find_all(['h1', 'h2']):
        text = heading.get_text(strip=True)
        if CHAPTER_HEADING.match(text) or (not FRONT_MATTER_HEADINGS.match(text) and not text.lower().startswith('front matter')):
            first_chapter = heading
            break

    for heading in soup.find_all(['h1', 'h2']):
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
            to_remove = [heading]
            sibling = heading.next_sibling
            while sibling:
                next_sib = sibling.next_sibling
                to_remove.append(sibling)
                sibling = next_sib
            for el in to_remove:
                el.extract()
            count += 1
            break
    return count


def _strip_images(soup):
    """Remove <img> tags and their <figure>/<figcaption> containers. Returns count."""
    count = 0
    # Remove entire <figure> elements (they contain <img> + optional <figcaption>)
    for fig in soup.find_all('figure'):
        fig.decompose()
        count += 1
    # Remove any standalone <img> tags not inside <figure>
    for img in soup.find_all('img'):
        img.decompose()
        count += 1
    # Remove any orphaned <figcaption> elements
    for fc in soup.find_all('figcaption'):
        fc.decompose()
    return count


def _strip_block_quotes(soup):
    """Convert <blockquote> to <p>, keeping content. Returns count."""
    count = 0
    for bq in soup.find_all('blockquote'):
        if bq.find('p'):
            bq.unwrap()
        else:
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

    heading_re = re.compile(r'^#{1,3}\s+(.+)$')

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
    for key in ('no_footnotes', 'no_index', 'no_bibliography', 'no_hyperlinks',
                'no_front_matter', 'no_back_matter', 'no_images', 'no_block_quotes'):
        if kwargs.get(key):
            flags[key] = True
    return flags


def filter_html(html_str: str, profile: str = 'full', **kwargs: bool) -> str:
    """Filter HTML content. Returns filtered HTML string."""
    filtered, _ = filter_html_with_report(html_str, profile, **kwargs)
    return filtered


def filter_html_with_report(html_str: str, profile: str = 'full', **kwargs: bool) -> tuple[str, dict[str, Any]]:
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

    if flags.get('no_bibliography'):
        n = _strip_bibliography(soup)
        if n: removed['bibliography_sections'] = n

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

def main() -> None:
    ap = argparse.ArgumentParser(description='Filter ebook content by profile/flags.')
    ap.add_argument('--input', required=True, help='Input HTML or TXT file')
    ap.add_argument('--output', required=True, help='Output filtered file')
    ap.add_argument('--profile', default='full',
                    choices=['full', 'clean-read', 'text-only'],
                    help='Conversion profile preset (default: full)')
    ap.add_argument('--no-footnotes', action='store_true')
    ap.add_argument('--no-index', action='store_true')
    ap.add_argument('--no-bibliography', action='store_true')
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
        'no_bibliography': args.no_bibliography,
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
