# Font-Based Heading Detection & Get-ChapterStructure Rewrite

**Date:** 2026-03-23
**Status:** Design approved
**Approach:** Sequential Two-File Implementation (Approach A)

## Problem

`Get-ChapterStructure` sends ~4000 words + sparse samples to Claude. On Burge ("Jesus and the Land"), Claude found only 2 back-matter headings (Notes, Further Reading) — real chapters like "4 The Fourth Gospel and the land" were never seen because they're past the front-matter window. Font analysis can scan every page in <5 seconds and catch these headings structurally.

Three root causes:
1. **Sampling is front-loaded** — 4000 words from the start captures front matter, not mid-book chapters
2. **Claude prompt doesn't prioritize** — treats "Notes" and "Chapter 4" equally
3. **No structural hints** — Claude searches raw text with no font/styling information

## Architecture

Two components, clean separation:

1. **`tools/detect_headings_font.py`** — Standalone CLI tool. Scans full PDF/EPUB, outputs JSON heading candidates with confidence scores.
2. **`Get-ChapterStructure` rewrite** (in `EbookAutomation.psm1`) — New three-zone sampling, integrates font candidates into Claude prompt, per-heading insertion.

The font detector always runs regardless of extraction path (pdfminer, PyMuPDF, or pypdf). The detector's purpose (heading identification with confidence scoring and header/footer dedup) is distinct from the extraction path's purpose (text extraction with font metadata as byproduct). The detector provides a clean JSON list Claude can work with directly — no HTML parsing needed.

## Component 1: `detect_headings_font.py`

### CLI Interface

```
python tools/detect_headings_font.py --input "path/to/book.pdf"
python tools/detect_headings_font.py --input "path/to/book.pdf" --format json
python tools/detect_headings_font.py --input "path/to/book.epub"
python tools/detect_headings_font.py --input "path/to/book.pdf" --verbose
python tools/detect_headings_font.py --input "F:\Books\*.pdf" --verbose
```

- `--input` (required): Path to PDF or EPUB. Supports glob patterns via Python `glob.glob()` — if multiple matches, process first and warn on stderr. If zero matches, error.
- `--epub` (optional): Force EPUB parsing mode. Auto-detected from `.epub` extension if omitted — flag only needed for non-standard extensions.
- `--format` (optional): `json` (default) or `text` (human-readable summary for debugging)
- `--verbose` (optional): Diagnostic info to stderr (font histogram, candidate count per page, filtering decisions)

### PDF Detection Algorithm

**Page sampling:** Scan all pages except first 2 (cover/title). No back-matter exclusion — the detector finds ALL headings. Back-matter classification happens at the Claude prompt level.

**Font profile construction:**
- Extract every text span via `page.get_text("dict")` → blocks → lines → spans
- Track `(font_name, font_size, flags)` per span
- `flags & 2^4` (bit 4) = bold; `flags & 2^1` (bit 1) = italic
- Character-count-weighted frequency histogram of font sizes
- **Body font size** = font size with highest total character count

**Heading candidate identification** — a text block qualifies if ANY of:
1. Font size >= 1.5x body size
2. Bold AND font size >= 1.2x body size
3. Matches chapter pattern: `^(Chapter|Part|CHAPTER|PART)\s+\d+`, `^\d+\.\s+\w`, `^[IVXLC]+\.\s+\w`, `^(Introduction|Conclusion|Preface|Foreword|Epilogue|Prologue|Appendix)`

**Noise filtering** — remove candidates that are:
- **Headers/footers:** Same text at same y-coordinate (+-5pt) on >50% of sampled pages
- **Page numbers:** Purely numeric or Roman numeral strings with no other text
- **Too short/long:** <3 chars or >120 chars
- **Running headers:** All-caps single words on >30% of pages

**Level assignment:**
- h1: Largest font size among candidates, OR matches Chapter/Part pattern
- h2: Second-largest font size, OR bold at body-size + 2pt
- h3: Third-largest or bold at body size

**Confidence scoring** (base 0.3, additive, capped at 0.99):
- Font size ratio >= 1.5x: +0.3
- Bold: +0.2
- Matches chapter pattern: +0.3
- Centered on page: +0.1
- Short text (<= 10 words): +0.1

Single-signal candidates score ~0.5, multi-signal candidates ~0.8-0.99.

### EPUB Detection Algorithm

**Step 1 — NCX/nav extraction (first check):**
- Check if EPUB has `toc.ncx` or `nav.xhtml` with >= 3 entries
- If yes, extract NCX entries as heading candidates at confidence 0.95 — publisher's own TOC structure, most reliable source
- NCX entries become the anchor; HTML parsing supplements for gaps

**Step 2 — HTML parsing (supplement):**
1. Semantic headings: `<h1>`, `<h2>`, `<h3>` tags — confidence 0.95
2. Class-styled headings: CSS classes containing `chapter`, `heading`, `title`, `part`, `section` — confidence 0.85
3. Inline-styled headings: `font-size` significantly larger than body OR `font-weight: bold` with larger font — confidence 0.75
4. Structural patterns: `<div>`/`<p>` matching chapter regexes — confidence 0.70

Deduplicate against NCX entries — don't double-count headings found in both NCX and HTML.

**EPUB level assignment:**
- Native `<h1>` → h1, `<h2>` → h2, `<h3>` → h3
- NCX entries: infer from nesting depth
- Class-styled: `part` → h1, `chapter` → h1, `section` → h2

**EPUB-specific fields:** `page` = spine document index. `font_size`/`font_name` = `null` when detected from semantic tags or NCX. `detection_signals` includes `"ncx_toc"`, `"semantic_h1"`, `"css_class:chapter"`, etc.

### Output JSON Schema

```json
{
  "file": "path/to/book.pdf",
  "format": "pdf",
  "body_font_size": 11.0,
  "body_font_name": "TimesNewRomanPSMT",
  "total_pages": 173,
  "pages_scanned": 171,
  "heading_candidates": [
    {
      "text": "4 The Fourth Gospel and the land",
      "page": 45,
      "level": "h1",
      "font_size": 16.0,
      "font_name": "TimesNewRomanPS-BoldMT",
      "is_bold": true,
      "confidence": 0.90,
      "detection_signals": ["font_size_ratio:1.45", "bold", "numbered_chapter"]
    }
  ],
  "font_histogram": {"11.0": 4523, "16.0": 12, "13.0": 45}
}
```

### `--format text` Output

```
Font Analysis: Burge - Jesus and the Land.pdf
Body font: TimesNewRomanPSMT @ 11.0pt (4523 chars)
Pages scanned: 171 of 173

Heading Candidates (14 found):
  h1  p.5   [0.85] "Preface" (16pt bold)
  h1  p.15  [0.90] "1 Promised land in the Old Testament" (16pt bold)
  ...
```

### Error Handling

- File not found / zero glob matches → exit 1, `{"error": "..."}`
- Unsupported format → exit 1, `{"error": "..."}`
- fitz import failure → exit 1, `{"error": "PyMuPDF (fitz) not installed"}`
- Zero candidates → exit 0, valid JSON with empty `heading_candidates`
- Glob resolves multiple files → process first match, warn on stderr
- All stdout is valid JSON; diagnostics to stderr only

## Component 2: `Get-ChapterStructure` Rewrite

### Three-Zone Sampling

Replace "first 4000 words + 15 sparse 100-word samples" with:

- **Zone 1 — Front matter:** First 3000 words
- **Zone 2 — Body samples:** 8 x 500-word chunks at 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80% of total word count
- **Zone 3 — Back matter:** Last 2000 words
- **Total:** ~9000 words max (~$0.03 per call)

Zone boundaries labeled in text sent to Claude:
```
=== FRONT MATTER (first 3000 words) ===
[text]

=== BODY SAMPLE 1 (~page 25 of 173) ===
[text]

... (7 more body samples) ...

=== BACK MATTER (last 2000 words) ===
[text]
```

Page estimates: `floor(word_position / total_words * total_pages)`.

### Font Candidate Integration

Always run font detector before Claude call:

```powershell
$fontResult = & $python "tools/detect_headings_font.py" --input $InputFile --format json 2>$null
```

- Parse succeeds + candidates exist → include `=== FONT-DETECTED HEADING CANDIDATES ===` section in Claude prompt
- Parse fails or zero candidates → omit section, Claude works from text samples alone
- Font detector failure never blocks the pipeline

### Rewritten Claude Prompt

```
You are analyzing an ebook to build its table of contents. Identify the CHAPTER STRUCTURE.

PRIORITY ORDER:
1. MAIN CHAPTERS — numbered or titled divisions of core content
2. MAJOR SECTIONS — Parts containing chapters
3. FRONT MATTER — Preface, Foreword, Introduction, Acknowledgments
4. BACK MATTER — Notes, Bibliography, Index, Appendix (mark is_back_matter: true)

DO NOT treat as chapter headings:
- Running headers/footers repeated on every page
- Section sub-headings within a chapter
- Decorative text, epigraphs, pull quotes
- List items or numbered points within body text

{FONT_CANDIDATES_SECTION}

{SAMPLED_TEXT}

Respond with JSON array:
{
  "title": "exact heading text",
  "level": "h1" | "h2" | "h3",
  "is_back_matter": false,
  "page_estimate": 45,
  "confidence": 0.95,
  "notes": "optional"
}

Rules:
- h1 = chapter-level; h2 = sub-chapter; h3 = sub-sections
- Preserve exact capitalization and numbering
- If font candidates provided, use as primary guide + add anything missed
- If no font candidates, identify from text samples only
- Mark back matter with is_back_matter: true
- A book with 10 chapters should have >= 10 h1 entries
```

### EPUB Early-Exit

```powershell
if ($InputFile -match '\.epub$') {
    $existingH1 = [regex]::Matches($htmlContent, '<h1[^>]*>(.+?)</h1>')
    $backMatterKeywords = @('Notes','Bibliography','Index','Appendix','Glossary',
                            'References','Further Reading','Works Cited')
    $nonBackMatter = $existingH1 | Where-Object {
        $text = $_.Groups[1].Value
        -not ($backMatterKeywords | Where-Object { $text -match "^$_$" })
    }
    if ($nonBackMatter.Count -ge 5) {
        Write-EbookLog "Found $($nonBackMatter.Count) non-back-matter h1 headings — skipping Claude"
        return
    }
}
```

Skip only if >= 5 existing `<h1>` tags AND at least 5 of them are NOT back-matter keywords. If all h1s are back matter, that's the signal real chapters are missing — proceed with Claude.

### Per-Heading Insertion (Fix "Already Present" Bug)

Current: if any headings already present, skip ALL insertion. New: per-heading check.

**Text-matching strategy:**
1. Normalize heading text (strip whitespace, collapse internal whitespace)
2. Search HTML for exact text match inside `<p>`, `<div>`, or bare text nodes
3. If exact match fails, fuzzy: match first 5+ words
4. If found → check it's not already inside `<h1>`/`<h2>`/`<h3>` → wrap in appropriate heading tag (replacing `<p>`/`<div>`)
5. If not found → skip gracefully, log warning: `Write-EbookLog "Heading not found in HTML: ..."`
6. Never insert duplicate heading tags

### h3 Support (New)

- Parse h3 entries from Claude's response
- Insert as `<h3>` tags in HTML
- Add `--level3-toc "//h:h3"` to Calibre flags only when h3 headings actually exist

## Error Boundaries

| Failure | Behavior |
|---|---|
| `detect_headings_font.py` crashes | Log warning, proceed without font candidates |
| Font detector returns 0 candidates | Claude works from text samples alone |
| Claude returns malformed JSON | Strip markdown fences, retry parse; if fails, return `$null` |
| Heading text not found in HTML | Skip that heading, log warning, continue |
| EPUB has no NCX/nav | Fall through to HTML parsing |
| EPUB HTML parsing finds nothing | Fall through to Claude with text samples |
| Glob path resolves to 0 files | Exit 1 with clear error message |
| Glob path resolves to multiple files | Process first match, warn on stderr |

## Files Modified

| File | Change |
|---|---|
| `tools/detect_headings_font.py` | **New file** — standalone font-based heading detector |
| `module/EbookAutomation.psm1` | Rewrite `Get-ChapterStructure` — new sampling, font integration, prompt, per-heading insertion |

## Files NOT Modified

- `classify_source.py` — untouched
- `pattern_db.py` — untouched
- `pdf_to_balabolka.py` — untouched
- Converge loop strategy — untouched

## Test Plan

**Font detector standalone:**
```
python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge*.pdf" --verbose
→ Numbered chapters + Preface, NOT just Notes/Further Reading

python tools/detect_headings_font.py --input "F:\Books\Bible Study\Fruchtenbaum*.pdf" --verbose
→ Scanned PDF with OCR — detect headings from font metrics

python tools/detect_headings_font.py --input "C:\Users\Joe\Downloads\Jesus Victory of God V2*.epub"
→ NCX TOC entries as primary, HTML headings as supplement
```

**Integration:**
```powershell
Convert-ToKindle -InputFile "Burge*.pdf" -NoCache
→ TOC shows all numbered chapters

Convert-ToKindle -InputFile "Wright*.epub" -NoCache
→ Parts and chapters from NCX/HTML
```

**Regression:**
```
python tools/test_pipeline.py
→ All 5 test books pass (Oil Kings, Genesis, Mexico, Brother of Jesus, Dionysius)
```

## Design Decisions

1. **Always run font detector** — regardless of extraction path. Different purpose than extraction-path font analysis.
2. **Approach A (sequential two-file)** — clean separation, independently testable, matches existing pattern of PowerShell calling Python tools.
3. **NCX/nav first for EPUBs** — publisher's TOC is highest-fidelity heading source.
4. **Confidence base 0.3** — single-signal ~0.5, multi-signal ~0.8-0.99 for useful ranking spread.
5. **Glob resolution in Python** — baked into `--input` handler to avoid repeated path-expansion bugs.
6. **Smart EPUB early-exit** — >= 5 non-back-matter h1s required to skip Claude, prevents Burge-style false exits.
