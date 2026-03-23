"""Tests for filter_content.py content filtering."""
import sys, os, json, tempfile, unittest
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
        self.assertNotIn('<sup>', result)
        self.assertNotIn('Abraham, 12', result)
        self.assertNotIn('href="https', result)
        self.assertNotIn('Endorsements', result)
        self.assertIn('Bibliography', result)
        self.assertIn('Chapter 1', result)

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
        self.assertIn('<sup>', result)


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
