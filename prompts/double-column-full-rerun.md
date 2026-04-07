# EB-75 Verification: Full Double-Column Batch Re-Run

## Session Name
Double-Column Full Re-Run

## Claude Code Model
Sonnet — straightforward batch execution and report analysis, no architectural changes.

## Objective
Re-run the full double-column batch with EB-75's fixed extraction path tracking to get the first accurate picture of PyMuPDF column extraction across all ~28 processable books.

## Context
- EB-75 (just shipped, commit `f4e0c3b`) fixed a diagnostic blind spot: `batch_qa.py` was hardcoding `extraction_path: "html_extraction"` for all PDFs
- Now `extraction_path` reflects the actual extractor used (pymupdb_columns, html_extraction, etc.)
- A 5-book verification run confirmed the fix works — all 5 showed `pymupdf_columns`
- This re-run covers the full corpus to get comprehensive data

## Phase 1: Run the Batch

Run batch QA on the double-column folder, **excluding files larger than 200,000 KB** (the two study bibles that timeout):

```bash
cd F:\Projects\EbookAutomation

# First, list what we're processing vs skipping
python -c "
import os
folder = r'F:\Books\Double_Columned'
for f in sorted(os.listdir(folder)):
    if f.lower().endswith('.pdf'):
        size_kb = os.path.getsize(os.path.join(folder, f)) / 1024
        status = 'SKIP (>200MB)' if size_kb > 200000 else 'PROCESS'
        print(f'  {status}: {f} ({size_kb:.0f} KB)')
"
```

Then run the batch with `--max-file-size 200000` if that flag exists, otherwise filter manually. Check if batch_qa.py supports a size filter:

```bash
python tools/batch_qa.py run --help 2>&1 | grep -i "size\|max\|skip\|exclude"
```

If no size filter flag exists, create a temporary filtered folder or use `--exclude` if available. If neither exists, use this approach:

```python
# Create a file list excluding oversized PDFs, then pass to batch_qa
import os, shutil, tempfile

source = r'F:\Books\Double_Columned'
# Create a temp folder with symlinks/copies of only the processable PDFs
filtered_dir = r'F:\Books\Double_Columned_Filtered'
os.makedirs(filtered_dir, exist_ok=True)

for f in os.listdir(source):
    if not f.lower().endswith('.pdf'):
        continue
    src = os.path.join(source, f)
    size_kb = os.path.getsize(src) / 1024
    if size_kb > 200000:
        print(f'  SKIP: {f} ({size_kb:.0f} KB)')
        continue
    # Create symlink (Windows: mklink) or just note it
    dst = os.path.join(filtered_dir, f)
    if not os.path.exists(dst):
        os.symlink(src, dst)  # or shutil.copy2 if symlinks fail
    print(f'  INCLUDE: {f} ({size_kb:.0f} KB)')
```

**Preferred approach:** Just run batch_qa.py on the full folder. The previous run already showed it skips oversized files automatically (the two bibles were "skipped" in the first batch). Confirm this behavior:

```bash
python tools/batch_qa.py run "F:\Books\Double_Columned" --parallel 2 --no-cache
```

The `--no-cache` flag is important — we need fresh extractions so the new `[EXTRACTION_PATH]` log lines fire. Without it, cached results won't have the structured log output for batch_qa to parse.

**If `--no-cache` doesn't exist as a batch_qa flag**, check what cache invalidation options are available. The pipeline cache is keyed on the SHA-256 hash of `pdf_to_balabolka.py`, which changed in the EB-75 commit — so the cache should auto-invalidate. Verify by checking if the first book's extraction actually runs (look for extraction log output rather than "using cached result").

Expected runtime: ~2-5 minutes for 28 books in quick mode with `--parallel 2`.

## Phase 2: Analyze the Report

Once the batch completes, analyze the JSON report for extraction path accuracy:

```python
import json
from pathlib import Path
from collections import Counter

# Load the latest batch report
reports_dir = Path(r'F:\Projects\EbookAutomation\data\batch_reports')
latest = sorted(reports_dir.glob('batch_*.json'), key=lambda f: f.stat().st_mtime)[-1]

with open(latest, 'r', encoding='utf-8') as f:
    report = json.load(f)

books = report['books']
print(f"Report: {latest.name}")
print(f"Total books: {len(books)}\n")

# 1. Extraction path distribution
paths = Counter()
for b in books:
    path = b['extraction'].get('extraction_path', 'unknown')
    paths[path] += 1

print("=== Extraction Path Distribution ===")
for path, count in paths.most_common():
    print(f"  {path}: {count}")

# 2. Multi-column detection vs extraction path
print("\n=== Multi-Column Books: Detection vs Extraction ===")
mc_books = [b for b in books if b.get('source_classification', {}).get('is_multicolumn')]
non_mc = [b for b in books if not b.get('source_classification', {}).get('is_multicolumn')]
print(f"  Detected as multi-column: {len(mc_books)}")
print(f"  Detected as single-column: {len(non_mc)}")

mc_pymupdf = sum(1 for b in mc_books if b['extraction'].get('extraction_path') == 'pymupdf_columns')
mc_pdfminer = sum(1 for b in mc_books if b['extraction'].get('extraction_path') != 'pymupdf_columns')
print(f"  Multi-column → PyMuPDF: {mc_pymupdf}")
print(f"  Multi-column → pdfminer fallback: {mc_pdfminer}")

# 3. PyMuPDF fallback reasons (if any)
print("\n=== PyMuPDF Fallback Details ===")
fallbacks = [(b['filename'], b['extraction'].get('pymupdf_fallback_reason'))
             for b in books if b['extraction'].get('pymupdf_fallback_reason')]
if fallbacks:
    for fname, reason in fallbacks:
        print(f"  {fname}: {reason}")
else:
    print("  No fallbacks — PyMuPDF succeeded on all attempted books")

# 4. Column-merge detection
print("\n=== Column-Merge Detection ===")
merges = [(b['filename'], b.get('text_quality', {}).get('possible_column_merge'))
          for b in books if b.get('text_quality', {}).get('possible_column_merge')]
if merges:
    for fname, _ in merges:
        print(f"  WARNING: Possible column merge: {fname}")
else:
    print("  No column merges detected")

# 5. Per-book summary table
print("\n=== Per-Book Summary ===")
print(f"{'Filename':<45} {'Path':<20} {'MC?':<5} {'Conf':<6} {'Score':<6} {'Merge?':<7}")
print("-" * 95)
for b in sorted(books, key=lambda x: x['filename']):
    fname = b['filename'][:44]
    path = b['extraction'].get('extraction_path', '?')
    mc = 'Yes' if b.get('source_classification', {}).get('is_multicolumn') else 'No'
    conf = b.get('source_classification', {}).get('column_confidence', 0)
    score = b.get('text_quality', {}).get('score', 0)
    merge = 'Yes' if b.get('text_quality', {}).get('possible_column_merge') else 'No'
    print(f"  {fname:<44} {path:<20} {mc:<5} {conf:<6.0%} {score:<6} {merge:<7}")
```

## Phase 3: Report Summary

Create a summary markdown file:

```bash
# Save to data/batch_reports/double_column_rerun_summary.md
```

The summary should include:
1. Total books processed vs skipped
2. Extraction path distribution (pymupdf_columns vs html_extraction vs other)
3. Multi-column detection accuracy (how many detected, confidence levels)
4. Any PyMuPDF fallbacks and their reasons
5. Any column-merge warnings
6. Comparison with the previous batch run (before EB-75): "Previously all 28 reported html_extraction; now X report pymupdf_columns"
7. Recommendations for next steps

## What NOT to Change
- Do NOT modify any source code — this is a diagnostic re-run only
- Do NOT run with `--full` or `--vqa` — quick mode only
- Do NOT process the study bibles (>200,000 KB)

## Git
No code changes, so no commit needed. The batch report files will be generated in `data/batch_reports/` but don't need to be committed — they're diagnostic data.

If for any reason the report reveals unexpected results (e.g., PyMuPDF NOT being used on multi-column books), document the finding in the summary but do NOT attempt to fix it in this session.
