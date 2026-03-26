# Book Metadata Capture & Reapplication — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract metadata from source files (PDF/EPUB), merge with filename-derived metadata, store in the pattern database, and reapply to all pipeline outputs — solving the "Unknown author" problem on Kindle.

**Architecture:** New `book_metadata` table in the existing SQLite database (`tools/data/ebook_patterns.db`). Python extraction functions in `tools/pattern_db.py` read internal PDF/EPUB metadata, merge with filename-derived data using a priority hierarchy, and expose CLI subcommands. PowerShell pipeline functions call these via `Start-Process` early in conversion, passing merged metadata to Calibre and email delivery.

**Tech Stack:** Python 3.8+ (PyMuPDF/fitz for PDF, ebooklib for EPUB), SQLite, PowerShell 5.1+. Zero new dependencies.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/pattern_db.py` | MODIFY | Add `book_metadata` table schema, extraction functions, merge logic, store/get functions, CLI subcommands |
| `tools/test_metadata.py` | CREATE | Unit tests for all metadata extraction, merge, store/get, CLI functions |
| `module/EbookAutomation.psm1` | MODIFY | Add early metadata capture blocks in `Convert-ToKindle`, `Convert-ToTTS`, `Send-ToKindle` |
| `tools/email_to_kindle.py` | MODIFY | Add `--metadata-file` argument, apply metadata to compressed/split PDFs |
| `CLAUDE.md` | MODIFY | Document metadata system |

---

## Task 1: Database Schema — `book_metadata` Table

**Files:**
- Modify: `tools/pattern_db.py` (lines 42-196 — schema and indexes)
- Test: `tools/test_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
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


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tools/test_metadata.py TestBookMetadataSchema -v`
Expected: FAIL — `book_metadata` table not found

- [ ] **Step 3: Add book_metadata table to schema and indexes**

In `tools/pattern_db.py`, append to `_SCHEMA_SQL` (before the closing `"""`):

```sql
-- Book metadata extracted from source files and merged across sources
CREATE TABLE IF NOT EXISTS book_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT,
    isbn TEXT,
    title_hash TEXT,
    title TEXT,
    authors TEXT,
    publisher TEXT,
    year TEXT,
    language TEXT DEFAULT 'en',
    subject TEXT,
    series TEXT,
    description TEXT,
    cover_path TEXT,
    extra_json TEXT,
    source_filename TEXT,
    source_type TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Append to `_INDEXES_SQL`:

```sql
CREATE INDEX IF NOT EXISTS idx_book_metadata_title_hash
    ON book_metadata(title_hash);
CREATE INDEX IF NOT EXISTS idx_book_metadata_isbn
    ON book_metadata(isbn);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tools/test_metadata.py TestBookMetadataSchema -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/pattern_db.py tools/test_metadata.py
git commit -m "feat: add book_metadata table schema and indexes"
```

---

## Task 2: Helper Functions — Garbage Filtering & Field Extraction

**Files:**
- Modify: `tools/pattern_db.py`
- Test: `tools/test_metadata.py`

- [ ] **Step 1: Write the failing tests**

Add to `tools/test_metadata.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tools/test_metadata.py TestMetadataHelpers -v`
Expected: FAIL — `_clean_meta_field` and `_extract_year` not defined

- [ ] **Step 3: Implement helper functions**

Add to `tools/pattern_db.py` in the Helpers section (near `_normalize_title_hash`):

```python
# Known software/tool names that appear as author/publisher in PDF metadata
_GARBAGE_CREATOR_NAMES = {
    'microsoft word', 'adobe indesign', 'adobe acrobat', 'latex',
    'pdflatex', 'xelatex', 'lualatex', 'tex', 'pdftex', 'xetex',
    'quarkxpress', 'libreoffice', 'openoffice', 'google docs',
    'calibre', 'prince', 'wkhtmltopdf', 'phantomjs', 'chrome',
    'firefox', 'acrobat distiller', 'acrobat pdfmaker',
    'microsoft office word', 'pages',
}

_GARBAGE_TITLES = {'untitled', 'document', 'microsoft word', 'unnamed'}


def _clean_meta_field(value, field_type='generic'):
    """Filter garbage values from PDF/EPUB metadata fields.

    Returns cleaned string or None if the value is empty or garbage.
    """
    if not value or not value.strip():
        return None

    cleaned = value.strip()

    if field_type == 'author':
        if cleaned.lower() in ('unknown', 'unknown author', ''):
            return None
        if cleaned.lower() in _GARBAGE_CREATOR_NAMES:
            return None

    elif field_type == 'title':
        if cleaned.lower() in _GARBAGE_TITLES:
            return None

    elif field_type == 'publisher':
        if cleaned.lower() in _GARBAGE_CREATOR_NAMES:
            return None

    return cleaned


def _extract_year(date_string):
    """Extract a 4-digit year from a PDF date string or plain string.

    PDF dates look like: D:20190415120000+00'00'
    Returns year as string (e.g., '2019') or None.
    """
    if not date_string:
        return None
    match = re.search(r'(1[89]\d{2}|20\d{2})', str(date_string))
    return match.group(1) if match else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tools/test_metadata.py TestMetadataHelpers -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/pattern_db.py tools/test_metadata.py
git commit -m "feat: add metadata garbage-filtering helpers"
```

---

## Task 3: PDF Metadata Extraction

**Files:**
- Modify: `tools/pattern_db.py`
- Test: `tools/test_metadata.py`

- [ ] **Step 1: Write the failing test**

Add to `tools/test_metadata.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tools/test_metadata.py TestPdfMetadataExtraction -v`
Expected: FAIL — `extract_pdf_metadata` not defined

- [ ] **Step 3: Implement extract_pdf_metadata**

Add to `tools/pattern_db.py`:

```python
def extract_pdf_metadata(file_path):
    """Extract metadata from a PDF file via PyMuPDF.

    Returns dict with keys: title, authors, publisher, year, language,
    subject, description, isbn, extra_json. All values are strings or None.
    Only non-None values are included in the returned dict.
    """
    import fitz
    doc = fitz.open(file_path)
    meta = doc.metadata or {}
    doc.close()

    result = {
        'title': _clean_meta_field(meta.get('title'), field_type='title'),
        'authors': _clean_meta_field(meta.get('author'), field_type='author'),
        'subject': meta.get('subject') or None,
        'publisher': _clean_meta_field(meta.get('creator'), field_type='publisher'),
        'year': _extract_year(meta.get('creationDate')),
    }

    # Store raw metadata in extra_json for debugging/traceability
    extra = {}
    for key in ('keywords', 'producer', 'creator'):
        val = meta.get(key)
        if val:
            extra[key] = val
    if extra:
        result['extra_json'] = json.dumps(extra)

    return {k: v for k, v in result.items() if v}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tools/test_metadata.py TestPdfMetadataExtraction -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/pattern_db.py tools/test_metadata.py
git commit -m "feat: add PDF metadata extraction via PyMuPDF"
```

---

## Task 4: EPUB Metadata Extraction

**Files:**
- Modify: `tools/pattern_db.py`
- Test: `tools/test_metadata.py`

- [ ] **Step 1: Write the failing test**

Add to `tools/test_metadata.py`:

```python
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

        # Need at least one chapter for a valid EPUB
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tools/test_metadata.py TestEpubMetadataExtraction -v`
Expected: FAIL — `extract_epub_metadata` not defined

- [ ] **Step 3: Implement extract_epub_metadata**

Add to `tools/pattern_db.py`:

```python
def _get_epub_meta(book, namespace, name):
    """Get a single metadata value from an ebooklib EpubBook.

    Returns the first value as a string, or None.
    """
    try:
        items = book.get_metadata(namespace, name)
        if items:
            val = items[0][0]
            if isinstance(val, str) and val.strip():
                return val.strip()
    except Exception:
        pass
    return None


def _extract_isbn_from_epub(book):
    """Extract ISBN from EPUB DC:identifier fields.

    Checks for identifiers that match ISBN-10 or ISBN-13 patterns,
    including 'isbn:' prefixed values.
    """
    try:
        identifiers = book.get_metadata('DC', 'identifier')
        for ident_tuple in identifiers:
            val = str(ident_tuple[0]).strip()
            # Strip common prefixes
            for prefix in ('isbn:', 'urn:isbn:', 'ISBN:'):
                if val.lower().startswith(prefix.lower()):
                    val = val[len(prefix):]
                    break
            # Check for ISBN pattern (10 or 13 digits, optional hyphens)
            cleaned = val.replace('-', '')
            if re.match(r'^(97[89])?\d{9}[\dXx]$', cleaned):
                return cleaned
    except Exception:
        pass
    return None


def extract_epub_metadata(file_path):
    """Extract metadata from an EPUB file via ebooklib.

    Returns dict with keys: title, authors, publisher, language,
    description, isbn, subject. Only non-None values included.
    """
    from ebooklib import epub
    book = epub.read_epub(file_path, options={'ignore_ncx': True})

    result = {
        'title': _get_epub_meta(book, 'DC', 'title'),
        'authors': _get_epub_meta(book, 'DC', 'creator'),
        'publisher': _get_epub_meta(book, 'DC', 'publisher'),
        'language': _get_epub_meta(book, 'DC', 'language'),
        'description': _get_epub_meta(book, 'DC', 'description'),
        'isbn': _extract_isbn_from_epub(book),
        'subject': _get_epub_meta(book, 'DC', 'subject'),
    }
    return {k: v for k, v in result.items() if v}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tools/test_metadata.py TestEpubMetadataExtraction -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/pattern_db.py tools/test_metadata.py
git commit -m "feat: add EPUB metadata extraction via ebooklib"
```

---

## Task 5: File Router & Store/Get/Merge Functions

**Files:**
- Modify: `tools/pattern_db.py`
- Test: `tools/test_metadata.py`

- [ ] **Step 1: Write the failing tests**

Add to `tools/test_metadata.py`:

```python
class TestExtractFileMetadata(unittest.TestCase):
    """Tests for the extract_file_metadata router."""

    def test_routes_pdf(self):
        """Should call extract_pdf_metadata for .pdf files."""
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
        """Should return empty dict for unsupported formats."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tools/test_metadata.py TestExtractFileMetadata TestStoreAndGetBookMetadata TestMergeMetadata -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement extract_file_metadata, store_book_metadata, get_book_metadata, merge_metadata**

Add to `tools/pattern_db.py`:

```python
def extract_file_metadata(file_path):
    """Extract internal metadata from a file based on its format.

    Returns dict. For formats without internal metadata (TXT, MOBI, etc.),
    returns empty dict — filename parsing fills the gaps.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return extract_pdf_metadata(file_path)
    elif ext == '.epub':
        return extract_epub_metadata(file_path)
    else:
        return {}


# Source priority for merge decisions
_SOURCE_PRIORITY = {
    'filename_parser': 1,
    'pdf_internal': 2,
    'epub_opf': 3,
    'database': 4,
    'user_override': 5,
    'claude_api': 5,
    'merged': 3,  # treat merged as medium priority
}

# Fields that participate in merge
_METADATA_FIELDS = [
    'title', 'authors', 'publisher', 'year', 'language', 'subject',
    'series', 'description', 'isbn', 'cover_path', 'extra_json',
]


def merge_metadata(existing, new_fields, new_source_type):
    """Merge new metadata fields into existing, respecting source priority.

    For each field:
    - If existing is empty/None, use new value
    - If both have values, higher priority source wins

    Returns merged dict with source_type set to 'merged' when multiple
    sources contribute.
    """
    result = dict(existing)
    existing_priority = _SOURCE_PRIORITY.get(existing.get('source_type', ''), 0)
    new_priority = _SOURCE_PRIORITY.get(new_source_type, 0)
    sources_used = set()

    if existing.get('source_type'):
        sources_used.add(existing['source_type'])

    for field in _METADATA_FIELDS:
        existing_val = result.get(field)
        new_val = new_fields.get(field)
        if new_val and (not existing_val or new_priority > existing_priority):
            result[field] = new_val
            sources_used.add(new_source_type)
        elif existing_val:
            pass  # keep existing

    if len(sources_used) > 1:
        result['source_type'] = 'merged'
    elif sources_used:
        result['source_type'] = sources_used.pop()
    else:
        result['source_type'] = new_source_type

    return result


def store_book_metadata(title_hash=None, isbn=None, title=None, authors=None,
                        publisher=None, year=None, language=None, subject=None,
                        series=None, description=None, cover_path=None,
                        extra_json=None, source_filename=None,
                        source_type=None, book_id=None, db_path=None):
    """Store or update book metadata in the database.

    Uses INSERT OR REPLACE keyed on title_hash (via DELETE + INSERT
    since SQLite INSERT OR REPLACE needs a UNIQUE constraint).
    Returns the stored metadata as a dict.
    """
    conn = get_db(db_path)
    try:
        # Check for existing entry by title_hash
        existing = None
        if title_hash:
            row = conn.execute(
                "SELECT * FROM book_metadata WHERE title_hash = ?",
                (title_hash,)
            ).fetchone()
            if row:
                existing = dict(row)

        if existing:
            # Update existing entry
            conn.execute(
                """UPDATE book_metadata SET
                    book_id = COALESCE(?, book_id),
                    isbn = COALESCE(?, isbn),
                    title = COALESCE(?, title),
                    authors = COALESCE(?, authors),
                    publisher = COALESCE(?, publisher),
                    year = COALESCE(?, year),
                    language = COALESCE(?, language),
                    subject = COALESCE(?, subject),
                    series = COALESCE(?, series),
                    description = COALESCE(?, description),
                    cover_path = COALESCE(?, cover_path),
                    extra_json = COALESCE(?, extra_json),
                    source_filename = COALESCE(?, source_filename),
                    source_type = COALESCE(?, source_type),
                    updated_at = CURRENT_TIMESTAMP
                WHERE title_hash = ?""",
                (book_id, isbn, title, authors, publisher, year,
                 language, subject, series, description, cover_path,
                 extra_json, source_filename, source_type, title_hash)
            )
        else:
            # Insert new entry
            conn.execute(
                """INSERT INTO book_metadata
                   (book_id, isbn, title_hash, title, authors, publisher,
                    year, language, subject, series, description,
                    cover_path, extra_json, source_filename, source_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (book_id, isbn, title_hash, title, authors, publisher,
                 year, language, subject, series, description,
                 cover_path, extra_json, source_filename, source_type)
            )
        conn.commit()

        # Return the stored record
        row = conn.execute(
            "SELECT * FROM book_metadata WHERE title_hash = ?",
            (title_hash,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_book_metadata(title_hash=None, isbn=None, title=None, author=None,
                      db_path=None):
    """Look up stored metadata for a book.

    Priority: title_hash > isbn > title+author fuzzy match.
    Returns dict with all metadata fields, or None if not found.
    """
    conn = get_db(db_path)
    try:
        row = None

        # 1. title_hash lookup
        if title_hash:
            row = conn.execute(
                "SELECT * FROM book_metadata WHERE title_hash = ?",
                (title_hash,)
            ).fetchone()

        # 2. ISBN lookup
        if not row and isbn:
            row = conn.execute(
                "SELECT * FROM book_metadata WHERE isbn = ?",
                (isbn,)
            ).fetchone()

        # 3. Title+author fuzzy match
        if not row and title:
            computed_hash = _normalize_title_hash(title, author)
            if computed_hash:
                row = conn.execute(
                    "SELECT * FROM book_metadata WHERE title_hash = ?",
                    (computed_hash,)
                ).fetchone()

        return dict(row) if row else None
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tools/test_metadata.py TestExtractFileMetadata TestStoreAndGetBookMetadata TestMergeMetadata -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/pattern_db.py tools/test_metadata.py
git commit -m "feat: add metadata store, get, merge, and file router functions"
```

---

## Task 6: CLI Subcommands

**Files:**
- Modify: `tools/pattern_db.py` (main/argparse section, lines 1935-2073)
- Test: `tools/test_metadata.py`

- [ ] **Step 1: Write the failing tests**

Add to `tools/test_metadata.py`:

```python
import subprocess

class TestMetadataCLI(unittest.TestCase):
    """Tests for CLI subcommands: extract-metadata, get-metadata, update-metadata."""

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
        # Create test PDF
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
        # Store first
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
        # Store initial
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
        # Verify it was stored
        result = pattern_db.get_book_metadata(title_hash='store_test_hash', db_path=self.db_path)
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Stored Book')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tools/test_metadata.py TestMetadataCLI -v`
Expected: FAIL — subcommands not recognized

- [ ] **Step 3: Add CLI subcommands to argparse and command handlers**

In `tools/pattern_db.py`, add to the subparsers section (after the `override` subparser, before `args = parser.parse_args()`):

```python
    # ── Metadata subcommands ──────────────────────────────────────────
    extract_meta_parser = subparsers.add_parser(
        'extract-metadata',
        help='Extract internal metadata from a file, merge with DB, store, output JSON'
    )
    extract_meta_parser.add_argument('--file', required=True, help='Path to ebook file')
    extract_meta_parser.add_argument(
        '--output-file', required=True, help='Path to write merged metadata JSON'
    )

    get_meta_parser = subparsers.add_parser(
        'get-metadata', help='Retrieve stored metadata by title-hash, isbn, or title+author'
    )
    get_meta_parser.add_argument('--title-hash', default=None)
    get_meta_parser.add_argument('--isbn', default=None)
    get_meta_parser.add_argument('--title', default=None)
    get_meta_parser.add_argument('--author', default=None)
    get_meta_parser.add_argument('--output-file', required=True, help='Path to write JSON')

    update_meta_parser = subparsers.add_parser(
        'update-metadata', help='Update specific metadata fields (merge with priority)'
    )
    update_meta_parser.add_argument('--title-hash', required=True)
    update_meta_parser.add_argument('--title', default=None)
    update_meta_parser.add_argument('--authors', default=None)
    update_meta_parser.add_argument('--publisher', default=None)
    update_meta_parser.add_argument('--year', default=None)
    update_meta_parser.add_argument('--isbn', default=None)
    update_meta_parser.add_argument('--cover-path', default=None)
    update_meta_parser.add_argument('--source-type', default='filename_parser')
    update_meta_parser.add_argument('--output-file', default=None,
                                    help='Optional: write merged result as JSON')

    store_meta_parser = subparsers.add_parser(
        'store-metadata', help='Store metadata from a JSON file'
    )
    store_meta_parser.add_argument('--metadata-file', required=True,
                                   help='Path to JSON file with metadata fields')
```

Add command handler functions:

```python
def _cmd_extract_metadata(args):
    """Extract internal metadata, merge with DB, store, output JSON."""
    file_path = os.path.abspath(args.file)
    if not os.path.isfile(file_path):
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)

    # Extract internal metadata
    internal_meta = extract_file_metadata(file_path)

    # Derive title_hash from internal metadata or filename
    filename = os.path.basename(file_path)
    title = internal_meta.get('title')
    authors = internal_meta.get('authors')
    if not title:
        parsed_title, parsed_author = _parse_metadata_from_filename(filename)
        title = parsed_title
        authors = authors or parsed_author

    title_hash = _normalize_title_hash(title, authors)
    if not title_hash:
        title_hash = _normalize_title_hash(Path(file_path).stem)

    # Check DB for existing entry
    existing = get_book_metadata(title_hash=title_hash, db_path=args.db_path)

    # Determine source type based on file format
    ext = os.path.splitext(file_path)[1].lower()
    source_type = 'pdf_internal' if ext == '.pdf' else 'epub_opf' if ext == '.epub' else 'filename_parser'

    if existing:
        merged = merge_metadata(existing, internal_meta, source_type)
    else:
        merged = dict(internal_meta)
        merged['source_type'] = source_type

    merged['title_hash'] = title_hash
    merged['source_filename'] = filename
    if title and 'title' not in merged:
        merged['title'] = title
    if authors and 'authors' not in merged:
        merged['authors'] = authors

    # Store merged result
    store_book_metadata(
        title_hash=title_hash,
        isbn=merged.get('isbn'),
        title=merged.get('title'),
        authors=merged.get('authors'),
        publisher=merged.get('publisher'),
        year=merged.get('year'),
        language=merged.get('language'),
        subject=merged.get('subject'),
        series=merged.get('series'),
        description=merged.get('description'),
        cover_path=merged.get('cover_path'),
        extra_json=merged.get('extra_json'),
        source_filename=filename,
        source_type=merged.get('source_type'),
        db_path=args.db_path,
    )

    # Write output JSON
    # Strip internal DB fields from output
    output = {k: v for k, v in merged.items()
              if v is not None and k not in ('id', 'created_at', 'updated_at')}
    with open(args.output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def _cmd_get_metadata(args):
    """Retrieve stored metadata and write to JSON."""
    result = get_book_metadata(
        title_hash=args.title_hash,
        isbn=args.isbn,
        title=args.title,
        author=args.author,
        db_path=args.db_path,
    )
    output = {}
    if result:
        output = {k: v for k, v in result.items()
                  if v is not None and k not in ('id', 'created_at', 'updated_at')}
    with open(args.output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def _cmd_update_metadata(args):
    """Update specific fields via merge priority logic."""
    existing = get_book_metadata(title_hash=args.title_hash, db_path=args.db_path)
    if not existing:
        existing = {'title_hash': args.title_hash}

    new_fields = {}
    for field in ('title', 'authors', 'publisher', 'year', 'isbn', 'cover_path'):
        val = getattr(args, field.replace('-', '_'), None)
        if val:
            new_fields[field] = val

    merged = merge_metadata(existing, new_fields, args.source_type)
    merged['title_hash'] = args.title_hash

    store_book_metadata(
        title_hash=args.title_hash,
        title=merged.get('title'),
        authors=merged.get('authors'),
        publisher=merged.get('publisher'),
        year=merged.get('year'),
        isbn=merged.get('isbn'),
        cover_path=merged.get('cover_path'),
        source_type=merged.get('source_type'),
        db_path=args.db_path,
    )

    if args.output_file:
        output = {k: v for k, v in merged.items()
                  if v is not None and k not in ('id', 'created_at', 'updated_at')}
        with open(args.output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)


def _cmd_store_metadata(args):
    """Store metadata from a JSON file."""
    with open(args.metadata_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    store_book_metadata(db_path=args.db_path, **{
        k: v for k, v in data.items()
        if k in ('title_hash', 'isbn', 'title', 'authors', 'publisher',
                 'year', 'language', 'subject', 'series', 'description',
                 'cover_path', 'extra_json', 'source_filename', 'source_type',
                 'book_id')
    })
```

Add the new commands to the dispatch dict in `main()`:

```python
    commands = {
        'init': _cmd_init,
        'stats': _cmd_stats,
        'import-vqa': _cmd_import_vqa,
        'history': _cmd_history,
        'fixes': _cmd_fixes,
        'trend': _cmd_trend,
        'cost': _cmd_cost,
        'cache': _cmd_cache,
        'classify': _cmd_classify,
        'recommend': _cmd_recommend,
        'extract-metadata': _cmd_extract_metadata,
        'get-metadata': _cmd_get_metadata,
        'update-metadata': _cmd_update_metadata,
        'store-metadata': _cmd_store_metadata,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tools/test_metadata.py TestMetadataCLI -v`
Expected: All tests PASS

- [ ] **Step 5: Run the full test file**

Run: `python tools/test_metadata.py -v`
Expected: All tests PASS (schema + helpers + PDF + EPUB + router + store/get + merge + CLI)

- [ ] **Step 6: Commit**

```bash
git add tools/pattern_db.py tools/test_metadata.py
git commit -m "feat: add metadata CLI subcommands (extract, get, update, store)"
```

---

## Task 7: PowerShell Integration — Convert-ToKindle Metadata Capture

**Files:**
- Modify: `module/EbookAutomation.psm1` (Convert-ToKindle, after line 714)

This task adds the early metadata capture block to `Convert-ToKindle`. The existing `$meta = Get-EbookMetadataFromFilename $fileName` at line 714 is replaced with a richer flow that extracts internal metadata first, merges with filename-derived data, and falls back gracefully.

- [ ] **Step 1: Identify the insertion point**

Read `module/EbookAutomation.psm1` lines 710-740. The target is replacing line 714 (`$meta = Get-EbookMetadataFromFilename $fileName`) with the metadata capture block, keeping the `$cleanStem` and `$outName` derivation intact.

- [ ] **Step 2: Replace the metadata derivation block**

Replace lines 713-714 with:

```powershell
    # ── Early metadata capture ────────────────────────────────────
    $metaTempFile = Join-Path (Resolve-ProjectPath 'processing') "ebook_meta_$(Get-Random).json"
    $titleHash = $null

    try {
        $python    = $cfg.paths.python
        $toolsDir  = Join-Path $script:ModuleRoot 'tools'

        # Step 1: Extract internal metadata from source file and store in database
        $extractArgs = "`"$toolsDir\pattern_db.py`" extract-metadata --file `"$InputFile`" --output-file `"$metaTempFile`""
        $extractProc = Start-Process -FilePath $python -ArgumentList $extractArgs -PassThru -NoNewWindow -Wait

        $dbMeta = $null
        if (Test-Path $metaTempFile) {
            $dbMeta = Get-Content $metaTempFile -Raw | ConvertFrom-Json
            $titleHash = $dbMeta.title_hash
        }

        # Step 2: Merge filename-derived metadata (fills gaps the internal metadata missed)
        $fileMeta = Get-EbookMetadataFromFilename $fileName
        if ($fileMeta.Title -or $fileMeta.Authors) {
            $updateArgs = "`"$toolsDir\pattern_db.py`" update-metadata"
            if ($titleHash) {
                $updateArgs += " --title-hash `"$titleHash`""
            } else {
                # Generate a title_hash from filename metadata for the update
                $hashTitle = if ($fileMeta.Title) { $fileMeta.Title } else { $stem }
                # Use extract-metadata output hash or derive one
                $updateArgs += " --title-hash `"$hashTitle`""
            }
            if ($fileMeta.Title) { $updateArgs += " --title `"$($fileMeta.Title -replace '"', "'")`"" }
            if ($fileMeta.Authors) { $updateArgs += " --authors `"$($fileMeta.Authors -replace '"', "'")`"" }
            if ($fileMeta.Publisher) { $updateArgs += " --publisher `"$($fileMeta.Publisher -replace '"', "'")`"" }
            if ($fileMeta.Year) { $updateArgs += " --year `"$($fileMeta.Year)`"" }
            if ($fileMeta.ISBN) { $updateArgs += " --isbn `"$($fileMeta.ISBN)`"" }
            $updateArgs += " --source-type filename_parser --output-file `"$metaTempFile`""
            Start-Process -FilePath $python -ArgumentList $updateArgs -NoNewWindow -Wait

            # Re-read the merged result
            if (Test-Path $metaTempFile) {
                $dbMeta = Get-Content $metaTempFile -Raw | ConvertFrom-Json
                $titleHash = $dbMeta.title_hash
            }
        }

        # Step 3: Build $meta from merged database metadata, filling gaps from filename
        if (-not $fileMeta) { $fileMeta = Get-EbookMetadataFromFilename $fileName }
        $meta = @{
            Title     = if ($dbMeta -and $dbMeta.title) { $dbMeta.title } else { $fileMeta.Title }
            Authors   = if ($dbMeta -and $dbMeta.authors) { $dbMeta.authors } else { $fileMeta.Authors }
            Publisher = if ($dbMeta -and $dbMeta.publisher) { $dbMeta.publisher } else { $fileMeta.Publisher }
            Year      = if ($dbMeta -and $dbMeta.year) { $dbMeta.year } else { $fileMeta.Year }
            ISBN      = if ($dbMeta -and $dbMeta.isbn) { $dbMeta.isbn } else { $fileMeta.ISBN }
        }

        Write-EbookLog "Kindle: metadata source -> $( if ($dbMeta.source_type) { $dbMeta.source_type } else { 'filename_parser' } )"
    }
    catch {
        Write-EbookLog "Kindle: metadata capture failed (non-blocking) -- $_" -Level WARN
        # Fall back to filename-only metadata (existing behavior)
        $fileMeta = Get-EbookMetadataFromFilename $fileName
        $meta = @{
            Title = $fileMeta.Title; Authors = $fileMeta.Authors
            Publisher = $fileMeta.Publisher; Year = $fileMeta.Year; ISBN = $fileMeta.ISBN
        }
    }
    finally {
        if (Test-Path $metaTempFile -ErrorAction SilentlyContinue) {
            Remove-Item $metaTempFile -Force -ErrorAction SilentlyContinue
        }
    }
```

The existing `$cleanStem` and `$outName` logic (lines 715-739) continues to work unchanged since it references `$meta.Title` and `$meta.Authors`, which are now populated from the merged source.

- [ ] **Step 3: Test manually with a real PDF**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psm1; Convert-ToKindle -InputFile 'inbox\SomeBook.pdf' -WhatIf -Verbose" 2>&1 | head -30`

Verify log output shows "Kindle: metadata source -> pdf_internal" or "merged" instead of only filename_parser.

- [ ] **Step 4: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: add metadata capture to Convert-ToKindle (extract + merge + fallback)"
```

---

## Task 8: PowerShell Integration — Convert-ToTTS Metadata Capture

**Files:**
- Modify: `module/EbookAutomation.psm1` (Convert-ToTTS function)

Database-population-only metadata capture. The TTS path outputs plain text (no metadata container), but capturing here ensures the database is populated for other pipeline steps and future features.

- [ ] **Step 1: Identify the insertion point**

Read `module/EbookAutomation.psm1` around the Convert-ToTTS function. Find the `$fileName` assignment and input validation section, before text extraction begins. The metadata capture block goes after `$fileName` is set and before the PDF/EPUB extraction logic.

- [ ] **Step 2: Add metadata capture block**

Insert after the `$fileName` / input validation section (before text extraction begins):

```powershell
    # ── Early metadata capture (database population only) ──────────
    $metaTempFile = Join-Path (Resolve-ProjectPath 'processing') "ebook_meta_tts_$(Get-Random).json"
    try {
        $python   = $cfg.paths.python
        $toolsDir = Join-Path $script:ModuleRoot 'tools'

        # Extract internal metadata from source file and store in database
        $extractArgs = "`"$toolsDir\pattern_db.py`" extract-metadata --file `"$InputFile`" --output-file `"$metaTempFile`""
        Start-Process -FilePath $python -ArgumentList $extractArgs -PassThru -NoNewWindow -Wait | Out-Null

        # Merge filename-derived metadata
        $fileMeta = Get-EbookMetadataFromFilename $fileName
        if (($fileMeta.Title -or $fileMeta.Authors) -and (Test-Path $metaTempFile)) {
            $dbMeta = Get-Content $metaTempFile -Raw | ConvertFrom-Json
            $titleHash = $dbMeta.title_hash
            if ($titleHash) {
                $updateArgs = "`"$toolsDir\pattern_db.py`" update-metadata --title-hash `"$titleHash`""
                if ($fileMeta.Title) { $updateArgs += " --title `"$($fileMeta.Title -replace '"', "'")`"" }
                if ($fileMeta.Authors) { $updateArgs += " --authors `"$($fileMeta.Authors -replace '"', "'")`"" }
                if ($fileMeta.Publisher) { $updateArgs += " --publisher `"$($fileMeta.Publisher -replace '"', "'")`"" }
                if ($fileMeta.Year) { $updateArgs += " --year `"$($fileMeta.Year)`"" }
                if ($fileMeta.ISBN) { $updateArgs += " --isbn `"$($fileMeta.ISBN)`"" }
                $updateArgs += " --source-type filename_parser"
                Start-Process -FilePath $python -ArgumentList $updateArgs -NoNewWindow -Wait | Out-Null
            }
        }
        Write-EbookLog "TTS: metadata captured to database"
    }
    catch {
        Write-EbookLog "TTS: metadata capture failed (non-blocking) -- $_" -Level WARN
    }
    finally {
        if (Test-Path $metaTempFile -ErrorAction SilentlyContinue) {
            Remove-Item $metaTempFile -Force -ErrorAction SilentlyContinue
        }
    }
```

Note: Unlike Convert-ToKindle, this block does NOT build a `$meta` hashtable from the merged result — Convert-ToTTS doesn't need metadata for output naming or Calibre flags. The block exists solely to populate the database.

- [ ] **Step 3: Test manually**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psm1; Convert-ToTTS -InputFile 'inbox\SomeBook.pdf' -WhatIf -Verbose" 2>&1 | head -20`

Verify log shows "TTS: metadata captured to database" or "TTS: metadata capture failed (non-blocking)".

- [ ] **Step 4: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: add metadata capture to Convert-ToTTS (database population)"
```

---

## Task 9: PowerShell Integration — Send-ToKindle Metadata Lookup

**Files:**
- Modify: `module/EbookAutomation.psm1` (Send-ToKindle function, email path around lines 2170-2200)

- [ ] **Step 1: Identify the insertion point**

The target is around line 2170-2182 where `$emailMeta` and `$bookTitle` are derived. After this block, before the `$pyArgs` construction, add a metadata lookup from the database and pass `--metadata-file` to `email_to_kindle.py`.

- [ ] **Step 2: Add metadata lookup and --metadata-file passing**

After line 2178 (the `$bookTitle` assignment), add:

```powershell
            # Look up enriched metadata from database (may have PDF/EPUB internal metadata)
            $metaTempFile = Join-Path (Resolve-ProjectPath 'processing') "ebook_meta_send_$(Get-Random).json"
            try {
                $toolsDir = Join-Path $script:ModuleRoot 'tools'
                $lookupArgs = "`"$toolsDir\pattern_db.py`" get-metadata"
                if ($emailMeta.Title) {
                    $lookupArgs += " --title `"$($emailMeta.Title -replace '"', "'")`""
                }
                if ($emailMeta.Authors) {
                    $lookupArgs += " --author `"$($emailMeta.Authors -replace '"', "'")`""
                }
                $lookupArgs += " --output-file `"$metaTempFile`""
                Start-Process -FilePath $python -ArgumentList $lookupArgs -NoNewWindow -Wait

                if ((Test-Path $metaTempFile) -and (Get-Item $metaTempFile).Length -gt 5) {
                    $pyArgs += " --metadata-file `"$metaTempFile`""
                    Write-EbookLog "SendToKindle: passing enriched metadata to email script"
                }
            }
            catch {
                Write-EbookLog "SendToKindle: metadata lookup failed (non-blocking) -- $_" -Level WARN
            }
```

After the email process completes (around line 2246), add cleanup:

```powershell
            if (Test-Path $metaTempFile -ErrorAction SilentlyContinue) {
                Remove-Item $metaTempFile -Force -ErrorAction SilentlyContinue
            }
```

- [ ] **Step 3: Test manually**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psm1; Send-ToKindle -InputFile 'output\kindle\SomeBook.epub' -Email -WhatIf" 2>&1`

Verify it shows "SendToKindle: passing enriched metadata to email script" or gracefully falls back.

- [ ] **Step 4: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: add metadata lookup to Send-ToKindle email path"
```

---

## Task 10: email_to_kindle.py — Metadata Application to PDFs

**Files:**
- Modify: `tools/email_to_kindle.py` (add `--metadata-file` argument, apply metadata to PDFs)
- Test: `tools/test_metadata.py`

- [ ] **Step 1: Write the failing test**

Add to `tools/test_metadata.py`:

```python
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
        # Add tools/ to path for email_to_kindle
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import email_to_kindle

        # Create PDF with no metadata in a subdirectory (avoid collision with output)
        src_dir = os.path.join(self.tmp_dir, 'src')
        os.makedirs(src_dir)
        pdf_path = os.path.join(src_dir, 'empty_meta.pdf')
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        metadata = {'title': 'Injected Title', 'authors': 'Injected Author', 'subject': 'Test'}
        result_path = email_to_kindle.inject_metadata_if_needed(pdf_path, metadata, self.tmp_dir)

        # Should have created a new file with _metadata suffix
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

        # Should return the original path (no modification needed)
        self.assertEqual(result_path, pdf_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tools/test_metadata.py TestEmailToKindleMetadata -v`
Expected: FAIL — `inject_metadata_if_needed` not defined

- [ ] **Step 3: Add --metadata-file argument and inject_metadata_if_needed to email_to_kindle.py**

In `tools/email_to_kindle.py`, add to `build_arg_parser()` (after the `--password-env-var` argument):

```python
    p.add_argument('--metadata-file', default=None,
                   help='Path to JSON file with book metadata (title, authors, etc.) '
                        'for injecting into PDFs with empty internal metadata')
```

Add the `inject_metadata_if_needed` function (before `main()`):

```python
def inject_metadata_if_needed(file_path, metadata, temp_dir):
    """Inject metadata into a PDF if its internal metadata is empty.

    Args:
        file_path: Path to the PDF file.
        metadata: Dict with keys like 'title', 'authors', 'subject'.
        temp_dir: Directory for writing the modified copy.

    Returns:
        Path to the file to send (original if metadata was already present,
        or a new file in temp_dir with metadata injected).
    """
    if not file_path.lower().endswith('.pdf') or not metadata:
        return file_path

    try:
        import fitz
    except ImportError:
        log.warning('PyMuPDF not installed — cannot inject PDF metadata')
        return file_path

    doc = fitz.open(file_path)
    existing = doc.metadata or {}

    # If the PDF already has good title and author, skip injection
    if existing.get('author') and existing.get('title'):
        doc.close()
        return file_path

    # Inject metadata from our database
    doc.set_metadata({
        'author': metadata.get('authors', ''),
        'title': metadata.get('title', ''),
        'subject': metadata.get('subject', ''),
        'creator': 'EbookAutomation',
    })
    stem = Path(file_path).stem
    suffix = Path(file_path).suffix
    output = os.path.join(temp_dir, f'{stem}_metadata{suffix}')
    doc.save(output)
    doc.close()
    log.info('Injected metadata into PDF: title=%s, author=%s',
             metadata.get('title', ''), metadata.get('authors', ''))
    return output
```

In `main()`, after `file_to_send = file_path` (line 566), add metadata loading and injection:

```python
    # --- Load metadata from JSON file if provided ---
    book_metadata = None
    if args.metadata_file and os.path.isfile(args.metadata_file):
        try:
            with open(args.metadata_file, 'r', encoding='utf-8') as mf:
                book_metadata = json.load(mf)
            log.info('Loaded metadata from %s', args.metadata_file)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning('Failed to load metadata file: %s', exc)
```

After the compression/splitting logic and before `send_email()` is called, add metadata injection for the final file(s):

For single-file sends, after `file_to_send` is finalized but before building the MIME message:
```python
    # Inject metadata into PDF if internal metadata is missing
    if book_metadata:
        file_to_send = inject_metadata_if_needed(file_to_send, book_metadata, tmp_dir)
```

For split PDF parts, in the `split_pdf` path, after each part is created:
```python
        # Inject metadata into each split part
        if book_metadata:
            for i, part_path in enumerate(part_paths):
                part_meta = dict(book_metadata)
                part_meta['title'] = f"{book_metadata.get('title', args.book_title)} - Part {i+1} of {len(part_paths)}"
                part_paths[i] = inject_metadata_if_needed(part_path, part_meta, tmp_dir)
```

Also update the `compress_pdf` path — after compression, inject metadata:
```python
        # Re-inject metadata after compression (PyMuPDF compression strips metadata)
        if book_metadata:
            file_to_send = inject_metadata_if_needed(file_to_send, book_metadata, tmp_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tools/test_metadata.py TestEmailToKindleMetadata -v`
Expected: All tests PASS

- [ ] **Step 5: Run the full test suite**

Run: `python tools/test_metadata.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tools/email_to_kindle.py tools/test_metadata.py
git commit -m "feat: add --metadata-file to email_to_kindle.py, inject metadata into PDFs"
```

---

## Task 11: Documentation Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add metadata system documentation**

Add a new section after "## Claude API Integration" in `CLAUDE.md`:

```markdown
---

## Book Metadata System

Centralized metadata capture, storage, and reapplication. Extracts metadata from source files (PDF internal metadata via PyMuPDF, EPUB OPF via ebooklib), merges with filename-derived metadata using a priority hierarchy, and stores in the pattern database.

### Metadata Priority (highest wins)

| Priority | Source | When |
|----------|--------|------|
| 5 | User override / Claude API | Explicit correction |
| 4 | Pattern database (existing entry) | Previously processed |
| 3 | EPUB OPF metadata | EPUB files |
| 2 | PDF internal metadata | PDF files |
| 1 | Filename parser (`Get-EbookMetadataFromFilename`) | Always |

### Database Table

`book_metadata` in `tools/data/ebook_patterns.db` — stores merged metadata per book, keyed on `title_hash`.

### CLI Commands

```bash
python tools/pattern_db.py extract-metadata --file "book.pdf" --output-file meta.json
python tools/pattern_db.py get-metadata --title-hash "abc123" --output-file meta.json
python tools/pattern_db.py update-metadata --title-hash "abc123" --title "Title" --source-type filename_parser
python tools/pattern_db.py store-metadata --metadata-file meta.json
```

### Pipeline Integration

- `Convert-ToKindle`: Extracts + merges metadata before text extraction. Merged values feed Calibre `--title`/`--authors`/etc. flags.
- `Convert-ToTTS`: Extracts + stores metadata (database population only, no reapplication to TXT).
- `Send-ToKindle` (email): Looks up metadata, passes `--metadata-file` to `email_to_kindle.py` which injects metadata into PDFs with empty internal metadata.

All metadata capture is non-blocking — failures log a warning and fall back to filename-only parsing.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document book metadata capture system"
```

---

## Task 12: Integration Verification

- [ ] **Step 1: Run full metadata test suite**

Run: `python tools/test_metadata.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run existing pipeline tests**

Run: `python tools/test_pipeline.py --quick`
Expected: No regressions — metadata changes are additive and non-breaking

- [ ] **Step 3: Manual end-to-end test with a real PDF**

Place a test PDF in `inbox/` and run:
```powershell
Import-Module .\module\EbookAutomation.psm1
Convert-ToKindle -InputFile "inbox\TestBook.pdf" -UseHtmlExtraction -NoCache
```

Verify:
1. Log shows "metadata source -> pdf_internal" or "merged"
2. `python tools/pattern_db.py get-metadata --title "TestBook" --output-file debug/meta_check.json` returns stored metadata
3. Output KFX has correct title/author in Calibre library

- [ ] **Step 4: Final commit with any fixes**

```bash
git add tools/pattern_db.py tools/test_metadata.py tools/email_to_kindle.py module/EbookAutomation.psm1 CLAUDE.md
git commit -m "feat: book metadata capture & reapplication system complete"
```
