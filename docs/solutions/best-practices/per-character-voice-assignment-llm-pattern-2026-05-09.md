---
title: "Per-Character Voice Assignment for Fiction TTS: LLM Attribution Pattern (Balabolka/SAPI Path)"
date: 2026-05-09
category: docs/solutions/best-practices
module: tts-voice-assignment
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "Fiction source material with multiple named speaking characters"
  - "Output target is the Balabolka/SAPI TTS path (not Kokoro)"
  - "OpenAI-compatible LLM endpoint available (Ollama, sb-chat, or compatible service)"
  - "Extending apply_voice_tags() with a new Tier pass"
related_components:
  - development_workflow
tags:
  - tts
  - voice-tags
  - per-character
  - balabolka
  - sapi-xml
  - llm-integration
  - speaker-attribution
  - fiction
---

# Per-Character Voice Assignment for Fiction TTS: LLM Attribution Pattern (Balabolka/SAPI Path)

## Context

EbookAutomation's `apply_voice_tags()` previously assigned a single uniform `dialogue_voice` to all
detected dialogue spans. For fiction with multiple named characters, this produces a flat,
hard-to-follow listening experience — every character sounds identical regardless of who is speaking.

EB-198 introduced a Tier 2b pass (`_apply_per_character_voices`) that uses LLM-based speaker
attribution to assign each named character a distinct SAPI voice, while preserving full backward
compatibility: no LLM call is made and output is bit-identical when the feature is disabled.

The core design — greedy character→voice mapping with chapter-level LLM batching and a
fallback-safe wrapper — was established in
`docs/brainstorms/2026-04-13-local-llm-integration-opportunities.md` (entry #17) before
implementation began (session history). The ticket spec referenced sb-chat (vLLM at `localhost:8000`)
as the attribution endpoint, but sb-chat was not running during implementation; Ollama at
`localhost:11434` was used as the default, with both endpoint URL and model configurable in
`config/settings.json` (session history).

## Guidance

### 1. Attribution as Pre-Pass Architecture

Run attribution against the original `paragraphs` list **before** Tier 1 processes headings. Build a
`span_text → voice_name` map at this stage; Tier 2b then looks up spans by text content in the
Tier-1-processed `output` list.

This works because Tier 1 only modifies heading paragraphs — it never alters body paragraph text.
Running attribution before Tier 1 operates on source-faithful text and does not depend on Tier 1
output structure.

```python
# In apply_voice_tags(), before Tier 1 runs:
if options.get('per_character_voices', False):
    span_voice_map, char_voice_map = _build_book_attribution(
        paragraphs, chapter_structure, llm_cfg, confidence_threshold, log
    )
# ... Tier 1 modifies headings in output[] here ...
# Tier 2b uses the pre-built span_voice_map on the now-processed output[]
```

### 2. Fallback-Safe LLM Wrapper

The attribution function must **never raise**. Any failure — `ImportError` for the `openai` library,
connection refused, timeout, malformed JSON — returns a list of `(None, 0.0)` tuples, one per span.
This ensures the pipeline degrades gracefully to the uniform `dialogue_voice` fallback rather than
aborting TTS generation mid-book.

```python
import logging
from openai import OpenAI

def _attribute_chapter_speakers(
    chapter_paragraphs: list[str],
    span_texts: list[str],
    llm_url: str,
    model: str,
    log: logging.Logger,
) -> list[tuple[str | None, float]]:
    """
    Inserts [SPAN_N] markers into a chapter excerpt and calls an
    OpenAI-compatible LLM endpoint. Returns [(speaker|None, confidence)].
    Never raises — any failure returns [(None, 0.0)] * n.
    """
    n = len(span_texts)
    try:
        # Build excerpt: replace each span with [SPAN_N] marker inline
        excerpt = _build_marked_excerpt(chapter_paragraphs, span_texts)
        client = OpenAI(base_url=llm_url, api_key="na")
        resp = client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": (
                    "You are a literary assistant. For each [SPAN_N] marker in the passage, "
                    "identify the speaker. Return JSON: "
                    '[{"span": N, "speaker": "Name or null", "confidence": 0.0-1.0}]'
                )},
                {"role": "user", "content": excerpt},
            ],
        )
        raw = resp.choices[0].message.content or "[]"
        parsed: list[dict] = json.loads(raw)
        by_idx = {item["span"]: (item.get("speaker"), float(item.get("confidence", 0.0)))
                  for item in parsed}
        return [by_idx.get(i, (None, 0.0)) for i in range(n)]
    except Exception as exc:
        log.warning("Speaker attribution failed (%s); falling back to uniform voice", exc)
        return [(None, 0.0)] * n
```

Use `temperature=0.1` for attribution consistency. `temperature=0` can trigger repetition loops
on structured JSON output when the schema itself has structural repetition — this was observed
during SCRUM-275 VQA debugging with the same endpoint stack (session history).

### 3. Greedy Voice Map

Assign voices greedily in first-appearance order across the book. Cycle through the available
voice list for books with more than three named speakers. Declare the pool as a module-level
constant so it can be adjusted without touching function signatures.

```python
_DIALOGUE_VOICES_ORDERED = [
    'Microsoft Guy Online',
    'Microsoft Jenny Online',
    'Microsoft Aria Online',
]

def _build_character_voice_map(speakers_in_order: list[str | None]) -> dict[str, str]:
    voice_map = {}
    idx = 0
    for name in speakers_in_order:
        if name and name not in voice_map:
            voice_map[name] = _DIALOGUE_VOICES_ORDERED[idx % len(_DIALOGUE_VOICES_ORDERED)]
            idx += 1
    return voice_map
```

`speakers_in_order` is the sequence of speaker names as they appear across chapter attributions.
`None` entries are safe — the `if name` guard skips them.

### 4. Confidence Threshold and Fallback

Each attributed span carries a confidence score from the LLM. Spans below the configured threshold
(default: `0.7`) are treated as unattributed and receive the uniform `fallback_voice`. Log the
fallback count per chapter so attribution gaps are visible without being noisy.

```python
def _build_voiced_paragraph_attributed(
    paragraph: str,
    spans: list,
    span_voice_map: dict[str, str],
    fallback_voice: str,
    tag_syntax: str,
    log: logging.Logger,
) -> tuple[str, int]:
    """Returns (tagged_str, fallback_count)."""
    fallback_count = 0
    parts = []
    for span in spans:
        voice = span_voice_map.get(span.text)
        if voice:
            parts.append(wrap_in_voice_tag(span.text, voice, tag_syntax))
        else:
            parts.append(wrap_in_voice_tag(span.text, fallback_voice, tag_syntax))
            fallback_count += 1
    return "".join(parts), fallback_count
```

**Invariant:** `span_voice_map` keys on `span.text` (raw span text from the original `paragraphs`
list). This is safe because Tier 1 never mutates body paragraph text — only heading paragraphs
are modified. If Tier 1 scope ever expands to modify body text, the lookup will silently degrade
to `fallback_voice` for all affected spans. Guard this with an assertion in the Tier 2b entry if
the invariant becomes less obvious over time.

### 5. Tier 2b Pass Wiring

The Tier 2 block in `apply_voice_tags()` branches on `per_character_voices` first, with the
existing `dialogue_voices` path as the else branch. This preserves backward compatibility: callers
passing `dialogue_voices=True` are unaffected.

```python
if options.get('per_character_voices', False):
    try:
        _cfg_path = Path(__file__).resolve().parent.parent / 'config' / 'settings.json'
        with open(_cfg_path, 'r', encoding='utf-8') as _f:
            _pc_cfg = json.load(_f).get('voice_tags', {}).get('per_character', {})
    except Exception:
        _pc_cfg = {}
    _threshold = max(0.0, min(1.0, float(_pc_cfg.get('confidence_threshold', 0.7))))
    span_voice_map, _ = _build_book_attribution(
        paragraphs, chapter_structure, _pc_cfg, _threshold, log
    )
    output = _apply_per_character_voices(output, span_voice_map, tag_syntax, options, log)
elif options.get('dialogue_voices', False):
    output = _apply_dialogue_voices(output, tag_syntax, options, log)
```

`config/settings.json` schema addition:

```json
"voice_tags": {
    "per_character": {
        "enabled": false,
        "attribution_url": "http://localhost:11434/v1",
        "attribution_model": "qwen3.5:122b-a10b",
        "confidence_threshold": 0.7
    }
}
```

The `attribution_url` defaults to Ollama at `localhost:11434`. Point it at sb-chat
(`localhost:8000`) when that service is running. Because sb-chat is a shared stack across
EbookAutomation, SecondBrain, and CareerPilot, any session that routes per-character attribution
through sb-chat should flag it as a `NEW DEPENDENCY` in the session summary (auto memory [claude]).

The CLI flag is `--per-character-voices`, which implies `--tts-enhance`. The feature is off by
default.

## Why This Matters

Fiction audiobooks with dialogue-heavy chapters become significantly more intelligible when each
character has a consistent voice. A two-character exchange where each speaker uses the same voice
throughout the book allows listeners to track turns without relying on attribution phrases ("she
said", "he replied").

The pre-pass architecture keeps LLM call volume proportional to chapter count, not paragraph count.
A 20-chapter novel makes 20 attribution calls, not 400+. Chapter-level batching was specified in
the original ticket as the latency mitigation (session history).

The fallback-safe wrapper is non-negotiable: a hard failure in LLM attribution during a 400-page
novel would otherwise abort TTS generation entirely. The graceful degradation path ensures the
pipeline always produces output even if attribution quality varies by chapter.

Without this pattern, ad-hoc approaches (per-paragraph LLM calls, or running attribution after
Tier 1) risk double-processing heading text or incorrect span lookups due to Tier 1 mutations.

## When to Apply

Apply when:
- The source material is fiction with multiple named speaking characters
- The output target is the **Balabolka/SAPI TTS path** (not Kokoro — see Scope Boundary)
- An OpenAI-compatible LLM endpoint is available (Ollama, sb-chat, or any compatible service)
- `--per-character-voices` is passed on the CLI, or `per_character_voices=True` is in options

Do not apply when:
- The source is non-fiction, academic, or reference material (dialogue is rare; attribution adds
  noise without benefit)
- The output target is Kokoro ONNX (requires multi-speaker audio stitching, not inline SAPI tags)
- No LLM endpoint is available (the feature degrades to uniform voice, but LLM startup overhead
  is still incurred at call-site)

**Contract constraint:** All new TTS voice emission paths must pass
`test_voice_tags.py::TestSecondBrainTagFormat`, which enforces the approved voice name allowlist
(`Microsoft Steffan|Guy|Aria|Jenny Online`) across 75 snapshot fixtures (session history). Any
addition to `_DIALOGUE_VOICES_ORDERED` must update this allowlist.

## Examples

**Before (uniform `dialogue_voice` — Tier 2 only):**

```
"I never wanted this," Elena said.
"You didn't have a choice," Marcus replied.
```

Rendered with both spans assigned to `dialogue_voice` (Jenny Online):

```xml
<voice required="Name=Microsoft Jenny Online">
"I never wanted this," Elena said.
</voice>
<voice required="Name=Microsoft Jenny Online">
"You didn't have a choice," Marcus replied.
</voice>
```

Both characters read in Jenny's voice. Listener cannot distinguish speaker from voice alone.

**After (per-character voices — EB-198):**

LLM attribution: Elena → first appearance → `Microsoft Jenny Online`; Marcus → second
appearance → `Microsoft Guy Online`. Confidence ≥ 0.7 for both.

```xml
<voice required="Name=Microsoft Jenny Online">
"I never wanted this," Elena said.
</voice>
<voice required="Name=Microsoft Guy Online">
"You didn't have a choice," Marcus replied.
</voice>
```

Each character has a consistent voice throughout the book. Spans the LLM could not attribute with
confidence ≥ 0.7 fall back to the configured `dialogue_voice`.

## Scope Boundary: Kokoro Requires Multi-Speaker Audio Stitching

Per-character voice assignment as implemented in EB-198 applies **exclusively to the
Balabolka/SAPI TTS path**. SAPI XML inline tags (`<voice required="Name=...">`) are a native
Balabolka feature — the engine switches voice mid-document during rendering with no audio stitching.

Kokoro ONNX synthesis has no equivalent inline switching mechanism. Per-character voices for Kokoro
would require:

1. Segment text into speaker-attributed spans
2. Synthesize each span independently with a different voice model or speaker embedding
3. Stitch the resulting audio segments in sequence

This is a distinct engineering problem (multi-speaker TTS pipeline design, not SAPI XML tagging)
and was explicitly deferred to a follow-on ticket. Do not attempt to reuse
`_apply_per_character_voices()` or the `span_voice_map` lookup pattern for Kokoro output without
first designing the audio-segment stitching layer.

## Related

- `docs/brainstorms/2026-04-13-local-llm-integration-opportunities.md` — Entry #17: original design
  sketch for this feature (session history)
- `docs/solutions/integration-issues/kokoro-onnx-v050-windows-integration-2026-05-09.md` — Kokoro
  ONNX TTS backend (the alternative path where this pattern does not apply)
- `tools/test_voice_tags.py::TestSecondBrainTagFormat` — Voice name allowlist enforcement (75
  snapshot fixtures, unchanged by EB-198)
- EB-198 — Jira ticket
