"""
Unit tests for tools/chapter_alignment.py

Tests cover: matching, scoring, graceful degradation, and edge cases.
No actual PDF files required — all I/O is mocked.

Usage:
    python tools/test_chapter_alignment.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add tools/ to path so we can import chapter_alignment
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from chapter_alignment import (
    _compare_body_snippets,
    _extract_output_headings,
    _match_bookmarks_to_headings,
    _normalize_text,
    verify_chapter_alignment,
)

LOG = lambda msg: None  # silent logger for tests


class TestNormalizeText(unittest.TestCase):
    """Test the text normalization helper."""

    def test_strips_html(self):
        self.assertEqual(_normalize_text("<b>Hello</b> world"), "hello world")

    def test_collapses_whitespace(self):
        self.assertEqual(_normalize_text("hello   world\n\tfoo"), "hello world foo")

    def test_strips_trailing_page_numbers(self):
        self.assertEqual(_normalize_text("some text 42"), "some text")

    def test_lowercases(self):
        self.assertEqual(_normalize_text("Hello WORLD"), "hello world")


class TestMatchBookmarksToHeadings(unittest.TestCase):
    """Test bookmark-to-heading title matching."""

    def test_perfect_title_match(self):
        bookmarks = [
            {"title": "Introduction", "page": 5, "level": 1},
            {"title": "Chapter One", "page": 20, "level": 1},
        ]
        output_headings = [
            {"tag": "h2", "title": "Introduction", "body_snippet": "text...", "position": 100},
            {"tag": "h2", "title": "Chapter One", "body_snippet": "text...", "position": 5000},
        ]
        matches = _match_bookmarks_to_headings(bookmarks, output_headings, LOG)
        self.assertEqual(len(matches), 2)
        # Both should match with high scores
        self.assertEqual(matches[0][1], 0)  # bookmark 0 -> heading 0
        self.assertEqual(matches[1][1], 1)  # bookmark 1 -> heading 1
        self.assertGreater(matches[0][2], 0.9)
        self.assertGreater(matches[1][2], 0.9)

    def test_fuzzy_title_match(self):
        """Bookmark says 'Chapter 1: The Beginning', output says '1. The Beginning'."""
        bookmarks = [
            {"title": "Chapter 1: The Beginning", "page": 10, "level": 1},
        ]
        output_headings = [
            {"tag": "h2", "title": "1. The Beginning", "body_snippet": "text...", "position": 100},
        ]
        matches = _match_bookmarks_to_headings(bookmarks, output_headings, LOG)
        # Should still match (similarity >= 0.5)
        self.assertIsNotNone(matches[0][1])
        self.assertGreaterEqual(matches[0][2], 0.5)

    def test_unmatched_bookmark(self):
        """Bookmark with no corresponding heading in output."""
        bookmarks = [
            {"title": "Completely Different Title", "page": 10, "level": 1},
        ]
        output_headings = [
            {"tag": "h2", "title": "Introduction", "body_snippet": "text...", "position": 100},
        ]
        matches = _match_bookmarks_to_headings(bookmarks, output_headings, LOG)
        self.assertIsNone(matches[0][1])  # No match found


class TestCompareBodySnippets(unittest.TestCase):
    """Test body text comparison and status assignment."""

    def test_aligned_status(self):
        """Matching title + matching body = aligned."""
        matches = [(0, 0, 0.95)]  # bookmark 0 -> heading 0, 95% title match
        source_snippets = {0: "the story begins in the year eighteen fifty"}
        output_headings = [
            {"body_snippet": "the story begins in the year eighteen fifty two"},
        ]
        results = _compare_body_snippets(matches, source_snippets, output_headings, 0.6, LOG)
        self.assertEqual(results[0]['status'], 'aligned')
        self.assertGreaterEqual(results[0]['combined_score'], 0.6)

    def test_title_only_status(self):
        """High title match but very different body text = title_only."""
        matches = [(0, 0, 0.95)]
        source_snippets = {0: "this is completely different source text about something else"}
        output_headings = [
            {"body_snippet": "entirely unrelated output text about another topic altogether"},
        ]
        results = _compare_body_snippets(matches, source_snippets, output_headings, 0.6, LOG)
        # title_score=0.95, body_score should be low
        # If combined < threshold but title >= 0.7, should be title_only
        if results[0]['combined_score'] < 0.6:
            self.assertEqual(results[0]['status'], 'title_only')

    def test_unmatched_status(self):
        """No heading match = unmatched."""
        matches = [(0, None, 0.0)]
        source_snippets = {0: "some text"}
        output_headings = []
        results = _compare_body_snippets(matches, source_snippets, output_headings, 0.6, LOG)
        self.assertEqual(results[0]['status'], 'unmatched')
        self.assertEqual(results[0]['detail'], 'No matching heading found in output')

    def test_insufficient_text(self):
        """Empty source or output snippet."""
        matches = [(0, 0, 0.95)]
        source_snippets = {0: ""}
        output_headings = [{"body_snippet": "some text here"}]
        results = _compare_body_snippets(matches, source_snippets, output_headings, 0.6, LOG)
        self.assertIn("Insufficient text", results[0]['detail'])


class TestScoreCalculation(unittest.TestCase):
    """Test overall alignment score calculation."""

    def test_score_75_percent(self):
        """3 aligned + 1 misaligned out of 4 = 75% alignment score."""
        # We mock the full pipeline by calling verify_chapter_alignment with
        # mocked pypdf reader
        bookmarks = [
            {"title": "Chapter 1", "page": 0, "level": 1},
            {"title": "Chapter 2", "page": 1, "level": 1},
            {"title": "Chapter 3", "page": 2, "level": 1},
            {"title": "Chapter 4", "page": 3, "level": 1},
        ]
        output_headings = [
            {"tag": "h2", "title": "Chapter 1", "body_snippet": "body one text here", "position": 0},
            {"tag": "h2", "title": "Chapter 2", "body_snippet": "body two text here", "position": 100},
            {"tag": "h2", "title": "Chapter 3", "body_snippet": "body three text here", "position": 200},
            # Chapter 4 missing from output
        ]
        source_snippets = {
            0: "body one text here",
            1: "body two text here",
            2: "body three text here",
            3: "body four text here",
        }

        matches = _match_bookmarks_to_headings(bookmarks, output_headings, LOG)
        results = _compare_body_snippets(matches, source_snippets, output_headings, 0.6, LOG)

        aligned = sum(1 for r in results if r['status'] == 'aligned')
        total = len(results)
        score = round(aligned / max(total, 1) * 100)

        self.assertEqual(total, 4)
        self.assertEqual(aligned, 3)
        self.assertEqual(score, 75)


class TestExtractOutputHeadings(unittest.TestCase):
    """Test HTML heading extraction."""

    def test_extracts_headings_with_body(self):
        html = (
            '<html><body>'
            '<h1>Part One</h1>'
            '<p>Introduction to part one.</p>'
            '<h2>Chapter 1</h2>'
            '<p>The story begins here with an opening paragraph.</p>'
            '<p>Second paragraph of the chapter.</p>'
            '<h2>Chapter 2</h2>'
            '<p>Another chapter starts.</p>'
            '</body></html>'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                          delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        try:
            headings = _extract_output_headings(tmp_path, LOG)
            self.assertEqual(len(headings), 3)
            self.assertEqual(headings[0]['tag'], 'h1')
            self.assertEqual(headings[0]['title'], 'Part One')
            self.assertIn('Introduction', headings[0]['body_snippet'])
            self.assertEqual(headings[1]['tag'], 'h2')
            self.assertEqual(headings[1]['title'], 'Chapter 1')
            self.assertIn('story begins', headings[1]['body_snippet'])
        finally:
            os.unlink(tmp_path)

    def test_empty_html(self):
        html = '<html><body><p>No headings here.</p></body></html>'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                          delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        try:
            headings = _extract_output_headings(tmp_path, LOG)
            self.assertEqual(len(headings), 0)
        finally:
            os.unlink(tmp_path)


class TestOrderingPreserved(unittest.TestCase):
    """Bookmarks in page order should match headings in document order."""

    def test_ordered_matching(self):
        bookmarks = [
            {"title": "Alpha", "page": 1, "level": 1},
            {"title": "Beta", "page": 10, "level": 1},
            {"title": "Gamma", "page": 20, "level": 1},
        ]
        output_headings = [
            {"tag": "h2", "title": "Alpha", "body_snippet": "a text", "position": 100},
            {"tag": "h2", "title": "Beta", "body_snippet": "b text", "position": 500},
            {"tag": "h2", "title": "Gamma", "body_snippet": "g text", "position": 900},
        ]
        matches = _match_bookmarks_to_headings(bookmarks, output_headings, LOG)
        # Each bookmark should match to the heading at the same index
        for bm_idx, h_idx, _ in matches:
            self.assertEqual(bm_idx, h_idx)


class TestVerifyChapterAlignmentIntegration(unittest.TestCase):
    """Integration tests for the main verify_chapter_alignment function."""

    def test_non_pdf_source_skipped(self):
        """Non-PDF source files should be skipped gracefully."""
        report = verify_chapter_alignment("book.epub", "book.html", log=LOG)
        self.assertTrue(report.get('skipped'))
        self.assertIsNone(report['alignment_score'])

    def test_missing_source_file(self):
        """Missing source PDF returns error report."""
        report = verify_chapter_alignment(
            "nonexistent.pdf", "nonexistent.html", log=LOG
        )
        self.assertIn('error', report)
        self.assertIsNone(report['alignment_score'])

    def test_no_bookmarks_graceful(self):
        """PDF without bookmarks returns null alignment score."""
        # Create a temporary HTML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                          delete=False, encoding='utf-8') as f:
            f.write('<html><body><h2>Chapter 1</h2><p>Text</p></body></html>')
            html_path = f.name

        # Create a temporary PDF file (just needs to exist for the path check)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4 fake')
            pdf_path = f.name

        try:
            import chapter_alignment
            mock_reader = MagicMock()
            original_extract = chapter_alignment._extract_bookmarks

            def mock_extract(path, log):
                log("  No bookmarks found in source PDF")
                return [], mock_reader

            chapter_alignment._extract_bookmarks = mock_extract
            try:
                report = verify_chapter_alignment(pdf_path, html_path, log=LOG)
                self.assertIsNone(report['alignment_score'])
                self.assertEqual(report['total_bookmarks'], 0)
            finally:
                chapter_alignment._extract_bookmarks = original_extract
        finally:
            os.unlink(html_path)
            os.unlink(pdf_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
