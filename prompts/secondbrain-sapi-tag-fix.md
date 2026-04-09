# Session: SecondBrain Autobook SAPI Tag Fix

## Claude Code Model
Sonnet (targeted fix to a known function + test wiring; no architectural changes)

## Context
SecondBrain's `Format-SBAutobookSSML` function is emitting voice and rate tags in a homemade format that **no TTS engine in the toolchain recognizes**. When the resulting `.txt` is fed to `Invoke-Balabolka` (which calls `balcon.exe`), the tags are read aloud verbatim ("voice colon Microsoft Steffan Online... rate colon negative two...") instead of being interpreted as control tags.

Confirmed in the Delta Faucet interview prep audiobook generated 2026-04-08.

## Root cause — four bugs in one function

**File:** `AutobookCmdlets.ps1` (in the SecondBrain module — likely `Public\Training\` or similar; locate via `Get-ChildItem -Recurse -Filter AutobookCmdlets.ps1`)

**Function:** `Format-SBAutobookSSML`

### Bug 1: Wrong tag format
Lines 73, 84, 94, 97, 105, 116 emit `{{Voice:Microsoft Steffan Online}}`. Line 74 emits `{{Rate:-2}}`. Neither matches any format the toolchain recognizes:

- EbookAutomation canonical format (see `tools/pdf_to_balabolka.py` lines 8297–8313, functions `_silence_tag` / `_rate_wrap` / `_voice_wrap`) is **SAPI XML**: `<voice required="Name=...">…</voice>`, `<rate speed="-2">…</rate>`, `<silence msec="500"/>`.
- The "universal" alternate format in `pdf_to_balabolka.py` uses `{{Pause=500}}` with `=` (not `:`) and per the code comments **does NOT support voice or rate switching at all**.
- Balabolka's GUI-only `{{Voice ...}}` braces format uses a space, not a colon — but it's GUI-only and balcon CLI doesn't honor it anyway.

So `{{Voice:...}}` / `{{Rate:...}}` is invented syntax that nothing parses.

### Bug 2: Standalone tag lines (balcon drops these)
The function builds output via `$lines += "{{Voice:...}}"` then `$lines += ""` then `$lines += $textLine`, then joins with `\n`. Every tag ends up on its own line in the final output.

Per prior balcon investigation: **balcon.exe drops SAPI control tags that sit on their own line entirely.** All voice/rate/silence tags must be inlined with adjacent speakable text on the same line. Tags-on-their-own-line render fine in the Balabolka GUI but vanish on the CLI audiobook render path that `Invoke-Balabolka` uses.

This is a structural issue in `Format-SBAutobookSSML` — every `$lines += "{{Voice:...}}"` needs to be refactored to prepend the tag onto the next non-empty content line instead of becoming its own array entry.

### Bug 3: Dead dispatcher branch
Around line 881:

```powershell
# Source content may already have SSML tags from EbookAutomation
if ($sourceContent -match '\{\{Voice:') {
    $ssmlContent = $sourceContent
} else {
    $ssmlContent = Format-SBAutobookSSML ...
}
```

The intent is "skip re-tagging if EbookAutomation already tagged it." But EbookAutomation emits `<voice required="Name=...">`, never `{{Voice:`. So this branch is dead — pre-tagged EbookAutomation content always falls through to `Format-SBAutobookSSML` and gets double-tagged with the broken format.

Fix: change the regex to detect real SAPI XML.

### Bug 4: Misleading function name (note only — do NOT rename)
The function is named `Format-SBAutobookSSML` but produces neither real SSML nor SAPI XML. Renaming would break callers. Leave the name; just fix the body. Optionally update the comment-based help `.SYNOPSIS` to say "SAPI XML voice tags" instead of "Balabolka SSML voice tags" so future-Joe isn't misled.

## Tasks

### 1. Patch `Format-SBAutobookSSML`
Replace the homemade format with SAPI XML matching `pdf_to_balabolka.py` conventions, AND refactor the line-building logic so tags are inlined with their adjacent speakable text rather than on standalone lines.

**Tag conversion table:**

| Current (broken)                           | Replacement (SAPI XML)                                       |
|--------------------------------------------|--------------------------------------------------------------|
| `{{Voice:Microsoft Steffan Online}}`       | `<voice required="Name=Microsoft Steffan Online">…</voice>`  |
| `{{Rate:-2}}`                              | `<rate speed="-2">…</rate>`                                  |
| (none currently)                           | `<silence msec="500"/>` for section breaks                   |

**Inlining pattern:** Instead of building separate `$lines` entries for tag-then-text, build each output line as a single string that contains both the control tags and the speakable text. For example, the intro should produce ONE line:

```
<voice required="Name=Microsoft Steffan Online"><rate speed="-2">This is a personalized study guide on Learning from the MISO Interview, generated for you on 2026-04-08.</rate></voice>
```

For voice switches mid-document (chapter headers, takeaway markers, warm closers), the voice/rate wrapper goes on the same line as the text it wraps. Add a `<silence msec="500"/>` at the end of that same line (not on its own line) for section breaks where you currently emit blank lines.

Voice routing logic in the existing `$voiceMap` switch is correct — keep all four format mappings (`StudyGuide`, `Review`, `Reflection`, `Session`) and the four approved Microsoft Online neural voices (Steffan, Guy, Aria, Jenny). Just change how they're emitted into the output string.

### 2. Patch the dispatcher at line ~881
Change:

```powershell
if ($sourceContent -match '\{\{Voice:') {
```

to:

```powershell
if ($sourceContent -match '<voice\s+required="Name=') {
```

So pre-tagged EbookAutomation content actually gets recognized and passed through unchanged.

Search the rest of `AutobookCmdlets.ps1` for any other references to `\{\{Voice:`, `\{\{Rate:`, `\{\{Silence:`, `\{\{Pause:` and update them to match real SAPI XML. There may be other dispatcher checks, doc comments, or examples.

### 3. Optional but recommended: update `.SYNOPSIS`
In the comment-based help for `Format-SBAutobookSSML`, change "Balabolka SSML voice tags" to "SAPI XML voice tags (compatible with balcon.exe)" so the contract is documented.

### 4. Add regression test in EbookAutomation
File: `F:\Projects\EbookAutomation\tools\test_voice_tags.py`

Add a new test class `TestSecondBrainTagFormat`. The test exercises the *output contract* — it does not need to import the PowerShell module; it validates a sample SecondBrain output string against the contract that the audiobook pipeline depends on.

Test cases:

1. `test_no_curly_voice_tags` — assert no `{{Voice` substring appears in any sample SecondBrain output
2. `test_no_curly_rate_tags` — assert no `{{Rate` substring
3. `test_no_curly_pause_or_silence_tags` — assert no `{{Pause` or `{{Silence` substring
4. `test_no_colon_tag_syntax` — assert no `{{Voice:`, `{{Rate:`, `{{Silence:`, `{{Pause:` substrings (the specific bug we fixed)
5. `test_voice_tag_xml_format` — assert any voice tag matches the regex `<voice required="Name=Microsoft (Steffan|Guy|Aria|Jenny) Online">`
6. `test_no_standalone_control_tag_lines` — assert no line in the sample contains *only* a control tag. Regex for a "bad" line: `^\s*<(voice|rate|silence)[^>]*/?>\s*$` (also catch closing `</voice>` / `</rate>` on their own). Every control tag must share its line with speakable text or other tags.
7. `test_approved_voices_only` — assert no occurrence of `Zira`, `Hazel`, `David`, or any voice name not ending in `Online`
8. `test_all_four_formats_have_intro_voice` — for each of the four `Format` values (StudyGuide, Review, Reflection, Session), assert the sample output for that format has its primary voice tag in the first non-empty content line

For sample fixtures, capture the actual output of `Format-SBAutobookSSML` after the patch for each of the four formats (use a short 3-paragraph stub StudyGuideText input) and paste them into the test file as multi-line string constants. This locks in the fixed contract as a snapshot.

### 5. Verify test suite
Run from `F:\Projects\EbookAutomation\`:

```powershell
python -m pytest tools/test_voice_tags.py -v
python -m pytest tools/test_pipeline.py -v
```

Both must stay green. Expected: 75 + 8 = 83 voice tag tests pass, 41/41 pipeline tests pass.

### 6. Smoke test the actual audio
Regenerate one of the Delta Faucet prep files through the patched function:

1. Pick the shortest of the three Delta Faucet study packs
2. Run it through `Format-SBAutobookSSML` → `Invoke-Balabolka` → MP3
3. Open the resulting `.txt` and confirm:
   - No `{{Voice:` / `{{Rate:` / `{{Pause:` strings remain
   - All control tags are inlined (no lines containing only a tag — visually scan or `Select-String -Pattern '^\s*<(voice|rate|silence)[^>]*/?>\s*$'` should return zero matches)
4. Listen to the first 30 seconds of the MP3 and confirm balcon does not speak the tags aloud

## Reporting
When done, report:

1. File path of `AutobookCmdlets.ps1` in the SecondBrain module
2. Commit hash for the SecondBrain patch (include line count delta for `Format-SBAutobookSSML` since it's being restructured)
3. Commit hash for the EbookAutomation `test_voice_tags.py` addition
4. Test results: `83/83 voice tag tests, 41/41 pipeline tests`
5. Confirmation from the smoke test: filename of the regenerated MP3 + one-sentence verdict on whether balcon spoke any tags aloud
