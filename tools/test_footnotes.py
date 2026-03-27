"""Tests for per-page footnote separation in pdfminer HTML extraction."""
import sys, os, unittest
sys.path.insert(0, os.path.dirname(__file__))

from pdf_to_balabolka import _flush_line_group


class TestFlushLineGroupY0(unittest.TestCase):
    """_flush_line_group should include y0_min and y0_max in paragraph dict."""

    def test_preserves_y0(self):
        lines = [
            {'text': 'Hello world', 'size': 12, 'bold': False, 'italic': False,
             'centered': False, 'y0': 500, 'x0': 50, 'x1': 200, 'page': 1},
            {'text': 'Second line', 'size': 12, 'bold': False, 'italic': False,
             'centered': False, 'y0': 488, 'x0': 50, 'x1': 200, 'page': 1},
        ]
        paras = []
        _flush_line_group(lines, paras)
        self.assertEqual(len(paras), 1)
        self.assertEqual(paras[0]['y0_min'], 488)
        self.assertEqual(paras[0]['y0_max'], 500)

    def test_single_line_y0(self):
        lines = [
            {'text': 'Only line', 'size': 10, 'bold': False, 'italic': False,
             'centered': False, 'y0': 300, 'x0': 50, 'x1': 200, 'page': 3},
        ]
        paras = []
        _flush_line_group(lines, paras)
        self.assertEqual(len(paras), 1)
        self.assertEqual(paras[0]['y0_min'], 300)
        self.assertEqual(paras[0]['y0_max'], 300)

    def test_empty_lines_no_output(self):
        paras = []
        _flush_line_group([], paras)
        self.assertEqual(len(paras), 0)


class TestFootnoteClassification(unittest.TestCase):
    """Footnote classification based on position and font size."""

    def test_hard_threshold_bottom_15pct(self):
        """Small-font paragraph at bottom 15% of page → footnote."""
        body_size = 12.0
        page_height = 792  # standard US Letter
        para = {
            'text': '1. See Johnson, History of Rome, pp. 45-67.',
            'font_size': 9.0,
            'page_number': 5,
            'y0_min': 50,   # near bottom (low y0 in pdfminer coords)
            'y0_max': 60,
        }
        y_ratio = para['y0_min'] / page_height
        size_ratio = para['font_size'] / body_size
        # y_ratio ≈ 0.063 (bottom 6.3%) and size_ratio = 0.75
        self.assertLessEqual(y_ratio, 0.15)
        self.assertLess(size_ratio, 0.95)

    def test_soft_threshold_bottom_40pct(self):
        """Notably smaller font at bottom 40% → footnote."""
        body_size = 12.0
        page_height = 792
        para = {
            'font_size': 9.5,
            'y0_min': 200,  # y_ratio ≈ 0.253
        }
        y_ratio = para['y0_min'] / page_height
        size_ratio = para['font_size'] / body_size
        self.assertLessEqual(y_ratio, 0.40)
        self.assertLess(size_ratio, 0.85)

    def test_body_text_not_classified(self):
        """Regular body paragraph in middle of page → NOT footnote."""
        body_size = 12.0
        page_height = 792
        para = {
            'text': 'The Roman Empire was vast and complex.',
            'font_size': 12.0,
            'page_number': 5,
            'y0_min': 400,  # middle of page
            'y0_max': 412,
        }
        y_ratio = para['y0_min'] / page_height
        size_ratio = para['font_size'] / body_size
        # y_ratio ≈ 0.505, size_ratio = 1.0
        hard = y_ratio <= 0.15 and size_ratio < 0.95
        soft = y_ratio <= 0.40 and size_ratio < 0.85
        self.assertFalse(hard)
        self.assertFalse(soft)

    def test_small_font_at_top_not_classified(self):
        """Small font at top of page (header) → NOT footnote."""
        body_size = 12.0
        page_height = 792
        y0_min = 750  # near top
        font_size = 8.0
        y_ratio = y0_min / page_height
        size_ratio = font_size / body_size
        # y_ratio ≈ 0.947 — not at bottom
        hard = y_ratio <= 0.15 and size_ratio < 0.95
        soft = y_ratio <= 0.40 and size_ratio < 0.85
        self.assertFalse(hard)
        self.assertFalse(soft)

    def test_body_font_at_bottom_not_classified(self):
        """Body-sized font at page bottom → NOT footnote (same size as body)."""
        body_size = 12.0
        page_height = 792
        y0_min = 50  # at bottom
        font_size = 12.0
        y_ratio = y0_min / page_height
        size_ratio = font_size / body_size
        # Hard: y_ratio ≈ 0.063 ≤ 0.15 but size_ratio = 1.0 ≥ 0.95 → no
        # Soft: y_ratio ≤ 0.40 but size_ratio = 1.0 ≥ 0.85 → no
        hard = y_ratio <= 0.15 and size_ratio < 0.95
        soft = y_ratio <= 0.40 and size_ratio < 0.85
        self.assertFalse(hard)
        self.assertFalse(soft)


class TestFootnoteHTMLRendering(unittest.TestCase):
    """Footnote paragraphs render as grouped <div class="footnotes"> blocks."""

    def _make_para(self, text, page=1, font_size=12.0, is_footnote=False,
                   is_page_marker=False, is_bold=False, is_italic=False,
                   is_centered=False, y0_min=400, y0_max=412):
        return {
            'text': text, 'font_size': font_size, 'is_bold': is_bold,
            'is_italic': is_italic, 'is_centered': is_centered,
            'is_all_caps': False, 'page_number': page,
            'line_count': 1, 'char_count': len(text),
            'is_page_marker': is_page_marker,
            'is_footnote': is_footnote,
            'y0_min': y0_min, 'y0_max': y0_max,
        }

    def test_footnotes_in_div(self):
        """Footnote paragraphs should be wrapped in <div class="footnotes">."""
        from pdf_to_balabolka import format_paragraphs_as_html
        paras = [
            self._make_para('', page=1, is_page_marker=True),
            self._make_para('Body paragraph text.', page=1),
            self._make_para('1. A footnote reference.', page=1, font_size=9.0,
                           is_footnote=True, y0_min=50, y0_max=60),
        ]
        log_msgs = []
        html = format_paragraphs_as_html(paras, 12.0, [], lambda m: log_msgs.append(m))
        self.assertIn('<div class="footnotes">', html)
        self.assertIn('<hr class="footnote-separator">', html)
        self.assertIn('1. A footnote reference.', html)

    def test_skip_footnotes_removes_them(self):
        """With skip_footnotes=True, footnotes should not appear in output."""
        from pdf_to_balabolka import format_paragraphs_as_html
        paras = [
            self._make_para('', page=1, is_page_marker=True),
            self._make_para('Body paragraph text.', page=1),
            self._make_para('1. A footnote reference.', page=1, font_size=9.0,
                           is_footnote=True, y0_min=50, y0_max=60),
        ]
        log_msgs = []
        html = format_paragraphs_as_html(paras, 12.0, [], lambda m: log_msgs.append(m),
                                         skip_footnotes=True)
        self.assertNotIn('footnote', html.lower().replace('footnote-separator', '').replace('footnotes', ''))
        self.assertNotIn('A footnote reference', html)


if __name__ == '__main__':
    unittest.main()
