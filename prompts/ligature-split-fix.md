# EB-64: Ligature Split Fix — 1,991 Remaining Across 5 Books

## Session Name
Ligature Split Fix

## Claude Code Model
**Sonnet** — targeted pattern expansion in a well-understood function

## Context

Batch QA (60 books) found **1,991 remaining ligature splits** after the existing `_fix_ligature_splits()` pass runs. The function uses `pyspellchecker` (English-only dictionary) to validate merges, so Latin/Greek academic terms fail validation and the splits remain.

### Top offenders:

| Book | Remaining | Per 1Kw | Root cause |
|------|-----------|---------|------------|
| Scott/Origen (Oxford ECS) | 1,342 | 8.6 | Dense Latin/Greek — 37.8% common word rate |
| Renz (Brill) | 498 | 2.4 | Hebrew/German theological terms |
| Collins (Eerdmans) | 70 | 0.3 | Jewish apocalyptic terminology |
| Weimar sourcebook | 27 | 0.0 | German terms |
| Mundill (Cambridge) | 23 | 0.2 | Medieval Latin |

### Detection regex (in test_pipeline.py):
```python
LIGATURE_SPLIT_RE = re.compile(
    r'\b(?:'
    r'[Tt]h e\b|[Tt]h is\b|[Tt]h at\b|[Tt]h ey\b|[Tt]h en\b|[Tt]h ere\b|'
    r'[Tt]h ose\b|[Tt]h us\b|[Tt]h an\b|[Tt]h eir\b|[Tt]h em\b|[Tt]h ese\b|'
    r'fi [a-z]|fl [a-z]|ffi [a-z]|ffl [a-z]'
    r')'
)
```

### Key function: `_fix_ligature_splits()` in `tools/pdf_to_balabolka.py`
- Uses `grep -n "_fix_ligature_splits"` to locate (around line 9534)
- Spellchecker-gated merge: only merges fragments if the combined word is in pyspellchecker's English dictionary
- Handles: fi/fl splits, ffi/ffl triples, "Th e" patterns, hyphen-split rejoining
- The multi-fragment merge loop (2-4 consecutive fragments) is the main workhorse

### Test books (in `C:\Users\Joe\Downloads\`):

1. **Scott/Origen (PRIMARY):** `[Oxford Early Christian Studies] Alan Scott - Origen and the life of the stars*.pdf`
2. **Renz:** `(Supplements to Vetus Testamentum 76) Thomas Renz - The Rhetorical Function of the Book of Ezekiel*.pdf`
3. **Oil Kings (CONTROL):** regression book in `inbox\` — must not regress

---

## Phase 1: Diagnostic (READ ONLY — no edits yet)

### Step 1a: Extract and count remaining splits

Convert Scott/Origen through the full pipeline to get the output HTML, then count remaining ligature splits:

```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\[Oxford Early Christian Studies] Alan Scott - Origen and the life of the stars*.pdf"
```

Then write a quick diagnostic script that:
1. Reads the output HTML
2. Finds ALL matches of `LIGATURE_SPLIT_RE` (the pattern from test_pipeline.py above)
3. For each match, prints the match + 30 chars of surrounding context
4. Groups matches by the fragment pair (e.g., "fi gure" → "fi + gure", "fl ight" → "fl + ight")
5. Counts frequency of each fragment pair
6. Prints the top 30 most common remaining split patterns

This tells us exactly WHAT is failing to merge and whether the remaining words are:
- (a) Latin/Greek terms that the English dictionary can't validate
- (b) English words that should be in the dictionary but aren't
- (c) Something else entirely

### Step 1b: Test the spellchecker hypothesis

For the top 20 remaining split patterns, check if the merged word is in pyspellchecker:
```python
from spellchecker import SpellChecker
spell = SpellChecker()
# For each "fi gure" → check if "figure" in spell
```

This confirms whether the dictionary is the bottleneck.

---

## Phase 2: Fix

Based on Phase 1 findings, implement one or more of these approaches in `_fix_ligature_splits()`:

### Approach A: Permissive fi/fl merge (RECOMMENDED starting point)

After the spellchecker-validated merge loop, add a second pass specifically for fi/fl fragments:

```python
# After the main spellchecker loop, do a permissive fi/fl pass:
# If fragment ends with "fi" or "fl" and next fragment is lowercase 2+ chars,
# AND the merged result is 5+ chars total,
# AND the merged result does NOT create a known bad merge,
# → merge without dictionary validation.
```

The key insight: `fi` and `fl` are almost never standalone words. If you see `"confi dence"`, `"sacri fi cial"`, `"signi fi cant"`, `"ful fi lled"` — these are ALWAYS ligature splits regardless of language. The false positive rate is near zero because:
- "fi" alone is not an English/Latin/Greek word
- "fl" alone is not a word in any relevant language
- The continuation must be lowercase (rules out abbreviations)

**Guardrails to prevent false positives:**
- Skip if the "fi"/"fl" fragment is a complete word that makes sense standalone (rare — but check against a small blocklist)
- Skip if the next fragment starts with a capital letter (proper noun boundary)
- Skip if the merged result is <5 chars (too short to be confident)
- Skip if within HTML tags

### Approach B: Suffix-based validation (SUPPLEMENT to A)

For merged words that end in common suffixes (-tion, -ment, -ence, -ity, etc.), validate the suffix rather than the whole word. This catches inflected Latin/Greek terms where the root isn't in the dictionary but the suffix pattern is universal.

### Approach C: Latin/Greek common roots (ONLY if A+B insufficient)

Add a small set (~50-100) of common Latin/Greek roots that appear in academic theology:
- Latin: sacri-, signi-, confi-, bene-, magni-, speci-, classi-, modi-, certi-, etc.
- Greek: philo-, theo-, cosmi-, astro-, etc.

Only pursue this if Approach A doesn't get Scott/Origen below 200.

### CRITICAL constraints:
- **Do NOT remove the spellchecker validation from the main loop** — it prevents false positives on English text. The permissive pass is a SUPPLEMENTARY step.
- **Oil Kings must not regress** — run `python tools/test_pipeline.py --quick` after changes.
- **The detection regex in test_pipeline.py (`LIGATURE_SPLIT_RE`) must stay in sync** — if you add new patterns to the fix, the detection regex should still catch any remaining splits.

---

## Phase 3: Verify with Proof

After implementing fixes:

### Step 3a: Re-count on Scott/Origen
Re-run conversion on Scott/Origen and count remaining splits using the same diagnostic from Phase 1.

Report:
```
Scott/Origen:
  Before: 1,342 remaining ligature splits
  After: [count] remaining
  Reduction: [percentage]%
  Sample remaining (if any): [list top 5]
```

### Step 3b: Re-count on Renz
Same for Renz.

### Step 3c: Run test suite
```powershell
python tools/test_pipeline.py --quick
```
Target: 39/41+ (same baseline). Oil Kings ligature count must not increase.

### Success criteria:
- Scott/Origen: <200 remaining (from 1,342)
- Renz: <100 remaining (from 498)
- Oil Kings: no regression in ligature count
- 39/41+ tests pass

If Scott/Origen is still above 200, go back to Phase 1 diagnostic on the REMAINING splits and implement Approach B or C.

---

## Phase 4: Commit & Push

```powershell
cd F:\Projects\EbookAutomation
git add -A
git commit -m "EB-64: Ligature split fix - permissive fi/fl merge for non-English text

- [describe specific approach used]
- Scott/Origen: 1,342 → [count] remaining ([X]% reduction)
- Renz: 498 → [count] remaining
- Oil Kings: no regression
- Tests: [X]/41 pass"
git push origin master
```

---

## Phase 5: Jira

Add a comment to EB-64 via MCP:
```
EB-64 complete ([commit hash]).
Approach: [describe what was implemented]
Results:
- Scott/Origen: 1,342 → [count] remaining
- Renz: 498 → [count] remaining  
- Oil Kings: no regression
Tests: [X]/41 pass.
```

Transition EB-64 to Done (transition ID 31).
