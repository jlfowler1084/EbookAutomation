"""Unit tests for EPUB heading extraction and paragraph matching (EB-20).

Tests cover _extract_epub_nav_headings, extract_epub_headings, and
match_epub_headings_to_paragraphs without requiring real EPUB files.
All EPUB I/O is mocked via unittest.mock.

Usage:
    python tools/test_epub_headings.py
"""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from extract_tts_text import (
    _extract_epub_nav_headings,
    extract_epub_headings,
    match_epub_headings_to_paragraphs,
)

LOG = lambda msg: None  # silent logger


# ---------------------------------------------------------------------------
# _extract_epub_nav_headings
# ---------------------------------------------------------------------------

EPUB3_NAV_HTML = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
<nav epub:type="toc">
  <ol>
    <li><a href="ch1.xhtml">Introduction</a></li>
    <li><a href="ch2.xhtml">A World on Fire</a>
      <ol>
        <li><a href="ch2a.xhtml">The Opening Shot</a></li>
      </ol>
    </li>
    <li><a href="ch3.xhtml">Aftermath</a></li>
  </ol>
</nav>
</body>
</html>"""

EPUB2_NCX_HTML = b"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">
  <navMap>
    <navPoint id="np1" playOrder="1">
      <navLabel><text>Prologue</text></navLabel>
      <content src="prologue.xhtml"/>
    </navPoint>
    <navPoint id="np2" playOrder="2">
      <navLabel><text>Part One</text></navLabel>
      <content src="part1.xhtml"/>
      <navPoint id="np2a" playOrder="3">
        <navLabel><text>Chapter 1</text></navLabel>
        <content src="ch1.xhtml"/>
      </navPoint>
    </navPoint>
    <navPoint id="np3" playOrder="4">
      <navLabel><text>Epilogue</text></navLabel>
      <content src="epilogue.xhtml"/>
    </navPoint>
  </navMap>
</ncx>"""


def _make_nav_item(html_bytes):
    item = MagicMock()
    item.get_content.return_value = html_bytes
    return item


def _make_book(nav_html_bytes):
    """Build a minimal mock ebooklib book with one nav item."""
    import ebooklib
    book = MagicMock()
    book.get_items_of_type.return_value = [_make_nav_item(nav_html_bytes)]
    return book


class TestExtractEpubNavHeadingsEpub3(unittest.TestCase):

    def setUp(self):
        self.book = _make_book(EPUB3_NAV_HTML)

    def test_returns_top_level_as_level1(self):
        headings = _extract_epub_nav_headings(self.book)
        level1 = [h for h in headings if h['level'] == 1]
        titles = [h['title'] for h in level1]
        self.assertIn('Introduction', titles)
        self.assertIn('A World on Fire', titles)
        self.assertIn('Aftermath', titles)

    def test_nested_items_are_level2(self):
        headings = _extract_epub_nav_headings(self.book)
        level2 = [h for h in headings if h['level'] == 2]
        self.assertEqual(len(level2), 1)
        self.assertEqual(level2[0]['title'], 'The Opening Shot')

    def test_reading_order_preserved(self):
        headings = _extract_epub_nav_headings(self.book)
        titles = [h['title'] for h in headings]
        intro_idx = titles.index('Introduction')
        fire_idx = titles.index('A World on Fire')
        shot_idx = titles.index('The Opening Shot')
        aftermath_idx = titles.index('Aftermath')
        self.assertLess(intro_idx, fire_idx)
        self.assertLess(fire_idx, shot_idx)
        self.assertLess(shot_idx, aftermath_idx)

    def test_empty_nav_items_returns_empty(self):
        import ebooklib
        book = MagicMock()
        book.get_items_of_type.return_value = []
        result = _extract_epub_nav_headings(book)
        self.assertEqual(result, [])


class TestExtractEpubNavHeadingsEpub2(unittest.TestCase):

    def setUp(self):
        self.book = _make_book(EPUB2_NCX_HTML)

    def test_top_level_navpoints_are_level1(self):
        headings = _extract_epub_nav_headings(self.book)
        level1 = [h for h in headings if h['level'] == 1]
        titles = [h['title'] for h in level1]
        self.assertIn('Prologue', titles)
        self.assertIn('Part One', titles)
        self.assertIn('Epilogue', titles)

    def test_nested_navpoints_are_level2(self):
        headings = _extract_epub_nav_headings(self.book)
        level2 = [h for h in headings if h['level'] == 2]
        self.assertEqual(len(level2), 1)
        self.assertEqual(level2[0]['title'], 'Chapter 1')


class TestExtractEpubNavHeadingsBrokenContent(unittest.TestCase):

    def test_nav_item_exception_returns_empty(self):
        import ebooklib
        item = MagicMock()
        item.get_content.side_effect = OSError("disk error")
        book = MagicMock()
        book.get_items_of_type.return_value = [item]
        result = _extract_epub_nav_headings(book)
        self.assertEqual(result, [])

    def test_html_with_no_nav_or_navpoints_returns_empty(self):
        book = _make_book(b"<html><body><p>No nav here</p></body></html>")
        result = _extract_epub_nav_headings(book)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# extract_epub_headings (file-level function)
# ---------------------------------------------------------------------------

class TestExtractEpubHeadingsFallbackWhenImportMissing(unittest.TestCase):

    def test_import_error_returns_empty(self):
        with patch.dict('sys.modules', {'ebooklib': None, 'ebooklib.epub': None}):
            logs = []
            result = extract_epub_headings("fake.epub", logs.append)
            self.assertEqual(result, [])

    def test_epub_read_failure_returns_empty(self):
        with patch('ebooklib.epub.read_epub', side_effect=Exception("bad epub")):
            logs = []
            result = extract_epub_headings("bad.epub", logs.append)
            self.assertEqual(result, [])
            self.assertTrue(any("warn" in m for m in logs))


class TestExtractEpubHeadingsNavPath(unittest.TestCase):

    def test_returns_nav_headings_when_available(self):
        mock_book = _make_book(EPUB3_NAV_HTML)
        with patch('ebooklib.epub.read_epub', return_value=mock_book):
            logs = []
            result = extract_epub_headings("test.epub", logs.append)
            self.assertGreater(len(result), 0)
            titles = [h['title'] for h in result]
            self.assertIn('Introduction', titles)
            self.assertIn('A World on Fire', titles)

    def test_logs_heading_count(self):
        mock_book = _make_book(EPUB3_NAV_HTML)
        with patch('ebooklib.epub.read_epub', return_value=mock_book):
            logs = []
            extract_epub_headings("test.epub", logs.append)
            combined = " ".join(logs)
            self.assertIn("NCX/nav", combined)


class TestExtractEpubHeadingsHtmlFallback(unittest.TestCase):
    """When no nav/NCX headings exist, fall back to scanning h1-h3 tags."""

    def _make_spine_item(self, html_bytes):
        import ebooklib
        item = MagicMock()
        item.get_content.return_value = html_bytes
        item.get_type.return_value = ebooklib.ITEM_DOCUMENT
        item.get_id.return_value = "chapter1"
        return item

    def test_h1_tags_extracted_as_level1(self):
        html = b"<html><body><h1>The Beginning</h1><p>body text here</p></body></html>"
        spine_item = self._make_spine_item(html)

        empty_nav_book = MagicMock()
        empty_nav_book.get_items_of_type.return_value = []  # no nav items
        empty_nav_book.spine = [("chapter1", True)]
        empty_nav_book.get_items.return_value = [spine_item]

        with patch('ebooklib.epub.read_epub', return_value=empty_nav_book):
            logs = []
            result = extract_epub_headings("test.epub", logs.append)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['title'], 'The Beginning')
            self.assertEqual(result[0]['level'], 1)

    def test_h3_clamped_to_level2(self):
        html = b"<html><body><h3>Deep Subheading</h3></body></html>"
        spine_item = self._make_spine_item(html)

        empty_nav_book = MagicMock()
        empty_nav_book.get_items_of_type.return_value = []
        empty_nav_book.spine = [("chapter1", True)]
        empty_nav_book.get_items.return_value = [spine_item]

        with patch('ebooklib.epub.read_epub', return_value=empty_nav_book):
            result = extract_epub_headings("test.epub", LOG)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['level'], 2)

    def test_no_headings_anywhere_returns_empty(self):
        html = b"<html><body><p>Just a paragraph.</p></body></html>"
        spine_item = self._make_spine_item(html)

        empty_nav_book = MagicMock()
        empty_nav_book.get_items_of_type.return_value = []
        empty_nav_book.spine = [("chapter1", True)]
        empty_nav_book.get_items.return_value = [spine_item]

        with patch('ebooklib.epub.read_epub', return_value=empty_nav_book):
            result = extract_epub_headings("test.epub", LOG)
            self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# match_epub_headings_to_paragraphs
# ---------------------------------------------------------------------------

class TestMatchEpubHeadingsToParagraphsEdgeCases(unittest.TestCase):

    def test_empty_paragraphs_returns_empty_dict(self):
        headings = [{'title': 'Intro', 'level': 1}]
        result = match_epub_headings_to_paragraphs([], headings, LOG)
        self.assertEqual(result, {'parts': [], 'chapters': []})

    def test_empty_headings_returns_empty_dict(self):
        paras = ["Introduction", "Some body text."]
        result = match_epub_headings_to_paragraphs(paras, [], LOG)
        self.assertEqual(result, {'parts': [], 'chapters': []})

    def test_both_empty_returns_empty_dict(self):
        result = match_epub_headings_to_paragraphs([], [], LOG)
        self.assertEqual(result, {'parts': [], 'chapters': []})


class TestMatchEpubHeadingsToParagraphsExactMatch(unittest.TestCase):

    def test_exact_match_level1_goes_to_parts_when_mixed(self):
        # Level-1 only goes to 'parts' when level-2 headings also exist;
        # otherwise the flat-NCX demotion moves everything to 'chapters'.
        paras = ["Some preamble.", "Part One", "Chapter A", "Body text."]
        headings = [
            {'title': 'Part One', 'level': 1},
            {'title': 'Chapter A', 'level': 2},
        ]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertIn(1, result['parts'])
        self.assertIn(2, result['chapters'])

    def test_exact_match_level2_goes_to_chapters(self):
        paras = ["Preamble.", "Chapter 1", "Body text."]
        headings = [{'title': 'Chapter 1', 'level': 2}]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertIn(1, result['chapters'])
        self.assertEqual(result['parts'], [])

    def test_case_insensitive_match(self):
        paras = ["INTRODUCTION", "Body text."]
        headings = [{'title': 'Introduction', 'level': 2}]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertIn(0, result['chapters'])

    def test_whitespace_normalized_in_match(self):
        paras = ["A  World   on Fire", "Body."]
        headings = [{'title': 'A World on Fire', 'level': 2}]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertIn(0, result['chapters'])


class TestMatchEpubHeadingsToParagraphsSubstringMatch(unittest.TestCase):

    def test_heading_contained_in_short_paragraph(self):
        # "Introduction" is a substring of "Introduction: The Early Years"
        paras = ["Introduction: The Early Years", "Body text here."]
        headings = [{'title': 'Introduction', 'level': 2}]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertIn(0, result['chapters'])

    def test_long_paragraph_not_matched_by_substring(self):
        # A 25-word body paragraph should not match a short heading substring
        long_para = "This is a very long body paragraph that happens to contain " \
                    "the word Introduction somewhere in it and should not match."
        paras = [long_para]
        headings = [{'title': 'Introduction', 'level': 2}]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertEqual(result['chapters'], [])


class TestMatchEpubHeadingsToParagraphsFlatNcx(unittest.TestCase):
    """Flat NCX (all level-1 headings) → all demoted to 'chapters'."""

    def test_all_level1_demoted_to_chapters(self):
        paras = ["Chapter One", "Body.", "Chapter Two", "Body.", "Chapter Three", "Body."]
        headings = [
            {'title': 'Chapter One', 'level': 1},
            {'title': 'Chapter Two', 'level': 1},
            {'title': 'Chapter Three', 'level': 1},
        ]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertEqual(result['parts'], [])
        self.assertIn(0, result['chapters'])
        self.assertIn(2, result['chapters'])
        self.assertIn(4, result['chapters'])

    def test_mixed_levels_not_demoted(self):
        paras = ["Part One", "Chapter 1", "Body."]
        headings = [
            {'title': 'Part One', 'level': 1},
            {'title': 'Chapter 1', 'level': 2},
        ]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertIn(0, result['parts'])
        self.assertIn(1, result['chapters'])


class TestMatchEpubHeadingsToParagraphsOrdering(unittest.TestCase):

    def test_output_indices_are_sorted(self):
        # Headings provided out of document order
        paras = ["Alpha", "Beta", "Gamma", "Delta"]
        headings = [
            {'title': 'Delta', 'level': 2},
            {'title': 'Alpha', 'level': 2},
            {'title': 'Gamma', 'level': 2},
        ]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertEqual(result['chapters'], sorted(result['chapters']))

    def test_each_paragraph_matched_at_most_once(self):
        paras = ["Introduction", "Body text."]
        headings = [
            {'title': 'Introduction', 'level': 2},
            {'title': 'Introduction', 'level': 2},  # duplicate
        ]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        # Para 0 should appear only once in chapters
        self.assertEqual(result['chapters'].count(0), 1)


class TestMatchEpubHeadingsToParagraphsUnmatched(unittest.TestCase):

    def test_unmatched_heading_skipped_gracefully(self):
        paras = ["Some other text.", "More body."]
        headings = [{'title': 'Completely Missing Title', 'level': 2}]
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        self.assertEqual(result['chapters'], [])
        self.assertEqual(result['parts'], [])

    def test_very_short_heading_skipped(self):
        paras = ["A", "Body text."]
        headings = [{'title': 'A', 'level': 2}]  # single char — len < 2 after norm
        result = match_epub_headings_to_paragraphs(paras, headings, LOG)
        # Single char is skipped (< 2 chars check)
        self.assertEqual(result['chapters'], [])


if __name__ == '__main__':
    unittest.main()
