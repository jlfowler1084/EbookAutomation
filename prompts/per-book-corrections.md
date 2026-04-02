## Session Name
per-book-corrections

## Claude Code Model
Sonnet — schema extension, new function, CLI flags, pipeline wiring. All well-defined integration points.

## Jira
EB-73: Per-book corrections system — user-submitted fixes cached for future conversions

## Objective

Build a per-book corrections system that lets users fix edge-case quality issues (running headers appearing as headings, misdetected chapters, unwanted content blocks) via CLI flags, and caches those corrections in pattern_db so future conversions of the same book auto-apply them.

**CRITICAL GUARDRAIL:** Corrections must ONLY run when the user explicitly passes `--apply-corrections` on the CLI. Without this flag, the pipeline must behave identically to today. This protects us from regressions in our batch testing pipeline.

## Context

### What already exists (DO NOT rebuild):

**pattern_db.py** has a `book_overrides` table with:
```sql
CREATE TABLE IF NOT EXISTS book_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER REFERENCES books(id),
    isbn TEXT,
    title_hash TEXT,
    chapter_structure TEXT,
    extraction_path TEXT,
    extraction_notes TEXT,
    calibre_options TEXT,
    skip_front_pages INTEGER,
    skip_back_pages INTEGER,
    source TEXT DEFAULT 'local',
    submitted_by TEXT,
    review_status TEXT DEFAULT 'approved',
    upvotes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Functions exist: `add_book_override()`, `get_book_override()`, `update_book_override()`.

Lookup chain in `get_book_override()`: book_id → ISBN → filename (via books table) → title_hash.

**But**: `get_book_override()` is never called from `pdf_to_balabolka.py`. The entire override system is unwired.

### Where corrections get applied in pdf_to_balabolka.py:

The HTML output flow (Kindle mode with html-extraction):
```
Line ~10021: html = format_paragraphs_as_html(para_dicts, body_size, bookmarks, log, title=title)
Line ~10028-10035: post-processing (tag merging, space collapsing)
Line ~10064-10069: html_path = ...; f.write(html)
```

Corrections should be applied AFTER the existing post-processing (line ~10035) and BEFORE writing to disk (line ~10068). This keeps corrections completely separate from heading detection logic.

## Implementation Plan

### Step 1: Add `corrections_json` column to book_overrides

**File:** `tools/pattern_db.py`

Add a migration-safe ALTER TABLE. Find the `ensure_tables()` or schema initialization function and add:

```python
# After existing table creation, add migration for corrections_json
try:
    conn.execute("SELECT corrections_json FROM book_overrides LIMIT 1")
except Exception:
    conn.execute("ALTER TABLE book_overrides ADD COLUMN corrections_json TEXT")
    conn.commit()
```

Place this in the same location where `_BATCH_RUNS_SQL` or other schema migrations happen, or inside the main `ensure_tables()` / initialization path.

### Step 2: Update `add_book_override()` and `update_book_override()`

**File:** `tools/pattern_db.py`

**In `add_book_override()` (~line 1152):**
- Add `corrections=None` parameter
- Serialize corrections to JSON string if provided
- Add to INSERT statement

**In `update_book_override()` (~line 1259):**
- Add `'corrections_json'` to the `allowed` set

**In `get_book_override()` (~line 1196):**
- After parsing `chapter_structure`, also parse `corrections_json`:
```python
if result.get("corrections_json"):
    try:
        result["corrections"] = json.loads(result["corrections_json"])
    except (json.JSONDecodeError, TypeError):
        result["corrections"] = []
else:
    result["corrections"] = []
```

### Step 3: Build `apply_corrections()` function

**File:** `tools/pdf_to_balabolka.py`

Add as a new top-level function, near the end of the file but before `if __name__ == "__main__":`. This function operates on the finished HTML string.

```python
def apply_corrections(html, corrections, log):
    """Apply per-book corrections to generated HTML.

    Corrections is a list of correction rule dicts. Each rule has:
    - action: str — one of 'strip_heading', 'strip_text', 'demote_heading',
                    'force_heading', 'replace_text'
    - pattern: str — text or regex pattern to match
    - match: str — 'exact' (default) or 'regex'
    - Plus action-specific fields (see below)

    Returns the corrected HTML string.
    """
    if not corrections:
        return html

    import re as _re

    total_applied = 0

    for rule in corrections:
        action = rule.get("action", "")
        pattern = rule.get("pattern", "")
        match_type = rule.get("match", "exact")
        note = rule.get("note", "")

        if not action or not pattern:
            log(f"  [CORRECTION] Skipping invalid rule: {rule}")
            continue

        count_before = len(html)

        if action == "strip_heading":
            # Remove heading tags containing the pattern, replace with nothing
            # (the content was a running header / duplicate, not real content)
            if match_type == "regex":
                pat = _re.compile(
                    r'<(h[1-6])([^>]*)>' + pattern + r'</\1>',
                    _re.IGNORECASE
                )
                html, n = pat.subn('', html)
            else:
                # Exact match: escape for regex, allow whitespace flexibility
                escaped = _re.escape(pattern)
                # Allow flexible whitespace between words
                escaped = _re.sub(r'\\ ', r'\\s+', escaped)
                pat = _re.compile(
                    r'<(h[1-6])([^>]*)>\s*' + escaped + r'\s*</\1>',
                    _re.IGNORECASE
                )
                html, n = pat.subn('', html)
            if n:
                log(f"  [CORRECTION] strip_heading: removed {n} headings matching "
                    f"'{pattern[:50]}'{f' — {note}' if note else ''}")
                total_applied += n

        elif action == "strip_text":
            # Remove <p> tags containing the pattern
            if match_type == "regex":
                pat = _re.compile(
                    r'<p[^>]*>' + pattern + r'</p>',
                    _re.IGNORECASE
                )
                html, n = pat.subn('', html)
            else:
                escaped = _re.escape(pattern)
                escaped = _re.sub(r'\\ ', r'\\s+', escaped)
                pat = _re.compile(
                    r'<p[^>]*>\s*' + escaped + r'\s*</p>',
                    _re.IGNORECASE
                )
                html, n = pat.subn('', html)
            if n:
                log(f"  [CORRECTION] strip_text: removed {n} paragraphs matching "
                    f"'{pattern[:50]}'{f' — {note}' if note else ''}")
                total_applied += n

        elif action == "demote_heading":
            # Change heading level: e.g., h1 → h3
            target_from = rule.get("from", "h1")
            target_to = rule.get("to", "h3")
            if match_type == "regex":
                pat = _re.compile(
                    r'<' + target_from + r'([^>]*)>(' + pattern + r')</' + target_from + r'>',
                    _re.IGNORECASE
                )
            else:
                escaped = _re.escape(pattern)
                escaped = _re.sub(r'\\ ', r'\\s+', escaped)
                pat = _re.compile(
                    r'<' + target_from + r'([^>]*)>\s*(' + escaped + r')\s*</' + target_from + r'>',
                    _re.IGNORECASE
                )
            def _demote_repl(m):
                return f'<{target_to}{m.group(1)}>{m.group(2)}</{target_to}>'
            html, n = pat.subn(_demote_repl, html)
            if n:
                log(f"  [CORRECTION] demote_heading: changed {n} '{target_from}' → '{target_to}' "
                    f"for '{pattern[:50]}'{f' — {note}' if note else ''}")
                total_applied += n

        elif action == "force_heading":
            # Promote a <p> to a heading
            text = rule.get("text", pattern)
            level = rule.get("level", "h1")
            escaped = _re.escape(text)
            escaped = _re.sub(r'\\ ', r'\\s+', escaped)
            pat = _re.compile(
                r'<p([^>]*)>\s*(' + escaped + r')\s*</p>',
                _re.IGNORECASE
            )
            def _promote_repl(m):
                return f'<{level}{m.group(1)}>{m.group(2)}</{level}>'
            html, n = pat.subn(_promote_repl, html)
            if n:
                log(f"  [CORRECTION] force_heading: promoted {n} paragraphs to '{level}' "
                    f"for '{text[:50]}'{f' — {note}' if note else ''}")
                total_applied += n

        elif action == "replace_text":
            # Find/replace within text content
            replacement = rule.get("replacement", "")
            if match_type == "regex":
                pat = _re.compile(pattern, _re.IGNORECASE)
                html, n = pat.subn(replacement, html)
            else:
                n = html.count(pattern)
                html = html.replace(pattern, replacement)
            if n:
                log(f"  [CORRECTION] replace_text: {n} replacements "
                    f"'{pattern[:30]}' → '{replacement[:30]}'{f' — {note}' if note else ''}")
                total_applied += n

        else:
            log(f"  [CORRECTION] Unknown action '{action}' — skipping")

    if total_applied:
        log(f"  [CORRECTION] Total: {total_applied} corrections applied")
    else:
        log(f"  [CORRECTION] {len(corrections)} rules loaded but 0 matched — "
            f"corrections may need updating for this book version")

    return html
```

### Step 4: Add CLI flags to pdf_to_balabolka.py

**File:** `tools/pdf_to_balabolka.py`

In the argparse section (after the existing `--tts-enhance` argument, around line 10837), add:

```python
# Per-book corrections
ap.add_argument("--apply-corrections", action="store_true",
                help="Apply cached per-book corrections from pattern_db "
                     "(and/or sidecar .corrections.json file)")
ap.add_argument("--strip-heading", action="append", default=[],
                metavar="TEXT",
                help="Strip all headings matching TEXT (exact match). "
                     "Can be used multiple times. Implies --apply-corrections. "
                     "Corrections are saved to pattern_db for future conversions.")
ap.add_argument("--strip-text", action="append", default=[],
                metavar="TEXT",
                help="Remove all paragraphs matching TEXT (exact match). "
                     "Can be used multiple times. Implies --apply-corrections.")
ap.add_argument("--force-heading", action="append", default=[],
                metavar="TEXT:LEVEL",
                help="Promote paragraph TEXT to heading LEVEL (e.g., 'Chapter One:h1'). "
                     "Can be used multiple times. Implies --apply-corrections.")
ap.add_argument("--export-corrections", action="store_true",
                help="Export current book corrections as a .corrections.json sidecar file")
```

### Step 5: Wire corrections into the pipeline

**File:** `tools/pdf_to_balabolka.py`

**5a. Build the corrections list from all sources.**

After `args = ap.parse_args()` and input validation, but before the main processing starts (around line 10910), add a helper to collect corrections:

```python
def _collect_corrections(args, input_path, log):
    """Collect corrections from CLI flags, sidecar file, and pattern_db.

    Returns (corrections_list, should_save_to_db).
    Only called when --apply-corrections is set (or implied by --strip-heading etc.)
    """
    corrections = []
    should_save = False

    # 1. CLI flags → correction rules
    for text in (args.strip_heading or []):
        corrections.append({
            "action": "strip_heading",
            "pattern": text,
            "match": "exact",
            "note": "Added via --strip-heading CLI flag"
        })
        should_save = True

    for text in (args.strip_text or []):
        corrections.append({
            "action": "strip_text",
            "pattern": text,
            "match": "exact",
            "note": "Added via --strip-text CLI flag"
        })
        should_save = True

    for spec in (args.force_heading or []):
        # Parse "Chapter One:h1" format
        if ':' in spec:
            text, level = spec.rsplit(':', 1)
            level = level.strip().lower()
            if level not in ('h1', 'h2', 'h3'):
                log(f"  [WARN] Invalid heading level '{level}' in --force-heading, using h1")
                level = 'h1'
        else:
            text = spec
            level = 'h1'
        corrections.append({
            "action": "force_heading",
            "text": text.strip(),
            "level": level,
            "match": "exact",
            "note": "Added via --force-heading CLI flag"
        })
        should_save = True

    # 2. Sidecar file: BookName.corrections.json next to the input PDF
    sidecar_path = Path(input_path).with_suffix('.corrections.json')
    if sidecar_path.exists():
        try:
            with open(sidecar_path, 'r', encoding='utf-8') as f:
                sidecar_rules = json.load(f)
            if isinstance(sidecar_rules, list):
                log(f"  [CORRECTION] Loaded {len(sidecar_rules)} rules from sidecar: {sidecar_path.name}")
                corrections.extend(sidecar_rules)
        except Exception as e:
            log(f"  [WARN] Failed to load sidecar corrections: {e}")

    # 3. pattern_db cached corrections
    try:
        from pattern_db import get_book_override
        filename = Path(input_path).name
        override = get_book_override(filename=filename)
        if override and override.get("corrections"):
            db_corrections = override["corrections"]
            if isinstance(db_corrections, list):
                log(f"  [CORRECTION] Loaded {len(db_corrections)} cached corrections from pattern_db")
                # Merge: CLI/sidecar corrections take precedence (appended after DB)
                # Deduplicate by (action, pattern) tuple
                existing = {(c.get("action"), c.get("pattern", c.get("text", "")))
                            for c in corrections}
                for rule in db_corrections:
                    key = (rule.get("action"), rule.get("pattern", rule.get("text", "")))
                    if key not in existing:
                        corrections.append(rule)
    except ImportError:
        pass  # pattern_db not available

    return corrections, should_save
```

**5b. Apply corrections to HTML output.**

Find the HTML write section (around line 10063-10069). Insert correction application BEFORE the write:

```python
    # ── Apply per-book corrections (opt-in only) ─────────────────────
    # Only runs when --apply-corrections is set (or implied by --strip-heading etc.)
    _corrections_applied = False
    if getattr(args, 'apply_corrections', False) or \
       getattr(args, 'strip_heading', None) or \
       getattr(args, 'strip_text', None) or \
       getattr(args, 'force_heading', None):
        corrections, should_save = _collect_corrections(args, pdf_path, log)
        if corrections:
            log(f"\n-- CORRECTIONS: Applying {len(corrections)} rules --------")
            html = apply_corrections(html, corrections, log)
            _corrections_applied = True

            # Save corrections to pattern_db for future conversions
            if should_save:
                try:
                    from pattern_db import get_book_override, add_book_override, \
                        update_book_override, get_or_create_book
                    filename = Path(pdf_path).name
                    book_id = get_or_create_book(filename)
                    existing = get_book_override(filename=filename)
                    corrections_json = json.dumps(corrections)
                    if existing:
                        update_book_override(existing['id'],
                                             corrections_json=corrections_json)
                        log(f"  [CORRECTION] Updated cached corrections in pattern_db "
                            f"(override #{existing['id']})")
                    else:
                        override_id = add_book_override(
                            book_id=book_id,
                            corrections=corrections
                        )
                        log(f"  [CORRECTION] Saved corrections to pattern_db "
                            f"(new override #{override_id})")
                except ImportError:
                    log("  [CORRECTION] pattern_db not available — corrections not cached")
                except Exception as e:
                    log(f"  [CORRECTION] Failed to save corrections: {e}")
```

**IMPORTANT:** This block must appear AFTER all the existing post-processing (tag merging at lines 10028-10035) and BEFORE `with open(html_path, 'w') as f: f.write(html)` (line 10068).

**5c. Handle `--export-corrections`.**

After the HTML write (around line 10072), add:

```python
    # Export corrections sidecar if requested
    if getattr(args, 'export_corrections', False):
        try:
            from pattern_db import get_book_override
            filename = Path(pdf_path).name
            override = get_book_override(filename=filename)
            if override and override.get("corrections"):
                sidecar_path = Path(pdf_path).with_suffix('.corrections.json')
                with open(sidecar_path, 'w', encoding='utf-8') as f:
                    json.dump(override["corrections"], f, indent=2, ensure_ascii=False)
                log(f"  Exported corrections to: {sidecar_path}")
            else:
                # Export an empty template
                sidecar_path = Path(pdf_path).with_suffix('.corrections.json')
                template = [
                    {
                        "action": "strip_heading",
                        "pattern": "EXAMPLE: Replace this with the heading text to remove",
                        "match": "exact",
                        "note": "Remove running headers that appear as headings"
                    }
                ]
                with open(sidecar_path, 'w', encoding='utf-8') as f:
                    json.dump(template, f, indent=2, ensure_ascii=False)
                log(f"  Exported correction template to: {sidecar_path}")
                log(f"  Edit the file, then re-run with --apply-corrections")
        except ImportError:
            log("  [WARN] pattern_db not available — cannot export corrections")
```

**5d.** There is a SECOND HTML write path for Kindle mode with convergence loop (around line 10157). Search for ALL places where HTML is written to disk and apply the same correction insertion pattern. Look for:
- `with open(html_path, 'w'` 
- Any other `f.write(html)` that outputs the final HTML

For each one, add the same correction guard. To avoid code duplication, the `_collect_corrections` call should happen ONCE early and the result stored, then `apply_corrections()` called at each write point.

**Better approach:** Collect corrections once near the top of the main processing flow, store in a variable, then apply at each HTML write point:

Near line 10910 (after args parsing), add:
```python
    # Pre-collect corrections (evaluated once, applied at each HTML write point)
    _pending_corrections = None
    _corrections_should_save = False
    if args.apply_corrections or args.strip_heading or args.strip_text or args.force_heading:
        _pending_corrections, _corrections_should_save = _collect_corrections(args, input_path, log_fn)
        if _pending_corrections:
            log_fn(f"[cli] Corrections: {len(_pending_corrections)} rules loaded")
```

Then at each HTML write point, before `f.write(html)`:
```python
    if _pending_corrections:
        log(f"\n-- CORRECTIONS: Applying {len(_pending_corrections)} rules --------")
        html = apply_corrections(html, _pending_corrections, log)
```

And the DB save logic runs once at the very end of the script, not at each write point.

### Step 6: Update pattern_db.py override CLI

**File:** `tools/pattern_db.py`

**6a. Add corrections args to the `override add` subparser (~line 2461):**

```python
ov_add.add_argument(
    '--corrections', help='Path to corrections JSON file'
)
ov_add.add_argument(
    '--strip-heading', action='append', default=[],
    help='Add a strip_heading correction (can be used multiple times)'
)
```

**6b. Update `_cmd_override_add()` to handle corrections:**

Find the handler and add logic to build corrections from the `--strip-heading` args and/or load from `--corrections` JSON file. Pass to `add_book_override()` as the `corrections` parameter.

**6c. Update `_cmd_override_show()` to display corrections:**

When showing an override, if `corrections_json` is present, pretty-print the correction rules.

### Step 7: Verify

1. **Run regression suite (NO corrections flag):**
```
python tools/test_pipeline.py
```
Expected: 41/41 passing — pipeline unchanged without --apply-corrections

2. **Test corrections on a book:**

First, create a corrections file for testing:
```
echo [{"action":"strip_heading","pattern":"Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology.","match":"exact","note":"Running header appearing as heading"}] > test_corrections.json
```

Then run with the flag:
```
python tools/pdf_to_balabolka.py --input "F:\Books\Inbox\SomeBook.pdf" --mode kindle --html-extraction --apply-corrections --strip-heading "Some Repeated Header Text"
```

Verify:
- `[CORRECTION] strip_heading: removed N headings` in output
- Corrections saved to pattern_db
- Re-running the same book with just `--apply-corrections` (no --strip-heading) picks up cached corrections

3. **Test sidecar file:**
```
python tools/pdf_to_balabolka.py --input book.pdf --export-corrections
```
Verify .corrections.json file created next to the PDF.

4. **Test pattern_db CLI:**
```
python tools/pattern_db.py override show SomeBook.pdf
```
Verify corrections_json displayed.

5. **Report these specific numbers:**
- Regression test results: X/41 passing
- Number of correction rules loaded from each source (CLI, sidecar, DB)
- Number of corrections actually applied (matched) on test book
- Whether DB persistence works (run 1 saves, run 2 loads)

## Files Modified
- `tools/pattern_db.py` — corrections_json column migration, add/get/update functions, CLI
- `tools/pdf_to_balabolka.py` — apply_corrections() function, CLI flags, pipeline wiring

## Git
```
git add -A
git commit -m "EB-73: Per-book corrections system (Phase 1+2)

- Added corrections_json column to book_overrides (migration-safe)
- apply_corrections() handles 5 action types: strip_heading, strip_text,
  demote_heading, force_heading, replace_text
- CLI flags: --apply-corrections, --strip-heading, --strip-text,
  --force-heading, --export-corrections
- Corrections loaded from CLI flags + sidecar .corrections.json + pattern_db
- Corrections ONLY applied when --apply-corrections is explicitly set
- CLI corrections auto-saved to pattern_db for future conversions
- pattern_db override CLI updated to show/add corrections"
git push origin master
```
