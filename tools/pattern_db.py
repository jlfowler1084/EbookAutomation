#!/usr/bin/env python3
"""SQLite pattern database for EbookAutomation pipeline.

Tracks books processed, conversion attempts, issues found, fixes applied,
and learned fix patterns. Foundation for the self-improving converge loop.

Usage:
    python tools/pattern_db.py init          # Create/verify database
    python tools/pattern_db.py stats         # Print summary statistics
    python tools/pattern_db.py import-vqa <report.json>  # Import a VQA report
    python tools/pattern_db.py history <filename>        # Show history for a book
    python tools/pattern_db.py fixes         # List fix patterns with success rates
    python tools/pattern_db.py trend         # Show recent score trend
    python tools/pattern_db.py cost          # Show cost summary
    python tools/pattern_db.py cache <filename>          # Check cache for a book
    python tools/pattern_db.py cache-stats               # Show extraction cache statistics
    python tools/pattern_db.py cache-invalidate [opts]   # Invalidate extraction cache entries
    python tools/pattern_db.py override add <filename>   # Add a book override
    python tools/pattern_db.py override show <filename>  # Show overrides for a book
    python tools/pattern_db.py override list             # List all book overrides
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Default database path: data/ebook_patterns.db relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "ebook_patterns.db"


# ---------------------------------------------------------------------------
# Hashing utilities
# ---------------------------------------------------------------------------

def compute_file_hash(file_path, algorithm='sha256'):
    """Compute SHA-256 hash of a file. Returns hex digest string."""
    h = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_text_hash(text):
    """Compute SHA-256 hash of text content for integrity verification."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- Books processed through the system
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    title TEXT,
    author TEXT,
    publisher TEXT,
    year INTEGER,
    format TEXT NOT NULL,  -- pdf, epub, mobi, azw, etc.
    file_size_bytes INTEGER,
    page_count INTEGER,
    source_type TEXT,  -- digital_native, scan, ocr, unknown
    title_hash TEXT,  -- normalized hash for fuzzy matching
    isbn TEXT,  -- ISBN-10 or ISBN-13
    source_file_path TEXT,  -- original input file path (PDF/EPUB in inbox or library)
    source_file_hash TEXT,  -- SHA-256 hash of the input file (identifies exact file version)
    cover_image_path TEXT,  -- path to extracted cover JPG
    language TEXT DEFAULT 'en',  -- ISO 639-1 language code
    pdf_producer TEXT,  -- PDF metadata: software that produced the file
    pdf_creator TEXT,   -- PDF metadata: original document creator
    detected_scripts TEXT,  -- JSON: detected Unicode script blocks {"latin": 94.2, "hebrew": 3.1}
    word_count INTEGER,  -- approximate word count from extracted text
    chapter_count INTEGER,  -- number of chapters/headings detected
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Each conversion attempt (a book may be converted multiple times across iterations)
CREATE TABLE IF NOT EXISTS conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    iteration INTEGER NOT NULL DEFAULT 1,
    extraction_path TEXT NOT NULL,  -- legacy, html_extraction, column_aware, ocr
    vqa_score INTEGER,
    vqa_report_path TEXT,
    text_quality_score INTEGER,
    fixes_applied INTEGER DEFAULT 0,
    fixes_failed INTEGER DEFAULT 0,
    api_input_tokens INTEGER DEFAULT 0,
    api_output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    duration_seconds REAL,
    output_file_path TEXT,  -- full path to the KFX/AZW3 output file
    output_file_size INTEGER,  -- output file size in bytes
    conversion_flags TEXT,  -- JSON of active flags: {"UseHtmlExtraction": true, ...}
    category_scores TEXT,  -- JSON of per-category VQA scores: {"text_integrity": 83, ...}
    quality_variance REAL,  -- std dev of multi-point quality sampling (0 = uniform, >15 = mixed quality)
    font_inventory TEXT,  -- JSON: unique font names and encodings found during extraction
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual issues found by VQA or text quality pass
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_id INTEGER NOT NULL REFERENCES conversions(id),
    book_id INTEGER NOT NULL REFERENCES books(id),
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT,
    page_number INTEGER,
    fix_attempted BOOLEAN DEFAULT 0,
    fix_succeeded BOOLEAN DEFAULT 0,
    fix_strategy TEXT,
    fix_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fix patterns learned across books
CREATE TABLE IF NOT EXISTS fix_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fix_type TEXT NOT NULL,
    trigger_category TEXT,
    trigger_pattern TEXT,
    fix_action TEXT NOT NULL,
    fix_replacement TEXT,
    publisher TEXT,
    format TEXT,
    source_type TEXT,
    times_applied INTEGER DEFAULT 0,
    times_succeeded INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0,
    avg_score_improvement REAL DEFAULT 0,
    first_seen_book_id INTEGER REFERENCES books(id),
    iteration_discovered INTEGER,
    promoted_to_iteration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Track extraction path switches and their outcomes
CREATE TABLE IF NOT EXISTS path_switches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    from_path TEXT NOT NULL,
    to_path TEXT NOT NULL,
    source_format TEXT,
    issue_categories TEXT,
    score_before INTEGER,
    score_after INTEGER,
    escalation_details TEXT,  -- JSON: category_scores_before/after, cost, duration
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Aggregated statistics per publisher/era/format
CREATE TABLE IF NOT EXISTS source_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publisher TEXT,
    decade TEXT,
    format TEXT,
    books_processed INTEGER DEFAULT 0,
    avg_initial_score REAL,
    avg_final_score REAL,
    avg_iterations_needed REAL,
    best_extraction_path TEXT,
    common_issues TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User-submitted book configurations and overrides
CREATE TABLE IF NOT EXISTS book_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER REFERENCES books(id),
    isbn TEXT,
    title_hash TEXT,  -- normalized hash of title+author for fuzzy matching
    chapter_structure TEXT,  -- JSON array of chapter definitions
    extraction_path TEXT,  -- recommended extraction path override
    extraction_notes TEXT,  -- free-text notes ("use OCR mode", "skip first 3 pages")
    calibre_options TEXT,  -- override calibre_options for this specific book
    skip_front_pages INTEGER,  -- number of front-matter pages to skip
    skip_back_pages INTEGER,  -- number of back-matter pages to skip
    source TEXT DEFAULT 'local',  -- 'local' = user-entered, 'community' = shared
    submitted_by TEXT,
    review_status TEXT DEFAULT 'approved',  -- local entries auto-approved
    upvotes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

-- Cached extraction results — stores extracted text to avoid re-extraction.
-- Key table for commercial amortization: first extraction costs $6-12 (Vision),
-- every subsequent request serves from cache at zero cost.
CREATE TABLE IF NOT EXISTS extraction_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER REFERENCES books(id),
    source_file_hash TEXT NOT NULL,
    extraction_tier INTEGER NOT NULL,     -- 1=standard, 2=re-ocr, 3=vision
    extraction_method TEXT NOT NULL,       -- pdfminer_html, pypdf, column_aware, tesseract5, claude_vision
    quality_score INTEGER,
    page_count INTEGER,
    word_count INTEGER,
    chapter_count INTEGER,
    extracted_html TEXT,
    extracted_text TEXT,
    chapter_hints_json TEXT,
    text_hash TEXT,
    extraction_cost_usd REAL DEFAULT 0,
    extraction_duration_seconds REAL,
    pipeline_version TEXT,
    cache_version INTEGER DEFAULT 1,
    times_served INTEGER DEFAULT 0,
    last_served_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_file_hash, extraction_tier)
);
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_fix_patterns_lookup
    ON fix_patterns(format, source_type, success_rate DESC);
CREATE INDEX IF NOT EXISTS idx_issues_category
    ON issues(category, severity, fix_succeeded);
CREATE INDEX IF NOT EXISTS idx_conversions_book
    ON conversions(book_id, iteration);
CREATE INDEX IF NOT EXISTS idx_books_filename
    ON books(filename);
CREATE INDEX IF NOT EXISTS idx_books_title_hash
    ON books(title_hash);
CREATE INDEX IF NOT EXISTS idx_book_overrides_isbn
    ON book_overrides(isbn);
CREATE INDEX IF NOT EXISTS idx_book_overrides_title_hash
    ON book_overrides(title_hash);
CREATE INDEX IF NOT EXISTS idx_book_overrides_book_id
    ON book_overrides(book_id);
CREATE INDEX IF NOT EXISTS idx_books_isbn
    ON books(isbn);
CREATE INDEX IF NOT EXISTS idx_books_source_hash
    ON books(source_file_hash);
CREATE INDEX IF NOT EXISTS idx_book_metadata_title_hash
    ON book_metadata(title_hash);
CREATE INDEX IF NOT EXISTS idx_book_metadata_isbn
    ON book_metadata(isbn);
CREATE INDEX IF NOT EXISTS idx_extraction_cache_hash
    ON extraction_cache(source_file_hash);
CREATE INDEX IF NOT EXISTS idx_extraction_cache_book
    ON extraction_cache(book_id);
"""

# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------


def _resolve_db_path(db_path=None):
    """Resolve database path, defaulting to project-relative location."""
    if db_path is None:
        return str(_DEFAULT_DB_PATH)
    return str(db_path)


def get_db(db_path=None):
    """Get a database connection. Creates DB and tables if they don't exist."""
    path = _resolve_db_path(db_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    _migrate(conn)
    conn.executescript(_INDEXES_SQL)
    return conn


def _migrate(conn):
    """Apply schema migrations for columns added after initial release."""
    # Check if books.title_hash exists (Phase 3B migration)
    book_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(books)").fetchall()
    }
    if 'title_hash' not in book_columns:
        conn.execute("ALTER TABLE books ADD COLUMN title_hash TEXT")
        conn.commit()

    # Phase 3C migrations — new columns on books and conversions
    _new_columns = [
        ("books", "isbn", "TEXT"),
        ("books", "source_file_path", "TEXT"),
        ("books", "source_file_hash", "TEXT"),
        ("books", "cover_image_path", "TEXT"),
        ("books", "language", "TEXT DEFAULT 'en'"),
        ("books", "word_count", "INTEGER"),
        ("books", "chapter_count", "INTEGER"),
        ("conversions", "output_file_path", "TEXT"),
        ("conversions", "output_file_size", "INTEGER"),
        ("conversions", "conversion_flags", "TEXT"),
        ("conversions", "category_scores", "TEXT"),
        ("conversions", "font_inventory", "TEXT"),
        ("books", "pdf_producer", "TEXT"),
        ("books", "pdf_creator", "TEXT"),
        ("books", "detected_scripts", "TEXT"),
        # FU-2: Escalation comparison details
        ("extraction_cache", "escalation_details", "TEXT"),
        # FU-3: Duration breakdown
        ("conversions", "duration_breakdown", "TEXT"),
        # DE-1: Encryption and permissions
        ("books", "is_encrypted", "BOOLEAN"),
        ("books", "pdf_permissions", "TEXT"),
        # DE-2: Bookmark depth and count
        ("books", "bookmark_count", "INTEGER"),
        ("books", "bookmark_max_depth", "INTEGER"),
        # DE-4: Image density
        ("books", "image_density", "TEXT"),
        # DE-5: Encoding distribution
        ("conversions", "encoding_distribution", "TEXT"),
        # DE-6: Extraction completeness
        ("conversions", "extraction_completeness", "TEXT"),
        # SCRUM-160: Quality variance
        ("conversions", "quality_variance", "REAL"),
        # SCRUM-161: Path switch escalation details
        ("path_switches", "escalation_details", "TEXT"),
        # SCRUM-16: Quality gate status
        ("conversions", "quality_status", "TEXT"),
        # SCRUM-125: Multi-extractor comparison results
        ("conversions", "extractor_comparison", "TEXT"),
        # EB-79: Image count in cached HTML
        ("extraction_cache", "image_count", "INTEGER"),
    ]
    for table, col, col_type in _new_columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # EB-73: Per-book corrections column on book_overrides
    try:
        conn.execute("SELECT corrections_json FROM book_overrides LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE book_overrides ADD COLUMN corrections_json TEXT")
        conn.commit()

    # FU-4: Unique index for source_profiles upsert (COALESCE handles NULLs)
    # First deduplicate any existing rows, then create the unique index
    try:
        conn.execute("""
            DELETE FROM source_profiles WHERE id NOT IN (
                SELECT MIN(id) FROM source_profiles
                GROUP BY COALESCE(publisher, ''), COALESCE(decade, ''), COALESCE(format, '')
            )
        """)
        # Drop old non-COALESCE index if it exists
        conn.execute("DROP INDEX IF EXISTS idx_source_profiles_unique")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_source_profiles_key "
            "ON source_profiles(COALESCE(publisher, ''), COALESCE(decade, ''), COALESCE(format, ''))")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def init_db(db_path=None):
    """Explicitly initialize the database (create tables, indexes)."""
    conn = get_db(db_path)
    # Verify tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()
    return tables


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------


def add_book(filename, title=None, author=None, publisher=None, year=None,
             format='pdf', file_size_bytes=None, page_count=None,
             source_type='unknown', isbn=None, source_file_path=None,
             source_file_hash=None, cover_image_path=None, language='en',
             pdf_producer=None, pdf_creator=None, detected_scripts=None,
             word_count=None, chapter_count=None, db_path=None):
    """Add a book record. Returns the book ID."""
    # Auto-compute file hash if path given but hash not provided
    if not source_file_hash and source_file_path and os.path.isfile(source_file_path):
        try:
            source_file_hash = compute_file_hash(source_file_path)
        except OSError:
            pass
    # DE-3: Auto-populate file size if not provided
    if file_size_bytes is None and source_file_path and os.path.isfile(source_file_path):
        try:
            file_size_bytes = os.path.getsize(source_file_path)
        except Exception:
            pass
    # DE-3: Auto-populate page count for PDFs if not provided
    if page_count is None and source_file_path and str(source_file_path).lower().endswith('.pdf'):
        try:
            from pypdf import PdfReader as _PageCountReader
            _pcr = _PageCountReader(source_file_path)
            page_count = len(_pcr.pages)
        except Exception:
            pass
    if isinstance(detected_scripts, dict):
        detected_scripts = json.dumps(detected_scripts)
    title_hash = _normalize_title_hash(title, author)
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO books
               (filename, title, author, publisher, year, format,
                file_size_bytes, page_count, source_type, title_hash,
                isbn, source_file_path, source_file_hash,
                cover_image_path, language, pdf_producer, pdf_creator,
                detected_scripts, word_count, chapter_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (filename, title, author, publisher, year, format,
             file_size_bytes, page_count, source_type, title_hash,
             isbn, source_file_path, source_file_hash,
             cover_image_path, language, pdf_producer, pdf_creator,
             detected_scripts, word_count, chapter_count)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_book_by_filename(filename, db_path=None):
    """Look up a book by filename. Returns dict or None if not found."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM books WHERE filename = ?", (filename,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _backfill_book_nulls(book_id, existing, kwargs, db_path=None):
    """DE-3: Backfill NULL fields on existing book records."""
    updates = []
    params = []
    src_path = kwargs.get('source_file_path')
    for col, val in [
        ('file_size_bytes', kwargs.get('file_size_bytes')),
        ('page_count', kwargs.get('page_count')),
        ('pdf_producer', kwargs.get('pdf_producer')),
        ('pdf_creator', kwargs.get('pdf_creator')),
        ('source_file_path', src_path),
        ('source_file_hash', kwargs.get('source_file_hash')),
    ]:
        if val and not existing.get(col):
            updates.append(f"{col} = ?")
            params.append(val)
    # Auto-compute missing file_size_bytes
    if not existing.get('file_size_bytes') and 'file_size_bytes' not in [u.split(' =')[0] for u in updates]:
        if src_path and os.path.isfile(src_path):
            try:
                updates.append("file_size_bytes = ?")
                params.append(os.path.getsize(src_path))
            except Exception:
                pass
    if updates:
        params.append(book_id)
        conn = get_db(db_path)
        try:
            conn.execute(
                f"UPDATE books SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        finally:
            conn.close()


def get_or_create_book(filename, db_path=None, **kwargs):
    """Get existing book ID or create new. Returns book ID.

    Lookup order: exact filename match, then title_hash fallback.
    """
    existing = get_book_by_filename(filename, db_path)
    if existing:
        _backfill_book_nulls(existing["id"], existing, kwargs, db_path)
        return existing["id"]

    # Try source_file_path match before creating a duplicate
    src_path = kwargs.get('source_file_path')
    if not existing and src_path:
        conn = get_db(db_path)
        try:
            basename = os.path.basename(src_path.replace('\\\\', '\\').replace('\\\\', '\\'))
            if not basename:
                basename = src_path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]
            if basename:
                row = conn.execute(
                    "SELECT id FROM books WHERE source_file_path LIKE ? ORDER BY id DESC LIMIT 1",
                    (f"%{basename}%",)
                ).fetchone()
                if row:
                    return row["id"]
        finally:
            conn.close()

    # Try title_hash fallback before creating
    title = kwargs.get('title')
    author = kwargs.get('author')
    if title:
        title_hash = _normalize_title_hash(title, author)
        if title_hash:
            conn = get_db(db_path)
            try:
                cursor = conn.execute(
                    "SELECT id FROM books WHERE title_hash = ? LIMIT 1",
                    (title_hash,)
                )
                row = cursor.fetchone()
                if row:
                    return row["id"]
            finally:
                conn.close()

    return add_book(filename, db_path=db_path, **kwargs)


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def add_conversion(book_id, iteration=1, extraction_path='legacy',
                   vqa_score=None, vqa_report_path=None,
                   text_quality_score=None, fixes_applied=0,
                   fixes_failed=0, api_input_tokens=0,
                   api_output_tokens=0, cost_usd=0,
                   duration_seconds=None, output_file_path=None,
                   output_file_size=None, conversion_flags=None,
                   category_scores=None, duration_breakdown=None,
                   quality_variance=None, quality_status=None,
                   extractor_comparison=None, db_path=None):
    """Record a conversion attempt. Returns conversion ID."""
    if isinstance(conversion_flags, dict):
        conversion_flags = json.dumps(conversion_flags)
    if isinstance(category_scores, dict):
        category_scores = json.dumps(category_scores)
    if isinstance(duration_breakdown, dict):
        duration_breakdown = json.dumps(duration_breakdown)
    if isinstance(extractor_comparison, dict):
        extractor_comparison = json.dumps(extractor_comparison)
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO conversions
               (book_id, iteration, extraction_path, vqa_score,
                vqa_report_path, text_quality_score, fixes_applied,
                fixes_failed, api_input_tokens, api_output_tokens,
                cost_usd, duration_seconds, output_file_path,
                output_file_size, conversion_flags, category_scores,
                duration_breakdown, quality_variance, quality_status,
                extractor_comparison)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (book_id, iteration, extraction_path, vqa_score,
             vqa_report_path, text_quality_score, fixes_applied,
             fixes_failed, api_input_tokens, api_output_tokens,
             cost_usd, duration_seconds, output_file_path,
             output_file_size, conversion_flags, category_scores,
             duration_breakdown, quality_variance, quality_status,
             extractor_comparison)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_conversions_for_book(book_id, db_path=None):
    """Get all conversion attempts for a book, ordered by iteration."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """SELECT * FROM conversions
               WHERE book_id = ? ORDER BY iteration""",
            (book_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


def add_issue(conversion_id, book_id, category, severity,
              description=None, page_number=None, db_path=None):
    """Record an issue. Returns issue ID."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO issues
               (conversion_id, book_id, category, severity,
                description, page_number)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (conversion_id, book_id, category, severity,
             description, page_number)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def add_issues_from_vqa_report(conversion_id, book_id, vqa_report,
                               db_path=None):
    """Bulk-add issues from a parsed VQA report dict. Returns count added."""
    conn = get_db(db_path)
    count = 0
    try:
        pages = vqa_report.get("pages", [])
        for page in pages:
            page_number = page.get("page_number")
            for issue in page.get("issues", []):
                conn.execute(
                    """INSERT INTO issues
                       (conversion_id, book_id, category, severity,
                        description, page_number)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (conversion_id, book_id,
                     issue.get("category", "unknown"),
                     issue.get("severity", "unknown"),
                     issue.get("description"),
                     page_number)
                )
                count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def update_issue_fix(issue_id, fix_attempted=True, fix_succeeded=False,
                     fix_strategy=None, fix_details=None, db_path=None):
    """Update an issue with fix results."""
    conn = get_db(db_path)
    try:
        conn.execute(
            """UPDATE issues
               SET fix_attempted = ?, fix_succeeded = ?,
                   fix_strategy = ?, fix_details = ?
               WHERE id = ?""",
            (fix_attempted, fix_succeeded, fix_strategy, fix_details,
             issue_id)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fix Patterns
# ---------------------------------------------------------------------------


def add_fix_pattern(fix_type, fix_action, trigger_category=None,
                    trigger_pattern=None, fix_replacement=None,
                    publisher=None, format=None, source_type=None,
                    first_seen_book_id=None, iteration_discovered=None,
                    db_path=None):
    """Record a new fix pattern. Returns pattern ID."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO fix_patterns
               (fix_type, trigger_category, trigger_pattern, fix_action,
                fix_replacement, publisher, format, source_type,
                first_seen_book_id, iteration_discovered)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fix_type, trigger_category, trigger_pattern, fix_action,
             fix_replacement, publisher, format, source_type,
             first_seen_book_id, iteration_discovered)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_applicable_fixes(format=None, source_type=None,
                         min_success_rate=0.7, db_path=None):
    """Get fix patterns applicable to a given book profile, ordered by success rate."""
    conn = get_db(db_path)
    try:
        conditions = ["success_rate >= ?"]
        params = [min_success_rate]

        if format is not None:
            conditions.append("(format = ? OR format IS NULL)")
            params.append(format)
        if source_type is not None:
            conditions.append("(source_type = ? OR source_type IS NULL)")
            params.append(source_type)

        where = " AND ".join(conditions)
        cursor = conn.execute(
            f"""SELECT * FROM fix_patterns
                WHERE {where}
                ORDER BY success_rate DESC, times_applied DESC""",
            params
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def record_fix_outcome(pattern_id, succeeded, score_improvement=0,
                       db_path=None):
    """Record whether a fix pattern succeeded, updating its stats."""
    conn = get_db(db_path)
    try:
        conn.execute(
            """UPDATE fix_patterns SET
                   times_applied = times_applied + 1,
                   times_succeeded = times_succeeded + CASE WHEN ? THEN 1 ELSE 0 END,
                   success_rate = CAST(times_succeeded + CASE WHEN ? THEN 1 ELSE 0 END AS REAL)
                                  / (times_applied + 1),
                   avg_score_improvement = (avg_score_improvement * times_applied + ?)
                                           / (times_applied + 1),
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (succeeded, succeeded, score_improvement, pattern_id)
        )
        conn.commit()
    finally:
        conn.close()


def record_fix_results(book_id, conversion_id, fixes_by_category, db_path=None):
    """Record fix engine results in the pattern database.

    For each fix category with > 0 fixes applied, update or create
    a fix_pattern record and increment times_applied/times_succeeded.
    """
    conn = get_db(db_path)
    try:
        for category, count in fixes_by_category.items():
            if count <= 0:
                continue
            existing = conn.execute(
                "SELECT id, times_applied, times_succeeded FROM fix_patterns WHERE fix_type = ?",
                (category,)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE fix_patterns
                       SET times_applied = times_applied + 1,
                           times_succeeded = times_succeeded + 1,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (existing["id"],)
                )
            else:
                conn.execute(
                    """INSERT INTO fix_patterns
                       (fix_type, fix_action, trigger_category, times_applied,
                        times_succeeded, first_seen_book_id, iteration_discovered,
                        promoted_to_iteration)
                       VALUES (?, ?, ?, 1, 1, ?, 1, 1)""",
                    (category, f"rule_based_{category}", category, book_id)
                )
        conn.commit()
    finally:
        conn.close()


def promote_fixes(min_successes=3, min_success_rate=0.7, db_path=None):
    """Promote high-success fixes to iteration 1. Returns count promoted."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """UPDATE fix_patterns
               SET promoted_to_iteration = 1, updated_at = CURRENT_TIMESTAMP
               WHERE times_succeeded >= ?
                 AND success_rate >= ?
                 AND promoted_to_iteration IS NULL""",
            (min_successes, min_success_rate)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Path Switches
# ---------------------------------------------------------------------------


def record_path_switch(book_id, from_path, to_path, source_format=None,
                       issue_categories=None, score_before=None,
                       score_after=None, escalation_details=None,
                       db_path=None):
    """Record an extraction path switch and its outcome."""
    if isinstance(escalation_details, dict):
        escalation_details = json.dumps(escalation_details)
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO path_switches
               (book_id, from_path, to_path, source_format,
                issue_categories, score_before, score_after,
                escalation_details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (book_id, from_path, to_path, source_format,
             issue_categories, score_before, score_after,
             escalation_details)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def record_path_switch_by_filename(filename, from_path, to_path,
                                   source_format=None, score_before=None,
                                   score_after=None, escalation_details=None,
                                   db_path=None):
    """Record a path switch using filename to resolve book_id.

    Returns the path_switch ID, or None if book not found.
    """
    book = get_book_by_filename(filename, db_path=db_path)
    if not book:
        # Try partial match
        conn = get_db(db_path)
        try:
            cursor = conn.execute(
                "SELECT id FROM books WHERE filename LIKE ? ORDER BY id DESC LIMIT 1",
                (f"%{filename}%",)
            )
            row = cursor.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        book_id = row["id"]
    else:
        book_id = book["id"]

    return record_path_switch(
        book_id=book_id,
        from_path=from_path,
        to_path=to_path,
        source_format=source_format,
        score_before=score_before,
        score_after=score_after,
        escalation_details=escalation_details,
        db_path=db_path,
    )


# ---------------------------------------------------------------------------
# Source Profiles
# ---------------------------------------------------------------------------


def update_source_profile(publisher, decade, format, db_path=None):
    """Recalculate aggregated stats for a publisher/decade/format combo."""
    conn = get_db(db_path)
    try:
        # Get aggregated data from conversions + books
        cursor = conn.execute(
            """SELECT
                   COUNT(DISTINCT b.id) as books_processed,
                   AVG(CASE WHEN c.iteration = 1 THEN c.vqa_score END) as avg_initial_score,
                   AVG(c.vqa_score) as avg_final_score,
                   AVG(max_iter.max_iteration) as avg_iterations_needed
               FROM books b
               JOIN conversions c ON c.book_id = b.id
               LEFT JOIN (
                   SELECT book_id, MAX(iteration) as max_iteration
                   FROM conversions GROUP BY book_id
               ) max_iter ON max_iter.book_id = b.id
               WHERE (b.publisher = ? OR ? IS NULL)
                 AND (b.format = ? OR ? IS NULL)""",
            (publisher, publisher, format, format)
        )
        row = cursor.fetchone()
        if not row or row["books_processed"] == 0:
            return

        # Find best extraction path
        path_cursor = conn.execute(
            """SELECT c.extraction_path, AVG(c.vqa_score) as avg_score
               FROM conversions c
               JOIN books b ON b.id = c.book_id
               WHERE (b.publisher = ? OR ? IS NULL)
                 AND (b.format = ? OR ? IS NULL)
               GROUP BY c.extraction_path
               ORDER BY avg_score DESC LIMIT 1""",
            (publisher, publisher, format, format)
        )
        path_row = path_cursor.fetchone()
        best_path = path_row["extraction_path"] if path_row else None

        # Find common issues
        issue_cursor = conn.execute(
            """SELECT i.category, COUNT(*) as cnt
               FROM issues i
               JOIN books b ON b.id = i.book_id
               WHERE (b.publisher = ? OR ? IS NULL)
                 AND (b.format = ? OR ? IS NULL)
               GROUP BY i.category
               ORDER BY cnt DESC LIMIT 5""",
            (publisher, publisher, format, format)
        )
        common = ", ".join(
            f"{r['category']}({r['cnt']})" for r in issue_cursor.fetchall()
        )

        # Upsert the profile (FU-4: COALESCE keys to handle NULLs)
        conn.execute(
            """INSERT INTO source_profiles
                   (publisher, decade, format, books_processed,
                    avg_initial_score, avg_final_score,
                    avg_iterations_needed, best_extraction_path,
                    common_issues, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(COALESCE(publisher, ''), COALESCE(decade, ''), COALESCE(format, '')) DO UPDATE SET
                   books_processed = excluded.books_processed,
                   avg_initial_score = excluded.avg_initial_score,
                   avg_final_score = excluded.avg_final_score,
                   avg_iterations_needed = excluded.avg_iterations_needed,
                   best_extraction_path = excluded.best_extraction_path,
                   common_issues = excluded.common_issues,
                   updated_at = CURRENT_TIMESTAMP""",
            (publisher or '', decade or '', format or '', row["books_processed"],
             row["avg_initial_score"], row["avg_final_score"],
             row["avg_iterations_needed"], best_path, common)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cache Lookup
# ---------------------------------------------------------------------------


def get_cached_result(filename=None, isbn=None, title=None, author=None,
                      source_file_path=None, min_score=80, db_path=None):
    """Check if a book has already been successfully converted.

    Lookup order:
    1. Exact filename match (books.filename)
    1b. Source file path match (books.source_file_path)
    2. ISBN match (if provided)
    3. Title+author fuzzy match (if provided)

    Returns the best conversion record as a dict, or None if no cache hit.
    The dict includes: book_id, filename, vqa_score, extraction_path,
    vqa_report_path, cost_usd, created_at.
    """
    conn = get_db(db_path)
    try:
        book_id = None

        # 1. Exact filename match
        if filename:
            row = conn.execute(
                "SELECT id FROM books WHERE filename = ?", (filename,)
            ).fetchone()
            if not row and not filename.endswith(('.kfx', '.azw3')):
                # Try with common output extensions
                for ext in ('.kfx', '.azw3'):
                    stem = Path(filename).stem
                    row = conn.execute(
                        "SELECT id FROM books WHERE filename = ?",
                        (stem + ext,)
                    ).fetchone()
                    if row:
                        break
            if row:
                book_id = row["id"]

        # 1b. Source file path match (input filename stored during write-back)
        if not book_id and (source_file_path or filename):
            search_val = source_file_path or filename
            # Extract just the filename (no directory path) to avoid backslash escaping mismatches
            basename = os.path.basename(search_val.replace('\\\\', '\\').replace('\\\\', '\\'))
            if not basename:
                basename = search_val.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]
            if basename:
                row = conn.execute(
                    "SELECT id FROM books WHERE source_file_path LIKE ? ORDER BY id DESC LIMIT 1",
                    (f"%{basename}%",)
                ).fetchone()
                if row:
                    book_id = row["id"]

        # 2. ISBN match
        if not book_id and isbn:
            row = conn.execute(
                """SELECT bo.book_id FROM book_overrides bo
                   WHERE bo.isbn = ? AND bo.book_id IS NOT NULL
                   LIMIT 1""",
                (isbn,)
            ).fetchone()
            if row:
                book_id = row["book_id"]

        # 3. Title+author fuzzy match
        if not book_id and title:
            title_hash = _normalize_title_hash(title, author)
            if title_hash:
                row = conn.execute(
                    "SELECT id FROM books WHERE title_hash = ? LIMIT 1",
                    (title_hash,)
                ).fetchone()
                if row:
                    book_id = row["id"]

        if not book_id:
            return None

        # Find the best conversion for this book
        # When min_score <= 0, return ANY conversion (even with NULL vqa_score).
        # When min_score > 0, require a non-NULL score meeting the threshold.
        cursor = conn.execute(
            """SELECT c.id as conversion_id, b.id as book_id, b.filename,
                      c.vqa_score, c.extraction_path, c.vqa_report_path,
                      c.output_file_path, c.cost_usd, c.created_at
               FROM conversions c
               JOIN books b ON b.id = c.book_id
               WHERE c.book_id = ?
                 AND (? <= 0 OR c.vqa_score >= ?)
               ORDER BY c.vqa_score DESC, c.created_at DESC
               LIMIT 1""",
            (book_id, min_score, min_score)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_cached_output_path(filename=None, isbn=None, title=None, author=None,
                           source_file_path=None, min_score=80, db_path=None):
    """Convenience wrapper -- returns just the output file path if a cached
    conversion exists, or None.

    Checks that the output file still exists on disk before returning.
    If the file has been deleted, returns None (cache miss).
    """
    result = get_cached_result(
        filename=filename, isbn=isbn, title=title, author=author,
        source_file_path=source_file_path, min_score=min_score, db_path=db_path
    )
    if not result:
        return None

    # Derive the output path from the VQA report path or filename
    report_path = result.get("vqa_report_path")
    if report_path:
        # The output file is alongside the report, same stem minus _visual_qa_report*
        report = Path(report_path)
        stem = report.stem
        for suffix in ('_visual_qa_report', '_visual_qa_report_LEGACY',
                       '_visual_qa_report_HTML'):
            if stem.endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        # Try common output extensions
        for ext in ('.kfx', '.azw3', '.epub'):
            candidate = report.parent / (stem + ext)
            if candidate.exists():
                return str(candidate)

    # Fallback: check the default kindle output directory
    kindle_dir = _PROJECT_ROOT / "output" / "kindle"
    book_filename = result.get("filename", "")
    candidate = kindle_dir / book_filename
    if candidate.exists():
        return str(candidate)

    return None


# ---------------------------------------------------------------------------
# Extraction Cache (content-addressable, stores extracted text)
# ---------------------------------------------------------------------------


def get_cached_extraction(source_file_hash=None, source_file_path=None,
                          min_score=60, min_tier=1, cache_version=None,
                          pipeline_version=None, db_path=None):
    """Look up cached extraction by source file hash.

    Returns dict with cache entry fields, or None on miss.
    On hit, increments times_served and updates last_served_at.
    """
    if not source_file_hash and source_file_path:
        source_file_hash = compute_file_hash(source_file_path)
    if not source_file_hash:
        return None

    conn = get_db(db_path)
    try:
        query = """
            SELECT * FROM extraction_cache
            WHERE source_file_hash = ?
              AND (quality_score IS NULL OR quality_score >= ?)
              AND extraction_tier >= ?
        """
        params = [source_file_hash, min_score, min_tier]

        if cache_version is not None:
            query += " AND cache_version >= ?"
            params.append(cache_version)

        if pipeline_version is not None:
            query += " AND pipeline_version = ?"
            params.append(pipeline_version)

        query += " ORDER BY extraction_tier DESC, quality_score DESC LIMIT 1"

        row = conn.execute(query, params).fetchone()
        if not row:
            return None

        result = dict(row)

        conn.execute("""
            UPDATE extraction_cache
            SET times_served = times_served + 1, last_served_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (result['id'],))
        conn.commit()

        return result
    finally:
        conn.close()


def store_extraction(book_id, source_file_hash, tier, method,
                     extracted_html=None, extracted_text=None,
                     chapter_hints_json=None, quality_score=None,
                     page_count=None, word_count=None, chapter_count=None,
                     cost_usd=0, duration_seconds=None, pipeline_version=None,
                     escalation_details=None, image_count=None, db_path=None):
    """Store an extraction result in the cache.

    Only replaces an existing entry if the new quality_score is higher.
    Returns cache entry ID, or None on failure.
    """
    content = extracted_html or extracted_text or ""
    text_hash = compute_text_hash(content) if content else None

    conn = get_db(db_path)
    try:
        existing = conn.execute("""
            SELECT id, quality_score FROM extraction_cache
            WHERE source_file_hash = ? AND extraction_tier = ?
        """, (source_file_hash, tier)).fetchone()

        if existing and existing['quality_score'] and quality_score:
            if existing['quality_score'] >= quality_score:
                return existing['id']

        if existing:
            conn.execute("""
                UPDATE extraction_cache SET
                    book_id = ?, extraction_method = ?, quality_score = ?,
                    page_count = ?, word_count = ?, chapter_count = ?,
                    extracted_html = ?, extracted_text = ?, chapter_hints_json = ?,
                    text_hash = ?, extraction_cost_usd = ?,
                    extraction_duration_seconds = ?, pipeline_version = ?,
                    escalation_details = ?, image_count = ?,
                    cache_version = 1, created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (book_id, method, quality_score, page_count, word_count,
                  chapter_count, extracted_html, extracted_text,
                  chapter_hints_json, text_hash, cost_usd, duration_seconds,
                  pipeline_version, escalation_details, image_count,
                  existing['id']))
            conn.commit()
            return existing['id']
        else:
            cursor = conn.execute("""
                INSERT INTO extraction_cache
                    (book_id, source_file_hash, extraction_tier, extraction_method,
                     quality_score, page_count, word_count, chapter_count,
                     extracted_html, extracted_text, chapter_hints_json,
                     text_hash, extraction_cost_usd, extraction_duration_seconds,
                     pipeline_version, escalation_details, image_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (book_id, source_file_hash, tier, method, quality_score,
                  page_count, word_count, chapter_count, extracted_html,
                  extracted_text, chapter_hints_json, text_hash, cost_usd,
                  duration_seconds, pipeline_version, escalation_details,
                  image_count))
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def invalidate_extraction_cache(source_file_hash=None, book_id=None,
                                older_than_version=None, db_path=None):
    """Invalidate cache entries. Returns number of entries deleted."""
    conn = get_db(db_path)
    try:
        if source_file_hash:
            cursor = conn.execute(
                "DELETE FROM extraction_cache WHERE source_file_hash = ?",
                (source_file_hash,))
        elif book_id:
            cursor = conn.execute(
                "DELETE FROM extraction_cache WHERE book_id = ?",
                (book_id,))
        elif older_than_version is not None:
            cursor = conn.execute(
                "DELETE FROM extraction_cache WHERE cache_version < ?",
                (older_than_version,))
        else:
            return 0
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def backfill_cache_image_counts(db_path=None):
    """Backfill image_count for existing extraction cache entries.

    Scans entries where image_count IS NULL and counts <figure> tags
    in their extracted_html. Returns number of entries updated.
    """
    conn = get_db(db_path)
    try:
        rows = conn.execute(
            "SELECT id, extracted_html FROM extraction_cache "
            "WHERE image_count IS NULL AND extracted_html IS NOT NULL"
        ).fetchall()

        updated = 0
        for row in rows:
            count = len(re.findall(r'<figure>', row['extracted_html'] or ''))
            conn.execute(
                "UPDATE extraction_cache SET image_count = ? WHERE id = ?",
                (count, row['id']))
            updated += 1

        conn.commit()
        return updated
    finally:
        conn.close()


def get_cache_stats(db_path=None):
    """Return extraction cache statistics for monitoring."""
    conn = get_db(db_path)
    try:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   COALESCE(SUM(times_served), 0) as total_served,
                   COALESCE(SUM(extraction_cost_usd), 0) as total_cost,
                   AVG(quality_score) as avg_quality,
                   COALESCE(SUM(CASE WHEN times_served > 0
                       THEN extraction_cost_usd * times_served ELSE 0 END), 0) as cost_saved
            FROM extraction_cache
        """).fetchone()

        stats = {
            'total_entries': row['total'] or 0,
            'total_times_served': row['total_served'] or 0,
            'total_extraction_cost_usd': round(row['total_cost'] or 0, 4),
            'avg_quality_score': round(row['avg_quality'] or 0, 1),
            'total_cost_saved_usd': round(row['cost_saved'] or 0, 4),
        }

        tiers = conn.execute("""
            SELECT extraction_tier, COUNT(*) as count,
                   COALESCE(SUM(times_served), 0) as served,
                   AVG(quality_score) as avg_score
            FROM extraction_cache GROUP BY extraction_tier
        """).fetchall()
        stats['by_tier'] = {r['extraction_tier']: dict(r) for r in tiers}

        methods = conn.execute("""
            SELECT extraction_method, COUNT(*) as count
            FROM extraction_cache GROUP BY extraction_method
        """).fetchall()
        stats['by_method'] = {r['extraction_method']: r['count'] for r in methods}

        return stats
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Smart Strategy Recommendation
# ---------------------------------------------------------------------------


def get_recommended_strategy(filename=None, source_file_path=None, isbn=None,
                             source_type=None, publisher=None, format='pdf',
                             db_path=None):
    """Query historical data to recommend the best extraction strategy.

    Checks three levels (most specific -> least specific):
      1. This exact book (by filename/source_file_path/ISBN)
      2. Books from the same publisher + format
      3. All books with the same source_type + format

    Returns dict with strategy_order, flags, confidence, reason, source.
    """
    conn = get_db(db_path)
    try:
        result = {
            "strategy_order": [],
            "flags": {"UseClaudeChapters": False, "ForceColumns": False},
            "confidence": 0.0,
            "reason": "no historical data available",
            "source": "default",
            "best_prior_score": None,
            "prior_conversions": 0,
        }

        # --- Level 1: This exact book ---
        book_id = None

        # Exact filename match
        if filename:
            row = conn.execute(
                "SELECT id FROM books WHERE filename = ?", (filename,)
            ).fetchone()
            if row:
                book_id = row["id"]

        # Source file path match (basename LIKE search)
        if not book_id and (source_file_path or filename):
            search_val = source_file_path or filename
            basename = os.path.basename(
                search_val.replace('\\\\', '\\').replace('\\\\', '\\')
            )
            if not basename:
                basename = search_val.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]
            if basename:
                row = conn.execute(
                    "SELECT id FROM books WHERE source_file_path LIKE ? "
                    "ORDER BY id DESC LIMIT 1",
                    (f"%{basename}%",)
                ).fetchone()
                if row:
                    book_id = row["id"]

        # ISBN match
        if not book_id and isbn:
            row = conn.execute(
                """SELECT bo.book_id FROM book_overrides bo
                   WHERE bo.isbn = ? AND bo.book_id IS NOT NULL
                   LIMIT 1""",
                (isbn,)
            ).fetchone()
            if row:
                book_id = row["book_id"]

        if book_id:
            # Get all conversions for this book with VQA scores
            convs = conn.execute(
                """SELECT extraction_path, vqa_score, category_scores,
                          conversion_flags
                   FROM conversions
                   WHERE book_id = ? AND vqa_score IS NOT NULL
                   ORDER BY vqa_score DESC""",
                (book_id,)
            ).fetchall()

            if convs:
                result["prior_conversions"] = len(convs)
                result["best_prior_score"] = convs[0]["vqa_score"]

                # Rank extraction paths by average score
                path_scores = {}
                for c in convs:
                    path = c["extraction_path"]
                    if path not in path_scores:
                        path_scores[path] = []
                    path_scores[path].append(c["vqa_score"])

                ranked_paths = sorted(
                    path_scores.items(),
                    key=lambda x: sum(x[1]) / len(x[1]),
                    reverse=True,
                )
                result["strategy_order"] = [p[0] for p in ranked_paths]

                # Check chapter/TOC status
                book = conn.execute(
                    "SELECT chapter_count FROM books WHERE id = ?",
                    (book_id,)
                ).fetchone()
                if book and (book["chapter_count"] is None
                             or book["chapter_count"] == 0):
                    result["flags"]["UseClaudeChapters"] = True

                # Check toc_navigation from best conversion's category_scores
                best_cats = convs[0]["category_scores"]
                if best_cats:
                    try:
                        cats = (json.loads(best_cats)
                                if isinstance(best_cats, str) else best_cats)
                        toc_score = cats.get("toc_navigation", 100)
                        if toc_score < 60:
                            result["flags"]["UseClaudeChapters"] = True
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Check if column-aware was the winner
                if ranked_paths and ranked_paths[0][0] == "column_aware":
                    result["flags"]["ForceColumns"] = True

                best_path = ranked_paths[0][0]
                best_avg = sum(ranked_paths[0][1]) / len(ranked_paths[0][1])
                reason_parts = [f"{best_path} scored avg {best_avg:.0f}"]
                if len(ranked_paths) > 1:
                    second_path = ranked_paths[1][0]
                    second_avg = (sum(ranked_paths[1][1])
                                  / len(ranked_paths[1][1]))
                    reason_parts.append(
                        f"vs {second_path} avg {second_avg:.0f}")
                if result["flags"]["UseClaudeChapters"]:
                    reason_parts.append(
                        "no chapters detected in prior runs")

                result["reason"] = "; ".join(reason_parts)
                result["confidence"] = min(0.95, 0.5 + len(convs) * 0.15)
                result["source"] = "book_history"
                return result

        # --- Level 2: Publisher + format profile ---
        if publisher:
            profile = conn.execute(
                """SELECT best_extraction_path, avg_final_score,
                          books_processed, common_issues
                   FROM source_profiles
                   WHERE publisher = ? AND format = ?
                   ORDER BY books_processed DESC LIMIT 1""",
                (publisher, format),
            ).fetchone()

            if profile and profile["books_processed"] >= 2:
                best = profile["best_extraction_path"]
                if best:
                    all_paths = ["html_extraction", "legacy", "column_aware"]
                    result["strategy_order"] = (
                        [best] + [p for p in all_paths if p != best]
                    )
                    result["confidence"] = min(
                        0.7, 0.3 + profile["books_processed"] * 0.1
                    )
                    result["source"] = "publisher_profile"
                    result["reason"] = (
                        f"{publisher} books avg "
                        f"{profile['avg_final_score']:.0f} with {best} "
                        f"({profile['books_processed']} books)"
                    )

                    # Check common issues for chapter problems
                    if profile["common_issues"]:
                        try:
                            if "toc_navigation" in str(
                                profile["common_issues"]
                            ):
                                result["flags"]["UseClaudeChapters"] = True
                        except Exception:
                            pass

                    return result

        # --- Level 3: Source type + format aggregate ---
        if source_type:
            path_data = conn.execute(
                """SELECT c.extraction_path,
                          AVG(c.vqa_score) as avg_score,
                          COUNT(*) as count
                   FROM conversions c
                   JOIN books b ON b.id = c.book_id
                   WHERE b.source_type = ? AND b.format = ?
                         AND c.vqa_score IS NOT NULL
                   GROUP BY c.extraction_path
                   HAVING count >= 2
                   ORDER BY avg_score DESC""",
                (source_type, format),
            ).fetchall()

            if path_data:
                result["strategy_order"] = [
                    r["extraction_path"] for r in path_data
                ]
                result["confidence"] = min(
                    0.5,
                    0.2 + sum(r["count"] for r in path_data) * 0.05,
                )
                result["source"] = "source_type_profile"
                best = path_data[0]
                result["reason"] = (
                    f"{source_type} PDFs avg {best['avg_score']:.0f} "
                    f"with {best['extraction_path']} "
                    f"({best['count']} conversions)"
                )
                return result

        # --- Level 4: No data ---
        return result
    finally:
        conn.close()


def update_source_profile_from_book(book_id, db_path=None):
    """Recalculate source profile after a new conversion for this book.

    Looks up the book's publisher and format, then recalculates the
    aggregate statistics for that publisher+format combination.
    """
    conn = get_db(db_path)
    try:
        book = conn.execute(
            "SELECT publisher, format, year FROM books WHERE id = ?",
            (book_id,)
        ).fetchone()
        if not book:
            return

        publisher = book["publisher"]
        fmt = book["format"]
        if not publisher and not fmt:
            return

        decade = (str((book["year"] // 10) * 10) + "s"
                  if book["year"] else None)
    finally:
        conn.close()

    update_source_profile(publisher, decade, fmt, db_path)


# ---------------------------------------------------------------------------
# Book Overrides
# ---------------------------------------------------------------------------


def add_book_override(book_id=None, isbn=None, title=None, author=None,
                      chapter_structure=None, extraction_path=None,
                      extraction_notes=None, calibre_options=None,
                      skip_front_pages=None, skip_back_pages=None,
                      corrections=None, db_path=None):
    """Add a manual override for a specific book.

    At least one of book_id, isbn, or title must be provided.
    chapter_structure should be a JSON-serializable list of dicts:
    [{"level": 1, "title": "Part One"}, {"level": 2, "title": "Chapter 1: ..."}]

    Returns the override ID.
    """
    if not any([book_id, isbn, title]):
        raise ValueError("At least one of book_id, isbn, or title is required")

    title_hash = _normalize_title_hash(title, author) if title else None

    # Serialize chapter_structure to JSON string
    chapters_json = None
    if chapter_structure is not None:
        if isinstance(chapter_structure, str):
            chapters_json = chapter_structure
        else:
            chapters_json = json.dumps(chapter_structure)

    # Serialize corrections to JSON string
    corrections_json = None
    if corrections is not None:
        if isinstance(corrections, str):
            corrections_json = corrections
        else:
            corrections_json = json.dumps(corrections)

    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO book_overrides
               (book_id, isbn, title_hash, chapter_structure,
                extraction_path, extraction_notes, calibre_options,
                skip_front_pages, skip_back_pages, corrections_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (book_id, isbn, title_hash, chapters_json,
             extraction_path, extraction_notes, calibre_options,
             skip_front_pages, skip_back_pages, corrections_json)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_book_override(filename=None, isbn=None, book_id=None, title=None,
                      author=None, db_path=None):
    """Look up overrides for a book.

    Lookup order: book_id > isbn > filename (via books table) > title_hash.
    Returns dict with all override fields, or None if no override exists.
    chapter_structure is returned as a parsed Python list (not raw JSON string).
    """
    conn = get_db(db_path)
    try:
        override = None

        # 1. Direct book_id lookup
        if book_id:
            override = conn.execute(
                "SELECT * FROM book_overrides WHERE book_id = ? LIMIT 1",
                (book_id,)
            ).fetchone()

        # 2. ISBN lookup
        if not override and isbn:
            override = conn.execute(
                "SELECT * FROM book_overrides WHERE isbn = ? LIMIT 1",
                (isbn,)
            ).fetchone()

        # 3. Filename -> book_id -> override
        if not override and filename:
            book = conn.execute(
                "SELECT id FROM books WHERE filename = ?", (filename,)
            ).fetchone()
            if book:
                override = conn.execute(
                    "SELECT * FROM book_overrides WHERE book_id = ? LIMIT 1",
                    (book["id"],)
                ).fetchone()

        # 4. Title hash lookup
        if not override and title:
            title_hash = _normalize_title_hash(title, author)
            if title_hash:
                override = conn.execute(
                    "SELECT * FROM book_overrides WHERE title_hash = ? LIMIT 1",
                    (title_hash,)
                ).fetchone()

        if not override:
            return None

        result = dict(override)
        # Parse chapter_structure from JSON string
        if result.get("chapter_structure"):
            try:
                result["chapter_structure"] = json.loads(
                    result["chapter_structure"]
                )
            except (json.JSONDecodeError, TypeError):
                pass  # Leave as string if not valid JSON
        # Parse corrections_json (EB-73)
        if result.get("corrections_json"):
            try:
                result["corrections"] = json.loads(result["corrections_json"])
            except (json.JSONDecodeError, TypeError):
                result["corrections"] = []
        else:
            result["corrections"] = []
        return result
    finally:
        conn.close()


def update_book_override(override_id, db_path=None, **kwargs):
    """Update fields on an existing override. Only provided kwargs are updated."""
    allowed = {
        'book_id', 'isbn', 'title_hash', 'chapter_structure',
        'extraction_path', 'extraction_notes', 'calibre_options',
        'skip_front_pages', 'skip_back_pages', 'source',
        'submitted_by', 'review_status', 'upvotes',
        'corrections_json'
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    # Serialize chapter_structure if present
    if 'chapter_structure' in updates:
        cs = updates['chapter_structure']
        if cs is not None and not isinstance(cs, str):
            updates['chapter_structure'] = json.dumps(cs)

    # Serialize corrections_json if present (EB-73)
    if 'corrections_json' in updates:
        cj = updates['corrections_json']
        if cj is not None and not isinstance(cj, str):
            updates['corrections_json'] = json.dumps(cj)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())
    values.append(override_id)

    conn = get_db(db_path)
    try:
        conn.execute(
            f"""UPDATE book_overrides
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            values
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def get_book_history(book_id, db_path=None):
    """Get full history for a book: all conversions, issues, fixes."""
    conn = get_db(db_path)
    try:
        book = conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        if not book:
            return None

        conversions = conn.execute(
            "SELECT * FROM conversions WHERE book_id = ? ORDER BY iteration",
            (book_id,)
        ).fetchall()

        issues = conn.execute(
            "SELECT * FROM issues WHERE book_id = ? ORDER BY conversion_id, id",
            (book_id,)
        ).fetchall()

        switches = conn.execute(
            "SELECT * FROM path_switches WHERE book_id = ? ORDER BY id",
            (book_id,)
        ).fetchall()

        return {
            "book": dict(book),
            "conversions": [dict(c) for c in conversions],
            "issues": [dict(i) for i in issues],
            "path_switches": [dict(s) for s in switches],
        }
    finally:
        conn.close()


def get_category_stats(db_path=None):
    """Get issue counts and fix rates grouped by category."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """SELECT
                   category,
                   COUNT(*) as total_issues,
                   SUM(CASE WHEN fix_attempted THEN 1 ELSE 0 END) as fixes_attempted,
                   SUM(CASE WHEN fix_succeeded THEN 1 ELSE 0 END) as fixes_succeeded,
                   CASE
                       WHEN SUM(CASE WHEN fix_attempted THEN 1 ELSE 0 END) > 0
                       THEN ROUND(CAST(SUM(CASE WHEN fix_succeeded THEN 1 ELSE 0 END) AS REAL)
                            / SUM(CASE WHEN fix_attempted THEN 1 ELSE 0 END) * 100, 1)
                       ELSE 0
                   END as fix_rate_pct
               FROM issues
               GROUP BY category
               ORDER BY total_issues DESC"""
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_score_trend(limit=20, db_path=None):
    """Get the most recent conversion scores to show improvement trend."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """SELECT c.id, b.filename, b.title, c.iteration,
                      c.extraction_path, c.vqa_score, c.cost_usd,
                      c.created_at
               FROM conversions c
               JOIN books b ON b.id = c.book_id
               WHERE c.vqa_score IS NOT NULL
               ORDER BY c.created_at DESC
               LIMIT ?""",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_cost_summary(db_path=None):
    """Get total API costs, average per book, etc."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """SELECT
                   COUNT(*) as total_conversions,
                   COUNT(DISTINCT book_id) as total_books,
                   SUM(cost_usd) as total_cost_usd,
                   AVG(cost_usd) as avg_cost_per_conversion,
                   SUM(api_input_tokens) as total_input_tokens,
                   SUM(api_output_tokens) as total_output_tokens,
                   AVG(vqa_score) as avg_vqa_score
               FROM conversions"""
        )
        row = cursor.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_init(args):
    tables = init_db(args.db_path)
    db_path = _resolve_db_path(args.db_path)
    print(f"Database initialized at: {db_path}")
    print(f"Tables: {', '.join(tables)}")


def _cmd_stats(args):
    conn = get_db(args.db_path)
    try:
        books = conn.execute("SELECT COUNT(*) as n FROM books").fetchone()["n"]
        conversions = conn.execute(
            "SELECT COUNT(*) as n FROM conversions"
        ).fetchone()["n"]
        issues = conn.execute(
            "SELECT COUNT(*) as n FROM issues"
        ).fetchone()["n"]
        patterns = conn.execute(
            "SELECT COUNT(*) as n FROM fix_patterns"
        ).fetchone()["n"]

        print(f"Books:       {books}")
        print(f"Conversions: {conversions}")
        print(f"Issues:      {issues}")
        print(f"Fix patterns:{patterns}")

        if books > 0:
            print()
            cat_stats = get_category_stats(args.db_path)
            if cat_stats:
                print("Issues by category:")
                for s in cat_stats:
                    fix_info = ""
                    if s["fixes_attempted"] > 0:
                        fix_info = (f" (fixed: {s['fixes_succeeded']}"
                                    f"/{s['fixes_attempted']}"
                                    f" = {s['fix_rate_pct']}%)")
                    print(f"  {s['category']}: {s['total_issues']}{fix_info}")

        # Quality gate breakdown
        try:
            quality_rows = conn.execute("""
                SELECT quality_status, COUNT(*) as cnt
                FROM conversions
                WHERE quality_status IS NOT NULL AND quality_status != ''
                GROUP BY quality_status
                ORDER BY cnt DESC
            """).fetchall()
            if quality_rows:
                print("\nQuality Gate Breakdown:")
                for r in quality_rows:
                    print(f"  {r['quality_status']:<15} {r['cnt']:>5}")
        except Exception:
            pass  # column may not exist in older DBs

        # Extraction cache summary
        cache_stats = get_cache_stats(args.db_path)
        if cache_stats['total_entries'] > 0:
            tier_names = {1: 'standard', 2: 're-ocr', 3: 'vision'}
            tier_parts = []
            for tid, data in sorted(cache_stats['by_tier'].items()):
                tier_parts.append(f"{data['count']} {tier_names.get(tid, '?')}")
            print(f"\nExtraction Cache:")
            print(f"  Entries: {cache_stats['total_entries']} ({', '.join(tier_parts)})")
            print(f"  Times served: {cache_stats['total_times_served']}")
            print(f"  Total extraction cost: ${cache_stats['total_extraction_cost_usd']:.2f}")
            print(f"  Cost savings from cache: ${cache_stats['total_cost_saved_usd']:.2f}")
    finally:
        conn.close()


def _cmd_import_vqa(args):
    report_path = Path(args.report).resolve()
    if not report_path.exists():
        print(f"Error: Report not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    filename = report.get("book", report_path.stem)
    title, author = _parse_metadata_from_filename(filename)

    book_id = get_or_create_book(
        filename,
        title=title,
        author=author,
        page_count=report.get("pages_total"),
        format=Path(filename).suffix.lstrip('.') or 'kfx',
        db_path=args.db_path,
    )

    token_usage = report.get("token_usage", {})
    conv_id = add_conversion(
        book_id=book_id,
        extraction_path='html_extraction',
        vqa_score=report.get("overall_score"),
        vqa_report_path=str(report_path),
        api_input_tokens=token_usage.get("input_tokens", 0),
        api_output_tokens=token_usage.get("output_tokens", 0),
        cost_usd=token_usage.get("estimated_cost_usd", 0),
        db_path=args.db_path,
    )

    issue_count = add_issues_from_vqa_report(
        conv_id, book_id, report, db_path=args.db_path
    )

    print(f"Imported: {filename}")
    print(f"  Book ID: {book_id}, Conversion ID: {conv_id}")
    print(f"  VQA Score: {report.get('overall_score')}")
    print(f"  Issues: {issue_count}")


def _cmd_history(args):
    filename = args.filename
    book = get_book_by_filename(filename, db_path=args.db_path)
    if not book:
        # Try partial match
        conn = get_db(args.db_path)
        try:
            cursor = conn.execute(
                "SELECT * FROM books WHERE filename LIKE ?",
                (f"%{filename}%",)
            )
            matches = cursor.fetchall()
        finally:
            conn.close()

        if not matches:
            print(f"No book found matching: {filename}")
            return
        if len(matches) > 1:
            print(f"Multiple matches for '{filename}':")
            for m in matches:
                print(f"  [{m['id']}] {m['filename']}")
            return
        book = dict(matches[0])

    history = get_book_history(book["id"], db_path=args.db_path)
    if not history:
        print(f"No history found for book ID {book['id']}")
        return

    b = history["book"]
    print(f"Book: {b['filename']}")
    if b.get("title"):
        print(f"  Title: {b['title']}")
    if b.get("author"):
        print(f"  Author: {b['author']}")
    print(f"  Format: {b['format']}, Pages: {b.get('page_count', '?')}")
    if b.get("isbn"):
        print(f"  ISBN: {b['isbn']}")
    if b.get("source_file_hash"):
        print(f"  Source hash: {b['source_file_hash'][:16]}...")
    if b.get("cover_image_path"):
        print(f"  Cover: {b['cover_image_path']}")
    print()

    for c in history["conversions"]:
        print(f"  Conversion #{c['iteration']} ({c['extraction_path']})")
        print(f"    VQA Score: {c.get('vqa_score', '?')}")
        print(f"    Cost: ${c.get('cost_usd', 0):.4f}")
        if c.get('output_file_path'):
            print(f"    Output: {c['output_file_path']}")
        if c.get('conversion_flags'):
            print(f"    Flags: {c['conversion_flags']}")
        if c.get('category_scores'):
            print(f"    Scores: {c['category_scores']}")
        print(f"    Date: {c['created_at']}")

        conv_issues = [
            i for i in history["issues"] if i["conversion_id"] == c["id"]
        ]
        if conv_issues:
            print(f"    Issues ({len(conv_issues)}):")
            for issue in conv_issues:
                fix = ""
                if issue["fix_attempted"]:
                    fix = " [FIXED]" if issue["fix_succeeded"] else " [FIX FAILED]"
                print(f"      - [{issue['severity']}] {issue['category']}: "
                      f"{(issue.get('description') or '')[:80]}{fix}")
        print()

    # Display path switches
    if history.get("path_switches"):
        print("  Path Switches:")
        for sw in history["path_switches"]:
            delta = ""
            if sw["score_before"] is not None and sw["score_after"] is not None:
                d = sw["score_after"] - sw["score_before"]
                delta = f" ({'+' if d >= 0 else ''}{d})"
            print(f"    {sw['from_path']} -> {sw['to_path']}: "
                  f"{sw.get('score_before', '?')} -> {sw.get('score_after', '?')}{delta}")

            if sw.get("escalation_details"):
                try:
                    details = json.loads(sw["escalation_details"]) if isinstance(
                        sw["escalation_details"], str
                    ) else sw["escalation_details"]
                    if details.get("cost_of_switch"):
                        print(f"      Cost: ${details['cost_of_switch']:.4f}")
                    if details.get("duration_before") and details.get("duration_after"):
                        print(f"      Duration: {details['duration_before']}s -> "
                              f"{details['duration_after']}s")
                except (json.JSONDecodeError, TypeError):
                    pass
            print(f"    Date: {sw['created_at']}")
        print()


def _cmd_switches(args):
    """Show all recorded path switches with outcomes."""
    conn = get_db(args.db_path)
    try:
        cursor = conn.execute(
            """SELECT ps.*, b.filename
               FROM path_switches ps
               JOIN books b ON b.id = ps.book_id
               ORDER BY ps.created_at DESC"""
        )
        switches = cursor.fetchall()
    finally:
        conn.close()

    if not switches:
        print("No path switches recorded yet.")
        print("Path switches are recorded when the converge loop tries multiple strategies.")
        return

    print(f"{'Book':<30} {'From':<25} {'To':<25} {'Before':>6} {'After':>5} {'Delta':>6}")
    print("-" * 100)
    for sw in switches:
        fname = (sw['filename'] or '?')[:29]
        before = str(sw['score_before']) if sw['score_before'] is not None else '?'
        after = str(sw['score_after']) if sw['score_after'] is not None else '?'
        delta = ''
        if sw['score_before'] is not None and sw['score_after'] is not None:
            d = sw['score_after'] - sw['score_before']
            delta = f"{'+' if d >= 0 else ''}{d}"
        print(f"{fname:<30} {sw['from_path']:<25} {sw['to_path']:<25} "
              f"{before:>6} {after:>5} {delta:>6}")


def _cmd_fixes(args):
    conn = get_db(args.db_path)
    try:
        cursor = conn.execute(
            """SELECT * FROM fix_patterns
               ORDER BY success_rate DESC, times_applied DESC"""
        )
        patterns = cursor.fetchall()
    finally:
        conn.close()

    if not patterns:
        print("No fix patterns recorded yet.")
        return

    print(f"{'ID':>4} {'Type':<20} {'Category':<20} {'Applied':>7} "
          f"{'Success':>7} {'Rate':>6} {'Promoted':>8}")
    print("-" * 80)
    for p in patterns:
        promoted = "Yes" if p["promoted_to_iteration"] else "No"
        print(f"{p['id']:>4} {p['fix_type']:<20} "
              f"{(p['trigger_category'] or '-'):<20} "
              f"{p['times_applied']:>7} {p['times_succeeded']:>7} "
              f"{p['success_rate']*100:>5.1f}% {promoted:>8}")


def _cmd_trend(args):
    trends = get_score_trend(limit=args.limit, db_path=args.db_path)
    if not trends:
        print("No scored conversions yet.")
        return

    print(f"{'Score':>5} {'Iter':>4} {'Path':<18} {'Cost':>8} {'Book'}")
    print("-" * 70)
    for t in trends:
        name = t.get("title") or t["filename"]
        if len(name) > 30:
            name = name[:27] + "..."
        print(f"{t['vqa_score']:>5} {t['iteration']:>4} "
              f"{t['extraction_path']:<18} "
              f"${t.get('cost_usd', 0):>7.4f} {name}")


def _cmd_cost(args):
    summary = get_cost_summary(db_path=args.db_path)
    if not summary or summary.get("total_conversions", 0) == 0:
        print("No conversions recorded yet.")
        return

    print(f"Total conversions:  {summary['total_conversions']}")
    print(f"Total books:        {summary['total_books']}")
    print(f"Total API cost:     ${summary.get('total_cost_usd', 0) or 0:.4f}")
    print(f"Avg cost/conversion:${summary.get('avg_cost_per_conversion', 0) or 0:.4f}")
    print(f"Total input tokens: {summary.get('total_input_tokens', 0) or 0:,}")
    print(f"Total output tokens:{summary.get('total_output_tokens', 0) or 0:,}")
    print(f"Avg VQA score:      {summary.get('avg_vqa_score', 0) or 0:.1f}")


def _cmd_cache(args):
    filename = args.filename
    min_score = args.min_score

    # Try exact match first, then partial
    result = get_cached_result(filename=filename, min_score=min_score,
                               db_path=args.db_path)
    if not result:
        # Try partial filename match to find the book, then look up cache
        conn = get_db(args.db_path)
        try:
            cursor = conn.execute(
                "SELECT filename FROM books WHERE filename LIKE ?",
                (f"%{filename}%",)
            )
            matches = cursor.fetchall()
        finally:
            conn.close()

        for m in matches:
            result = get_cached_result(
                filename=m["filename"], min_score=min_score,
                db_path=args.db_path
            )
            if result:
                break

    if not result:
        print(f"Conversion cache: MISS for '{filename}' (min score: {min_score})")
    else:
        print(f"Conversion cache: HIT — {result['filename']}")
        print(f"  VQA Score:       {result['vqa_score']}")
        print(f"  Extraction path: {result['extraction_path']}")
        print(f"  Cost:            ${result.get('cost_usd', 0):.4f}")
        print(f"  Date:            {result['created_at']}")
        if result.get('output_file_path'):
            exists = Path(result['output_file_path']).exists()
            status = "" if exists else " (FILE MISSING)"
            print(f"  Output (DB):     {result['output_file_path']}{status}")

        output_path = get_cached_output_path(
            filename=result['filename'], min_score=min_score,
            db_path=args.db_path
        )
        if output_path:
            print(f"  Output file:     {output_path}")
        else:
            print(f"  Output file:     NOT FOUND ON DISK (cache stale)")

    # Also check extraction cache — find book's source_file_hash
    conn = get_db(args.db_path)
    try:
        row = conn.execute(
            "SELECT source_file_hash FROM books WHERE filename LIKE ? AND source_file_hash IS NOT NULL LIMIT 1",
            (f"%{filename}%",)
        ).fetchone()
    finally:
        conn.close()

    if row and row['source_file_hash']:
        ext_cached = get_cached_extraction(
            source_file_hash=row['source_file_hash'], min_score=0,
            db_path=args.db_path
        )
        if ext_cached:
            tier_names = {1: 'standard', 2: 're-ocr', 3: 'vision'}
            print(f"Extraction cache: HIT (tier {ext_cached['extraction_tier']} "
                  f"{tier_names.get(ext_cached['extraction_tier'], '?')}, "
                  f"method: {ext_cached['extraction_method']}, "
                  f"score: {ext_cached['quality_score']}, "
                  f"served {ext_cached['times_served']} times)")
        else:
            print(f"Extraction cache: MISS")
    else:
        print(f"Extraction cache: MISS (no source_file_hash for this book)")


def _cmd_cache_stats(args):
    """Show extraction cache statistics."""
    stats = get_cache_stats(db_path=args.db_path)
    tier_names = {1: 'standard', 2: 're-ocr', 3: 'vision'}

    print("Extraction Cache Statistics")
    print(f"  Total entries:       {stats['total_entries']}")
    print(f"  Total times served:  {stats['total_times_served']}")
    print(f"  Extraction cost:     ${stats['total_extraction_cost_usd']:.2f}")
    print(f"  Cost savings:        ${stats['total_cost_saved_usd']:.2f}")
    print(f"  Avg quality score:   {stats['avg_quality_score']}")

    if stats['by_tier']:
        print("\n  By tier:")
        for tier_id, data in sorted(stats['by_tier'].items()):
            name = tier_names.get(tier_id, f'tier-{tier_id}')
            print(f"    Tier {tier_id} ({name}): "
                  f"{data['count']} entries, {data['served']} served")

    if stats['by_method']:
        print("\n  By method:")
        for method, count in sorted(stats['by_method'].items()):
            print(f"    {method:<20} {count}")


def _cmd_cache_invalidate(args):
    """Invalidate extraction cache entries."""
    if not args.file_hash and not args.book_id and args.older_than_version is None:
        print("Error: specify --file-hash, --book-id, or --older-than-version",
              file=sys.stderr)
        sys.exit(1)

    count = invalidate_extraction_cache(
        source_file_hash=args.file_hash,
        book_id=args.book_id,
        older_than_version=args.older_than_version,
        db_path=args.db_path,
    )
    print(f"Invalidated {count} extraction cache entries")


def _cmd_cache_backfill_images(args):
    """Backfill image_count for existing extraction cache entries."""
    updated = backfill_cache_image_counts(db_path=getattr(args, 'db_path', None))
    print(f"Backfilled image_count for {updated} cache entries")


def _cmd_publisher_report(args):
    """Print per-publisher conversion stats (FU-4)."""
    conn = get_db(getattr(args, 'db_path', None))
    try:
        where = ""
        params = []
        if getattr(args, 'publisher', None):
            where = "WHERE b.publisher LIKE ?"
            params = [f"%{args.publisher}%"]

        cursor = conn.execute(f"""
            SELECT
                COALESCE(b.publisher, '(unknown)') as publisher,
                COUNT(DISTINCT b.id) as books,
                ROUND(AVG(CASE WHEN c.iteration = 1 THEN c.vqa_score END), 1) as avg_initial,
                ROUND(AVG(c.vqa_score), 1) as avg_final,
                ROUND(SUM(c.cost_usd), 4) as total_cost,
                ROUND(AVG(c.duration_seconds), 1) as avg_duration
            FROM books b
            LEFT JOIN conversions c ON c.book_id = b.id
            {where}
            GROUP BY COALESCE(b.publisher, '(unknown)')
            HAVING books > 0
            ORDER BY books DESC
        """, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        print("No publisher data found.")
        return

    print(f"{'Publisher':<30} {'Books':>5} {'Avg Init':>9} {'Avg Final':>9} "
          f"{'Cost':>8} {'Avg Dur':>8}")
    print("-" * 80)
    for r in rows:
        init_s = f"{r['avg_initial']:.1f}" if r['avg_initial'] else "-"
        final_s = f"{r['avg_final']:.1f}" if r['avg_final'] else "-"
        cost_s = f"${r['total_cost']:.2f}" if r['total_cost'] else "$0.00"
        dur_s = f"{r['avg_duration']:.0f}s" if r['avg_duration'] else "-"
        print(f"{r['publisher']:<30} {r['books']:>5} {init_s:>9} {final_s:>9} "
              f"{cost_s:>8} {dur_s:>8}")


def _cmd_cache_roi(args):
    """Print cost-per-serve amortization for cached extractions and conversions (FU-5)."""
    conn = get_db(getattr(args, 'db_path', None))
    try:
        # Check if extraction_cache table has data
        _has_cache = False
        try:
            cache_rows = conn.execute("""
                SELECT
                    ec.source_file_hash,
                    ec.extraction_tier,
                    ec.extraction_method,
                    ec.extraction_cost_usd,
                    ec.times_served,
                    ec.quality_score,
                    CASE WHEN ec.times_served > 0
                         THEN ROUND(ec.extraction_cost_usd / ec.times_served, 4)
                         ELSE ec.extraction_cost_usd END as cost_per_serve,
                    COALESCE(b.title, b.filename, ec.source_file_hash) as name
                FROM extraction_cache ec
                LEFT JOIN books b ON b.source_file_hash = ec.source_file_hash
                ORDER BY ec.times_served DESC, ec.extraction_cost_usd DESC
            """).fetchall()
            if cache_rows:
                _has_cache = True
                total_cache_cost = sum(r['extraction_cost_usd'] or 0 for r in cache_rows)
                total_serves = sum(r['times_served'] or 0 for r in cache_rows)
                print(f"=== Extraction Cache ({len(cache_rows)} entries, "
                      f"${total_cache_cost:.2f} total cost, {total_serves} total serves) ===")
                print(f"{'Title/File':<35} {'Tier':>4} {'Method':<14} {'Cost':>7} "
                      f"{'Serves':>6} {'$/Serve':>8} {'Score':>5}")
                print("-" * 85)
                for r in cache_rows:
                    name = (r['name'] or '?')[:34]
                    method = (r['extraction_method'] or '?')[:13]
                    cost = r['extraction_cost_usd'] or 0
                    cps = r['cost_per_serve'] or 0
                    score_s = str(r['quality_score']) if r['quality_score'] else "-"
                    print(f"{name:<35} {r['extraction_tier'] or '?':>4} {method:<14} "
                          f"${cost:>6.2f} {r['times_served'] or 0:>6} ${cps:>7.4f} {score_s:>5}")
                print()
        except Exception:
            pass  # extraction_cache may not exist in older DBs

        # Also show conversion-level cost amortization
        min_cost_clause = ""
        params = []
        if getattr(args, 'min_cost', None):
            min_cost_clause = "HAVING total_cost >= ?"
            params = [args.min_cost]

        cursor = conn.execute(f"""
            SELECT
                b.filename,
                COALESCE(b.title, '(untitled)') as title,
                COUNT(c.id) as conversions,
                ROUND(SUM(c.cost_usd), 4) as total_cost,
                MAX(c.vqa_score) as best_score,
                CASE
                    WHEN COUNT(c.id) = 0 THEN 0
                    ELSE ROUND(SUM(c.cost_usd) / COUNT(c.id), 4)
                END as cost_per_serve
            FROM books b
            LEFT JOIN conversions c ON c.book_id = b.id
            GROUP BY b.id
            {min_cost_clause}
            ORDER BY total_cost DESC
        """, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows and not _has_cache:
        print("No conversion or cache data found.")
        return

    if rows:
        print(f"=== Conversion Cost Amortization ({len(rows)} books) ===")
        print(f"{'Title':<35} {'Runs':>4} {'Cost':>8} {'$/Serve':>8} "
              f"{'Best':>5} {'Status':<12}")
        print("-" * 80)

        total_all_cost = 0
        for r in rows:
            cost = r['total_cost'] or 0
            cps = r['cost_per_serve'] or 0
            total_all_cost += cost
            score_s = str(r['best_score']) if r['best_score'] else "-"

            if cps == 0:
                status = "free"
            elif cps < 0.50:
                status = "amortized"
            elif cps < 2.00:
                status = "recovering"
            else:
                status = "sunk"

            title = (r['title'] or r['filename'])[:34]
            print(f"{title:<35} {r['conversions']:>4} ${cost:>7.2f} ${cps:>7.4f} "
                  f"{score_s:>5} {status:<12}")

        print("-" * 80)
        print(f"Total cost across all books: ${total_all_cost:.4f}")


def _cmd_extractor_stats(args):
    """Show which extractors win in multi-extractor comparisons."""
    conn = get_db(getattr(args, 'db_path', None))
    try:
        cursor = conn.execute("""
            SELECT extractor_comparison
            FROM conversions
            WHERE extractor_comparison IS NOT NULL
              AND extractor_comparison != ''
        """)
        rows = cursor.fetchall()
        if not rows:
            print("No extractor comparison data recorded yet.")
            print("Run conversions with --compare-extractors to start collecting data.")
            return

        from collections import Counter
        wins = Counter()
        total = 0
        for r in rows:
            try:
                data = json.loads(r['extractor_comparison'])
                if isinstance(data, dict):
                    best = max(data.items(), key=lambda x: x[1].get('score', 0))
                    wins[best[0]] += 1
                    total += 1
            except (json.JSONDecodeError, ValueError):
                continue

        print(f"Extractor Comparison Results ({total} comparisons)")
        print(f"{'Extractor':<20} {'Wins':>6} {'Win %':>7}")
        print("-" * 35)
        for name, count in wins.most_common():
            pct = (count / total * 100) if total else 0
            print(f"{name:<20} {count:>6} {pct:>6.1f}%")
    finally:
        conn.close()


def _cmd_ocr_stats(args):
    """Show OCR substitution statistics across all conversions."""
    conn = get_db(getattr(args, 'db_path', None))
    try:
        cursor = conn.execute("""
            SELECT fix_type, SUM(times_applied) as total_applied,
                   SUM(times_succeeded) as total_succeeded,
                   ROUND(AVG(success_rate), 1) as avg_success_rate,
                   ROUND(AVG(avg_score_improvement), 1) as avg_improvement
            FROM fix_patterns
            GROUP BY fix_type
            ORDER BY total_applied DESC
        """)
        rows = cursor.fetchall()
        if not rows:
            print("No OCR fix statistics recorded yet.")
            print("Run conversions with VQA enabled to start collecting fix data.")
            return
        delta = '\u0394'
        print(f"{'Fix Type':<30} {'Applied':>8} {'Succeeded':>10} {'Rate':>6} {delta + ' Score':>8}")
        print("-" * 70)
        for r in rows:
            print(f"{r['fix_type']:<30} {r['total_applied']:>8} "
                  f"{r['total_succeeded']:>10} {r['avg_success_rate'] or 0:>5.1f}% "
                  f"{r['avg_improvement'] or 0:>+7.1f}")
    finally:
        conn.close()


def _cmd_classify(args):
    """Classify a PDF source and print the result."""
    pdf_path = args.pdf_path
    if not Path(pdf_path).is_file():
        print(f"File not found: {pdf_path}")
        return

    try:
        from classify_source import classify_pdf
    except ImportError:
        # Try relative import from same directory
        script_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(script_dir))
        from classify_source import classify_pdf

    result = classify_pdf(pdf_path)
    print(json.dumps(result, indent=2))

    # Show summary
    cls = result["classification"]
    conf = result["confidence"]
    strats = " -> ".join(result["recommended_strategies"])
    print(f"\nClassification: {cls} (confidence: {conf})")
    print(f"Strategies: {strats}")
    if result["flags"]["needs_ocr"]:
        print("WARNING: Source needs OCR")
    if result["flags"]["likely_two_column"]:
        print("Detected: likely two-column layout")


def _cmd_recommend(args):
    """Recommend extraction strategy from historical data."""
    rec = get_recommended_strategy(
        filename=args.filename,
        source_file_path=args.filename,
        source_type=args.source_type,
        publisher=args.publisher,
        format=args.format,
        db_path=args.db_path,
    )

    print(f"Source:       {rec['source']}")
    print(f"Confidence:   {rec['confidence']}")
    if rec["strategy_order"]:
        print(f"Strategies:   {' -> '.join(rec['strategy_order'])}")
    else:
        print("Strategies:   (none — no historical data)")
    print(f"Reason:       {rec['reason']}")

    if rec["best_prior_score"] is not None:
        print(f"Best score:   {rec['best_prior_score']}")
    if rec["prior_conversions"] > 0:
        print(f"Prior runs:   {rec['prior_conversions']}")

    flags = [k for k, v in rec["flags"].items() if v]
    if flags:
        print(f"Auto-flags:   {', '.join(flags)}")


def _cmd_override_add(args):
    filename = args.filename

    # Look up existing book
    book = get_book_by_filename(filename, db_path=args.db_path)
    if not book:
        conn = get_db(args.db_path)
        try:
            cursor = conn.execute(
                "SELECT * FROM books WHERE filename LIKE ?",
                (f"%{filename}%",)
            )
            matches = cursor.fetchall()
        finally:
            conn.close()

        if len(matches) == 1:
            book = dict(matches[0])
        elif len(matches) > 1:
            print(f"Multiple books match '{filename}':")
            for m in matches:
                print(f"  [{m['id']}] {m['filename']}")
            print("Use an exact filename.")
            return

    book_id = book["id"] if book else None
    title = book["title"] if book else None
    author = book["author"] if book else None

    # Load chapter structure from file if provided
    chapter_structure = None
    if args.chapters:
        with open(args.chapters, 'r', encoding='utf-8') as f:
            chapter_structure = json.load(f)

    # Build corrections list from --corrections file and --strip-heading flags
    corrections = None
    if args.corrections:
        with open(args.corrections, 'r', encoding='utf-8') as f:
            corrections = json.load(f)
    if args.strip_heading:
        if corrections is None:
            corrections = []
        for text in args.strip_heading:
            corrections.append({
                "action": "strip_heading",
                "pattern": text,
                "match": "exact",
                "note": "Added via pattern_db CLI"
            })

    override_id = add_book_override(
        book_id=book_id,
        title=title,
        author=author,
        extraction_path=args.extraction_path,
        extraction_notes=args.notes,
        chapter_structure=chapter_structure,
        skip_front_pages=args.skip_front,
        skip_back_pages=args.skip_back,
        corrections=corrections,
        db_path=args.db_path,
    )

    print(f"Override added (ID: {override_id})")
    if book:
        print(f"  Book: [{book_id}] {book['filename']}")
    else:
        print(f"  Book not in DB yet (override will match by title hash)")
    if args.extraction_path:
        print(f"  Extraction path: {args.extraction_path}")
    if args.notes:
        print(f"  Notes: {args.notes}")
    if chapter_structure:
        print(f"  Chapter structure: {len(chapter_structure)} entries loaded")
    if corrections:
        print(f"  Corrections: {len(corrections)} rules loaded")
    if args.skip_front:
        print(f"  Skip front pages: {args.skip_front}")
    if args.skip_back:
        print(f"  Skip back pages: {args.skip_back}")


def _cmd_override_show(args):
    filename = args.filename
    override = get_book_override(filename=filename, db_path=args.db_path)
    if not override:
        # Try partial match
        conn = get_db(args.db_path)
        try:
            cursor = conn.execute(
                "SELECT filename FROM books WHERE filename LIKE ?",
                (f"%{filename}%",)
            )
            matches = cursor.fetchall()
        finally:
            conn.close()

        for m in matches:
            override = get_book_override(
                filename=m["filename"], db_path=args.db_path
            )
            if override:
                break

    if not override:
        print(f"No overrides found for: {filename}")
        return

    print(f"Override ID: {override['id']}")
    if override.get('book_id'):
        print(f"  Book ID:         {override['book_id']}")
    if override.get('isbn'):
        print(f"  ISBN:            {override['isbn']}")
    if override.get('extraction_path'):
        print(f"  Extraction path: {override['extraction_path']}")
    if override.get('extraction_notes'):
        print(f"  Notes:           {override['extraction_notes']}")
    if override.get('calibre_options'):
        print(f"  Calibre options: {override['calibre_options']}")
    if override.get('skip_front_pages'):
        print(f"  Skip front:      {override['skip_front_pages']} pages")
    if override.get('skip_back_pages'):
        print(f"  Skip back:       {override['skip_back_pages']} pages")
    if override.get('chapter_structure'):
        chapters = override['chapter_structure']
        if isinstance(chapters, list):
            print(f"  Chapters:        {len(chapters)} entries")
            for ch in chapters[:5]:
                lvl = ch.get('level', '?')
                ttl = ch.get('title', '?')
                print(f"    L{lvl}: {ttl}")
            if len(chapters) > 5:
                print(f"    ... and {len(chapters) - 5} more")
        else:
            print(f"  Chapters:        {chapters}")
    if override.get('corrections'):
        corrections = override['corrections']
        if isinstance(corrections, list) and corrections:
            print(f"  Corrections:     {len(corrections)} rules")
            for i, rule in enumerate(corrections[:10]):
                action = rule.get('action', '?')
                pattern = rule.get('pattern', rule.get('text', '?'))
                note = rule.get('note', '')
                print(f"    [{i+1}] {action}: '{pattern[:60]}'"
                      f"{f' ({note})' if note else ''}")
            if len(corrections) > 10:
                print(f"    ... and {len(corrections) - 10} more")
    print(f"  Source:          {override.get('source', 'local')}")
    print(f"  Created:         {override.get('created_at')}")


def _cmd_override_list(args):
    conn = get_db(args.db_path)
    try:
        cursor = conn.execute(
            """SELECT bo.*, b.filename, b.title
               FROM book_overrides bo
               LEFT JOIN books b ON b.id = bo.book_id
               ORDER BY bo.created_at DESC"""
        )
        overrides = cursor.fetchall()
    finally:
        conn.close()

    if not overrides:
        print("No book overrides recorded yet.")
        return

    print(f"{'ID':>4} {'Book':<40} {'Path':<18} {'Notes'}")
    print("-" * 80)
    for o in overrides:
        name = o["title"] or o["filename"] or f"(hash: {o['title_hash']})"
        if name and len(name) > 38:
            name = name[:35] + "..."
        path = o["extraction_path"] or "-"
        notes = (o["extraction_notes"] or "")[:25]
        print(f"{o['id']:>4} {name:<40} {path:<18} {notes}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

# Literal placeholder strings that appear in PDF metadata when a field is
# unset but written as a stringified None/null value (SCRUM-322). Some PDF
# authoring tools (e.g. Pdf995) write the literal text "None" instead of
# leaving the field empty, which previously slipped through and ended up
# in output filenames as "<Author> - None.kfx".
_GARBAGE_PLACEHOLDERS = {'none', 'null', 'n/a', 'na', 'undefined', 'nil'}


def _clean_meta_field(value, field_type='generic'):
    """Filter garbage values from PDF/EPUB metadata fields.

    Returns cleaned string or None if the value is empty or garbage.
    """
    if not value or not value.strip():
        return None

    cleaned = value.strip()

    if cleaned.lower() in _GARBAGE_PLACEHOLDERS:
        return None

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


def _normalize_title_hash(title, author=None):
    """Create a normalized hash for fuzzy title+author matching.

    Strips punctuation, lowercases, removes common words like 'the', 'a', 'an',
    removes subtitle after colon/dash, and combines with author last name.
    Returns a string suitable for exact comparison.

    Examples:
        _normalize_title_hash("The Book of Ezekiel, Chapters 25-48", "Daniel I. Block")
        -> "book ezekiel chapters 25 48 block"

        _normalize_title_hash("Jesus and the Land", "Gary M. Burge")
        -> "jesus land burge"
    """
    if not title:
        return None

    # Remove subtitle after colon or em-dash
    text = re.split(r'[:\u2014]', title)[0]

    # Lowercase, strip punctuation
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)

    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at',
                  'to', 'for', 'by', 'with', 'from', 'is', 'was', 'are'}
    words = [w for w in text.split() if w not in stop_words]

    # Add author last name if available
    if author:
        # Extract last name: take last word, ignoring initials and suffixes
        author_clean = re.sub(r'[^\w\s]', ' ', author).strip()
        author_parts = [p for p in author_clean.split() if len(p) > 1]
        if author_parts:
            # Last name is typically the first significant word for
            # "LastName, FirstName" format, or last word otherwise
            if ',' in author:
                last_name = author_parts[0].lower()
            else:
                last_name = author_parts[-1].lower()
            words.append(last_name)

    return ' '.join(words) if words else None


def _parse_metadata_from_filename(filename):
    """Parse title and author from ebook filename.

    Handles patterns like:
        "Author - Title (Year, Publisher).ext"               (libgen)
        "Author - Title (Year, Publisher) - libgen.li.ext"   (libgen with suffix)
        "(Series Name) Author - Title (Year, Publisher).ext" (libgen with series prefix)
        "Author - Title-Publisher (Year).ext"                (libgen, publisher dash variant)
        "Title - Author.ext"                                 (legacy pipeline-output naming)
        "Title.ext"                                          (no separator)

    SCRUM-323: previously this function did `rsplit(' - ', 1)` and assigned
    parts[0] to title, parts[1] to author. That inverts the libgen convention
    (Author - Title) and was also fooled by trailing `- libgen.li` noise.
    The PowerShell `Get-EbookMetadataFromFilename` Pattern 2 anchors on the
    trailing parenthetical year/publisher block and treats the LHS of the
    dash as the author. This implementation mirrors that.
    """
    stem = Path(filename).stem

    # Remove common suffixes added by the pipeline
    for suffix in ('_visual_qa_report', '_visual_qa_report_LEGACY',
                   '_visual_qa_report_HTML'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]

    # Strip trailing libgen / Anna's Archive noise so it doesn't end up captured
    # as the author or as part of the title.
    stem = re.sub(r'\s*-\s*libgen[\.\s]?li\s*$', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s*--\s*Anna'?’?s?\s*Archive\s*$", '', stem,
                  flags=re.IGNORECASE)
    stem = stem.strip()

    # Strip a leading parenthetical that is NOT a 4-digit year. A leading (YYYY)
    # is a year, not a series tag, so leave that alone for the libgen regex.
    series_prefix = re.match(r'^\(([^)]+)\)\s+(.+)$', stem)
    if series_prefix and not re.fullmatch(r'\s*\d{4}\s*',
                                          series_prefix.group(1)):
        stem = series_prefix.group(2)

    # Libgen heuristic: when the stem contains a parenthetical or bracket
    # anywhere, treat it as 'Author - Title (...)' convention and stop the
    # title capture at the FIRST open paren. This prevents inner parentheticals
    # like '(Great Books in Philosophy)' or trailing '-Prometheus Books (1989)'
    # publisher metadata from leaking into the title.
    # Mirrors PowerShell Get-EbookMetadataFromFilename Pattern 2.
    if '(' in stem or '[' in stem:
        libgen_match = re.match(r'^(.+?)\s+-\s+(.+?)\s*[\(\[]', stem)
        if libgen_match:
            author = libgen_match.group(1).strip().rstrip('-').strip()
            title = libgen_match.group(2).strip().rstrip('-').strip()
            return title, author

    # Legacy fallback: 'Title - Author' format (pipeline output naming).
    parts = stem.rsplit(' - ', 1)
    if len(parts) == 2:
        title = parts[0].strip()
        author = parts[1].strip()
    else:
        title = stem.strip()
        author = None

    return title, author


def _parse_year_from_filename(filename):
    """Extract the publication year from a filename.

    SCRUM-323: prefer the filename's year over the PDF's `creationDate` year
    when pdf_internal is rejected. Looks for a 4-digit year in 19xx/20xx range.
    Returns the LAST matching year (matches PowerShell Get-EbookMetadataFromFilename
    behavior — handles reprint patterns where original year appears early and
    reprint year appears late).
    """
    stem = Path(filename).stem
    matches = re.findall(r'\b(19\d{2}|20\d{2})\b', stem)
    return matches[-1] if matches else None


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


def _get_epub_meta(book, namespace, name):
    """Get a single metadata value from an ebooklib EpubBook."""
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
    """Extract ISBN from EPUB DC:identifier fields."""
    try:
        identifiers = book.get_metadata('DC', 'identifier')
        for ident_tuple in identifiers:
            val = str(ident_tuple[0]).strip()
            for prefix in ('isbn:', 'urn:isbn:', 'ISBN:'):
                if val.lower().startswith(prefix.lower()):
                    val = val[len(prefix):]
                    break
            cleaned = val.replace('-', '')
            if re.match(r'^(97[89])?\d{9}[\dXx]$', cleaned):
                return cleaned
    except Exception:
        pass
    return None


def extract_epub_metadata(file_path):
    """Extract metadata from an EPUB file via ebooklib."""
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


def extract_file_metadata(file_path):
    """Extract internal metadata from a file based on its format.
    Returns dict. For unsupported formats, returns empty dict.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return extract_pdf_metadata(file_path)
    elif ext == '.epub':
        return extract_epub_metadata(file_path)
    else:
        return {}


# SCRUM-323 Bug 2: PDF authoring tools known to write garbage / filename-as-title
# metadata. When the PDF's creator or producer matches one of these tokens
# (case-insensitive substring), `_is_pdf_internal_suspicious` rejects the
# pdf_internal record in favor of filename_parser values. The list is kept
# tight on purpose: tools whose embedded metadata is generally reliable
# (calibre, Adobe InDesign, Acrobat Distiller) must NOT appear here.
_KNOWN_BAD_PDF_TOOLS = (
    'pdf995',
    'pdfcreator',
    'pdfsam',
)


def _is_pdf_internal_suspicious(internal_meta, filename_author):
    """Return True when pdf_internal metadata should be rejected as junk.

    SCRUM-323 Bug 2: the metadata-merge logic gives `pdf_internal` higher
    source priority than `filename_parser`, which is normally correct.
    But Pdf995-class tools write the filename as the title field and the
    literal string 'None' as author, with creationDate set to the PDF
    generation date (not the book's publication year). This gate detects
    two patterns and triggers a fallback to filename_parser:

        1. PDF creator/producer matches a known bad-tool fingerprint.
        2. PDF title contains the filename-derived author verbatim
           (case-insensitive) — strong signal the filename was injected
           into the title field.

    `internal_meta` is the dict returned by `extract_pdf_metadata`. The
    raw producer/creator strings live in `extra_json`.
    """
    extra_json = internal_meta.get('extra_json')
    creator = ''
    producer = ''
    if extra_json:
        try:
            extra = json.loads(extra_json)
            creator = (extra.get('creator') or '').lower()
            producer = (extra.get('producer') or '').lower()
        except (json.JSONDecodeError, TypeError):
            pass

    for tool in _KNOWN_BAD_PDF_TOOLS:
        if tool in creator or tool in producer:
            return True

    pdf_title = (internal_meta.get('title') or '').lower()
    if filename_author and pdf_title and filename_author.lower() in pdf_title:
        return True

    return False


# Source priority for merge decisions
_SOURCE_PRIORITY = {
    'filename_parser': 1,
    'pdf_internal': 2,
    'epub_opf': 3,
    'database': 4,
    'user_override': 5,
    'claude_api': 5,
    'merged': 3,
}

_METADATA_FIELDS = [
    'title', 'authors', 'publisher', 'year', 'language', 'subject',
    'series', 'description', 'isbn', 'cover_path', 'extra_json',
]


def merge_metadata(existing, new_fields, new_source_type):
    """Merge new metadata fields into existing, respecting source priority.
    For each field:
    - If existing is empty/None, use new value
    - If both have values, higher priority source wins
    Returns merged dict with source_type set to 'merged' when multiple sources contribute.
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
            pass

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
    Uses COALESCE-based upsert keyed on title_hash.
    Returns the stored metadata as a dict.
    """
    conn = get_db(db_path)
    try:
        existing = None
        if title_hash:
            row = conn.execute(
                "SELECT * FROM book_metadata WHERE title_hash = ?",
                (title_hash,)
            ).fetchone()
            if row:
                existing = dict(row)

        if existing:
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
    Returns dict or None.
    """
    conn = get_db(db_path)
    try:
        row = None

        if title_hash:
            row = conn.execute(
                "SELECT * FROM book_metadata WHERE title_hash = ?",
                (title_hash,)
            ).fetchone()

        if not row and isbn:
            row = conn.execute(
                "SELECT * FROM book_metadata WHERE isbn = ?",
                (isbn,)
            ).fetchone()

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _cmd_extract_metadata(args):
    """Extract internal metadata, merge with DB, store, output JSON."""
    file_path = os.path.abspath(args.file)
    if not os.path.isfile(file_path):
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)

    internal_meta = extract_file_metadata(file_path)

    filename = os.path.basename(file_path)
    parsed_title, parsed_author = _parse_metadata_from_filename(filename)
    parsed_year = _parse_year_from_filename(filename)

    ext = os.path.splitext(file_path)[1].lower()
    source_type = 'pdf_internal' if ext == '.pdf' else 'epub_opf' if ext == '.epub' else 'filename_parser'

    # SCRUM-323 Bug 2: when the PDF was produced by a tool known to write
    # garbage metadata (Pdf995) or when the PDF title contains the filename-
    # derived author, reject pdf_internal in favor of filename_parser. The
    # `extra_json` field is preserved for debugging traceability.
    if (source_type == 'pdf_internal'
            and _is_pdf_internal_suspicious(internal_meta, parsed_author)):
        extra_json = internal_meta.get('extra_json')
        internal_meta = {}
        if parsed_title:
            internal_meta['title'] = parsed_title
        if parsed_author:
            internal_meta['authors'] = parsed_author
        if parsed_year:
            internal_meta['year'] = parsed_year
        if extra_json:
            internal_meta['extra_json'] = extra_json
        source_type = 'filename_parser'

    title = internal_meta.get('title')
    authors = internal_meta.get('authors')
    if not title:
        title = parsed_title
        authors = authors or parsed_author

    title_hash = _normalize_title_hash(title, authors)
    if not title_hash:
        title_hash = _normalize_title_hash(Path(file_path).stem)

    existing = get_book_metadata(title_hash=title_hash, db_path=args.db_path)

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


def main():
    parser = argparse.ArgumentParser(
        description="EbookAutomation pattern database CLI"
    )
    parser.add_argument(
        '--db-path', default=None,
        help=f"Database path (default: {_DEFAULT_DB_PATH})"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    subparsers.add_parser('init', help='Create/verify database')
    subparsers.add_parser('stats', help='Print summary statistics')

    import_parser = subparsers.add_parser(
        'import-vqa', help='Import a VQA report'
    )
    import_parser.add_argument('report', help='Path to VQA report JSON')

    history_parser = subparsers.add_parser(
        'history', help='Show history for a book'
    )
    history_parser.add_argument(
        'filename', help='Book filename (exact or partial match)'
    )

    subparsers.add_parser('fixes', help='List fix patterns with success rates')

    trend_parser = subparsers.add_parser(
        'trend', help='Show recent score trend'
    )
    trend_parser.add_argument(
        '--limit', type=int, default=20, help='Number of entries'
    )

    subparsers.add_parser('cost', help='Show cost summary')
    subparsers.add_parser('switches', help='Show all recorded path switches')

    classify_parser = subparsers.add_parser(
        'classify', help='Classify a PDF source (digital_native, scan, etc.)'
    )
    classify_parser.add_argument('pdf_path', help='Path to PDF file')

    recommend_parser = subparsers.add_parser(
        'recommend', help='Recommend extraction strategy from historical data'
    )
    recommend_parser.add_argument(
        'filename', nargs='?', default=None,
        help='Book filename or source file path (exact or partial match)'
    )
    recommend_parser.add_argument(
        '--source-type', default=None,
        help='Source type (digital_native, scan_with_text, scan_no_text)'
    )
    recommend_parser.add_argument(
        '--publisher', default=None, help='Publisher name'
    )
    recommend_parser.add_argument(
        '--format', default='pdf', help='File format (default: pdf)'
    )

    cache_parser = subparsers.add_parser(
        'cache', help='Check if a book has a cached result'
    )
    cache_parser.add_argument(
        'filename', help='Book filename (exact or partial match)'
    )
    cache_parser.add_argument(
        '--min-score', type=int, default=80,
        help='Minimum VQA score to consider a cache hit (default: 80)'
    )

    override_sub = subparsers.add_parser(
        'override', help='Manage book overrides'
    )
    override_cmds = override_sub.add_subparsers(
        dest='override_command', help='Override subcommand'
    )

    ov_add = override_cmds.add_parser('add', help='Add a book override')
    ov_add.add_argument('filename', help='Book filename')
    ov_add.add_argument(
        '--extraction-path', help='Extraction path override'
    )
    ov_add.add_argument('--notes', help='Extraction notes')
    ov_add.add_argument(
        '--chapters', help='Path to chapter structure JSON file'
    )
    ov_add.add_argument(
        '--skip-front', type=int, help='Pages to skip at front'
    )
    ov_add.add_argument(
        '--skip-back', type=int, help='Pages to skip at back'
    )
    ov_add.add_argument(
        '--corrections', help='Path to corrections JSON file'
    )
    ov_add.add_argument(
        '--strip-heading', action='append', default=[],
        help='Add a strip_heading correction (can be used multiple times)'
    )

    ov_show = override_cmds.add_parser(
        'show', help='Show overrides for a book'
    )
    ov_show.add_argument(
        'filename', help='Book filename (exact or partial match)'
    )

    override_cmds.add_parser('list', help='List all book overrides')

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

    # ── Publisher report + Cache ROI (SCRUM-133 follow-ups) ──────
    pub_rpt_parser = subparsers.add_parser(
        'publisher-report', help='Show per-publisher conversion stats')
    pub_rpt_parser.add_argument('--publisher', help='Filter to specific publisher (partial match)')
    pub_rpt_parser.add_argument('--db-path', default=None)

    cache_roi_parser = subparsers.add_parser(
        'cache-roi', help='Show cost-per-serve amortization for all books')
    cache_roi_parser.add_argument('--min-cost', type=float, default=None,
                                  help='Only show books above this total cost')
    cache_roi_parser.add_argument('--db-path', default=None)

    # ── Extractor stats (SCRUM-125) ─────────────────────────────
    ext_stats_parser = subparsers.add_parser(
        'extractor-stats', help='Show extractor comparison win rates')
    ext_stats_parser.add_argument('--db-path', default=None)

    # ── OCR stats (SCRUM-39) ────────────────────────────────────
    ocr_stats_parser = subparsers.add_parser(
        'ocr-stats', help='Show OCR substitution fix statistics')
    ocr_stats_parser.add_argument('--db-path', default=None)

    # ── Extraction cache subcommands ─────────────────────────────
    subparsers.add_parser('cache-stats', help='Show extraction cache statistics')

    cache_inv_parser = subparsers.add_parser(
        'cache-invalidate', help='Invalidate extraction cache entries'
    )
    cache_inv_parser.add_argument('--file-hash', default=None,
                                  help='SHA-256 hash of source file')
    cache_inv_parser.add_argument('--book-id', type=int, default=None,
                                  help='Book ID to invalidate')
    cache_inv_parser.add_argument('--older-than-version', type=int, default=None,
                                  help='Invalidate entries below this cache_version')

    subparsers.add_parser('cache-backfill-images',
                          help='Backfill image_count for existing cache entries')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == 'override':
        if not hasattr(args, 'override_command') or not args.override_command:
            override_sub.print_help()
            sys.exit(1)
        override_commands = {
            'add': _cmd_override_add,
            'show': _cmd_override_show,
            'list': _cmd_override_list,
        }
        override_commands[args.override_command](args)
        return

    commands = {
        'init': _cmd_init,
        'stats': _cmd_stats,
        'import-vqa': _cmd_import_vqa,
        'history': _cmd_history,
        'fixes': _cmd_fixes,
        'trend': _cmd_trend,
        'cost': _cmd_cost,
        'switches': _cmd_switches,
        'cache': _cmd_cache,
        'cache-stats': _cmd_cache_stats,
        'cache-invalidate': _cmd_cache_invalidate,
        'cache-backfill-images': _cmd_cache_backfill_images,
        'classify': _cmd_classify,
        'recommend': _cmd_recommend,
        'extract-metadata': _cmd_extract_metadata,
        'get-metadata': _cmd_get_metadata,
        'update-metadata': _cmd_update_metadata,
        'store-metadata': _cmd_store_metadata,
        'publisher-report': _cmd_publisher_report,
        'cache-roi': _cmd_cache_roi,
        'ocr-stats': _cmd_ocr_stats,
        'extractor-stats': _cmd_extractor_stats,
    }

    commands[args.command](args)


if __name__ == '__main__':
    main()
