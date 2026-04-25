# tools/test_metadata.py
"""Unit tests for book metadata capture system."""
import json
import os
import sqlite3
import subprocess
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

    def test_clean_filters_literal_none_placeholder(self):
        """SCRUM-322: literal 'None' / 'null' / 'n/a' placeholders are not real metadata.

        Some PDF authoring tools (Pdf995 in particular) write the literal text
        'None' into metadata fields instead of leaving them empty. Without this
        filter the value flows through to Calibre's --authors arg and produces
        output filenames like '... - None.kfx'.
        """
        # Author field
        self.assertIsNone(pattern_db._clean_meta_field('None', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('NONE', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('none', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('null', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('N/A', field_type='author'))
        self.assertIsNone(pattern_db._clean_meta_field('undefined', field_type='author'))
        # Title field
        self.assertIsNone(pattern_db._clean_meta_field('None', field_type='title'))
        self.assertIsNone(pattern_db._clean_meta_field('null', field_type='title'))
        # Publisher field
        self.assertIsNone(pattern_db._clean_meta_field('None', field_type='publisher'))
        self.assertIsNone(pattern_db._clean_meta_field('n/a', field_type='publisher'))
        # Generic / unspecified field_type
        self.assertIsNone(pattern_db._clean_meta_field('None'))

    def test_clean_keeps_real_value_that_starts_with_none(self):
        """A name like 'None Such Press' or a title 'None of the Above' must NOT be filtered."""
        self.assertEqual('None Such Press', pattern_db._clean_meta_field('None Such Press', field_type='publisher'))
        self.assertEqual('None of the Above', pattern_db._clean_meta_field('None of the Above', field_type='title'))

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


class TestEpubMetadataExtraction(unittest.TestCase):
    """Tests for extract_epub_metadata — requires ebooklib."""

    def setUp(self):
        """Create a minimal EPUB with metadata using ebooklib."""
        try:
            from ebooklib import epub
        except ImportError:
            self.skipTest('ebooklib not installed')

        self.tmp_dir = tempfile.mkdtemp()
        self.epub_path = os.path.join(self.tmp_dir, 'test_book.epub')

        book = epub.EpubBook()
        book.set_identifier('isbn:9780802826503')
        book.set_title('Jesus and the Land')
        book.set_language('en')
        book.add_author('Gary M. Burge')
        book.add_metadata('DC', 'publisher', 'Baker Academic')
        book.add_metadata('DC', 'description', 'A study of land theology')
        book.add_metadata('DC', 'subject', 'Theology')

        ch = epub.EpubHtml(title='Chapter 1', file_name='ch1.xhtml', lang='en')
        ch.content = '<html><body><h1>Chapter 1</h1><p>Content.</p></body></html>'
        book.add_item(ch)
        book.spine = ['nav', ch]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub.write_epub(self.epub_path, book, {})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_extracts_title(self):
        result = pattern_db.extract_epub_metadata(self.epub_path)
        self.assertEqual(result['title'], 'Jesus and the Land')

    def test_extracts_author(self):
        result = pattern_db.extract_epub_metadata(self.epub_path)
        self.assertEqual(result['authors'], 'Gary M. Burge')

    def test_extracts_publisher(self):
        result = pattern_db.extract_epub_metadata(self.epub_path)
        self.assertEqual(result['publisher'], 'Baker Academic')

    def test_extracts_language(self):
        result = pattern_db.extract_epub_metadata(self.epub_path)
        self.assertEqual(result['language'], 'en')

    def test_extracts_isbn(self):
        result = pattern_db.extract_epub_metadata(self.epub_path)
        self.assertEqual(result['isbn'], '9780802826503')

    def test_extracts_description(self):
        result = pattern_db.extract_epub_metadata(self.epub_path)
        self.assertEqual(result['description'], 'A study of land theology')

    def test_extracts_subject(self):
        result = pattern_db.extract_epub_metadata(self.epub_path)
        self.assertEqual(result['subject'], 'Theology')


class TestExtractFileMetadata(unittest.TestCase):
    """Tests for the extract_file_metadata router."""

    def test_routes_pdf(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF not installed')
        tmp_dir = tempfile.mkdtemp()
        pdf_path = os.path.join(tmp_dir, 'test.pdf')
        doc = fitz.open()
        doc.new_page()
        doc.set_metadata({'title': 'Router Test'})
        doc.save(pdf_path)
        doc.close()
        result = pattern_db.extract_file_metadata(pdf_path)
        self.assertEqual(result.get('title'), 'Router Test')
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_unknown_format_returns_empty(self):
        result = pattern_db.extract_file_metadata('book.mobi')
        self.assertEqual(result, {})


class TestStoreAndGetBookMetadata(unittest.TestCase):
    """Tests for store_book_metadata and get_book_metadata."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_store_and_retrieve_by_title_hash(self):
        title_hash = pattern_db._normalize_title_hash('The Book of Ezekiel', 'Daniel Block')
        pattern_db.store_book_metadata(
            title_hash=title_hash,
            title='The Book of Ezekiel',
            authors='Daniel I. Block',
            publisher='Eerdmans',
            year='1997',
            source_type='pdf_internal',
            db_path=self.db_path,
        )
        result = pattern_db.get_book_metadata(title_hash=title_hash, db_path=self.db_path)
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'The Book of Ezekiel')
        self.assertEqual(result['authors'], 'Daniel I. Block')
        self.assertEqual(result['publisher'], 'Eerdmans')

    def test_retrieve_by_isbn(self):
        pattern_db.store_book_metadata(
            title_hash='test_hash',
            isbn='9780802826503',
            title='Jesus and the Land',
            source_type='epub_opf',
            db_path=self.db_path,
        )
        result = pattern_db.get_book_metadata(isbn='9780802826503', db_path=self.db_path)
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Jesus and the Land')

    def test_upsert_updates_existing(self):
        pattern_db.store_book_metadata(
            title_hash='upsert_test',
            title='Original Title',
            source_type='filename_parser',
            db_path=self.db_path,
        )
        pattern_db.store_book_metadata(
            title_hash='upsert_test',
            title='Updated Title',
            authors='New Author',
            source_type='pdf_internal',
            db_path=self.db_path,
        )
        result = pattern_db.get_book_metadata(title_hash='upsert_test', db_path=self.db_path)
        self.assertEqual(result['title'], 'Updated Title')
        self.assertEqual(result['authors'], 'New Author')

    def test_returns_none_when_not_found(self):
        result = pattern_db.get_book_metadata(title_hash='nonexistent', db_path=self.db_path)
        self.assertIsNone(result)


class TestMergeMetadata(unittest.TestCase):
    """Tests for the merge_metadata priority logic."""

    def test_fills_empty_fields(self):
        existing = {'title': 'Book Title', 'source_type': 'filename_parser'}
        new_fields = {'authors': 'John Smith', 'year': '2020'}
        result = pattern_db.merge_metadata(existing, new_fields, 'pdf_internal')
        self.assertEqual(result['title'], 'Book Title')
        self.assertEqual(result['authors'], 'John Smith')
        self.assertEqual(result['year'], '2020')

    def test_higher_priority_wins(self):
        existing = {'title': 'Filename Title', 'authors': 'Filename Author', 'source_type': 'filename_parser'}
        new_fields = {'title': 'PDF Title', 'authors': 'PDF Author'}
        result = pattern_db.merge_metadata(existing, new_fields, 'pdf_internal')
        self.assertEqual(result['title'], 'PDF Title')
        self.assertEqual(result['authors'], 'PDF Author')

    def test_lower_priority_does_not_overwrite(self):
        existing = {'title': 'EPUB Title', 'source_type': 'epub_opf'}
        new_fields = {'title': 'Filename Title'}
        result = pattern_db.merge_metadata(existing, new_fields, 'filename_parser')
        self.assertEqual(result['title'], 'EPUB Title')

    def test_lower_priority_fills_gaps(self):
        existing = {'title': 'EPUB Title', 'source_type': 'epub_opf'}
        new_fields = {'authors': 'Filename Author'}
        result = pattern_db.merge_metadata(existing, new_fields, 'filename_parser')
        self.assertEqual(result['title'], 'EPUB Title')
        self.assertEqual(result['authors'], 'Filename Author')

    def test_merged_source_type(self):
        existing = {'title': 'Book', 'source_type': 'filename_parser'}
        new_fields = {'authors': 'Author'}
        result = pattern_db.merge_metadata(existing, new_fields, 'pdf_internal')
        self.assertEqual(result['source_type'], 'merged')


class TestMetadataCLI(unittest.TestCase):
    """Tests for CLI subcommands: extract-metadata, get-metadata, update-metadata, store-metadata."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, 'test.db')
        self.output_file = os.path.join(self.tmp_dir, 'meta.json')
        self.script = str(Path(__file__).resolve().parent / 'pattern_db.py')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run_cli(self, args):
        """Run pattern_db.py with args, return (returncode, stdout, stderr)."""
        cmd = [sys.executable, self.script, '--db-path', self.db_path] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr

    def test_extract_metadata_pdf(self):
        """extract-metadata should extract and store PDF metadata."""
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF not installed')
        pdf_path = os.path.join(self.tmp_dir, 'Test Book - Author Name.pdf')
        doc = fitz.open()
        doc.new_page()
        doc.set_metadata({'title': 'Test Book', 'author': 'Author Name'})
        doc.save(pdf_path)
        doc.close()

        rc, stdout, stderr = self._run_cli([
            'extract-metadata', '--file', pdf_path,
            '--output-file', self.output_file,
        ])
        self.assertEqual(rc, 0, f'stderr: {stderr}')
        self.assertTrue(os.path.exists(self.output_file))
        with open(self.output_file) as f:
            data = json.load(f)
        self.assertEqual(data['title'], 'Test Book')

    def test_get_metadata(self):
        """get-metadata should retrieve stored metadata."""
        pattern_db.store_book_metadata(
            title_hash='cli_test_hash',
            title='CLI Test Book',
            authors='CLI Author',
            source_type='pdf_internal',
            db_path=self.db_path,
        )
        rc, stdout, stderr = self._run_cli([
            'get-metadata', '--title-hash', 'cli_test_hash',
            '--output-file', self.output_file,
        ])
        self.assertEqual(rc, 0, f'stderr: {stderr}')
        with open(self.output_file) as f:
            data = json.load(f)
        self.assertEqual(data['title'], 'CLI Test Book')

    def test_update_metadata(self):
        """update-metadata should merge in new fields."""
        pattern_db.store_book_metadata(
            title_hash='update_test',
            title='Original',
            source_type='pdf_internal',
            db_path=self.db_path,
        )
        rc, stdout, stderr = self._run_cli([
            'update-metadata', '--title-hash', 'update_test',
            '--authors', 'New Author', '--source-type', 'filename_parser',
            '--output-file', self.output_file,
        ])
        self.assertEqual(rc, 0, f'stderr: {stderr}')
        with open(self.output_file) as f:
            data = json.load(f)
        self.assertEqual(data['title'], 'Original')  # kept from higher-priority source
        self.assertEqual(data['authors'], 'New Author')  # filled from filename_parser

    def test_get_metadata_not_found(self):
        """get-metadata for nonexistent book should exit 0 with empty JSON."""
        rc, stdout, stderr = self._run_cli([
            'get-metadata', '--title-hash', 'nonexistent',
            '--output-file', self.output_file,
        ])
        self.assertEqual(rc, 0)
        with open(self.output_file) as f:
            data = json.load(f)
        self.assertEqual(data, {})

    def test_store_metadata_from_json(self):
        """store-metadata should import metadata from a JSON file."""
        meta_file = os.path.join(self.tmp_dir, 'import.json')
        with open(meta_file, 'w') as f:
            json.dump({
                'title_hash': 'store_test_hash',
                'title': 'Stored Book',
                'authors': 'Stored Author',
                'source_type': 'epub_opf',
            }, f)
        rc, stdout, stderr = self._run_cli([
            'store-metadata', '--metadata-file', meta_file,
        ])
        self.assertEqual(rc, 0, f'stderr: {stderr}')
        result = pattern_db.get_book_metadata(title_hash='store_test_hash', db_path=self.db_path)
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Stored Book')


class TestEmailToKindleMetadata(unittest.TestCase):
    """Tests for metadata injection in email_to_kindle.py."""

    def setUp(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF not installed')
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_inject_metadata_adds_to_empty_pdf(self):
        """inject_metadata_if_needed should add metadata to a PDF with empty metadata."""
        import fitz
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import email_to_kindle

        src_dir = os.path.join(self.tmp_dir, 'src')
        os.makedirs(src_dir)
        pdf_path = os.path.join(src_dir, 'empty_meta.pdf')
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        metadata = {'title': 'Injected Title', 'authors': 'Injected Author', 'subject': 'Test'}
        result_path = email_to_kindle.inject_metadata_if_needed(pdf_path, metadata, self.tmp_dir)

        self.assertNotEqual(result_path, pdf_path)
        self.assertIn('_metadata', result_path)
        doc2 = fitz.open(result_path)
        self.assertEqual(doc2.metadata.get('title'), 'Injected Title')
        self.assertEqual(doc2.metadata.get('author'), 'Injected Author')
        doc2.close()

    def test_inject_metadata_skips_good_pdf(self):
        """inject_metadata_if_needed should not modify a PDF with existing good metadata."""
        import fitz
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import email_to_kindle

        pdf_path = os.path.join(self.tmp_dir, 'good_meta.pdf')
        doc = fitz.open()
        doc.new_page()
        doc.set_metadata({'title': 'Existing Title', 'author': 'Existing Author'})
        doc.save(pdf_path)
        doc.close()

        metadata = {'title': 'Should Not Override', 'authors': 'Should Not Override'}
        result_path = email_to_kindle.inject_metadata_if_needed(pdf_path, metadata, self.tmp_dir)

        self.assertEqual(result_path, pdf_path)


class TestParseMetadataFromFilenameSCRUM323(unittest.TestCase):
    """SCRUM-323 Bug 1: Python parser must handle libgen 'Author - Title (Year, Pub)' format.

    Previously `_parse_metadata_from_filename` did `rsplit(' - ', 1)` and assigned
    parts[0]=title, parts[1]=author. That inverts libgen convention (Author - Title)
    and also gets confused by trailing `- libgen.li` noise. The PowerShell
    `Get-EbookMetadataFromFilename` Pattern 2 anchors on the trailing parenthetical
    and treats the LHS of the dash as the author. The Python parser is now expected
    to do the same.
    """

    def test_libgen_format_oil_kings(self):
        title, author = pattern_db._parse_metadata_from_filename(
            'Cooper, Andrew Scott - The Oil Kings_ How the U (2011, Simon & Schuster) - libgen.li.pdf'
        )
        self.assertEqual(author, 'Cooper, Andrew Scott')
        self.assertIn('Oil Kings', title)
        self.assertNotIn('libgen', title.lower())

    def test_libgen_format_with_series_prefix_feuerbach(self):
        """Feuerbach case — leading series parenthetical must not bleed into author,
        and publisher metadata after the dash must not bleed into author either."""
        title, author = pattern_db._parse_metadata_from_filename(
            '(Great Books in Philosophy) Ludwig Feuerbach - The Essence of Christianity (Great Books in Philosophy)-Prometheus Books (1989).pdf'
        )
        self.assertEqual(author, 'Ludwig Feuerbach')
        self.assertIn('Essence of Christianity', title)
        self.assertNotIn('Prometheus', title)
        self.assertNotIn('Great Books in Philosophy', author)

    def test_libgen_format_year_only_no_publisher(self):
        title, author = pattern_db._parse_metadata_from_filename(
            'John Glubb - The Fate of Empires and Search for Survival (1976) - libgen.li.pdf'
        )
        self.assertEqual(author, 'John Glubb')
        self.assertEqual(title, 'The Fate of Empires and Search for Survival')

    def test_libgen_format_publisher_dash_year(self):
        """Publisher-Year-only libgen variant: 'Author - Title-Publisher (Year).pdf'."""
        title, author = pattern_db._parse_metadata_from_filename(
            'Helen Boak - Women in the Weimar Republic-Manchester University Press (2015).pdf'
        )
        self.assertEqual(author, 'Helen Boak')
        self.assertIn('Women in the Weimar Republic', title)

    def test_legacy_title_dash_author_format(self):
        """Pipeline-output naming (Title - Author) — must still work for the no-parenthetical case."""
        title, author = pattern_db._parse_metadata_from_filename(
            'The Oil Kings - Andrew Scott Cooper.pdf'
        )
        self.assertEqual(title, 'The Oil Kings')
        self.assertEqual(author, 'Andrew Scott Cooper')

    def test_no_separator(self):
        title, author = pattern_db._parse_metadata_from_filename('SimpleName.pdf')
        self.assertEqual(title, 'SimpleName')
        self.assertIsNone(author)

    def test_strips_visual_qa_suffix(self):
        title, author = pattern_db._parse_metadata_from_filename(
            'My Book - Some Author_visual_qa_report.pdf'
        )
        self.assertEqual(title, 'My Book')
        self.assertEqual(author, 'Some Author')

    def test_year_in_leading_parenthetical_is_not_series(self):
        """A leading (YYYY) prefix is a year, not a series tag — don't strip it as series."""
        title, author = pattern_db._parse_metadata_from_filename(
            '(2011) Some Author - Some Book.pdf'
        )
        # Authors should not contain the year-paren prefix; title should not be empty
        self.assertIsNotNone(author)
        self.assertNotIn('2011', author)


class TestPdfInternalSuspiciousSCRUM323(unittest.TestCase):
    """SCRUM-323 Bug 2: detect when pdf_internal metadata is junk and should be rejected
    in favor of filename_parser.

    Trip conditions:
      1. PDF producer or creator matches a known PDF-tool fingerprint (Pdf995, etc.)
      2. PDF title contains the filename-derived author (suggests filename was injected
         as the title field by the PDF authoring tool).
    """

    def test_pdf995_creator_is_suspicious(self):
        """Feuerbach's actual fingerprint: creator='Pdf995'."""
        meta = {
            'extra_json': json.dumps({'creator': 'Pdf995', 'producer': 'GPL Ghostscript 8.15'})
        }
        self.assertTrue(pattern_db._is_pdf_internal_suspicious(meta, 'Ludwig Feuerbach'))

    def test_pdfcreator_producer_is_suspicious(self):
        meta = {'extra_json': json.dumps({'producer': 'PDFCreator 2.5'})}
        self.assertTrue(pattern_db._is_pdf_internal_suspicious(meta, 'Some Author'))

    def test_calibre_is_not_suspicious(self):
        """Calibre re-saves PDFs but preserves real metadata — must NOT trip the gate.
        Oil Kings is the canonical regression anchor here."""
        meta = {
            'title': 'The Oil Kings',
            'authors': 'Cooper, Andrew Scott',
            'extra_json': json.dumps({'creator': 'calibre 1.22.0', 'producer': 'calibre 1.22.0 [http://calibre-ebook.com]'}),
        }
        self.assertFalse(pattern_db._is_pdf_internal_suspicious(meta, 'Cooper, Andrew Scott'))

    def test_adobe_indesign_is_not_suspicious(self):
        """InDesign-produced PDFs from real publishers (Helen Boak / Manchester UP) must NOT trip."""
        meta = {
            'title': 'Women in the Weimar Republic',
            'extra_json': json.dumps({'creator': 'Adobe InDesign CS6 (Macintosh)', 'producer': 'Adobe PDF Library 10.0.1'}),
        }
        self.assertFalse(pattern_db._is_pdf_internal_suspicious(meta, 'Helen Boak'))

    def test_acrobat_distiller_is_not_suspicious(self):
        """Mackinder uses Acrobat Distiller (legitimate prepress tool) — must NOT trip."""
        meta = {'extra_json': json.dumps({'producer': 'Acrobat Distiller 5.0.5 for Macintosh'})}
        self.assertFalse(pattern_db._is_pdf_internal_suspicious(meta, 'Halford John Mackinder'))

    def test_filename_author_appears_in_pdf_title_is_suspicious(self):
        """If the PDF title contains the filename-derived author verbatim, the PDF metadata
        is almost certainly the filename injected as title (Pdf995 pattern)."""
        meta = {
            'title': '(Great Books in Philosophy) Ludwig Feuerbach',
            'extra_json': json.dumps({'producer': 'Some Innocuous Producer'}),
        }
        self.assertTrue(pattern_db._is_pdf_internal_suspicious(meta, 'Ludwig Feuerbach'))

    def test_clean_metadata_is_not_suspicious(self):
        meta = {
            'title': 'Real Book Title',
            'authors': 'Real Author',
            'extra_json': json.dumps({'producer': 'Real Publisher Press'}),
        }
        self.assertFalse(pattern_db._is_pdf_internal_suspicious(meta, 'Real Author'))

    def test_missing_extra_json_handles_gracefully(self):
        """If extra_json is missing or unparseable, the gate must not throw."""
        self.assertFalse(pattern_db._is_pdf_internal_suspicious({'title': 'X'}, 'Y'))
        self.assertFalse(pattern_db._is_pdf_internal_suspicious({'extra_json': 'not-json'}, 'Y'))

    def test_no_filename_author_no_tool_fingerprint(self):
        """When filename author is None and no tool fingerprint, gate is False."""
        meta = {'title': 'X', 'extra_json': json.dumps({'producer': 'Some Press'})}
        self.assertFalse(pattern_db._is_pdf_internal_suspicious(meta, None))


class TestExtractMetadataPdf995EndToEnd(unittest.TestCase):
    """SCRUM-323 end-to-end: a Pdf995-fingerprinted PDF with the Feuerbach-style filename
    must produce the filename-parsed title/author/year, not the PDF's internal junk."""

    def setUp(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF not installed')
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, 'test.db')
        self.output_file = os.path.join(self.tmp_dir, 'meta.json')
        self.script = str(Path(__file__).resolve().parent / 'pattern_db.py')

        # Reproduce Feuerbach's actual PDF metadata: empty title, literal 'None' author,
        # creator='Pdf995', producer='GPL Ghostscript 8.15', creationDate in 2006.
        self.pdf_path = os.path.join(
            self.tmp_dir,
            '(Great Books in Philosophy) Ludwig Feuerbach - The Essence of Christianity (Great Books in Philosophy)-Prometheus Books (1989).pdf',
        )
        doc = fitz.open()
        doc.new_page()
        doc.set_metadata({
            'title': '',
            'author': 'None',
            'creator': 'Pdf995',
            'producer': 'GPL Ghostscript 8.15',
            'creationDate': "D:20060420073213",
        })
        doc.save(self.pdf_path)
        doc.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run_cli(self, args):
        cmd = [sys.executable, self.script, '--db-path', self.db_path] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr

    def test_feuerbach_extract_uses_filename_metadata(self):
        rc, stdout, stderr = self._run_cli([
            'extract-metadata', '--file', self.pdf_path,
            '--output-file', self.output_file,
        ])
        self.assertEqual(rc, 0, f'stderr: {stderr}')
        with open(self.output_file) as f:
            data = json.load(f)

        # Title and author must come from the filename, not the empty/junk PDF fields.
        self.assertIn('Essence of Christianity', data.get('title') or '')
        self.assertNotIn('Prometheus', data.get('title') or '')
        self.assertEqual(data.get('authors'), 'Ludwig Feuerbach')

        # Year must be the publication year (1989) from the filename, NOT the PDF
        # creationDate year (2006).
        self.assertEqual(data.get('year'), '1989')


if __name__ == '__main__':
    unittest.main()
