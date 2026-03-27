# SCRUM-39: Master OCR Substitution Table

## Session Name
SCRUM-39 OCR Substitution Table

## Claude Code Model
Opus

## Jira
SCRUM-39 — In Progress

## Overview
Extract all hardcoded OCR/extraction substitution patterns from `pdf_to_balabolka.py` into a JSON config file (`config/ocr_substitutions.json`), refactor `fix_ocr_artifacts()` to load from that file, record fix statistics into the pattern database, and add CLI tooling. The goal is data-driven, extensible fix patterns instead of patterns buried in 700 lines of inline code.

**CRITICAL**: `pdf_to_balabolka.py` is 11,000+ lines. Use `grep -n` to find exact locations — never guess line numbers.

## Project Root
`F:\Projects\EbookAutomation\`

---

## Audit: What's Extractable vs Algorithmic

The codebase audit identified which patterns can be externalized to JSON and which must remain as code:

### EXTRACTABLE to JSON (hardcoded lookup tables):

1. **Mojibake map** (~40 entries) — grep for `mojibake_map` in `pdf_to_balabolka.py`
   - Maps corrupted byte sequences to correct Unicode characters
   - Example: `'\xe2\x80\x9c'` → `'\u201C'`

2. **Unicode normalization** (Phase 1) — grep for `Phase 1: Normalize Unicode`
   - Smart quotes, dashes, ellipsis → ASCII equivalents
   - 5 entries: `\u2018→'`, `\u2019→'`, `\u201c→"`, `\u201d→"`, `\u2013→-`, `\u2014→--`, `\u2026→...`

3. **Backtick replacement candidates** (Phase 1b) — grep for `Phase 1b`
   - List of letter combos that backtick might replace: `['bl', 'dd', 'ff', 'fi', 'fl', 'tt', 'll', 'ft', 'fb', 'ffi', 'ffl']`

4. **Merged word pairs** (Phase 2d) — grep for `Phase 2d` or `_merged_word_fixes`
   - ~16 entries: `ofthe→of the`, `inthe→in the`, etc.

5. **Ligature map** (Phase 3) — grep for `Phase 3: Fix common ligature`
   - 5 entries: `ﬁ→fi`, `ﬂ→fl`, `ﬀ→ff`, `ﬃ→ffi`, `ﬄ→ffl`

6. **Biblical/chapter keywords for i→1** (Phase 2b) — grep for `Phase 2b` or `standalone_i_pattern`
   - ~20 keywords: Genesis, Exodus, Chapter, Samuel, etc.

### STAYS AS CODE (algorithmic, not table-driven):
- rn/m substitution (Phase 2) — spell-checker dictionary validation
- Dehyphenation (Phase 3b) — algorithmic word join
- o→0 / i→1 number fixes (Phase 2b/2c) — regex + numeric validation
- Spaced-letter collapse (Phase 8) — greedy dictionary word splitting
- Running header detection (Phase 0/9) — frequency-based
- All other structural phases (4-7, 9-10) — algorithmic

---

## Part 1: Create `config/ocr_substitutions.json`

Create directory `config/` in project root and populate the JSON file:

```json
{
  "_comment": "Master OCR substitution table for EbookAutomation. Loaded by fix_ocr_artifacts() in pdf_to_balabolka.py. Edit this file to add/modify patterns without touching Python code.",
  "_version": "1.0",

  "mojibake_map": {
    "_comment": "Corrupted byte sequences → correct Unicode. Keys are the bad sequences as they appear in extracted text.",
    "entries": {}
  },

  "unicode_normalization": {
    "_comment": "Unicode characters → ASCII equivalents for TTS readability.",
    "entries": {}
  },

  "backtick_replacements": {
    "_comment": "Letter combinations that a backtick character might replace in pypdf extraction. Tried in order.",
    "candidates": []
  },

  "merged_word_splits": {
    "_comment": "Merged word pairs from pypdf line-break artifacts. Key = merged form, value = split form.",
    "entries": {}
  },

  "ligature_map": {
    "_comment": "Unicode ligature characters → decomposed ASCII equivalents.",
    "entries": {}
  },

  "chapter_keywords": {
    "_comment": "Keywords after which standalone 'i' should become '1'. Used in Phase 2b OCR i→1 fix.",
    "words": []
  }
}
```

**IMPORTANT**: To populate the actual values, extract them from the current code:

1. **mojibake_map**: Find the `mojibake_map = {` dict (grep for `mojibake_map`). Copy all key-value pairs. Since the keys contain raw bytes that don't serialize cleanly to JSON, use the Python hex escape representation as the key (e.g., `"\\xe2\\x80\\x9c"`) and the target character as the value (e.g., `"\u201c"`). Add a note in the `_comment` that keys use Python byte-escape notation.

2. **unicode_normalization**: Extract from Phase 1 — the `.replace()` calls for smart quotes, dashes, ellipsis. Store as `{"source_char": "target_char"}`.

3. **backtick_replacements**: Extract the `replacements` list from Phase 1b.

4. **merged_word_splits**: Extract `_merged_word_fixes` dict from Phase 2d.

5. **ligature_map**: Extract the 5 ligature mappings from Phase 3.

6. **chapter_keywords**: Extract the keyword list from Phase 2b's regex pattern.

---

## Part 2: Add Loader Function in `pdf_to_balabolka.py`

Add a function near the top of the file (after imports, before any extraction functions):

```python
import os
import json

_OCR_SUBSTITUTIONS_CACHE = None

def load_ocr_substitutions(custom_path=None):
    """Load OCR substitution table from config/ocr_substitutions.json.

    Falls back to hardcoded defaults if file is missing.
    Caches the loaded table for subsequent calls.

    Args:
        custom_path: Optional path to a custom substitution JSON file.
                     Merged on top of the base config (custom entries win).
    Returns:
        dict with keys: mojibake_map, unicode_normalization, backtick_replacements,
                        merged_word_splits, ligature_map, chapter_keywords
    """
    global _OCR_SUBSTITUTIONS_CACHE

    if _OCR_SUBSTITUTIONS_CACHE is not None and custom_path is None:
        return _OCR_SUBSTITUTIONS_CACHE

    # Default path: config/ocr_substitutions.json relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # pdf_to_balabolka.py is in project root; config/ is sibling
    default_path = os.path.join(script_dir, 'config', 'ocr_substitutions.json')

    result = _get_hardcoded_defaults()  # fallback

    if os.path.isfile(default_path):
        try:
            with open(default_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result = _merge_substitution_data(result, data)
        except (json.JSONDecodeError, IOError) as e:
            pass  # fall back to hardcoded defaults silently

    # Merge custom overrides on top
    if custom_path and os.path.isfile(custom_path):
        try:
            with open(custom_path, 'r', encoding='utf-8') as f:
                custom_data = json.load(f)
            result = _merge_substitution_data(result, custom_data)
        except (json.JSONDecodeError, IOError):
            pass

    if custom_path is None:
        _OCR_SUBSTITUTIONS_CACHE = result

    return result


def _get_hardcoded_defaults():
    """Return hardcoded defaults as fallback if JSON file is missing."""
    return {
        'mojibake_map': {},  # Will be populated from JSON; empty = skip mojibake phase
        'unicode_normalization': {
            '\u2018': "'", '\u2019': "'",
            '\u201c': '"', '\u201d': '"',
            '\u2013': '-', '\u2014': '--',
            '\u2026': '...',
        },
        'backtick_replacements': ['bl', 'dd', 'ff', 'fi', 'fl', 'tt', 'll', 'ft', 'fb', 'ffi', 'ffl'],
        'merged_word_splits': {
            'ofthe': 'of the', 'ofthis': 'of this', 'ofthat': 'of that',
            'oftheir': 'of their', 'inthe': 'in the', 'inthis': 'in this',
            'inthat': 'in that', 'tothe': 'to the', 'forthe': 'for the',
            'onthe': 'on the', 'atthe': 'at the', 'bythe': 'by the',
            'isthe': 'is the', 'andthe': 'and the', 'fromthe': 'from the',
            'withthe': 'with the', 'asthe': 'as the', 'butthe': 'but the',
        },
        'ligature_map': {
            '\ufb01': 'fi', '\ufb02': 'fl', '\ufb00': 'ff',
            '\ufb03': 'ffi', '\ufb04': 'ffl',
        },
        'chapter_keywords': [
            'Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy',
            'Chapter', 'Chapters', 'chapter', 'chapters',
            'Samuel', 'Kings', 'Chronicles', 'Corinthians',
            'Thessalonians', 'Timothy', 'Peter', 'John',
            'Psalm', 'Isaiah', 'Jeremiah', 'Ezekiel', 'Daniel',
            'verse', 'verses', 'Verse', 'Verses',
        ],
    }


def _merge_substitution_data(base, overlay):
    """Deep-merge overlay onto base. Overlay values win for conflicts."""
    result = dict(base)
    for key in overlay:
        if key.startswith('_'):
            continue  # skip _comment, _version
        if key in result and isinstance(result[key], dict) and isinstance(overlay[key], dict):
            # For nested dicts, look for 'entries' sub-key
            if 'entries' in overlay[key]:
                if isinstance(result[key], dict) and not any(k.startswith('_') for k in result[key] if isinstance(k, str)):
                    # result[key] is a flat dict (hardcoded default), overlay has {entries: ...}
                    result[key] = dict(result[key])
                    result[key].update(overlay[key]['entries'])
                else:
                    result[key] = dict(result[key])
                    result[key].update(overlay[key]['entries'])
            else:
                result[key] = dict(result[key])
                result[key].update(overlay[key])
        elif key in result and isinstance(result[key], list) and isinstance(overlay[key], dict) and 'candidates' in overlay[key]:
            result[key] = overlay[key]['candidates']
        elif key in result and isinstance(result[key], list) and isinstance(overlay[key], dict) and 'words' in overlay[key]:
            result[key] = overlay[key]['words']
        elif key in result and isinstance(result[key], list) and isinstance(overlay[key], list):
            result[key] = overlay[key]
        else:
            result[key] = overlay[key]
    return result
```

**NOTE**: The merge logic needs to handle the JSON structure (which uses `entries`, `candidates`, `words` sub-keys) vs the flat dict structure from `_get_hardcoded_defaults()`. Test this carefully. The simplest approach may be to normalize both to flat dicts at load time, stripping the wrapper keys.

---

## Part 3: Refactor `fix_ocr_artifacts()` to Use Loaded Tables

This is the core refactor. For each extractable phase, replace the hardcoded data with a lookup against the loaded substitution table.

### Phase 1 (Unicode normalization)
**Find**: the Phase 1 block with inline `.replace()` calls (grep for `Phase 1: Normalize Unicode`)

**Replace the hardcoded replacements with**:
```python
subs = load_ocr_substitutions()
unicode_map = subs.get('unicode_normalization', {})
for i in range(len(paragraphs)):
    original = paragraphs[i]
    text = paragraphs[i]
    for src, tgt in unicode_map.items():
        text = text.replace(src, tgt)
    if text != original:
        paragraphs[i] = text
        normalized += 1
```

### Phase 1b (Backtick corruption)
**Find**: `replacements = ['bl', 'dd', 'ff', ...]` (grep for `Phase 1b`)

**Replace with**:
```python
subs = load_ocr_substitutions()
replacements = subs.get('backtick_replacements', ['bl', 'dd', 'ff', 'fi', 'fl', 'tt', 'll', 'ft', 'fb', 'ffi', 'ffl'])
```

### Phase 2b (i→1 keywords)
**Find**: the `standalone_i_pattern = re.compile(...)` with the long keyword alternation (grep for `Phase 2b` or `standalone_i_pattern`)

**Replace with**:
```python
subs = load_ocr_substitutions()
chapter_kw = subs.get('chapter_keywords', [])
if chapter_kw:
    kw_pattern = '|'.join(re.escape(kw) for kw in chapter_kw)
    standalone_i_pattern = re.compile(r'\b(' + kw_pattern + r')\s+i\b')
```

### Phase 2d (Merged word pairs)
**Find**: `_merged_word_fixes = { 'ofthe': 'of the', ... }` (grep for `_merged_word_fixes` or `Phase 2d`)

**Replace with**:
```python
subs = load_ocr_substitutions()
_merged_word_fixes = subs.get('merged_word_splits', {})
```

### Phase 3 (Ligature map)
**Find**: the inline `.replace('\ufb01', 'fi')` calls (grep for `Phase 3: Fix common ligature`)

**Replace with**:
```python
subs = load_ocr_substitutions()
lig_map = subs.get('ligature_map', {})
for i in range(len(paragraphs)):
    original = paragraphs[i]
    text = paragraphs[i]
    for src, tgt in lig_map.items():
        text = text.replace(src, tgt)
    if text != original:
        paragraphs[i] = text
        ligature_fixes += 1
```

### Mojibake map
**Find**: `mojibake_map = {` dict (grep for `mojibake_map`)

**Replace with**:
```python
subs = load_ocr_substitutions()
mojibake_map = subs.get('mojibake_map', {})
```

**IMPORTANT performance note**: Call `load_ocr_substitutions()` ONCE at the start of `fix_ocr_artifacts()` and pass `subs` to each phase — do NOT call it 6 times per book. Store it in a local variable:

```python
def fix_ocr_artifacts(paragraphs, log, bookmark_titles=None, heading_indices=None):
    subs = load_ocr_substitutions()
    # ... then use subs['unicode_normalization'], subs['backtick_replacements'], etc.
```

---

## Part 4: Fix Statistics Recording

After `fix_ocr_artifacts()` completes, it should return a summary dict of what it fixed:

### Add return value
Currently the function modifies `paragraphs` in place and returns it. Change it to also return fix statistics:

```python
# At the end of fix_ocr_artifacts(), before the final return:
fix_stats = {
    'unicode_normalized': normalized,
    'backtick_fixes': backtick_fixes,
    'rn_m_fixes': fixes_made,
    'i_to_1_fixes': i_to_1_fixes + standalone_i_fixes,
    'o_to_0_fixes': o_to_0_fixes,
    'merged_word_fixes': merged_word_count,
    'ligature_fixes': ligature_fixes,
    'dehyphenation_fixes': dehyphen_count,
    'spaced_letter_fixes': spaced_fixes,  # if this variable exists
    # ... add any other phase counters that exist
}

return paragraphs, fix_stats
```

**IMPORTANT**: Find every caller of `fix_ocr_artifacts()` and update to handle the new return signature:
```python
# Old:
paragraphs = fix_ocr_artifacts(paragraphs, log, ...)
# New:
paragraphs, fix_stats = fix_ocr_artifacts(paragraphs, log, ...)
```

Grep for `fix_ocr_artifacts(` to find ALL call sites. There may be multiple in `pdf_to_balabolka.py`.

### Record to pattern database
After `fix_ocr_artifacts` returns, if `fix_stats` has any non-zero values, record them. Add this near the call site (or pass through to the caller that writes to the DB):

```python
# Include fix_stats in the extraction result dict
result['fix_stats'] = fix_stats
```

This data can then be included in the conversion record. The PSM1 db-write block already captures `fixes_applied` — we can enhance it to include the breakdown. But for this ticket, just making `fix_stats` available in the result dict is sufficient — wiring into the database is a follow-up.

---

## Part 5: `-OCRTable` Parameter for Custom Overrides

### In `pdf_to_balabolka.py` CLI
Find the argparse setup (grep for `argparse\|add_argument`). Add:

```python
parser.add_argument('--ocr-table', default=None,
                    help='Path to custom OCR substitution JSON (merged on top of config/ocr_substitutions.json)')
```

Then pass it through to `fix_ocr_artifacts`:
```python
# Wherever fix_ocr_artifacts is called, if args.ocr_table is available:
subs = load_ocr_substitutions(custom_path=args.ocr_table if hasattr(args, 'ocr_table') else None)
```

Actually, the cleaner approach: since `load_ocr_substitutions()` takes a `custom_path`, and `fix_ocr_artifacts()` calls it internally, add an optional parameter:

```python
def fix_ocr_artifacts(paragraphs, log, bookmark_titles=None, heading_indices=None, ocr_table_path=None):
    subs = load_ocr_substitutions(custom_path=ocr_table_path)
    ...
```

### In `EbookAutomation.psm1`
Add an `-OCRTable` parameter to `Convert-ToKindle`:

```powershell
[string]$OCRTable
```

Pass it through to the Python call as `--ocr-table "$OCRTable"` if set.

---

## Part 6: CLI Commands for Substitution Table Management

### Add `pattern_db.py ocr-stats` command

This queries the fix_patterns table (or the new fix_stats data if stored) to show aggregated OCR fix statistics:

```python
def _cmd_ocr_stats(args):
    """Show OCR substitution statistics across all conversions."""
    conn = get_db(args.db if hasattr(args, 'db') and args.db else None)
    try:
        # Show fix pattern effectiveness from fix_patterns table
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
        print(f"{'Fix Type':<30} {'Applied':>8} {'Succeeded':>10} {'Rate':>6} {'Δ Score':>8}")
        print("-" * 70)
        for r in rows:
            print(f"{r['fix_type']:<30} {r['total_applied']:>8} "
                  f"{r['total_succeeded']:>10} {r['avg_success_rate'] or 0:>5.1f}% "
                  f"{r['avg_improvement'] or 0:>+7.1f}")
    finally:
        conn.close()
```

Register it: `subparsers.add_parser('ocr-stats', help='Show OCR substitution fix statistics')` and add to commands dict.

### Add `pdf_to_balabolka.py --dump-ocr-table` flag

A diagnostic flag that loads the effective OCR substitution table (base + custom) and prints it as formatted JSON to stdout:

```python
parser.add_argument('--dump-ocr-table', action='store_true',
                    help='Print the effective OCR substitution table and exit')
```

In the main block:
```python
if args.dump_ocr_table:
    subs = load_ocr_substitutions(custom_path=args.ocr_table if hasattr(args, 'ocr_table') else None)
    print(json.dumps(subs, indent=2, ensure_ascii=False))
    sys.exit(0)
```

---

## Testing

### Automated tests
```bash
cd F:\Projects\EbookAutomation
python -m pytest tests/ -x -v
```
All existing tests must pass. The `fix_ocr_artifacts` return signature change is the most likely regression source — find and update every call site.

### Manual verification
```bash
# Verify config file loads
python pdf_to_balabolka.py --dump-ocr-table

# Verify custom override merges
echo '{"merged_word_splits": {"entries": {"forthis": "for this"}}}' > test_custom.json
python pdf_to_balabolka.py --dump-ocr-table --ocr-table test_custom.json
# Should show "forthis" in merged_word_splits alongside the defaults
del test_custom.json

# Verify OCR stats CLI
python tools/pattern_db.py ocr-stats
```

### Regression check
Convert a known book with and without the refactor. The output text should be byte-identical — this refactor externalizes data, it doesn't change behavior.

---

## Git
```bash
git add -A
git commit -m "SCRUM-39: Master OCR substitution table

- Extract 6 hardcoded substitution tables into config/ocr_substitutions.json
  (mojibake map, unicode normalization, backtick candidates, merged word pairs,
   ligature map, chapter keywords for i→1)
- Add load_ocr_substitutions() with JSON loading, caching, and custom override merge
- Refactor fix_ocr_artifacts() to load patterns from JSON instead of inline
- fix_ocr_artifacts() now returns (paragraphs, fix_stats) tuple
- Add --ocr-table CLI param for custom substitution overrides
- Add --dump-ocr-table diagnostic flag
- Add -OCRTable parameter to Convert-ToKindle in PSM1
- Add pattern_db.py ocr-stats command
- Algorithmic phases (rn/m, dehyphen, spaced-letter, etc.) unchanged"
git push origin master
```

## Jira
After completion, comment on SCRUM-39 via MCP:
```
Shipped Master OCR Substitution Table:
- 6 hardcoded pattern tables extracted to config/ocr_substitutions.json
- load_ocr_substitutions() with caching, fallback defaults, and custom override merge
- fix_ocr_artifacts() refactored to load from JSON — no behavior change
- fix_ocr_artifacts() returns fix_stats dict for downstream recording
- --ocr-table CLI param + -OCRTable PSM1 param for per-book custom overrides
- --dump-ocr-table diagnostic flag
- pattern_db.py ocr-stats command
- Algorithmic phases unchanged (rn/m, dehyphen, spaced-letter collapse)
- All tests pass, zero regression
```
Then transition SCRUM-39 → Done (transition ID 41).
