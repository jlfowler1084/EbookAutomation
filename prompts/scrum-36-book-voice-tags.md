# SCRUM-36: Balabolka Voice Tags for Book Conversions

## Session Name
SCRUM-36 Book Voice Tags

## Claude Code Model
Sonnet

## Jira
SCRUM-36 — In Progress

## Overview
Add Tier 2 voice tags to book TTS output: detect dialogue/quoted speech in prose and wrap it in Balabolka `<voice>` tags so the TTS engine uses a different voice for dialogue vs narration. This extends the existing Tier 1 structural tags (silences, emphatic closers) with voice differentiation.

**Existing infrastructure** (do NOT modify):
- `apply_voice_tags()` at line ~7025 in `pdf_to_balabolka.py` — handles Tier 1 structural tags
- `_silence_tag()`, `_rate_wrap()` — helper functions
- `--tts-enhance` CLI flag enables voice tagging
- FOH brief template uses the same `<voice required="Name=...">` tag format

**CRITICAL**: `pdf_to_balabolka.py` is 11,000+ lines. Use `grep -n` to find exact locations.

## Project Root
`F:\Projects\EbookAutomation\`

---

## Voice Assignments

These are the approved Microsoft Online voices (never use offline/SAPI voices):

| Voice | Role | Tag |
|-------|------|-----|
| Microsoft Steffan Online | Narrator (default) | No tags needed — Steffan reads everything untagged |
| Microsoft Guy Online | Male dialogue | `<voice required="Name=Microsoft Guy Online">` |
| Microsoft Aria Online | Female formal / blockquotes | `<voice required="Name=Microsoft Aria Online">` |
| Microsoft Jenny Online | Female conversational | `<voice required="Name=Microsoft Jenny Online">` |

**Default behavior**: All detected dialogue → Guy Online (male voice). Gender-aware voice assignment via Claude API is a future enhancement, not part of this ticket.

**Blockquotes / epigraphs**: When a paragraph is a blockquote (indented, italic, or starts with `>`), use Aria Online for formal citations.

---

## Part 1: Voice Tag Configuration in `settings.json`

Add a `voice_tags` section:

```json
{
  "voice_tags": {
    "enabled": true,
    "dialogue_voice": "Microsoft Guy Online",
    "blockquote_voice": "Microsoft Aria Online",
    "narrator_voice": "Microsoft Steffan Online",
    "dialogue_silence_before_ms": 150,
    "dialogue_silence_after_ms": 200,
    "blockquote_silence_before_ms": 200,
    "blockquote_silence_after_ms": 300
  }
}
```

---

## Part 2: Dialogue Detection Function

Add to `pdf_to_balabolka.py` near the existing voice tag functions (grep for `def apply_voice_tags`):

```python
def detect_dialogue_spans(paragraph):
    """Detect quoted speech spans in a paragraph.

    Returns a list of (start, end, quote_text) tuples for each dialogue span.
    Handles:
    - Double-quoted dialogue: "Hello," she said.
    - Smart-quoted dialogue: \u201cHello,\u201d she said.
    - Single-quoted dialogue in British style: 'Hello,' she said.

    Does NOT tag:
    - Very short quotes (< 3 words) — likely emphasis, not dialogue
    - Quotes that contain only numbers or single words
    - Quotes inside parentheses (likely citations)
    """
    spans = []

    # Pattern for double-quoted and smart-quoted dialogue
    # Matches: "...", \u201c...\u201d, and mixed variants
    patterns = [
        # Standard double quotes
        re.compile(r'"([^"]{10,})"'),
        # Smart double quotes (left/right)
        re.compile(r'\u201c([^\u201d]{10,})\u201d'),
        # Escaped smart quotes (in case normalization already ran)
        re.compile(r'"([^"]{10,})"'),
    ]

    for pattern in patterns:
        for m in pattern.finditer(paragraph):
            quote_text = m.group(1).strip()
            # Filter: at least 3 words
            if len(quote_text.split()) < 3:
                continue
            # Filter: not just numbers
            if re.match(r'^[\d\s.,]+$', quote_text):
                continue
            spans.append((m.start(), m.end(), quote_text))

    # Deduplicate overlapping spans (keep longest)
    if len(spans) > 1:
        spans.sort(key=lambda s: s[0])
        deduped = [spans[0]]
        for s in spans[1:]:
            if s[0] >= deduped[-1][1]:  # no overlap
                deduped.append(s)
            elif (s[1] - s[0]) > (deduped[-1][1] - deduped[-1][0]):
                deduped[-1] = s  # replace with longer span
        spans = deduped

    return spans
```

---

## Part 3: Voice Wrapping Helper

Add near the existing `_silence_tag()` and `_rate_wrap()` functions:

```python
def _voice_wrap(text, voice_name, syntax):
    """Wrap text in a voice tag for Balabolka/SAPI TTS."""
    if syntax == 'universal':
        return text  # Universal syntax doesn't support voice switching
    return f'<voice required="Name={voice_name}">{text}</voice>'
```

---

## Part 4: Extend `apply_voice_tags()` with Dialogue Voice Tags

This is the core change. The existing function handles Tier 1 (structural). Add Tier 2 (dialogue voices) as an additional pass.

**Find**: `def apply_voice_tags(paragraphs, chapter_structure, tag_syntax='sapi', options=None, log=lambda m: None)` (grep for it)

**Approach**: After the existing structural tagging loop, add a second pass that scans the output for dialogue and wraps it in voice tags. This keeps the two tiers cleanly separated.

Add the `voice_tags_enabled` option and dialogue processing:

```python
def apply_voice_tags(paragraphs, chapter_structure, tag_syntax='sapi', options=None, log=lambda m: None):
    """Apply structural (Tier 1) and dialogue (Tier 2) voice tags to paragraphs."""
    if options is None:
        options = {
            'chapter_silence': True,
            'scene_break_silence': True,
            'emphatic_closers': True,
            'dialogue_voices': False,  # NEW: Tier 2
        }

    # ... existing Tier 1 code stays exactly as-is ...

    # ── Tier 2: Dialogue voice tags ──────────────────────────────────
    if options.get('dialogue_voices', False):
        output = _apply_dialogue_voices(output, tag_syntax, options, log)

    return output
```

Then add the dialogue voice application function:

```python
def _apply_dialogue_voices(paragraphs, tag_syntax, options, log):
    """Apply voice tags to detected dialogue spans in paragraphs.

    Narrator text (Steffan) is untagged. Detected dialogue gets wrapped
    in <voice> tags for Guy Online (default dialogue voice).

    Blockquotes (lines starting with >) get Aria Online.
    """
    # Load voice config
    try:
        from pathlib import Path
        config_path = Path(__file__).parent / 'settings.json'
        if config_path.exists():
            import json as _json
            with open(config_path) as f:
                cfg = _json.load(f).get('voice_tags', {})
        else:
            cfg = {}
    except Exception:
        cfg = {}

    dialogue_voice = cfg.get('dialogue_voice', 'Microsoft Guy Online')
    blockquote_voice = cfg.get('blockquote_voice', 'Microsoft Aria Online')
    dlg_silence_before = cfg.get('dialogue_silence_before_ms', 150)
    dlg_silence_after = cfg.get('dialogue_silence_after_ms', 200)
    bq_silence_before = cfg.get('blockquote_silence_before_ms', 200)
    bq_silence_after = cfg.get('blockquote_silence_after_ms', 300)

    tagged_count = 0
    blockquote_count = 0
    result = []

    for p in paragraphs:
        # Skip empty, silence tags, or already-tagged content
        if not p or p.startswith('<silence') or p.startswith('{{Pause'):
            result.append(p)
            continue

        # Blockquote detection: lines starting with > or tab-indented blockquote markers
        stripped = p.strip()
        if stripped.startswith('>') or stripped.startswith('\t>'):
            # Strip the > prefix, wrap in blockquote voice
            bq_text = re.sub(r'^>\s*', '', stripped)
            tagged = (_silence_tag(bq_silence_before, tag_syntax) +
                      _voice_wrap(bq_text, blockquote_voice, tag_syntax) +
                      _silence_tag(bq_silence_after, tag_syntax))
            result.append(tagged)
            blockquote_count += 1
            continue

        # Dialogue detection within prose paragraphs
        spans = detect_dialogue_spans(p)
        if not spans:
            result.append(p)
            continue

        # Build the paragraph with voice tags inserted around dialogue
        tagged_para = _build_voiced_paragraph(
            p, spans, dialogue_voice, dlg_silence_before, dlg_silence_after,
            tag_syntax
        )
        result.append(tagged_para)
        tagged_count += len(spans)

    if tagged_count or blockquote_count:
        log(f"  Voice tags: {tagged_count} dialogue spans, {blockquote_count} blockquotes")

    return result


def _build_voiced_paragraph(paragraph, spans, voice_name, silence_before, silence_after, tag_syntax):
    """Reconstruct a paragraph with voice tags wrapped around dialogue spans.

    The narrator reads attribution text (he said, she replied) and the
    dialogue voice reads the quoted text.

    Example input:  'He turned and said, "I never meant for this to happen." She nodded slowly.'
    Example output: 'He turned and said, <silence msec="150"/><voice required="Name=Microsoft Guy Online">"I never meant for this to happen."</voice><silence msec="200"/> She nodded slowly.'
    """
    parts = []
    last_end = 0

    for start, end, _ in spans:
        # Narrator text before the quote
        if start > last_end:
            parts.append(paragraph[last_end:start])

        # The quoted text (including quote marks)
        quote_with_marks = paragraph[start:end]
        parts.append(_silence_tag(silence_before, tag_syntax))
        parts.append(_voice_wrap(quote_with_marks, voice_name, tag_syntax))
        parts.append(_silence_tag(silence_after, tag_syntax))

        last_end = end

    # Remaining narrator text after last quote
    if last_end < len(paragraph):
        parts.append(paragraph[last_end:])

    return ''.join(parts)
```

---

## Part 5: Wire `dialogue_voices` Option Through the Pipeline

### In `format_output()` (grep for `def format_output`)
The function already calls `apply_voice_tags()`. Update to pass the dialogue option:

```python
def format_output(paragraphs, chapter_structure, log, tts_enhance=False,
                  tag_syntax='sapi', dialogue_voices=False):
    if tts_enhance:
        options = {
            'chapter_silence': True,
            'scene_break_silence': True,
            'emphatic_closers': True,
            'dialogue_voices': dialogue_voices,
        }
        tagged = apply_voice_tags(paragraphs, chapter_structure,
                                  tag_syntax=tag_syntax, options=options, log=log)
        return "\n\n".join(tagged)
    # ... rest unchanged
```

### In `process_balabolka()` / balabolka mode
Find where `format_output()` is called (grep for `format_output` in the process functions). Pass through `dialogue_voices`:

```python
final_text = format_output(body, _cs, log, tts_enhance=tts_enhance,
                           tag_syntax=tag_syntax,
                           dialogue_voices=dialogue_voices)
```

Add `dialogue_voices=False` parameter to `process_balabolka()` (grep for `def process_balabolka` — it's actually in the unnamed main processing functions; find each call to `format_output` and trace back to the function signature).

### CLI flag
Find the argparse setup. Add:

```python
ap.add_argument("--dialogue-voices", action="store_true", default=False,
                help="Tag detected dialogue with alternate TTS voice (Guy Online)")
```

Pass it through wherever `format_output()` is called:

```python
dialogue_voices=args.dialogue_voices,
```

**Note**: `--dialogue-voices` implies `--tts-enhance` (voice tags only make sense if TTS enhancement is active). If `--dialogue-voices` is set but `--tts-enhance` is not, auto-enable tts_enhance:

```python
if args.dialogue_voices and not args.tts_enhance:
    args.tts_enhance = True
    log_fn("[cli] --dialogue-voices implies --tts-enhance, enabling")
```

### PSM1 parameter
Add `-DialogueVoices` switch to `Convert-ToTTS`:

```powershell
[switch]$DialogueVoices
```

Wire into the Python argument building:

```powershell
if ($DialogueVoices) {
    $extractArgs += " --dialogue-voices"
    Write-EbookLog "TTS: dialogue voice tags ENABLED"
}
```

---

## Part 6: Tests

Add test cases to `test_voice_tags.py`:

### Test `detect_dialogue_spans()`
```python
def test_detect_dialogue_basic(self):
    spans = detect_dialogue_spans('He said, "I never meant for this to happen." She nodded.')
    assert len(spans) == 1
    assert spans[0][2] == 'I never meant for this to happen.'

def test_detect_dialogue_multiple(self):
    text = '"Where are you going?" she asked. "To the store," he replied.'
    spans = detect_dialogue_spans(text)
    assert len(spans) == 2

def test_detect_dialogue_short_ignored(self):
    """Quotes under 3 words are not dialogue — likely emphasis."""
    spans = detect_dialogue_spans('She said "no" firmly.')
    assert len(spans) == 0

def test_detect_dialogue_smart_quotes(self):
    spans = detect_dialogue_spans('He whispered, \u201cThis changes everything between us.\u201d')
    assert len(spans) == 1
```

### Test `_build_voiced_paragraph()`
```python
def test_build_voiced_simple(self):
    para = 'He said, "I never meant for this to happen." She nodded.'
    spans = detect_dialogue_spans(para)
    result = _build_voiced_paragraph(para, spans, 'Microsoft Guy Online', 150, 200, 'sapi')
    assert '<voice required="Name=Microsoft Guy Online">' in result
    assert '<silence msec="150"/>' in result
    assert '<silence msec="200"/>' in result
    assert 'She nodded.' in result  # narrator text preserved
```

### Test `apply_voice_tags()` with dialogue
```python
def test_apply_voice_tags_dialogue(self):
    paras = [
        '# Chapter One',
        'He walked into the room.',
        '"I have been waiting for you," she said quietly.',
        'The door closed behind him.',
    ]
    cs = self._cs(chapters=[0])
    options = {'chapter_silence': True, 'scene_break_silence': True,
               'emphatic_closers': True, 'dialogue_voices': True}
    out = apply_voice_tags(paras, cs, tag_syntax='sapi', options=options, log=nolog)
    # Chapter heading should be uppercased
    assert out[0] == '# CHAPTER ONE'
    # Dialogue paragraph should have voice tags
    tagged_para = [p for p in out if 'Microsoft Guy Online' in p]
    assert len(tagged_para) == 1

def test_apply_voice_tags_no_dialogue_by_default(self):
    """Dialogue voices off by default — no <voice> tags appear."""
    paras = ['"Hello there," he said.']
    cs = self._cs()
    out = apply_voice_tags(paras, cs, tag_syntax='sapi', log=nolog)
    assert '<voice' not in out[0]
```

---

## Testing

```bash
cd F:\Projects\EbookAutomation
python -m pytest tests/ -x -v
python -m pytest test_voice_tags.py -x -v
```
All existing tests must pass plus new dialogue voice tag tests.

### Manual verification
```bash
# Generate TTS output with dialogue voices:
python pdf_to_balabolka.py --input "inbox\some-fiction-book.pdf" --mode balabolka --tts-enhance --dialogue-voices --output-dir output\balabolka-txt

# Check the output file for voice tags:
# Should see: <voice required="Name=Microsoft Guy Online">..."dialogue"...</voice>
# around detected dialogue, with silence tags flanking each voice switch.
```

---

## Git
```bash
git add -A
git commit -m "SCRUM-36: Balabolka voice tags for book conversions

- Add detect_dialogue_spans() for quoted speech detection in prose
- Add _voice_wrap() helper for <voice required='Name=...'> tags
- Extend apply_voice_tags() with Tier 2 dialogue voice tagging
- Dialogue → Guy Online, blockquotes → Aria Online, narrator → Steffan (untagged)
- Configurable voices and silence timings in settings.json voice_tags section
- --dialogue-voices CLI flag (implies --tts-enhance)
- -DialogueVoices PSM1 switch on Convert-ToTTS
- Test coverage for dialogue detection, voice wrapping, and integration"
git push origin master
```

## Jira
After completion, comment on SCRUM-36 via MCP:
```
Shipped Balabolka voice tags for book conversions:
- detect_dialogue_spans() finds quoted speech in prose paragraphs
- Dialogue wrapped in <voice required="Name=Microsoft Guy Online"> tags
- Blockquotes wrapped in Aria Online voice
- Narrator (Steffan) reads all untagged text
- Silence tags flank voice switches (150ms before, 200ms after dialogue)
- Configurable voices/timings in settings.json voice_tags section
- --dialogue-voices CLI flag, -DialogueVoices PSM1 switch
- Tests for dialogue detection, voice wrapping, and full pipeline integration
- All tests pass, zero regression
```
Then transition SCRUM-36 → Done (transition ID 41).
