#!/usr/bin/env python3
r"""
BookDownloader — Download and manage ebook downloads with resume and retry.

Manages downloads from LibGen and Anna's Archive with automatic resume for
interrupted downloads, exponential backoff retry, and format preference logic.

Usage:
    python book_downloader.py download --ids 12345,67890 --format epub
    python book_downloader.py download --ids 12345,67890 --format pdf --output-dir "F:\Books\BookFinder"
    python book_downloader.py download --json results.json
    python book_downloader.py download --list          # show queue status
    python book_downloader.py download --resume        # resume failed downloads
    python book_downloader.py download --stats         # show download statistics

Download queue is persisted in SQLite so you can stop and resume at any time.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_ROOT = r"F:\Books\BookFinder"
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_DELAY = 30  # seconds between retries
DEFAULT_MAX_RETRY_BACKOFF = 300  # max backoff (5 minutes)
DEFAULT_TIMEOUT = 600  # 10 minutes per download
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Known good file extensions for ebooks.
VALID_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw", ".azw3", ".txt", ".djvu"}

LOG = logging.getLogger("book_downloader")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class DownloadDB:
    """SQLite-backed download queue manager."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.Connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    md5 TEXT DEFAULT '',
                    format TEXT NOT NULL,
                    file_size TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    local_path TEXT DEFAULT '',
                    download_url TEXT DEFAULT '',
                    download_source TEXT DEFAULT '',
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    last_error TEXT DEFAULT '',
                    session_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP DEFAULT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS download_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP DEFAULT NULL,
                    total_books INTEGER DEFAULT 0,
                    completed_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running',
                    output_root TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_title TEXT NOT NULL,
                    book_author TEXT NOT NULL,
                    format TEXT NOT NULL,
                    local_path TEXT,
                    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size TEXT DEFAULT '',
                    md5 TEXT DEFAULT ''
                )
            """)
            conn.commit()

    def start_session(self, output_root: str) -> int:
        """Create a new download session. Returns session ID."""
        with sqlite3.Connection(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO download_sessions (output_root) VALUES (?)",
                (output_root,)
            )
            conn.commit()
            return cursor.lastrowid

    def complete_session(self, session_id: int, completed: int, failed: int):
        with sqlite3.Connection(self.db_path) as conn:
            conn.execute("""
                UPDATE download_sessions
                SET completed_at = CURRENT_TIMESTAMP,
                    completed_count = ?,
                    failed_count = ?,
                    status = 'complete'
                WHERE id = ?
            """, (completed, failed, session_id))
            conn.commit()

    def add_book(self, title: str, author: str, format: str,
                 download_url: str = "", md5: str = "",
                 file_size: str = "", source: str = "",
                 session_id: int | None = None) -> int:
        """Add a book to the queue. Returns row ID."""
        with sqlite3.Connection(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO books
                    (title, author, format, download_url, md5, file_size,
                     download_source, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, author, format, download_url, md5, file_size,
                  source, session_id))
            conn.commit()
            return cursor.lastrowid

    def get_pending(self, session_id: int | None = None,
                    limit: int = 100) -> list[dict]:
        """Get pending/download-in-progress books."""
        # EB-356: build the full WHERE clause BEFORE ORDER BY. Previously the
        # session filter was appended after "ORDER BY id", producing
        # "... ORDER BY id AND session_id = ? LIMIT" — invalid filtering that
        # returned rows from every session.
        query = "SELECT * FROM books WHERE status IN ('pending', 'downloading')"
        params: list = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY id"
        query += f" LIMIT {limit}"
        with sqlite3.Connection(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_failed(self, session_id: int | None = None) -> list[dict]:
        """Get books that failed downloading."""
        query = "SELECT * FROM books WHERE status = 'failed'"
        params: list = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        with sqlite3.Connection(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def update_status(self, book_id: int, status: str,
                      local_path: str = "", error: str = ""):
        with sqlite3.Connection(self.db_path) as conn:
            if error:
                conn.execute("""
                    UPDATE books SET status = ?, last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, error, book_id))
            elif local_path:
                conn.execute("""
                    UPDATE books SET status = ?, local_path = ?,
                    updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, local_path, book_id))
            else:
                conn.execute("""
                    UPDATE books SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, book_id))
            conn.commit()

    def increment_retry(self, book_id: int, error: str = ""):
        with sqlite3.Connection(self.db_path) as conn:
            conn.execute("""
                UPDATE books SET
                    retry_count = retry_count + 1,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (error, book_id))
            conn.commit()

    def mark_complete(self, book_id: int, local_path: str,
                      file_size: str = ""):
        with sqlite3.Connection(self.db_path) as conn:
            # EB-356: row_factory required — the history INSERT below indexes
            # the fetched row by name (book["title"]); without it the row is a
            # tuple and the lookup raises TypeError, failing the completion.
            conn.row_factory = sqlite3.Row
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                UPDATE books SET status = 'complete', local_path = ?,
                completed_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (local_path, now, book_id))
            # Also record in history
            book = conn.execute(
                "SELECT title, author, format, md5 FROM books WHERE id = ?",
                (book_id,)
            ).fetchone()
            if book:
                conn.execute("""
                    INSERT INTO download_history
                        (book_title, book_author, format, local_path, file_size)
                    VALUES (?, ?, ?, ?, ?)
                """, (book["title"], book["author"], book["format"],
                      local_path, file_size))
            conn.commit()

    def get_stats(self) -> dict:
        """Return download statistics."""
        with sqlite3.Connection(self.db_path) as conn:
            # EB-356: same row_factory fix as mark_complete — row["c"] below
            # needs name access, not tuple indexing.
            conn.row_factory = sqlite3.Row
            stats: dict = {}
            for status in ("pending", "downloading", "complete", "failed"):
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM books WHERE status = ?",
                    (status,)
                ).fetchone()
                stats[status] = row["c"] if row else 0

            history = conn.execute(
                "SELECT COUNT(*) as c FROM download_history"
            ).fetchone()
            stats["downloaded_total"] = history["c"] if history else 0
            return stats

    def list_books(self, limit: int = 50) -> list[dict]:
        with sqlite3.Connection(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, author, format, status, retry_count, "
                "local_path, created_at FROM books ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------

class BookDownloader:
    """Download books with resume, retry, and state management."""

    def __init__(self, output_root: str = DEFAULT_OUTPUT_ROOT,
                 max_retries: int = DEFAULT_MAX_RETRIES,
                 retry_delay: int = DEFAULT_RETRY_DELAY,
                 max_backoff: int = DEFAULT_MAX_RETRY_BACKOFF,
                 timeout: int = DEFAULT_TIMEOUT,
                 user_agent: str = DEFAULT_USER_AGENT):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_backoff = max_backoff
        self.timeout = timeout
        self.user_agent = user_agent
        self.db = DownloadDB(self.output_root / "state.db")
        self.session: requests.Session | None = None
        self._session_id: int | None = None

    def _get_session(self) -> requests.Session:
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": self.user_agent,
                "Accept": "*/*",
            })
        return self.session

    def start_session(self) -> int:
        """Start a new download session. Call before queuing books."""
        self._session_id = self.db.start_session(str(self.output_root))
        return self._session_id

    def queue_book(self, title: str, author: str, format: str,
                   download_url: str = "", md5: str = "",
                   file_size: str = "", source: str = "") -> int:
        """Queue a book for download."""
        book_id = self.db.add_book(
            title=title, author=author, format=format,
            download_url=download_url, md5=md5,
            file_size=file_size, source=source,
            session_id=self._session_id,
        )
        LOG.info("Queued: %s by %s [%s]", title, author or "(no author)", format)
        return book_id

    def queue_from_results(self, results, session_id: int | None = None):
        """Queue books from BookResult list (from book_finder)."""
        for r in results:
            self.queue_book(
                title=r.title, author=r.author, format=r.format,
                download_url=r.download_url, md5=r.md5,
                file_size=r.file_size, source=r.source,
            )

    def _make_folder(self, title: str, author: str, format: str) -> Path:
        """Create book-specific folder. Returns folder path."""
        author_slug = slugify(author or "unknown")
        title_slug = slugify(title)
        folder_name = f"{author_slug}-{title_slug}"
        folder = self.output_root / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _resolve_filename(self, title: str, format: str,
                          local_path: str = "") -> str:
        """Resolve the final filename for a download."""
        if local_path:
            return local_path
        stem = slugify(title)
        return f"{stem}.{format.lower()}"

    def _find_existing(self, folder: Path, format: str) -> Path | None:
        """Check if correct format already exists in folder."""
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() == f".{format.lower()}":
                LOG.info("Already exists: %s", f)
                return f
        return None

    def download_book(self, book: dict) -> bool:
        """Download a single book. Returns True on success."""
        book_id = book["id"]
        title = book["title"]
        author = book["author"]
        fmt = book["format"]
        download_url = book["download_url"]
        max_retries = book["max_retries"] or self.max_retries

        if not download_url:
            LOG.warning("Book #%d (%s): No download URL — skipping", book_id, title)
            self.db.update_status(book_id, "failed",
                                  error="No download URL available")
            return False

        # Determine folder and path
        folder = self._make_folder(title, author, fmt)
        filename = self._resolve_filename(title, fmt, book["local_path"])
        filepath = folder / filename
        existing = self._find_existing(folder, fmt)

        if existing:
            LOG.info("Skip #%d (%s): already downloaded", book_id, title)
            self.db.mark_complete(book_id, str(existing))
            return True

        part_path = Path(str(filepath) + ".part")

        # Check for resume
        resume_pos = 0
        if part_path.exists():
            resume_pos = part_path.stat().st_size
            LOG.info("Resume #%d (%s): %d bytes already downloaded",
                     book_id, title, resume_pos)

        # Try download
        attempt = book["retry_count"]
        success = False
        for attempt_num in range(attempt, max_retries):
            try:
                session = self._get_session()
                headers = {"Range": f"bytes={resume_pos}-"} if resume_pos > 0 else {}
                LOG.info("Downloading #%d (%s) [attempt %d/%d, resume=%d bytes]",
                         book_id, title, attempt_num + 1, max_retries, resume_pos)

                self.db.update_status(book_id, "downloading")

                resp = session.get(download_url, headers=headers,
                                   timeout=self.timeout, stream=True)
                resp.raise_for_status()

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = resume_pos

                with open(part_path, "ab") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Progress logging
                        if total_size > 0:
                            pct = downloaded / total_size * 100
                            LOG.info("  %.1f%% (%d/%d bytes)", pct, downloaded, total_size)
                        else:
                            if downloaded % (10 * 1024 * 1024) < 8192:  # every ~10MB
                                LOG.info("  Downloaded %d bytes", downloaded)

                # Verify we got something substantial (> 100 bytes)
                if downloaded < 100:
                    raise RuntimeError(f"Download too small: {downloaded} bytes")

                # Rename .part → actual file
                part_path.rename(filepath)
                LOG.info("Downloaded #%d (%s) → %s", book_id, title, filepath)

                # Record completion
                self.db.mark_complete(book_id, str(filepath),
                                      file_size=f"{downloaded} bytes")
                success = True
                resume_pos = 0  # Reset for future
                break

            except requests.RequestException as e:
                LOG.warning("Download #%d (%s) failed (attempt %d/%d): %s",
                            book_id, title, attempt_num + 1, max_retries, e)
                self.db.increment_retry(book_id, str(e))
                attempt += 1

                # Exponential backoff
                if attempt_num < max_retries - 1:
                    wait = min(
                        self.retry_delay * (2 ** (attempt_num - attempt)),
                        self.max_backoff,
                    )
                    wait = max(wait, 5)  # minimum 5 seconds
                    LOG.info("  Waiting %.0f seconds before retry...", wait)
                    time.sleep(wait)
                    resume_pos = part_path.stat().st_size if part_path.exists() else 0

            except Exception as e:
                LOG.error("Unexpected error downloading #%d (%s): %s",
                          book_id, title, e)
                self.db.increment_retry(book_id, str(e))
                attempt += 1

                if attempt_num < max_retries - 1:
                    time.sleep(min(self.retry_delay, self.max_backoff))
                    resume_pos = part_path.stat().st_size if part_path.exists() else 0

        if not success:
            LOG.error("FAILED #%d (%s): %d attempts exhausted",
                      book_id, title, max_retries)
            self.db.update_status(book_id, "failed",
                                  error="Max retries exceeded")
            # Clean up stale .part file
            if part_path.exists():
                try:
                    part_path.unlink()
                except OSError:
                    pass

        return success

    def run(self, limit: int = 100, books: list[dict] | None = None) -> dict:
        """Process the download queue. Returns summary stats.

        EB-356: when ``books`` is provided (e.g. an explicit --ids selection or
        a --json-loaded list), download exactly those; otherwise pull the
        pending queue (capped at ``limit``). Previously run() always re-pulled
        the whole pending queue, so --ids was silently ignored.
        """
        LOG.info("Starting download queue (limit=%d)", limit)
        if books is None:
            books = self.db.get_pending(limit=limit)
        if not books:
            print("No pending downloads.")
            return {"pending": 0, "downloading": 0, "complete": 0, "failed": 0}

        print(f"\nProcessing {len(books)} pending download(s)...\n")

        completed = 0
        failed = 0

        for book in books:
            try:
                if self.download_book(book):
                    completed += 1
                else:
                    failed += 1
            except Exception as e:
                LOG.error("Unexpected error processing #%d: %s", book["id"], e)
                failed += 1

            # Small delay between books
            time.sleep(1)

        # Save session state
        if self._session_id is not None:
            self.db.complete_session(self._session_id, completed, failed)

        print(f"\n{'='*50}")
        print(f"  Completed: {completed}")
        print(f"  Failed:    {failed}")
        print(f"{'='*50}\n")

        return {"completed": completed, "failed": failed}

    def resume_failed(self) -> dict:
        """Resume all failed downloads."""
        failed = self.db.get_failed(session_id=self._session_id)
        if not failed:
            print("No failed downloads to resume.")
            return {}

        print(f"Resuming {len(failed)} failed download(s)...\n")

        completed = 0
        still_failed = 0

        for book in failed:
            try:
                if self.download_book(book):
                    completed += 1
                else:
                    still_failed += 1
            except Exception as e:
                LOG.error("Unexpected error resuming #%d: %s", book["id"], e)
                still_failed += 1
            time.sleep(1)

        print(f"\n{'='*50}")
        print(f"  Resumed successfully: {completed}")
        print(f"  Still failed:         {still_failed}")
        print(f"{'='*50}\n")

        return {"completed": completed, "still_failed": still_failed}

    def show_queue(self, limit: int = 50):
        """Show current download queue status."""
        books = self.db.list_books(limit=limit)
        stats = self.db.get_stats()

        if not books:
            print("Download queue is empty.")
            return

        # Header
        print(f"\n{'ID':>4}  {'Title':<40}  {'Author':<25}  "
              f"{'Format':<8}  {'Status':<12}  {'Retries':<7}")
        print("-" * 100)

        for b in books:
            title_short = b["title"][:40]
            author_short = (b["author"] or "?")[:25]
            status = b["status"] or "?"
            retries = b["retry_count"] or 0
            fmt = b["format"] or "?"

            # Add indicator for local path
            path_hint = ""
            if b["local_path"]:
                path_hint = f"  → {Path(b['local_path']).name}"

            print(f"{b['id']:>4}  {title_short:<40}  {author_short:<25}  "
                  f"{fmt:<8}  {status:<12}  {retries:<7}{path_hint}")

        print("-" * 100)
        print(f"\nStatus summary:")
        for k, v in stats.items():
            if v > 0:
                print(f"  {k}: {v}")
        print()

    def show_stats(self):
        """Show overall download statistics."""
        stats = self.db.get_stats()
        print("\nDownload Statistics")
        print("=" * 40)
        for key, count in stats.items():
            print(f"  {key}: {count}")
        print("=" * 40)

    def show_history(self, limit: int = 20):
        """Show recently downloaded books."""
        with sqlite3.Connection(self.db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT book_title, book_author, format, local_path,
                       downloaded_at, file_size
                FROM download_history
                ORDER BY downloaded_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

        if not rows:
            print("No download history.")
            return

        print(f"\n{'Downloaded':<22}  {'Title':<35}  "
              f"{'Author':<20}  {'Format':<8}  {'Size':<12}")
        print("-" * 110)

        for r in rows:
            dt = r["downloaded_at"] or "?"
            title = (r["book_title"] or "?")[:35]
            author = (r["book_author"] or "?")[:20]
            fmt = r["format"] or "?"
            size = r["file_size"] or "?"
            print(f"  {dt:<22}  {title:<35}  {author:<20}  "
                  f"{fmt:<8}  {size:<12}")
        print()

    def cleanup(self, keep_days: int = 30):
        """Remove completed books older than keep_days from active queue."""
        with sqlite3.Connection(self.db.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM books
                WHERE status = 'complete'
                AND completed_at < datetime('now', ?)
            """, (f"-{keep_days} days",))
            deleted = cursor.rowcount
            conn.commit()

        if deleted:
            print(f"Cleaned up {deleted} completed book(s) older than {keep_days} days.")
        else:
            print(f"No completed books older than {keep_days} days found.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Create a filesystem-safe slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-_")
    return text[:80] or "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and manage ebook downloads with resume/retry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s download --ids 12345,67890 --format epub
  %(prog)s download --json search_results.json
  %(prog)s download --list
  %(prog)s download --resume
  %(prog)s download --stats
  %(prog)s download --history --limit 20
        """,
    )

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # Download command
    dl = sub.add_parser("download", help="Download queued books")
    dl.add_argument("--ids", "-i",
                    help="Comma-separated book IDs from search results")
    dl.add_argument("--json", "-j",
                    help="JSON file with book results to download")
    dl.add_argument("--format", "-f", default="epub",
                    choices=["epub", "pdf", "mobi", "azw3", "txt", "djvu"],
                    help="Preferred format (default: epub)")
    dl.add_argument("--output-dir", "-o", default=DEFAULT_OUTPUT_ROOT,
                    help=f"Download root directory (default: {DEFAULT_OUTPUT_ROOT})")
    dl.add_argument("--max-retries", "-r", type=int, default=DEFAULT_MAX_RETRIES,
                    help=f"Max download retries (default: {DEFAULT_MAX_RETRIES})")
    dl.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT,
                    help=f"Download timeout in seconds (default: {DEFAULT_TIMEOUT})")
    dl.add_argument("--dry-run", action="store_true",
                    help="Show what would be downloaded without downloading")
    dl.add_argument("--list", action="store_true",
                    help="Show current download queue")
    dl.add_argument("--resume", action="store_true",
                    help="Resume failed downloads")
    dl.add_argument("--stats", action="store_true",
                    help="Show download statistics")
    dl.add_argument("--history", action="store_true",
                    help="Show download history")
    dl.add_argument("--limit", type=int, default=100,
                    help="Max downloads to process (default: 100)")

    # Cleanup command
    sub.add_parser("cleanup", help="Remove old completed downloads from queue")

    # Stats command
    sub.add_parser("stats", help="Show download statistics")

    # History command
    hist = sub.add_parser("history", help="Show download history")
    hist.add_argument("--limit", type=int, default=20)

    return parser


def parse_ids_string(ids_str: str) -> list[int]:
    """Parse comma-separated IDs string into list of ints."""
    return [int(x.strip()) for x in ids_str.split(",") if x.strip()]


def load_books_from_json(json_path: str) -> list[dict]:
    """Load book data from a JSON file (output from book_finder)."""
    path = Path(json_path)
    if not path.exists():
        print(f"Error: File not found: {json_path}", file=sys.stderr)
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Support both list of results and nested structure
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        # Could be {"results": [...]} or similar
        for key in ("results", "books", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return []

    return []


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Setup logging
    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.command == "download":
        downloader = BookDownloader(
            output_root=args.output_dir,
            max_retries=args.max_retries,
            timeout=args.timeout,
        )

        if args.list:
            downloader.show_queue()
            return 0

        if args.resume:
            downloader.resume_failed()
            return 0

        if args.stats:
            downloader.show_stats()
            return 0

        if args.history:
            downloader.show_history(limit=args.limit)
            return 0

        # Load books to download
        books_to_download: list[dict] = []

        if args.ids:
            # Load books by ID from DB
            book_ids = parse_ids_string(args.ids)
            with sqlite3.Connection(downloader.db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                placeholders = ",".join("?" for _ in book_ids)
                rows = conn.execute(
                    f"SELECT * FROM books WHERE id IN ({placeholders}) AND status IN ('pending', 'failed')",
                    book_ids
                ).fetchall()
                books_to_download = [dict(r) for r in rows]
                if not books_to_download:
                    print(f"No pending/failed books found with IDs: {args.ids}")
                    print("Use --list to see available books.")
                    return 1

        elif args.json:
            raw = load_books_from_json(args.json)
            if not raw:
                print(f"No books found in {args.json}")
                return 1

            downloader.start_session()

            for book in raw:
                # Normalize fields from BookResult format
                title = book.get("title", "Unknown Title")
                author = book.get("author", "")
                fmt = book.get("format", args.format)
                download_url = book.get("download_url", "")
                md5 = book.get("md5", "")
                file_size = book.get("file_size", "")
                source = book.get("source", "")

                if not fmt:
                    fmt = args.format  # Use default format

                downloader.queue_book(
                    title=title, author=author, format=fmt,
                    download_url=download_url, md5=md5,
                    file_size=file_size, source=source,
                )

            books_to_download = downloader.db.get_pending()

        else:
            print("Error: Provide --ids, --json, or --list")
            return 1

        if args.dry_run:
            print(f"\nDry run — {len(books_to_download)} book(s) to download:\n")
            for b in books_to_download:
                print(f"  #{b['id']} {b['title']} by {b['author']} [{b['format']}]")
                print(f"    URL: {b['download_url']}")
            return 0

        # Run downloads — EB-356: pass the explicit selection (--ids / --json)
        # so run() downloads exactly those books instead of re-pulling the
        # entire pending queue.
        result = downloader.run(limit=args.limit, books=books_to_download)
        return 0

    elif args.command == "cleanup":
        db = DownloadDB(Path(DEFAULT_OUTPUT_ROOT) / "state.db")
        db.cleanup(keep_days=30)
        return 0

    elif args.command == "stats":
        db = DownloadDB(Path(DEFAULT_OUTPUT_ROOT) / "state.db")
        db.show_stats()
        return 0

    elif args.command == "history":
        db = DownloadDB(Path(DEFAULT_OUTPUT_ROOT) / "state.db")
        db.show_history(limit=getattr(args, 'limit', 20))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
