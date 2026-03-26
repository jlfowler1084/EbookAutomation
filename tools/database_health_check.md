# Prompt: Database Health Check After Batch QA Runs

## Goal
Show me the current state of the pattern_db after our batch QA runs. I want to see what data we've accumulated and whether it looks healthy.

## Steps

### 1. Run the built-in stats command
```powershell
cd F:\Projects\EbookAutomation
python tools/pattern_db.py stats
```

### 2. List batch runs
```powershell
python tools/batch_qa.py list
```

### 3. Run a deeper database query
Run this Python script to get a comprehensive view:

```python
import sqlite3, json
from pathlib import Path

db_path = Path(r"F:\Projects\EbookAutomation\data\ebook_patterns.db")
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

print("=" * 60)
print("  EbookAutomation Database Health Check")
print("=" * 60)

# Table row counts
print("\n── Table Row Counts ──")
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:<30} {count:>6} rows")

# Books by format
print("\n── Books by Format ──")
for r in conn.execute(
    "SELECT format, COUNT(*) as cnt FROM books GROUP BY format ORDER BY cnt DESC"
).fetchall():
    print(f"  {r['format']:<10} {r['cnt']:>4} books")

# Books by source type
print("\n── Books by Source Type ──")
for r in conn.execute(
    "SELECT COALESCE(source_type, 'null') as st, COUNT(*) as cnt "
    "FROM books GROUP BY source_type ORDER BY cnt DESC"
).fetchall():
    print(f"  {r['st']:<15} {r['cnt']:>4} books")

# Conversion stats
print("\n── Conversion Summary ──")
total_conv = conn.execute("SELECT COUNT(*) FROM conversions").fetchone()[0]
print(f"  Total conversions:  {total_conv}")
with_vqa = conn.execute(
    "SELECT COUNT(*) FROM conversions WHERE vqa_score IS NOT NULL"
).fetchone()[0]
print(f"  With VQA scores:    {with_vqa}")
if with_vqa:
    avg = conn.execute(
        "SELECT AVG(vqa_score) FROM conversions WHERE vqa_score IS NOT NULL"
    ).fetchone()[0]
    print(f"  Average VQA score:  {avg:.1f}")

# Extraction paths used
print("\n── Extraction Paths Used ──")
for r in conn.execute(
    "SELECT extraction_path, COUNT(*) as cnt "
    "FROM conversions GROUP BY extraction_path ORDER BY cnt DESC"
).fetchall():
    print(f"  {r['extraction_path']:<20} {r['cnt']:>4} conversions")

# Issues breakdown
print("\n── Issues by Category ──")
total_issues = conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
print(f"  Total issues recorded: {total_issues}")
for r in conn.execute(
    "SELECT category, severity, COUNT(*) as cnt "
    "FROM issues GROUP BY category, severity ORDER BY cnt DESC LIMIT 15"
).fetchall():
    print(f"  {r['severity']:<10} {r['category']:<35} {r['cnt']:>4}")

# Batch runs
print("\n── Batch Runs ──")
try:
    for r in conn.execute(
        "SELECT run_id, books_total, books_passed, books_failed, "
        "books_errored, total_duration_seconds, created_at "
        "FROM batch_runs ORDER BY created_at DESC LIMIT 10"
    ).fetchall():
        dur = r['total_duration_seconds'] or 0
        print(f"  {r['run_id']}")
        print(f"    Books: {r['books_total']} total, {r['books_passed']} pass, "
              f"{r['books_failed']} fail, {r['books_errored']} err  "
              f"({int(dur//60)}m{int(dur%60):02d}s)")
except Exception as e:
    print(f"  (batch_runs table not found or empty: {e})")

# Recent books (last 10 added)
print("\n── 10 Most Recently Added Books ──")
for r in conn.execute(
    "SELECT filename, format, file_size_bytes, chapter_count, word_count, created_at "
    "FROM books ORDER BY created_at DESC LIMIT 10"
).fetchall():
    size_mb = (r['file_size_bytes'] or 0) / (1024*1024)
    ch = r['chapter_count'] if r['chapter_count'] is not None else '?'
    wc = r['word_count'] if r['word_count'] is not None else '?'
    print(f"  {r['filename'][:50]:<52} {size_mb:>6.1f}MB  ch={ch}  words={wc}")

# Database file size
db_size = db_path.stat().st_size / 1024
print(f"\n── Database File Size: {db_size:.0f} KB ──")

conn.close()
print(f"\n{'=' * 60}")
```

### 4. Check for any data quality issues
Look for:
- Books with NULL filename (shouldn't happen)
- Duplicate book entries (same filename appearing multiple times)
- Conversions with no matching book_id
- Batch book results that reference non-existent run_ids

```python
print("\n── Data Quality Checks ──")

# Null filenames
null_fn = conn.execute("SELECT COUNT(*) FROM books WHERE filename IS NULL").fetchone()[0]
print(f"  Books with NULL filename:     {null_fn} {'✓' if null_fn == 0 else '⚠ FIX NEEDED'}")

# Duplicate filenames
dupes = conn.execute(
    "SELECT filename, COUNT(*) as cnt FROM books "
    "GROUP BY filename HAVING cnt > 1 ORDER BY cnt DESC LIMIT 5"
).fetchall()
print(f"  Duplicate filenames:          {len(dupes)} {'✓' if len(dupes) == 0 else '⚠'}")
for d in dupes:
    print(f"    '{d['filename']}' appears {d['cnt']} times")

# Orphaned conversions
orphans = conn.execute(
    "SELECT COUNT(*) FROM conversions c "
    "LEFT JOIN books b ON c.book_id = b.id WHERE b.id IS NULL"
).fetchone()[0]
print(f"  Orphaned conversions:         {orphans} {'✓' if orphans == 0 else '⚠'}")

# Orphaned issues
orphan_issues = conn.execute(
    "SELECT COUNT(*) FROM issues i "
    "LEFT JOIN conversions c ON i.conversion_id = c.id WHERE c.id IS NULL"
).fetchone()[0]
print(f"  Orphaned issues:              {orphan_issues} {'✓' if orphan_issues == 0 else '⚠'}")
```

Print everything to the terminal so I can see it. Don't modify anything — read-only queries only.
