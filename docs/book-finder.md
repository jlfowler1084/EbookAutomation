# BookFinder — Ebook Search & Download Tool

## Overview

A search/download layer that sits **upstream** of the EbookAutomation pipeline. Searches **Library Genesis** first (stable, structured API), falls back to **Anna's Archive** (meta-indexer that catches LibGen-missing books), and downloads with **format preference** (EPUB > PDF) and **automatic resume/retry** for interrupted downloads.

**Output**: `F:\Books\BookFinder\` — ready for `Invoke-EbookPipeline`

## What's been built

| File | Purpose |
|---|---|
| `tools/book_finder.py` | Search LibGen → fallback AA → ranked results (CLI + library) |
| `tools/book_downloader.py` | Download queue with resume, retry, SQLite state DB |
| `module\EbookAutomation.psm1` | `Invoke-EbookBookSearch`, `Invoke-EbookBookDownload`, `Invoke-EbookBookDownloadFromList` |
| `config\settings.json` | BookFinder config section (output root, formats, retry settings) |

## Quick Reference

### PowerShell (preferred)

```powershell
# Import module
Import-Module .\module\EbookAutomation.psm1

# Search a single book (LibGen first, AA fallback)
Invoke-EbookBookSearch -Title "Atomic Habits" -Author "James Clear"

# Batch search
Invoke-EbookBookSearch -Titles @("Book One", "Book Two", "Book Three") -Format epub

# Search → download pipeline
Invoke-EbookBookSearch -Title "The Name of the Wind" -Format epub |
    Invoke-EbookBookDownload -Format epub

# Search → download with dry run
Invoke-EbookBookSearch -Title "Deep Work" -Format epub |
    Invoke-EbookBookDownload -Format epub -DryRun

# Resume failed downloads
Invoke-EbookBookDownload -Resume

# View queue / stats
Invoke-EbookBookDownload -List
Invoke-EbookBookDownload -Stats

# Download from a text file of titles (one per line)
Get-Content "F:\Books\wishlist.txt" |
    Invoke-EbookBookDownloadFromList -FilePath "F:\Books\wishlist.txt" -Format epub

# Process downloaded books through the TTS pipeline
Get-ChildItem "F:\Books\BookFinder\*" -Recurse -Include *.epub,*.pdf |
    Invoke-EbookPipeline
```

### Python CLI

```bash
# Search
python tools\book_finder.py search "Atomic Habits" --author "James Clear"
python tools\book_finder.py search "Atomic Habits" --sources libgen anna --top 10
python tools\book_finder.py search --file book-list.txt

# Download
python tools\book_downloader.py download --json results.json --format epub
python tools\book_downloader.py download --ids 12345,67890 --format epub
python tools\book_downloader.py download --list
python tools\book_downloader.py download --resume
python tools\book_downloader.py download --stats
python tools\book_downloader.py download --history

# Dry run
python tools\book_downloader.py download --json results.json --dry-run
```

### Python Library

```python
from tools.book_finder import search_books, BookResult
from tools.book_downloader import BookDownloader

# Search
results = search_books("Atomic Habits", sources=["libgen", "anna"], top=5)

# Download
manager = BookDownloader(output_root=r"F:\Books\BookFinder")
manager.start_session()
manager.queue_from_results(results)
manager.run()  # starts download queue with resume/retry
```

## Directory Layout

```
tools/
  book_finder.py          # Search engine: LibGen + Anna's Archive
  book_downloader.py      # Download queue with resume/retry
F:\Books\
  BookFinder\             # Download root (configured in settings.json)
    state.db              # SQLite: download queue, progress, history
    atomic-habits-james-clear\
      atomic-habits-james-clear.epub
    deep-work-cal-newport\
      deep-work-cal-newport.pdf       # PDF fallback (no EPUB available)
```

## Search Architecture

```
search_books(title, author?, sources, format_pref?)
    │
    ├── 1. LibGen search (stable HTML table)
    │     └── Parse table columns: Title, Author, Publisher, Year, Language, Size, Extension, MD5, Download
    │     └── Deduplicate by MD5 hash
    │
    ├── 2. If no good match → Anna's Archive search (meta-indexer)
    │     └── Try table layout first, fall back to div layout
    │     └── Deduplicate by title+author similarity
    │
    └── 3. Rank & filter
          └── Score: title match (40%), author match (30%), format pref (20%), base (10%)
          └── Format preference bonus: EPUB=10, PDF=8, MOBI=6, AZW3=4, TXT=2, DJVU=0
          └── Return top N results
```

### LibGen Search Details

**Endpoint**: `https://libgen.is/search.php`

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `req` | Search string | required | URL-encoded |
| `column` | `title`, `author`, `any` | `any` | Search scope |
| `res` | Results count | `100` (top*2) | Max results fetched |
| `phrase` | `0` or `1` | `0` | Exact phrase matching |

**Table columns** (in order, td indices):

| Index | Field | Notes |
|---|---|---|
| 0 | `Title` | Link text; may contain " – Author" suffix |
| 1 | `Author` | Author name(s) |
| 2 | `Publisher` | Publisher name (often empty) |
| 3 | `Year` | Publication year |
| 4 | `Language` | Language code (usually `en`) |
| 5 | `Size` | File size in bytes (e.g., "5 MB", "120 kB") |
| 6 | `Extension` | Format: `epub`, `pdf`, `mobi`, `djvu`, etc. |
| 7 | `MD5` | File hash (dedup key) |
| 8+ | Download links | Multiple mirror URLs in `<a href="...">` elements |

**Download links**: The "Download" column contains multiple `<a>` elements, each pointing to a different mirror. They typically point to `http://librarygenius.ru/download.php?md5=HASH` or similar mirror URLs. First link is used as primary.

**Rate limiting**: None known. Add 1-2 second delays between requests.

**Gotcha**: The table may contain multiple entries for the same book (different editions, formats). Deduplicate by MD5 hash, keeping highest-scored entry.

### Anna's Archive Search Details

**Endpoint**: `https://annasarchive.org/search`

| Parameter | Values | Default | Notes |
|---|---|---|---|
| `q` | Search query | required | URL-encoded |

Anna's Archive is a meta-search engine aggregating from LibGen, Z-Library, and other sources.

**Layout fallbacks**:
1. **Table layout** (primary) — parse `<table><tbody><tr><td>...` structure
2. **Div layout** (fallback) — parse `<div>` containers with class attributes

**Gotcha**: AA has no stable API. Layout may change without notice. The code tries table layout first, falls back to div layout. Results are deduplicated by title+author similarity (no MD5 in AA results).

**Rate limiting**: AA is slower and more prone to blocking. Add 2-3 second delays between requests.

## Download Behavior

### Queue Processing

1. **Create book folder**: `F:\Books\BookFinder\{author_slug}-{title_slug}\`
2. **Check for existing file**: Skip if correct format already exists locally
3. **Start download**: Save to `.part` file while downloading
4. **Resume support**: If `.part` exists, use HTTP `Range` header to resume
5. **Rename on complete**: `.part` → actual filename
6. **Retry logic**: On failure, exponential backoff (30s → 60s → 120s → 240s → 300s), max 5 retries
7. **Process one at a time**: No parallel downloads — these sources don't handle it well

### SQLite State DB

Location: `F:\Books\BookFinder\state.db`

**Tables**:

```sql
CREATE TABLE books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    md5 TEXT DEFAULT '',
    format TEXT NOT NULL,
    file_size TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',        -- pending, downloading, complete, failed
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
);

CREATE TABLE download_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP DEFAULT NULL,
    total_books INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',         -- running, paused, complete, failed
    output_root TEXT DEFAULT ''
);

CREATE TABLE download_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_title TEXT NOT NULL,
    book_author TEXT NOT NULL,
    format TEXT NOT NULL,
    local_path TEXT,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_size TEXT DEFAULT '',
    md5 TEXT DEFAULT ''
);
```

### Configuration

Stored in `config\settings.json` under `"BookFinder"` key:

```json
{
  "BookFinder": {
    "output_root": "F:\\Books\\BookFinder",
    "default_format": "epub",
    "format_preference": ["epub", "pdf", "mobi", "azw3", "txt", "djvu"],
    "max_retries": 5,
    "retry_delay_seconds": 30,
    "max_retry_backoff_seconds": 300,
    "timeout_seconds": 600
  }
}
```

| Setting | Default | Description |
|---|---|---|
| `output_root` | `F:\Books\BookFinder` | Download destination root |
| `default_format` | `epub` | Preferred download format |
| `format_preference` | `[epub, pdf, mobi, azw3, txt, djvu]` | Format priority for ranking |
| `max_retries` | `5` | Max retries per download |
| `retry_delay_seconds` | `30` | Base delay between retries |
| `max_retry_backoff_seconds` | `300` | Maximum backoff (5 min) |
| `timeout_seconds` | `600` | Download timeout per request (10 min) |

## Pipeline Integration

After downloading, books sit in `F:\Books\BookFinder\` and can be processed by the existing pipeline:

```powershell
# Option 1: Pipe directly
Get-ChildItem "F:\Books\BookFinder\*" -Recurse -Include *.epub,*.pdf,*.mobi |
    Invoke-EbookPipeline

# Option 2: Move to inbox
Copy-Item "F:\Books\BookFinder\*" "F:\Projects\EbookAutomation\module\inbox\"
Invoke-EbookPipeline
```

## Module Functions Reference

### `Invoke-EbookBookSearch`

Search for books. Returns JSON objects that pipe to download.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `-Title` | string | required | Book title |
| `-Titles` | string[] | required (batch) | Array of titles for batch search |
| `-Author` | string | optional | Author name |
| `-Format` | string | none | Preferred format |
| `-Top` | int | 10 | Max results per source |
| `-Sources` | string[] | libgen, anna | Which sources to search |
| `-Column` | string | any | LibGen search column |
| `-PassThru` | switch | false | Output JSON to pipeline |

### `Invoke-EbookBookDownload`

Download books from search results.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `InputObject` | pipeline | required | Book objects from search |
| `-Ids` | string | required (ById) | Comma-separated book IDs |
| `-File` | string | required (FromFile) | JSON file with book results |
| `-Format` | string | epub | Preferred download format |
| `-OutputDir` | string | from config | Download root directory |
| `-MaxRetries` | int | 5 | Max download retries |
| `-DryRun` | switch | false | Show without downloading |
| `-Resume` | switch | false | Resume failed downloads |
| `-List` | switch | false | Show queue status |
| `-Stats` | switch | false | Show download statistics |
| `-History` | switch | false | Show download history |
| `-Limit` | int | 100 | Max downloads to process |

### `Invoke-EbookBookDownloadFromList`

Search and download from a file of titles.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `-FilePath` | string[] | required | Path to text file (one title per line) |
| `-Format` | string | epub | Preferred download format |
| `-OutputDir` | string | from config | Download root directory |
| `-MaxRetries` | int | 5 | Max download retries |
| `-DryRun` | switch | false | Show without downloading |

## Testing & Verification

```powershell
# Verify module loads
Import-Module .\module\EbookAutomation.psm1 -Force
Get-Command -Module EbookAutomation | Where-Object { $_.Name -like "*Book*" }

# Search with table output
Invoke-EbookBookSearch -Title "Atomic Habits" -Author "James Clear"

# Check download queue
Invoke-EbookBookDownload -List
Invoke-EbookBookDownload -Stats
Invoke-EbookBookDownload -History

# Test with dry run first
Invoke-EbookBookSearch -Title "Deep Work" -Format epub |
    Invoke-EbookBookDownload -Format epub -DryRun
```

## Known Limitations & Gotchas

- **LibGen and AA can be slow or block requests** — the `web_fetch` tool may timeout (as observed during development). The downloader handles timeouts gracefully with retry logic.
- **LibGen results often duplicate** across editions/mirrors — deduplicated by MD5 hash automatically.
- **Anna's Archive has no stable API** — scraping HTML tables only. Schema may change without notice; the code has table and div layout fallbacks.
- **No parallel downloads** — books process one at a time. These sources don't handle concurrent requests well.
- **Format detection is heuristic** — AA format detection scans for known format strings in table cells; may miss entries where format is embedded in other text.
- **Never add books you don't have rights to access** — this tool is for finding books you already own or have permission to download.

## Future Enhancements

- **ISBN search** — resolve by ISBN-10/13 for precise matching
- **Z-Library mirrors** — add as another source tier after AA
- **Tor mode** — support for downloading via Tor (some LibGen mirrors require it)
- **Checksum verification** — validate downloaded files by MD5
- **Metadata extraction** — pull cover images and metadata during download
- **Auto-cleanup** — remove `.part` files older than N days
- **Batch list from spreadsheet** — read from CSV/XLSX instead of text file
