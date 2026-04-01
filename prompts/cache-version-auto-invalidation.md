# EB-66: Extraction Cache — Auto-Invalidate on Pipeline Code Changes

## Session Name
Cache Version Auto-Invalidation

## Claude Code Model
Sonnet — well-scoped changes across two files with clear integration points; existing schema already has the columns.

## Problem

Batch QA runs serve stale cached HTML from before code fixes (EB-63 footnote linking, EB-64 ligature splits). Example: Vendrell was fixed to 100% footnote linking in the live session, but the 100-book batch still reports 0% because the cache returns pre-fix HTML.

The extraction cache in `pattern_db.py` has `pipeline_version` and `cache_version` columns that are **never populated or checked**:
- `cache_version` is hardcoded to `1` on every store
- `pipeline_version` is accepted as a parameter in `store_extraction()` but never passed from `pdf_to_balabolka.py`
- `get_cached_extraction()` accepts `cache_version` but the caller never passes it

## Solution

Hash `pdf_to_balabolka.py` at module load time. Store the hash as `pipeline_version` when caching. On cache lookup, reject entries with a different `pipeline_version`. Any code change to `pdf_to_balabolka.py` automatically invalidates all cached extractions.

## Files to Modify

1. **`tools/pdf_to_balabolka.py`** — compute pipeline hash at startup, pass to cache calls
2. **`tools/pattern_db.py`** — enforce pipeline_version matching in `get_cached_extraction()`

## Implementation Steps

### Step 1: Add pipeline hash computation to `pdf_to_balabolka.py`

Near the top of the file (after imports, before any function definitions), add:

```python
# Pipeline version hash — computed once at import time.
# Any code change to this file auto-invalidates the extraction cache.
def _compute_pipeline_hash():
    """SHA-256 of this file's contents, truncated to 16 hex chars."""
    import hashlib
    _this_file = os.path.abspath(__file__)
    h = hashlib.sha256()
    with open(_this_file, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()[:16]

_PIPELINE_HASH = _compute_pipeline_hash()
```

### Step 2: Pass `_PIPELINE_HASH` to `store_extraction()` calls

In `process_kindle_html()`, find the `store_extraction(...)` call (search for `store_extraction(`). It currently does NOT pass `pipeline_version`. Add it:

```python
store_extraction(
    ...existing params...,
    pipeline_version=_PIPELINE_HASH,
)
```

There should be exactly ONE `store_extraction` call in the file. Verify with: `grep -n "store_extraction(" tools/pdf_to_balabolka.py`

### Step 3: Pass `_PIPELINE_HASH` to cache lookup

In the `__main__` block of `pdf_to_balabolka.py`, find the extraction cache check section (search for `get_cached_extraction(`). It currently calls:

```python
_cached = get_cached_extraction(source_file_hash=_src_hash, min_score=60)
```

Change to:

```python
_cached = get_cached_extraction(source_file_hash=_src_hash, min_score=60, pipeline_version=_PIPELINE_HASH)
```

There should be exactly ONE `get_cached_extraction` call in the file. Verify with: `grep -n "get_cached_extraction(" tools/pdf_to_balabolka.py`

### Step 4: Enforce `pipeline_version` matching in `pattern_db.py`

In `get_cached_extraction()`, the function already accepts `cache_version` but NOT `pipeline_version`. Modify it:

1. Add `pipeline_version=None` parameter to the function signature.

2. After the existing `cache_version` filter block, add pipeline_version filtering:

```python
if pipeline_version is not None:
    query += " AND pipeline_version = ?"
    params.append(pipeline_version)
```

This goes right before the `ORDER BY` line.

### Step 5: Log cache misses due to version mismatch

In `pdf_to_balabolka.py`, enhance the cache hit/miss logging. After the `get_cached_extraction` call, if we get a miss, do a secondary check to see if a cache entry EXISTS but was rejected due to version mismatch:

```python
if _cached:
    # existing cache hit logging...
else:
    # Check if miss was due to version mismatch
    _stale = get_cached_extraction(source_file_hash=_src_hash, min_score=60)
    if _stale:
        log_fn(f"Extraction cache STALE: cached version {_stale.get('pipeline_version', 'None')[:12]} "
               f"≠ current {_PIPELINE_HASH[:12]} — re-extracting")
    else:
        log_fn(f"Extraction cache miss for {_src_hash[:12]}... — running fresh extraction")
```

**Important:** This secondary lookup must NOT pass `pipeline_version` — it's checking whether an entry exists at all (just version-mismatched). Make sure the existing miss log message is replaced, not duplicated.

### Step 6: Add `--force-recache` logging

The file already has `--no-cache` support. No need to add a new flag — `--no-cache` already bypasses the cache entirely. But when the pipeline hash causes a miss, the log message from Step 5 makes it clear why.

## Verification

### Test 1: Pipeline hash is computed
```bash
cd F:\Projects\EbookAutomation
python -c "import sys; sys.path.insert(0, 'tools'); from pdf_to_balabolka import _PIPELINE_HASH; print(f'Pipeline hash: {_PIPELINE_HASH}')"
```
Should print a 16-char hex string.

### Test 2: Hash changes when code changes
```bash
python -c "import sys; sys.path.insert(0, 'tools'); from pdf_to_balabolka import _PIPELINE_HASH; print(_PIPELINE_HASH)"
```
Note the hash. Then add a comment anywhere in `pdf_to_balabolka.py`, re-run, confirm hash changed. Remove the comment.

### Test 3: Stale cache detection
Pick a book that has a cached extraction (e.g., Vendrell):
```bash
python tools/pattern_db.py cache "Vendrell"
```
Confirm extraction cache HIT exists. Then run a quick conversion:
```bash
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\(German and European Studies, 35) Javier Samper Vendrell*" --mode kindle --html-extraction --output temp_test.html
```
Check the log output — it should show "Extraction cache STALE" (version mismatch), NOT a cache HIT. The extraction should run fresh and the new cache entry should store the current `_PIPELINE_HASH` as `pipeline_version`.

### Test 4: Regression — Oil Kings still passes
```bash
python tools/test_pipeline.py
```
Must be 39/41 (same 2 pre-existing Mexico failures). No regression.

### Test 5: Verify stored pipeline_version
After Test 3, check the database:
```bash
python -c "import sys; sys.path.insert(0, 'tools'); from pattern_db import get_db; conn = get_db(); rows = conn.execute('SELECT source_file_hash, pipeline_version, created_at FROM extraction_cache ORDER BY created_at DESC LIMIT 5').fetchall(); [print(dict(r)) for r in rows]"
```
The most recent entries should have `pipeline_version` set to the current hash. Older entries will have `NULL`.

## Commit

```bash
git add tools/pdf_to_balabolka.py tools/pattern_db.py
git commit -m "EB-66: Auto-invalidate extraction cache on pipeline code changes

- Compute SHA-256 hash of pdf_to_balabolka.py at import time
- Store hash as pipeline_version in extraction_cache entries
- Reject cache hits with mismatched pipeline_version
- Log stale cache entries with version mismatch detail
- Existing cache entries (pipeline_version=NULL) treated as stale"
git push origin master
```

## What NOT to Change

- Do NOT modify the `cache_version` column behavior — leave it as-is for potential future manual version bumping
- Do NOT delete or mass-invalidate existing cache entries — let them naturally miss via version mismatch and get replaced on next extraction
- Do NOT hash multiple files — `pdf_to_balabolka.py` is the only file that produces extraction output stored in the cache. Changes to `pattern_db.py` (the cache layer itself) don't affect extraction content.
- Do NOT change `--no-cache` behavior — it already works correctly for full bypass
