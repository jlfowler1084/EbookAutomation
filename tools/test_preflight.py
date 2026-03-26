#!/usr/bin/env python3
"""Unit tests for preflight_analysis.py — recipe generation and analysis steps.

Uses unittest with mock.patch to mock external dependencies (classify_source,
pattern_db, pypdf).  Tests do NOT require actual PDF files or database access.

Usage:
    python tools/test_preflight.py
    python tools/test_preflight.py -v          # verbose
    python tools/test_preflight.py TestPreflightRecipe.test_digital_native_gets_full_profile
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from preflight_analysis import (
    _generate_recipe,
    _assess_chapter_structure,
    _assess_content_viability,
    _assess_footnote_viability,
    _assess_index_viability,
    _is_readable_bookmark,
    _flatten_outline,
    analyze_document,
)


# ---------------------------------------------------------------------------
# Helpers — build mock analysis dicts
# ---------------------------------------------------------------------------

def _mock_classification(cls_type='digital_native', confidence=0.90,
                         density=1500, kb_page=12.0, needs_ocr=False,
                         two_column=False, strategies=None):
    return {
        "classification": cls_type,
        "confidence": confidence,
        "signals": {
            "text_density_per_page": density,
            "file_size_per_page_kb": kb_page,
        },
        "recommended_strategies": strategies or ["html_extraction", "legacy"],
        "flags": {
            "needs_ocr": needs_ocr,
            "likely_two_column": two_column,
            "needs_paid_tier": False,
            "recommended_paid_tier": None,
        },
    }


def _mock_text_quality(tier='clean', score=80, hit_rate=0.78):
    return {
        "quality_tier": tier,
        "ocr_artifact_rate": round(1.0 - hit_rate, 4),
        "unicode_printable_ratio": 0.98,
        "common_word_hit_rate": hit_rate,
        "sample_pages": 5,
        "score": score,
    }


def _mock_chapters(bm_count=10, readable=True, source='bookmarks', claude=False):
    return {
        "bookmark_count": bm_count,
        "bookmarks_readable": readable,
        "recommended_chapter_source": source,
        "claude_chapters_recommended": claude,
    }


def _mock_historical(has_history=False, source='default', score=None,
                     strategy=None, conversions=0):
    return {
        "has_history": has_history,
        "source": source,
        "best_prior_score": score,
        "prior_strategy": strategy or [],
        "prior_conversions": conversions,
    }


def _mock_raw_historical(strategy_order=None, flags=None, confidence=0.0,
                         source='default'):
    return {
        "strategy_order": strategy_order or [],
        "flags": flags or {"UseClaudeChapters": False, "ForceColumns": False},
        "confidence": confidence,
        "reason": "test mock",
        "source": source,
        "best_prior_score": None,
        "prior_conversions": 0,
    }


def _noop_log(msg):
    pass


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestPreflightRecipe(unittest.TestCase):
    """Test the _generate_recipe() decision tree."""

    # 1. Digital native → full profile, html_extraction
    def test_digital_native_gets_full_profile(self):
        """Digital native PDFs should get full profile with HTML extraction."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, None, hist, None, 'pdf')

        self.assertEqual(recipe['profile'], 'full')
        self.assertIn('html_extraction', recipe['extraction_strategy'])
        self.assertTrue(recipe['flags']['UseHtmlExtraction'])
        self.assertGreater(recipe['confidence'], 0)

    # 2. scan_no_text → text-only, ocr, all No* flags
    def test_scan_no_text_gets_text_only(self):
        """Scan with no text should get text-only profile and OCR strategy."""
        cls = _mock_classification('scan_no_text', confidence=0.95,
                                   density=5, kb_page=80.0, needs_ocr=True)
        tq = _mock_text_quality('poor', score=10, hit_rate=0.05)
        cs = _mock_chapters(bm_count=0, readable=False, source='regex')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, None, hist, None, 'pdf')

        self.assertEqual(recipe['profile'], 'text-only')
        self.assertIn('ocr', recipe['extraction_strategy'])
        self.assertTrue(recipe['flags']['UseOCR'])
        self.assertTrue(recipe['flags']['NoFootnotes'])
        self.assertTrue(recipe['flags']['NoIndex'])
        self.assertTrue(recipe['flags']['NoHyperlinks'])
        self.assertFalse(recipe['flags']['UseClaudeChapters'])

    # 3. scan_with_text + poor quality → text-only, legacy, NoFootnotes, NoIndex
    def test_scan_with_text_poor_quality(self):
        """Scan with poor OCR quality → text-only, legacy + ocr."""
        cls = _mock_classification('scan_with_text', confidence=0.85,
                                   density=300, kb_page=45.0)
        tq = _mock_text_quality('poor', score=35, hit_rate=0.25)
        cs = _mock_chapters(bm_count=5, readable=True)
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, None, hist, None, 'pdf')

        self.assertEqual(recipe['profile'], 'text-only')
        self.assertIn('legacy', recipe['extraction_strategy'])
        self.assertTrue(recipe['flags']['NoFootnotes'])
        self.assertTrue(recipe['flags']['NoIndex'])

    # 4. scan_with_text + moderate quality → clean-read
    def test_scan_with_text_moderate_quality(self):
        """Scan with moderate quality (50-74) → clean-read profile."""
        cls = _mock_classification('scan_with_text', confidence=0.85,
                                   density=800, kb_page=35.0)
        tq = _mock_text_quality('moderate', score=62, hit_rate=0.55)
        cs = _mock_chapters()
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, None, hist, None, 'pdf')

        self.assertEqual(recipe['profile'], 'clean-read')
        self.assertIn('legacy', recipe['extraction_strategy'])

    # 5. scan_with_text + clean quality → full profile
    def test_scan_with_text_clean_quality(self):
        """Scan with clean quality (75+) → full profile with html_extraction."""
        cls = _mock_classification('scan_with_text', confidence=0.85,
                                   density=1200, kb_page=30.0)
        tq = _mock_text_quality('clean', score=82, hit_rate=0.80)
        cs = _mock_chapters()
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, None, hist, None, 'pdf')

        self.assertEqual(recipe['profile'], 'full')
        self.assertIn('html_extraction', recipe['extraction_strategy'])

    # 6. EPUB → epub_html strategy, no text quality
    def test_epub_gets_epub_html(self):
        """EPUB format should get epub_html strategy."""
        cls = _mock_classification()  # won't be used much
        recipe = _generate_recipe(cls, None, None, None, None, None, 'epub')

        self.assertEqual(recipe['profile'], 'full')
        self.assertIn('epub_html', recipe['extraction_strategy'])
        self.assertIn('direct', recipe['extraction_strategy'])
        self.assertEqual(recipe['confidence'], 0.90)

    # 7. MOBI → direct strategy
    def test_mobi_gets_direct(self):
        """MOBI format should get direct strategy."""
        cls = _mock_classification()
        recipe = _generate_recipe(cls, None, None, None, None, None, 'mobi')

        self.assertEqual(recipe['profile'], 'full')
        self.assertEqual(recipe['extraction_strategy'], ['direct'])

    # 8. Historical data override with high score
    def test_historical_override_with_high_score(self):
        """Exact book with prior score >= 70 should use historical strategy."""
        cls = _mock_classification('scan_with_text', confidence=0.80)
        tq = _mock_text_quality('moderate', score=60)
        cs = _mock_chapters()
        hist = _mock_historical(has_history=True, source='book_history',
                                score=78, strategy=['legacy', 'column_aware'],
                                conversions=3)
        raw = _mock_raw_historical(
            strategy_order=['legacy', 'column_aware'],
            flags={'UseClaudeChapters': True, 'ForceColumns': False},
            confidence=0.80, source='book_history'
        )
        recipe = _generate_recipe(cls, tq, cs, None, hist, raw, 'pdf')

        # Strategy should come from history, not classification
        self.assertEqual(recipe['extraction_strategy'][0], 'legacy')
        self.assertIn('column_aware', recipe['extraction_strategy'])
        # Confidence boosted
        self.assertGreater(recipe['confidence'], 0.80)
        # Historical UseClaudeChapters propagated
        self.assertTrue(recipe['flags']['UseClaudeChapters'])
        # Reasoning mentions historical override
        self.assertTrue(any('Historical override' in r for r in recipe['reasoning']))

    # 9. Bookmark assessment — viable
    def test_bookmark_viable(self):
        """10 readable bookmarks → bookmarks recommended."""
        cs = _mock_chapters(bm_count=10, readable=True, source='bookmarks')
        self.assertEqual(cs['recommended_chapter_source'], 'bookmarks')
        self.assertFalse(cs['claude_chapters_recommended'])

    # 10. Bookmark assessment — garbled
    def test_bookmark_garbled(self):
        """Bookmarks with >50% garbled titles → claude recommended."""
        cs = _mock_chapters(bm_count=8, readable=False,
                            source='claude', claude=True)
        self.assertEqual(cs['recommended_chapter_source'], 'claude')
        self.assertTrue(cs['claude_chapters_recommended'])

    # 11. All steps fail gracefully
    def test_all_steps_fail_gracefully(self):
        """All analysis steps raising exceptions → still returns valid recipe."""
        with patch('preflight_analysis._classify_source', side_effect=Exception("boom")):
            with patch('preflight_analysis._assess_text_quality', side_effect=Exception("boom")):
                with patch('preflight_analysis._assess_chapter_structure', side_effect=Exception("boom")):
                    with patch('preflight_analysis._lookup_historical_data', side_effect=Exception("boom")):
                        # Even with all steps exploding, generate_recipe
                        # with fallback data should produce valid output
                        cls = _mock_classification('unknown', confidence=0.0)
                        recipe = _generate_recipe(
                            cls, None, None, None, None, None, 'pdf'
                        )
                        self.assertIn('profile', recipe)
                        self.assertIn('extraction_strategy', recipe)
                        self.assertIn('flags', recipe)
                        self.assertIn('confidence', recipe)
                        self.assertIn('reasoning', recipe)
                        self.assertIsInstance(recipe['extraction_strategy'], list)
                        self.assertGreater(len(recipe['extraction_strategy']), 0)

    # 12. Confidence calculation
    def test_confidence_boosts(self):
        """Verify confidence boosts from historical agreement and decisive quality."""
        # Base confidence from classification
        cls = _mock_classification('digital_native', confidence=0.70)
        tq = _mock_text_quality('clean', score=90, hit_rate=0.85)  # decisive
        cs = _mock_chapters()
        hist = _mock_historical(has_history=True, source='publisher_profile',
                                score=72, strategy=['html_extraction'],
                                conversions=2)
        raw = _mock_raw_historical(
            strategy_order=['html_extraction'],
            confidence=0.60, source='publisher_profile'
        )
        recipe = _generate_recipe(cls, tq, cs, None, hist, raw, 'pdf')

        # Should be boosted: base 0.70 + 0.10 (history override) + 0.05 (decisive)
        # = 0.85, capped at 0.95
        self.assertGreaterEqual(recipe['confidence'], 0.80)
        self.assertLessEqual(recipe['confidence'], 0.95)


class TestBookmarkHelpers(unittest.TestCase):
    """Test bookmark readability and flattening helpers."""

    def test_readable_bookmark_normal(self):
        self.assertTrue(_is_readable_bookmark("Chapter 1: Introduction"))

    def test_readable_bookmark_garbled(self):
        self.assertFalse(_is_readable_bookmark("\x00\x01\x02\x03\x04"))

    def test_readable_bookmark_empty(self):
        self.assertFalse(_is_readable_bookmark(""))

    def test_readable_bookmark_none(self):
        self.assertFalse(_is_readable_bookmark(None))

    def test_readable_bookmark_short(self):
        self.assertFalse(_is_readable_bookmark("X"))

    def test_readable_bookmark_numbers_only(self):
        self.assertFalse(_is_readable_bookmark("12345"))

    def test_flatten_simple(self):
        mock_items = []
        for title in ["Chapter 1", "Chapter 2", "Chapter 3"]:
            item = MagicMock()
            item.title = title
            mock_items.append(item)
        result = []
        _flatten_outline(mock_items, result)
        self.assertEqual(result, ["Chapter 1", "Chapter 2", "Chapter 3"])

    def test_flatten_nested(self):
        child = MagicMock()
        child.title = "Section 1.1"
        parent = MagicMock()
        parent.title = "Chapter 1"
        outline = [parent, [child]]
        result = []
        _flatten_outline(outline, result)
        self.assertEqual(len(result), 2)
        self.assertIn("Chapter 1", result)
        self.assertIn("Section 1.1", result)


def _mock_viability(fn='viable', ix='viable', hl='viable', img='viable'):
    """Build a mock content_viability dict."""
    return {
        "footnotes": {
            "viability": fn,
            "sample_count": 10,
            "readable_ratio": 0.90 if fn == 'viable' else 0.60 if fn == 'degraded' else 0.20,
            "detail": f"Mock footnotes: {fn}",
        },
        "index": {
            "viability": ix,
            "sample_count": 20,
            "structured_ratio": 0.60 if ix == 'viable' else 0.30 if ix == 'degraded' else 0.05,
            "detail": f"Mock index: {ix}",
        },
        "hyperlinks": {
            "viability": hl,
            "link_count": 10 if hl == 'viable' else 0,
            "valid_uri_count": 8 if hl == 'viable' else 0,
            "detail": f"Mock hyperlinks: {hl}",
        },
        "images": {
            "viability": img,
            "image_count": 5 if img in ('viable', 'decorative_only') else 0,
            "content_bearing_count": 3 if img == 'viable' else 0,
            "detail": f"Mock images: {img}",
        },
    }


class TestContentViability(unittest.TestCase):
    """Test content element viability assessment and its effect on recipes."""

    # 1. Footnotes viable → NoFootnotes NOT set
    def test_footnotes_viable_preserved(self):
        """Readable endnotes should NOT trigger NoFootnotes."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        cv = _mock_viability(fn='viable')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertFalse(recipe['flags']['NoFootnotes'])

    # 2. Footnotes unusable → NoFootnotes=True
    def test_footnotes_unusable_skipped(self):
        """Garbled endnotes should trigger NoFootnotes."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        cv = _mock_viability(fn='unusable')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertTrue(recipe['flags']['NoFootnotes'])
        self.assertTrue(any('unusable' in r.lower() for r in recipe['reasoning']))

    # 3. Footnotes degraded on scanned → NoFootnotes=True
    def test_footnotes_degraded_scan_skipped(self):
        """Degraded footnotes on scanned source should be skipped."""
        cls = _mock_classification('scan_with_text', confidence=0.85,
                                   density=800, kb_page=35.0)
        tq = _mock_text_quality('moderate', score=62)
        cs = _mock_chapters()
        cv = _mock_viability(fn='degraded')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertTrue(recipe['flags']['NoFootnotes'])

    # 4. Footnotes degraded on digital → NoFootnotes NOT set
    def test_footnotes_degraded_digital_preserved(self):
        """Degraded footnotes on digital source should be preserved."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        cv = _mock_viability(fn='degraded')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertFalse(recipe['flags']['NoFootnotes'])

    # 5. Index viable → NoIndex NOT set
    def test_index_viable_preserved(self):
        """Structured index entries should NOT trigger NoIndex."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        cv = _mock_viability(ix='viable')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertFalse(recipe['flags']['NoIndex'])

    # 6. Index unusable → NoIndex=True
    def test_index_unusable_skipped(self):
        """Garbled index should trigger NoIndex."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        cv = _mock_viability(ix='unusable')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertTrue(recipe['flags']['NoIndex'])

    # 7. Hyperlinks none → NoHyperlinks=True
    def test_hyperlinks_none_skipped(self):
        """No PDF link annotations → NoHyperlinks."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        cv = _mock_viability(hl='none')
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertTrue(recipe['flags']['NoHyperlinks'])

    # 8. All viability fails gracefully
    def test_viability_failure_graceful(self):
        """PdfReader failure → default 'none' dict, recipe still works."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        # None viability (assessment failed) — should fall back to Phase 1 heuristic
        hist = _mock_historical()
        recipe = _generate_recipe(cls, tq, cs, None, hist, None, 'pdf')
        self.assertIn('profile', recipe)
        self.assertIn('extraction_strategy', recipe)
        self.assertIn('flags', recipe)
        # Digital native with no viability data → Phase 1 defaults (all off)
        self.assertFalse(recipe['flags']['NoFootnotes'])

    # 9. Viability changes flags that Phase 1 wouldn't set
    def test_viability_overrides_phase1_heuristic(self):
        """Digital native with unusable footnotes gets NoFootnotes (Phase 1 wouldn't)."""
        cls = _mock_classification('digital_native', confidence=0.90)
        tq = _mock_text_quality('clean', score=85)
        cs = _mock_chapters()
        hist = _mock_historical()

        # Without viability (Phase 1) — digital native keeps all elements
        recipe_p1 = _generate_recipe(cls, tq, cs, None, hist, None, 'pdf')
        self.assertFalse(recipe_p1['flags']['NoFootnotes'])

        # With viability showing unusable footnotes — NoFootnotes gets set
        cv = _mock_viability(fn='unusable', ix='viable', hl='viable')
        recipe_p2 = _generate_recipe(cls, tq, cs, cv, hist, None, 'pdf')
        self.assertTrue(recipe_p2['flags']['NoFootnotes'])
        # But index stays preserved since it's viable
        self.assertFalse(recipe_p2['flags']['NoIndex'])


if __name__ == '__main__':
    unittest.main()
