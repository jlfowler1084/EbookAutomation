#!/usr/bin/env python3
"""
BookFinder — Search Library Genesis and Anna's Archive for ebooks.

Searches LibGen first (stable, structured API), falls back to Anna's Archive
(meta-indexer, catches LibGen-missing books). Returns ranked results with
format preference scoring (EPUB > PDF > MOBI > AZW3).

Usage:
    python book_finder.py search "Atomic Habits" --author "James Clear"
    python book_finder.py search "Deep Work" --sources libgen anna --top 10
    python book_finder.py search --file book-list.txt
    python book_finder.py search "Title" --format epub --limit 5

Output: JSON to stdout (parseable) or formatted table to terminal.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Default sources in order of preference (searched sequentially).
DEFAULT_SOURCES = ["libgen", "anna"]

# Format preference order — higher = better quality for TTS pipeline.
FORMAT_PREFERENCE = ["epub", "pdf", "mobi", "azw3", "txt", "djvu"]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Timeout per request (seconds).
REQUEST_TIMEOUT = 30

# Delay between requests (seconds) — be polite.
REQUEST_DELAY = 2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BookResult:
    """A single book search result."""
    title: str
    author: str
    md5: str = ""
    format: str = ""
    file_size: str = ""
    year: str = ""
    publisher: str = ""
    language: str = ""
    extension: str = ""
    source: str = ""  # "libgen" or "anna"
    download_url: str = ""  # Primary download link
    score: float = 0.0  # Ranking score
    match_type: str = ""  # "title_exact", "title_partial", "author_match"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LOG = logging.getLogger("book_finder")


def slugify(text: str) -> str:
    """Create a filesystem-safe slug from text."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-_")
    return text[:80] or "unknown"


def format_file_size(size_str: str) -> str:
    """Return human-readable file size. Already formatted by source."""
    if not size_str:
        return ""
    return size_str


def score_format(fmt: str) -> int:
    """Return score for format (higher = better). EPUB=10, PDF=8, etc."""
    fmt_lower = fmt.lower()
    for i, pref in enumerate(FORMAT_PREFERENCE):
        if fmt_lower == pref:
            return len(FORMAT_PREFERENCE) - i * 2  # 10, 8, 6, 4, 2, 0
    return 0  # Unknown format


def score_match(title: str, query_title: str) -> float:
    """Score how well title matches the query title. 1.0 = exact."""
    title_lower = title.lower().strip()
    query_lower = query_title.lower().strip()

    # Clean common suffixes like " – Author" or " by Author"
    title_clean = re.sub(r'\s*[-–—]\s*(by\s+)?\S+', '', title_lower)
    query_clean = re.sub(r'\s*[-–—]\s*(by\s+)?\S+', '', query_lower)

    if title_clean == query_clean:
        return 1.0
    if query_lower in title_lower or title_lower in query_lower:
        return 0.8
    # Word overlap
    title_words = set(title_lower.split())
    query_words = set(query_lower.split())
    if query_words and title_words:
        overlap = len(title_words & query_words) / len(query_words)
        return overlap * 0.7
    return 0.0


def score_author(author: str, query_author: str) -> float:
    """Score how well author matches the query author. 1.0 = exact."""
    if not query_author or not author:
        return 0.0
    author_lower = author.lower().strip()
    query_lower = query_author.lower().strip()
    if query_lower in author_lower or author_lower in query_lower:
        return 0.9
    # Check if last name from query appears in author string
    query_parts = query_lower.split()
    if len(query_parts) >= 2:
        last_name = query_parts[-1]
        if last_name in author_lower:
            return 0.6
    return 0.0


def rank_results(results: list[BookResult], query_title: str,
                 query_author: str, format_pref: str | None) -> list[BookResult]:
    """Rank results by relevance and format preference."""
    scored = []
    for r in results:
        title_score = score_match(r.title, query_title)
        author_score = score_author(r.author, query_author)
        format_score = score_format(r.format) if r.format else 0
        if format_pref:
            format_bonus = 5 if r.format.lower() == format_pref.lower() else 0
        else:
            format_bonus = 0

        # Determine match type
        if title_score >= 0.95 and author_score >= 0.8:
            match_type = "title_exact_author_match"
        elif title_score >= 0.95:
            match_type = "title_exact"
        elif title_score >= 0.8:
            match_type = "title_partial"
        elif author_score > 0:
            match_type = "author_match"
        else:
            match_type = "low_match"

        # Combined score: title weight 40%, author 30%, format 20%, base 10%
        combined = (
            title_score * 40 +
            author_score * 30 +
            format_score * 0.2 +
            format_bonus +
            10
        )

        r.score = combined
        r.match_type = match_type
        scored.append(r)

    scored.sort(key=lambda x: (x.score, x.author), reverse=True)
    return scored


def deduplicate(results: list[BookResult]) -> list[BookResult]:
    """Remove duplicates by MD5 hash, keeping highest-scored entry."""
    seen_md5: dict[str, BookResult] = {}
    for r in results:
        key = r.md5 if r.md5 else f"{r.title.lower()}|{r.author.lower()}"
        if key not in seen_md5 or r.score > seen_md5[key].score:
            seen_md5[key] = r
    return list(seen_md5.values())


# ---------------------------------------------------------------------------
# LibGen Search
# ---------------------------------------------------------------------------

LIBGEN_SEARCH_URL = "https://libgen.is/search.php"
LIBGEN_DIARY_URL = "https://libgen.is/diary.php"  # for session cookie


class LibGenSearchError(Exception):
    pass


def search_libgen(title: str, author: str = "",
                  column: str = "any", top: int = 30,
                  format_pref: str | None = None) -> list[BookResult]:
    """Search Library Genesis and return BookResults.

    Args:
        title: Book title to search for
        author: Author name (optional)
        column: Search column — "title", "author", or "any"
        top: Maximum number of results
        format_pref: Preferred format string (for filtering)

    Returns:
        List of BookResult instances, ranked by relevance
    """
    params: dict[str, str] = {
        "req": title if not author else f"{title} {author}",
        "column": column,
        "res": str(top * 2),  # Request more to allow filtering
        "phrase": "0",
    }

    headers = {"User-Agent": DEFAULT_USER_AGENT}

    LOG.info("Searching LibGen: %s (author=%s, column=%s)", title, author or "(none)", column)

    try:
        # Get diary page first for cookie/session
        requests.get(LIBGEN_DIARY_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        pass  # Non-fatal; libgen may block but search still works

    time.sleep(1)

    try:
        resp = requests.get(LIBGEN_SEARCH_URL, params=params, headers=headers,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise LibGenSearchError(f"LibGen search failed: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[BookResult] = []

    # Find the results table
    table = soup.find("table")
    if not table:
        LOG.warning("LibGen search returned no table — possible block or changed schema")
        return results

    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")

    # Skip header row
    for i, row in enumerate(rows):
        if i == 0 and row.find("th"):
            continue  # Skip header
        if not row.find("td"):
            continue  # Not a data row

        tds = row.find_all("td")
        if len(tds) < 8:
            continue  # Malformed row

        # Parse columns
        title_cell = tds[0].find("a")
        title = title_cell.get_text().strip() if title_cell else tds[0].get_text().strip()

        author_cell = tds[1]
        author_text = author_cell.get_text().strip()

        publisher_cell = tds[2]
        publisher = publisher_cell.get_text().strip()

        year_cell = tds[3]
        year = year_cell.get_text().strip()

        lang_cell = tds[4]
        language = lang_cell.get_text().strip()

        size_cell = tds[5]
        size = size_cell.get_text().strip()

        ext_cell = tds[6]
        extension = ext_cell.get_text().strip().lower()

        md5_cell = tds[7]
        md5_text = md5_cell.get_text().strip()

        # Parse download links from column 8+
        download_links: list[str] = []
        download_cell = tds[8] if len(tds) > 8 else None
        if download_cell:
            for a in download_cell.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    download_links.append(href)
                elif href.startswith("/"):
                    download_links.append(f"https://libgen.is{href}")

        if not title:
            continue

        result = BookResult(
            title=title,
            author=author_text,
            md5=md5_text,
            format=extension,
            file_size=size,
            year=year,
            publisher=publisher,
            language=language,
            extension=extension,
            source="libgen",
            download_url=download_links[0] if download_links else "",
        )
        results.append(result)

    LOG.info("LibGen returned %d raw results for '%s'", len(results), title)

    # Filter by format preference if requested
    if format_pref:
        results = [r for r in results
                   if r.format.lower() == format_pref.lower()
                   or r.format.lower() in FORMAT_PREFERENCE
                   or not r.format]
        if results and len(results) < 3:
            # Be lenient — include format-agnostic results too
            LOG.info("Format-filtered LibGen results low (%d), broadening filter",
                     len(results))

    return results


# ---------------------------------------------------------------------------
# Anna's Archive Search
# ---------------------------------------------------------------------------

ANNA_SEARCH_URL = "https://annasarchive.org/search"


class AnnasArchiveSearchError(Exception):
    pass


def search_annas_archive(title: str, author: str = "",
                         top: int = 30,
                         format_pref: str | None = None) -> list[BookResult]:
    """Search Anna's Archive and return BookResults.

    Anna's Archive is a meta-search engine. It aggregates from LibGen,
    Z-Library, and other sources. Results include metadata like page count,
    file count, and available download sources.

    Args:
        title: Book title to search for
        author: Author name (optional)
        top: Maximum number of results
        format_pref: Preferred format string (for filtering)

    Returns:
        List of BookResult instances, ranked by relevance
    """
    query = title if not author else f"{title} {author}"
    params = {"q": query, "page": "1"}

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    LOG.info("Searching Anna's Archive: %s (author=%s)", title, author or "(none)")

    try:
        resp = requests.get(ANNA_SEARCH_URL, params=params, headers=headers,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise AnnasArchiveSearchError(f"Anna's Archive search failed: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[BookResult] = []

    # Anna's Archive uses a table-based layout for search results
    # Look for the search results table
    table = soup.find("table")
    if not table:
        # Try div-based layout (AA has changed UI multiple times)
        results = _parse_annas_div_layout(soup, query)
    else:
        results = _parse_annas_table_layout(soup, query)

    LOG.info("Anna's Archive returned %d raw results for '%s'", len(results), query)

    return results


def _parse_annas_table_layout(soup: BeautifulSoup, query: str) -> list[BookResult]:
    """Parse Anna's Archive results from table layout."""
    results: list[BookResult] = []
    tbody = soup.find("tbody")
    rows = tbody.find_all("tr") if tbody else soup.find_all("tr")

    for i, row in enumerate(rows):
        if i == 0 and row.find("th"):
            continue
        if not row.find("td"):
            continue

        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        # Try to find title link
        title_link = row.find("a", href=True)
        title = title_link.get_text().strip() if title_link else ""
        title_url = title_link["href"] if title_link else ""

        if not title:
            continue

        # Try to find author
        author_text = ""
        author_cells = row.find_all("td")
        if len(author_cells) >= 2:
            author_text = author_cells[1].get_text().strip()

        # Find format and size
        fmt = ""
        size = ""
        for td in tds:
            text = td.get_text().strip().lower()
            if text in FORMAT_PREFERENCE:
                fmt = text
                break
            # Check for size-like patterns
            if re.search(r'\d+\s*(KB|MB|GB)', text):
                size = td.get_text().strip()

        # Try to find download links
        download_links: list[str] = []
        for a in row.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                download_links.append(href)

        result = BookResult(
            title=title,
            author=author_text,
            format=fmt,
            file_size=size,
            source="anna",
            download_url=download_links[0] if download_links else "",
            extra={"title_url": title_url},
        )
        results.append(result)

    return results


def _parse_annas_div_layout(soup: BeautifulSoup, query: str) -> list[BookResult]:
    """Parse Anna's Archive results from div-based layout (newer UI)."""
    results: list[BookResult] = []

    # Look for result cards/containers
    containers = soup.find_all("div", class_=re.compile(r"result|book|card|item"))
    if not containers:
        containers = soup.find_all("article")
    if not containers:
        # Last resort: look for any clickable links that look like book titles
        containers = [soup]  # parse everything

    for container in containers:
        title_link = container.find("a", href=True)
        if not title_link:
            continue

        title = title_link.get_text().strip()
        if len(title) < 3 or len(title) > 200:
            continue  # Too short/long = not a book title

        # Author might be in a span or sibling element
        author_text = ""
        author_span = container.find("span", class_=re.compile(r"author|writer"))
        if author_span:
            author_text = author_span.get_text().strip()
        else:
            # Try next sibling or parent
            parent = title_link.parent
            if parent:
                for sib in parent.find_next_siblings():
                    text = sib.get_text().strip()
                    if text and len(text) < 100:
                        author_text = text
                        break

        # Format and size
        fmt = ""
        size = ""
        for span in container.find_all(["span", "div"]):
            text = span.get_text().strip().lower()
            if text in FORMAT_PREFERENCE:
                fmt = text
                break

        download_links: list[str] = []
        for a in container.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                download_links.append(href)

        result = BookResult(
            title=title,
            author=author_text,
            format=fmt,
            source="anna",
            download_url=download_links[0] if download_links else "",
            extra={"title_url": title_link["href"]},
        )
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

def search_books(title: str, author: str = "",
                 sources: list[str] | None = None,
                 top: int = 10,
                 format_pref: str | None = None,
                 column: str = "any") -> list[BookResult]:
    """Search for books across configured sources.

    Searches LibGen first, falls back to Anna's Archive if no good matches
    found. Returns ranked results.

    Args:
        title: Book title to search for
        author: Author name (optional)
        sources: Which sources to search ["libgen", "anna"]. Defaults to all.
        top: Maximum results to return
        format_pref: Preferred format (e.g., "epub", "pdf")
        column: LibGen search column ("title", "author", "any")

    Returns:
        List of BookResult instances, ranked by relevance
    """
    if sources is None:
        sources = list(DEFAULT_SOURCES)

    all_results: list[BookResult] = []

    # Search LibGen first
    if "libgen" in sources:
        try:
            libgen_results = search_libgen(title, author, column=column,
                                           top=top, format_pref=format_pref)
            all_results.extend(libgen_results)
        except LibGenSearchError as e:
            LOG.warning("LibGen search failed: %s", e)

    # Determine if we need to search Anna's Archive
    search_annas = False
    if all_results:
        # Check if we have good matches
        best_score = all_results[0].score if all_results else 0
        if best_score < 30:  # Low match score — try AA too
            search_annas = True
    else:
        search_annas = True

    if "anna" in sources and search_annas:
        time.sleep(REQUEST_DELAY)  # Be polite between sources
        try:
            anna_results = search_annas_archive(title, author, top=top,
                                                format_pref=format_pref)
            all_results.extend(anna_results)
        except AnnasArchiveSearchError as e:
            LOG.warning("Anna's Archive search failed: %s", e)

    # Deduplicate and rank
    if all_results:
        all_results = deduplicate(all_results)
        all_results = rank_results(all_results, title, author, format_pref)

    return all_results[:top]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search Library Genesis and Anna's Archive for ebooks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s search "Atomic Habits" --author "James Clear"
  %(prog)s search "Deep Work" --sources libgen anna --top 10
  %(prog)s search "The Name of the Wind" --format epub
  %(prog)s search --file book-list.txt  (one title per line)

Output:
  Results are printed as a formatted table to the terminal, and also
  emitted as JSON to stdout when --json is used.
        """,
    )

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # Search command
    search = sub.add_parser("search", help="Search for books")
    search.add_argument("title", nargs="?", help="Book title to search for")
    search.add_argument("--author", "-a", default="", help="Author name")
    search.add_argument("--sources", "-s", nargs="+",
                        choices=["libgen", "anna"],
                        default=DEFAULT_SOURCES,
                        help="Sources to search (default: libgen anna)")
    search.add_argument("--top", "-n", type=int, default=10,
                        help="Max results per source (default: 10)")
    search.add_argument("--format", "-f", default=None,
                        choices=FORMAT_PREFERENCE,
                        help="Preferred format (default: any)")
    search.add_argument("--file", "-F", help="File containing titles to search (one per line)")
    search.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    search.add_argument("--column", "-c", default="any",
                        choices=["title", "author", "any"],
                        help="Search column for LibGen (default: any)")

    return parser


def format_table(results: list[BookResult]) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "No results found."

    # Column widths
    w_title = max(40, min(60, max((len(r.title) for r in results), default=40)))
    w_author = max(20, min(40, max((len(r.author) for r in results), default=20)))
    w_format = 8
    w_size = 12
    w_source = 8

    header = (
        f"{'#':>3}  {'Title':<{w_title}}  "
        f"{'Author':<{w_author}}  "
        f"{'Format':<{w_format}}  {'Size':<{w_size}}  {'Source':<{w_source}}"
    )
    sep = "-" * len(header)

    lines = [sep, header, sep]

    for i, r in enumerate(results, 1):
        title_short = r.title[:w_title - 3] + "..." if len(r.title) > w_title else r.title
        author_short = r.author[:w_author - 3] + "..." if len(r.author) > w_author else r.author
        fmt = r.format.upper() if r.format else "?"
        size = r.file_size or "?"
        source = "LG" if r.source == "libgen" else "AA"

        line = (
            f"{i:>3}  {title_short:<{w_title}}  "
            f"{author_short:<{w_author}}  "
            f"{fmt:<{w_format}}  {size:<{w_size}}  {source:<{w_source}}"
        )
        lines.append(line)

    lines.append(sep)
    lines.append(f"\n{len(results)} result(s) found.")
    return "\n".join(lines)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.command == "search":
        if not args.title and not args.file:
            print("Error: Provide a title or use --file", file=sys.stderr)
            return 1

        if args.file:
            # Read titles from file
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"Error: File not found: {args.file}", file=sys.stderr)
                return 1
            titles = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines()
                      if line.strip() and not line.startswith("#")]
            if not titles:
                print(f"Error: No titles found in {args.file}", file=sys.stderr)
                return 1

            print(f"Searching {len(titles)} title(s) from {file_path}...")
            all_results: list[BookResult] = []
            for title in titles:
                results = search_books(title, format_pref=args.format,
                                       sources=args.sources, top=args.top)
                all_results.extend(results)
                time.sleep(REQUEST_DELAY)  # Be polite

            print(f"\nFound {len(all_results)} result(s) total.\n")
            table = format_table(all_results)
            print(table)

            if args.json:
                print("\n--- JSON START ---")
                print(json.dumps([r.to_dict() for r in all_results], indent=2))
                print("--- JSON END ---")
        else:
            # Single title search
            results = search_books(args.title, author=args.author,
                                   format_pref=args.format,
                                   sources=args.sources,
                                   top=args.top,
                                   column=args.column)

            if not results:
                print("No results found.")
            else:
                print(f"\nSearch: '{args.title}'" +
                      (f" by {args.author}" if args.author else ""))
                table = format_table(results)
                print(table)

            if args.json:
                print("\n--- JSON START ---")
                print(json.dumps([r.to_dict() for r in results], indent=2))
                print("--- JSON END ---")

    return 0


if __name__ == "__main__":
    sys.exit(main())
