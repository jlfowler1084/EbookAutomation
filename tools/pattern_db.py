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
    python tools/pattern_db.py override add <filename>   # Add a book override
    python tools/pattern_db.py override show <filename>  # Show overrides for a book
    python tools/pattern_db.py override list             # List all book overrides
"""

import argparse
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
    ]
    for table, col, col_type in _new_columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists
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
             word_count=None, chapter_count=None, db_path=None):
    """Add a book record. Returns the book ID."""
    title_hash = _normalize_title_hash(title, author)
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO books
               (filename, title, author, publisher, year, format,
                file_size_bytes, page_count, source_type, title_hash,
                isbn, source_file_path, source_file_hash,
                cover_image_path, language, word_count, chapter_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (filename, title, author, publisher, year, format,
             file_size_bytes, page_count, source_type, title_hash,
             isbn, source_file_path, source_file_hash,
             cover_image_path, language, word_count, chapter_count)
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


def get_or_create_book(filename, db_path=None, **kwargs):
    """Get existing book ID or create new. Returns book ID.

    Lookup order: exact filename match, then title_hash fallback.
    """
    existing = get_book_by_filename(filename, db_path)
    if existing:
        return existing["id"]

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
                   category_scores=None, db_path=None):
    """Record a conversion attempt. Returns conversion ID."""
    if isinstance(conversion_flags, dict):
        conversion_flags = json.dumps(conversion_flags)
    if isinstance(category_scores, dict):
        category_scores = json.dumps(category_scores)
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO conversions
               (book_id, iteration, extraction_path, vqa_score,
                vqa_report_path, text_quality_score, fixes_applied,
                fixes_failed, api_input_tokens, api_output_tokens,
                cost_usd, duration_seconds, output_file_path,
                output_file_size, conversion_flags, category_scores)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (book_id, iteration, extraction_path, vqa_score,
             vqa_report_path, text_quality_score, fixes_applied,
             fixes_failed, api_input_tokens, api_output_tokens,
             cost_usd, duration_seconds, output_file_path,
             output_file_size, conversion_flags, category_scores)
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
                       score_after=None, db_path=None):
    """Record an extraction path switch and its outcome."""
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO path_switches
               (book_id, from_path, to_path, source_format,
                issue_categories, score_before, score_after)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (book_id, from_path, to_path, source_format,
             issue_categories, score_before, score_after)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


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

        # Upsert the profile
        conn.execute(
            """INSERT INTO source_profiles
                   (publisher, decade, format, books_processed,
                    avg_initial_score, avg_final_score,
                    avg_iterations_needed, best_extraction_path,
                    common_issues, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
                   books_processed = excluded.books_processed,
                   avg_initial_score = excluded.avg_initial_score,
                   avg_final_score = excluded.avg_final_score,
                   avg_iterations_needed = excluded.avg_iterations_needed,
                   best_extraction_path = excluded.best_extraction_path,
                   common_issues = excluded.common_issues,
                   updated_at = CURRENT_TIMESTAMP""",
            (publisher, decade, format, row["books_processed"],
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
                      min_score=80, db_path=None):
    """Check if a book has already been successfully converted.

    Lookup order:
    1. Exact filename match
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
        cursor = conn.execute(
            """SELECT c.id as conversion_id, b.id as book_id, b.filename,
                      c.vqa_score, c.extraction_path, c.vqa_report_path,
                      c.output_file_path, c.cost_usd, c.created_at
               FROM conversions c
               JOIN books b ON b.id = c.book_id
               WHERE c.book_id = ? AND c.vqa_score >= ?
               ORDER BY c.vqa_score DESC, c.created_at DESC
               LIMIT 1""",
            (book_id, min_score)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_cached_output_path(filename=None, isbn=None, title=None, author=None,
                           min_score=80, db_path=None):
    """Convenience wrapper -- returns just the output file path if a cached
    conversion exists, or None.

    Checks that the output file still exists on disk before returning.
    If the file has been deleted, returns None (cache miss).
    """
    result = get_cached_result(
        filename=filename, isbn=isbn, title=title, author=author,
        min_score=min_score, db_path=db_path
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
# Book Overrides
# ---------------------------------------------------------------------------


def add_book_override(book_id=None, isbn=None, title=None, author=None,
                      chapter_structure=None, extraction_path=None,
                      extraction_notes=None, calibre_options=None,
                      skip_front_pages=None, skip_back_pages=None,
                      db_path=None):
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

    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO book_overrides
               (book_id, isbn, title_hash, chapter_structure,
                extraction_path, extraction_notes, calibre_options,
                skip_front_pages, skip_back_pages)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (book_id, isbn, title_hash, chapters_json,
             extraction_path, extraction_notes, calibre_options,
             skip_front_pages, skip_back_pages)
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
        return result
    finally:
        conn.close()


def update_book_override(override_id, db_path=None, **kwargs):
    """Update fields on an existing override. Only provided kwargs are updated."""
    allowed = {
        'book_id', 'isbn', 'title_hash', 'chapter_structure',
        'extraction_path', 'extraction_notes', 'calibre_options',
        'skip_front_pages', 'skip_back_pages', 'source',
        'submitted_by', 'review_status', 'upvotes'
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    # Serialize chapter_structure if present
    if 'chapter_structure' in updates:
        cs = updates['chapter_structure']
        if cs is not None and not isinstance(cs, str):
            updates['chapter_structure'] = json.dumps(cs)

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
        print(f"No cache hit for: {filename} (min score: {min_score})")
        return

    print(f"Cache HIT: {result['filename']}")
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

    override_id = add_book_override(
        book_id=book_id,
        title=title,
        author=author,
        extraction_path=args.extraction_path,
        extraction_notes=args.notes,
        chapter_structure=chapter_structure,
        skip_front_pages=args.skip_front,
        skip_back_pages=args.skip_back,
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
        "Title - Author.ext"
        "Title - Subtitle - Author.ext"
        "Title.ext"
    """
    stem = Path(filename).stem

    # Remove common suffixes added by the pipeline
    for suffix in ('_visual_qa_report', '_visual_qa_report_LEGACY',
                   '_visual_qa_report_HTML'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]

    parts = stem.rsplit(' - ', 1)
    if len(parts) == 2:
        title = parts[0].strip()
        author = parts[1].strip()
    else:
        title = stem.strip()
        author = None

    return title, author


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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

    ov_show = override_cmds.add_parser(
        'show', help='Show overrides for a book'
    )
    ov_show.add_argument(
        'filename', help='Book filename (exact or partial match)'
    )

    override_cmds.add_parser('list', help='List all book overrides')

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
        'cache': _cmd_cache,
    }

    commands[args.command](args)


if __name__ == '__main__':
    main()
