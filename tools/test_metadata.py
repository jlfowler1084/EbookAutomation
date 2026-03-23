# tools/test_metadata.py
"""Unit tests for book metadata capture system."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add tools/ to path so we can import pattern_db
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pattern_db


class TestBookMetadataSchema(unittest.TestCase):
    """Tests for the book_metadata table creation."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_book_metadata_table_exists(self):
        """book_metadata table should be created by get_db()."""
        conn = pattern_db.get_db(self.db_path)
        tables = [
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        conn.close()
        self.assertIn('book_metadata', tables)

    def test_book_metadata_columns(self):
        """book_metadata table should have all expected columns."""
        conn = pattern_db.get_db(self.db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(book_metadata)").fetchall()}
        conn.close()
        expected = {
            'id', 'book_id', 'isbn', 'title_hash', 'title', 'authors',
            'publisher', 'year', 'language', 'subject', 'series',
            'description', 'cover_path', 'extra_json', 'source_filename',
            'source_type', 'created_at', 'updated_at',
        }
        self.assertEqual(expected, cols)

    def test_book_metadata_indexes(self):
        """Indexes on title_hash and isbn should exist."""
        conn = pattern_db.get_db(self.db_path)
        indexes = {
            row[1] for row in
            conn.execute("SELECT * FROM sqlite_master WHERE type='index'").fetchall()
            if row[1]  # skip auto-indexes
        }
        conn.close()
        self.assertIn('idx_book_metadata_title_hash', indexes)
        self.assertIn('idx_book_metadata_isbn', indexes)


class TestMetadataHelpers(unittest.TestCase):
    """Tests for _clean_meta_field and _extract_year."""

    def test_clean_author_removes_software_names(self):
        self.assertIsNone(pattern_db._clean_meta_field('Microsoft Word', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('Adobe InDesign', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('LaTeX', field_type='author'))

    def test_clean_author_keeps_real_names(self):
        self.assertEqual('John Smith', pattern_db._clean_meta_field('John Smith', field_type='author'))

    def test_clean_author_removes_unknown(self):
        self.assertIsNone(pattern_db._clean_meta_field('Unknown', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('unknown', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('', field_type='author'))

    def test_clean_title_removes_untitled(self):
        self.assertIsNone(pattern_db._clean_meta_field('Untitled', field_type='title'))
        self.assertIsNone(pattern_db._clean_meta_field('Document', field_type='title'))

    def test_clean_title_keeps_real_titles(self):
        self.assertEqual('The Book of Ezekiel', pattern_db._clean_meta_field('The Book of Ezekiel', field_type='title'))

    def test_clean_publisher_removes_tools(self):
        self.assertIsNone(pattern_db._clean_meta_field('Adobe InDesign', field_type='publisher'))
        self.assertIsNone(pattern_db._clean_meta_field('Microsoft Word', field_type='publisher'))

    def test_clean_publisher_keeps_real(self):
        self.assertEqual('Oxford University Press', pattern_db._clean_meta_field('Oxford University Press', field_type='publisher'))

    def test_extract_year_from_pdf_date(self):
        self.assertEqual('2019', pattern_db._extract_year("D:20190415120000+00'00'"))
        self.assertEqual('2005', pattern_db._extract_year('D:20050101'))

    def test_extract_year_from_plain(self):
        self.assertEqual('2021', pattern_db._extract_year('2021'))

    def test_extract_year_none_for_garbage(self):
        self.assertIsNone(pattern_db._extract_year(None))
        self.assertIsNone(pattern_db._extract_year(''))
        self.assertIsNone(pattern_db._extract_year('no year here'))


class TestPdfMetadataExtraction(unittest.TestCase):
    """Tests for extract_pdf_metadata — requires PyMuPDF."""

    def setUp(self):
        """Create a minimal PDF with metadata using PyMuPDF."""
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF not installed')
        self.tmp_dir = tempfile.mkdtemp()
        self.pdf_path = os.path.join(self.tmp_dir, 'test_book.pdf')
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), 'Test content')
        doc.set_metadata({
            'title': 'The Book of Ezekiel',
            'author': 'Daniel I. Block',
            'subject': 'Biblical Commentary',
            'creator': 'Adobe InDesign',
            'producer': 'Adobe PDF Library',
            'creationDate': "D:20190415120000+00'00'",
        })
        doc.save(self.pdf_path)
        doc.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_extracts_title(self):
        result = pattern_db.extract_pdf_metadata(self.pdf_path)
        self.assertEqual(result['title'], 'The Book of Ezekiel')

    def test_extracts_author(self):
        result = pattern_db.extract_pdf_metadata(self.pdf_path)
        self.assertEqual(result['authors'], 'Daniel I. Block')

    def test_extracts_year(self):
        result = pattern_db.extract_pdf_metadata(self.pdf_path)
        self.assertEqual(result['year'], '2019')

    def test_filters_creator_as_publisher(self):
        """Creator='Adobe InDesign' should be filtered out as garbage."""
        result = pattern_db.extract_pdf_metadata(self.pdf_path)
        self.assertNotIn('publisher', result)

    def test_extracts_subject(self):
        result = pattern_db.extract_pdf_metadata(self.pdf_path)
        self.assertEqual(result['subject'], 'Biblical Commentary')

    def test_includes_extra_json(self):
        result = pattern_db.extract_pdf_metadata(self.pdf_path)
        extra = json.loads(result['extra_json'])
        self.assertEqual(extra['producer'], 'Adobe PDF Library')

    def test_empty_metadata_pdf(self):
        """PDF with no metadata should return empty dict (plus extra_json)."""
        import fitz
        empty_path = os.path.join(self.tmp_dir, 'empty_meta.pdf')
        doc = fitz.open()
        doc.new_page()
        doc.save(empty_path)
        doc.close()
        result = pattern_db.extract_pdf_metadata(empty_path)
        # Should have at most extra_json
        self.assertNotIn('title', result)
        self.assertNotIn('authors', result)


if __name__ == '__main__':
    unittest.main()
