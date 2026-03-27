# SCRUM-194: Data Collection Follow-Ups (FU-1 through FU-5)

## Session Name
SCRUM-194 Data Collection Follow-Ups

## Claude Code Model
Sonnet

## Jira
SCRUM-194 — In Progress

## Overview
Five data collection enrichments from the SCRUM-133 follow-up list. Each is a small, well-defined addition. Files are large — use `grep -n` to find exact locations, never estimated line ranges.

## Project Root
`F:\Projects\EbookAutomation\`

---

## FU-1: Per-Page Quality Variance (~1 hr)

### What
Extend the preflight text quality assessment in `tools/preflight_analysis.py` to sample multiple page positions instead of just one midpoint.

### How
1. Find the function that assesses text quality (grep for `def.*text.*quality` or `def.*assess.*text` or `quality_score` in `tools/preflight_analysis.py`).
2. Currently it samples one page (roughly the midpoint). Change it to sample 5 pages at positions: 10%, 25%, 50%, 75%, 90% of total page count.
3. For each sampled page, compute the same quality metrics (garbled char ratio, word-like token ratio, etc.) that the single-point assessment currently computes.
4. Return the **median** score as the overall score (backward compatible), plus two new fields:
   - `quality_scores`: list of individual page scores, e.g. `[82, 75, 88, 90, 71]`
   - `quality_variance`: the standard deviation of those scores (use `statistics.stdev` if ≥2 samples, else 0)
5. These new fields go into the preflight report JSON alongside the existing quality score.
6. If a PDF has fewer than 5 pages, sample all pages.

### Verification
- Run: `python tools/preflight_analysis.py "F:\Projects\EbookAutomation\inbox\<any-test-pdf>"` and confirm the report JSON includes `quality_scores` and `quality_variance`.
- Run: `python -m pytest tests/ -x` — all 89 tests must pass.

---

## FU-2: Tier Escalation Comparison Details (~45 min)

### What
When the pipeline auto-escalates between extraction tiers, capture before/after metrics.

### How
1. In `pdf_to_balabolka.py`, find where tier escalation happens (grep for `escalat` or `tier` or `auto.*escal` or `quality.*gate`).
2. At each escalation point, the pipeline already has a `word_count` and `quality_score` from the previous tier and computes new ones for the next tier. Capture these into a dict:
   ```python
   escalation_details = {
       "from_tier": "tier1",       # or "tier2", "tier2.5"
       "to_tier": "tier2",         # or "tier2.5", "tier3"
       "word_count_before": 1234,
       "word_count_after": 5678,
       "quality_before": 45,
       "quality_after": 78,
   }
   ```
3. If multiple escalations happen (T1→T2→T2.5), accumulate them into a list:
   ```python
   escalation_history = [
       {"from_tier": "tier1", "to_tier": "tier2", ...},
       {"from_tier": "tier2", "to_tier": "tier2.5", ...}
   ]
   ```
4. Pass this data back to the caller. The PSM1 will pick it up in FU-3's changes. For now, just ensure the data is available in the extraction result dict that `pdf_to_balabolka.py` returns/prints.
5. Add an `escalation_details` key to the JSON output of `pdf_to_balabolka.py` (the script prints JSON to stdout for the PSM1 to parse).

### Finding the code
- `grep -n "escalat\|tier.*1\|tier.*2\|quality.*gate\|auto.*upgrade" pdf_to_balabolka.py`
- The file is 7000+ lines — do NOT guess line numbers.

---

## FU-3: Extraction Duration Breakdown (~30 min)

### What
Store per-phase timing in the conversion record instead of just the overall duration.

### Database Change (pattern_db.py)
1. Add a schema migration: new column `duration_breakdown TEXT` on the `conversions` table. Use `ALTER TABLE` in a migration block (follow the existing pattern — grep for `ALTER TABLE` in `pattern_db.py` to see if there's an existing migration pattern, or add one in the `_ensure_schema()` / `init_db()` function).
2. Update `add_conversion()` to accept `duration_breakdown=None` parameter. If passed as a dict, `json.dumps()` it before INSERT.

### PSM1 Change (EbookAutomation.psm1)
1. Find the inline Python block that calls `add_conversion` (grep for `add_conversion` — it's around line 2030 based on the audit).
2. Before that block, capture the existing stopwatch values into PowerShell variables:
   ```powershell
   $dbDurationBreakdown = @{
       extraction_seconds = [math]::Round($pySw.Elapsed.TotalSeconds, 1)
       formatting_seconds = [math]::Round($claudeSw.Elapsed.TotalSeconds, 1)
       calibre_seconds    = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
   } | ConvertTo-Json -Compress
   ```
   **IMPORTANT**: Verify the actual stopwatch variable names by grepping — they may vary between the TTS path and the Kindle path. Use the Kindle path stopwatches (that's the primary conversion pipeline). The variable names from the audit are: `$pySw` (extraction), `$claudeSw` (AI/chapter detection), `$stopwatch` (calibre conversion near line 1748). Some of these may not exist in all code paths — use `if` guards.
3. Pass `duration_breakdown` into the inline Python `conv_kwargs`:
   ```python
   conv_kwargs['duration_breakdown'] = '$dbDurationBreakdown' or None
   ```

---

## FU-4: Publisher-Level Pattern Aggregation (~1 hr)

### Bug Fix: source_profiles upsert

In `tools/pattern_db.py`:

1. Find the `source_profiles` CREATE TABLE (line ~140). Add a UNIQUE constraint:
   ```sql
   CREATE TABLE IF NOT EXISTS source_profiles (
       ...existing columns...
       UNIQUE(publisher, decade, format)
   );
   ```
   Since SQLite doesn't support `ALTER TABLE ADD CONSTRAINT`, handle this with a migration:
   - In the schema migration section, add:
     ```sql
     CREATE UNIQUE INDEX IF NOT EXISTS idx_source_profiles_natural_key
         ON source_profiles(publisher, decade, format);
     ```
   - Also add it to `_INDEXES_SQL` for fresh installs.

2. Fix `update_source_profile()` (grep for it — around line 676). Change:
   ```sql
   ON CONFLICT(id) DO UPDATE SET
   ```
   to:
   ```sql
   ON CONFLICT(publisher, decade, format) DO UPDATE SET
   ```

3. **Dedup existing data**: Add a one-time migration that deduplicates existing rows:
   ```sql
   DELETE FROM source_profiles
   WHERE id NOT IN (
       SELECT MIN(id) FROM source_profiles
       GROUP BY publisher, decade, format
   );
   ```
   Run this BEFORE creating the unique index.

### New Command: publisher-report

1. Add a `_cmd_publisher_report(args)` function:
   ```python
   def _cmd_publisher_report(args):
       """Show publisher-level aggregation of conversion outcomes."""
       conn = get_db(args.db if hasattr(args, 'db') and args.db else None)
       try:
           cursor = conn.execute("""
               SELECT
                   b.publisher,
                   COUNT(DISTINCT b.id) as book_count,
                   ROUND(AVG(c.vqa_score), 1) as avg_score,
                   ROUND(AVG(c.text_quality_score), 1) as avg_text_quality,
                   COUNT(CASE WHEN c.vqa_score >= 80 THEN 1 END) as pass_count,
                   COUNT(CASE WHEN c.vqa_score < 80 THEN 1 END) as fail_count,
                   GROUP_CONCAT(DISTINCT c.extraction_path) as extraction_paths
               FROM books b
               JOIN conversions c ON c.book_id = b.id
               WHERE b.publisher IS NOT NULL AND b.publisher != ''
               GROUP BY b.publisher
               ORDER BY book_count DESC, avg_score DESC
           """)
           rows = cursor.fetchall()
           if not rows:
               print("No publisher data found.")
               return
           # Header
           print(f"{'Publisher':<35} {'Books':>5} {'Avg':>5} {'Pass':>5} {'Fail':>5} {'Paths'}")
           print("-" * 90)
           for r in rows:
               pub = (r['publisher'] or 'Unknown')[:34]
               print(f"{pub:<35} {r['book_count']:>5} {r['avg_score'] or 0:>5.1f} "
                     f"{r['pass_count']:>5} {r['fail_count']:>5} {r['extraction_paths'] or '-'}")
       finally:
           conn.close()
   ```

2. Register it in the CLI:
   - Add parser: `subparsers.add_parser('publisher-report', help='Show publisher-level conversion outcomes')`
   - Add to commands dict: `'publisher-report': _cmd_publisher_report`
   - Add `--db` argument for optional db path.

---

## FU-5: Cache Amortization View (~30 min)

### New Command: cache-roi

**NOTE**: First verify whether an `extraction_cache` table exists. Grep for `extraction_cache` in `pattern_db.py`. If it does NOT exist as a CREATE TABLE, check if caching is managed elsewhere (e.g., file-based cache in `pdf_to_balabolka.py`). If so, the `cache-roi` command should query whatever cache store exists. If no cache table exists at all, create a placeholder command that reports "Cache table not found — caching may use file-based storage" and skip the SQL.

If the table exists:
1. Add `_cmd_cache_roi(args)`:
   ```python
   def _cmd_cache_roi(args):
       """Show cache amortization — cost per serve for cached extractions."""
       conn = get_db(args.db if hasattr(args, 'db') and args.db else None)
       try:
           # Check if extraction_cache table exists
           tables = [r[0] for r in conn.execute(
               "SELECT name FROM sqlite_master WHERE type='table'"
           ).fetchall()]
           if 'extraction_cache' not in tables:
               print("No extraction_cache table found.")
               print("Cache may be file-based. Check pdf_to_balabolka.py cache directory.")
               return
           cursor = conn.execute("""
               SELECT
                   ec.content_hash,
                   ec.extraction_tier,
                   ec.cost_usd,
                   ec.times_served,
                   CASE WHEN ec.times_served > 0
                        THEN ROUND(ec.cost_usd / ec.times_served, 4)
                        ELSE ec.cost_usd END as cost_per_serve,
                   b.title,
                   b.filename
               FROM extraction_cache ec
               LEFT JOIN books b ON b.source_file_hash = ec.content_hash
               ORDER BY ec.times_served DESC, ec.cost_usd DESC
           """)
           rows = cursor.fetchall()
           if not rows:
               print("Cache is empty.")
               return
           total_cost = sum(r['cost_usd'] or 0 for r in rows)
           total_serves = sum(r['times_served'] or 0 for r in rows)
           print(f"Cache Summary: {len(rows)} entries, ${total_cost:.2f} total cost, "
                 f"{total_serves} total serves")
           print(f"{'Title/File':<45} {'Tier':<8} {'Cost':>7} {'Serves':>7} {'$/Serve':>8}")
           print("-" * 80)
           for r in rows:
               name = (r['title'] or r['filename'] or r['content_hash'][:12])[:44]
               tier = r['extraction_tier'] or '?'
               print(f"{name:<45} {tier:<8} ${r['cost_usd'] or 0:>6.2f} "
                     f"{r['times_served'] or 0:>7} ${r['cost_per_serve'] or 0:>7.4f}")
       finally:
           conn.close()
   ```

2. Register: `subparsers.add_parser('cache-roi', help='Show cache amortization and cost-per-serve')` and add to commands dict.

**If the extraction_cache table schema differs from what's shown above** (different column names), adapt the query to match. Use `PRAGMA table_info(extraction_cache)` to discover the actual schema.

---

## Testing

After all changes:
```bash
cd F:\Projects\EbookAutomation
python -m pytest tests/ -x -v
```
All 89 tests must pass.

Then test the new CLI commands:
```bash
python tools/pattern_db.py publisher-report
python tools/pattern_db.py cache-roi
```

## Git
```bash
git add -A
git commit -m "SCRUM-194: Data collection follow-ups (FU-1–FU-5)

- FU-1: Multi-point quality variance in preflight (5-page sampling)
- FU-2: Escalation comparison details in extraction output
- FU-3: Duration breakdown (extraction/formatting/calibre) in conversions
- FU-4: Fix source_profiles upsert bug (ON CONFLICT natural key), add publisher-report command
- FU-5: Add cache-roi command for cache amortization analysis"
git push origin master
```

## Jira
After completion, comment on SCRUM-194 via MCP:
```
Shipped FU-1 through FU-5:
- Preflight now samples 5 pages, reports quality_variance
- Escalation details (before/after word count, quality) captured in extraction output
- Duration breakdown stored as JSON on conversions
- source_profiles upsert bug fixed (was ON CONFLICT(id), now natural key)
- publisher-report and cache-roi CLI commands added
- 89/89 tests pass, zero regression
```
Then transition SCRUM-194 → Done (transition ID 41).
