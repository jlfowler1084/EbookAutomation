# EbookAutomation — Project Tracker

**Owner:** Joe
**Started:** March 2026
**Last Updated:** 2026-03-24

---

## Project Principles

1. **Source-first, then heuristics, then AI** — Always prefer structured data from the source PDF (bookmarks, metadata, embedded TOC) over generated structure. Use regex/heuristics for cleaning messy source data. Use Claude API ONLY when no structured source data exists AND the problem requires contextual understanding.

2. **Layered processing** — Layer 1: fast regex cleanup (free, handles 90%+). Layer 2: Claude API pass (cheap, handles ambiguous cases). Layer 3: human review (only when AI flags uncertainty). Most books should never need Layer 3.

3. **Generic over specific** — Every fix should work across all books, not just the current one. If a fix only helps one book, it's a workaround, not a solution.

4. **Fix the foundation before adding compensating layers** — If the same category of problem keeps recurring despite multiple fixes, the extraction layer needs to change, not more heuristics.

---

## Project Overview

A PowerShell + Python automation suite for converting ebooks (PDF, EPUB, etc.) into TTS-ready text for Balabolka, Kindle-formatted files (KFX) via Calibre, and podcast/audiobook MP3s. Also includes the FOH scraper/parser tooling for content aggregation and episode generation.

### Directory Structure (v1.1 — reorganized 2026-03-17)

```
F:\Projects\EbookAutomation\
├── config\
│   └── settings.json
├── dictionaries\              ← pronunciation .dic files
├── inbox\                     ← staging area: drop ebooks here for processing
├── logs\                      ← daily log files + processed.txt manifest
├── module\                    ← PowerShell module files
│   ├── EbookAutomation.psd1
│   ├── EbookAutomation.psm1
│   └── launch.bat
├── output\
│   ├── audiobooks\            ← final MP3 audiobook files
│   ├── balabolka-txt\         ← Balabolka-ready TXT files
│   ├── episodes\              ← FOH podcast MP4/MP3 episodes
│   ├── foh-data\              ← scraped FOH JSON output files
│   └── kindle\                ← KFX Kindle conversions
├── processing\                ← temp work area during conversion
├── archive\                   ← originals moved here after successful conversion
└── tools\
    ├── balcon\                ← Balabolka CLI engine
    ├── pdf_to_balabolka.py
    ├── foh_scraper.py
    ├── foh_parser.py
    └── data\                  ← FOH credentials/session files only
```

### Current Components

| Component | Language | Status |
|---|---|---|
| `EbookAutomation.psm1` — Main pipeline module | PowerShell | Active — v1.1.0 |
| `EbookAutomation.psd1` — Module manifest | PowerShell | Active — v1.1.0 |
| `pdf_to_balabolka.py` — PDF → TTS/Kindle text converter (GUI + CLI) | Python | Active |
| `foh_scraper.py` — Fires of Heaven forum scraper | Python | Active |
| `foh_parser.py` — FOH data parser / brief generator | Python | Active |
| `visual_qa.py` — Visual QA pipeline (KFX→PDF→PNG→Claude Vision) | Python | Active |
| `batch_qa.py` — Batch QA system for cross-book diagnostics | Python | Active |
| `pattern_db.py` — Pattern database + metadata CLI | Python | Active |
| `content_filter.py` — Profile-based content filtering | Python | Active |
| `email_to_kindle.py` — SMTP delivery to Kindle | Python | Active |
| `detect_headings_font.py` — PDF font-based heading detection | Python | Active |
| `settings.json` — Central config file | JSON | Active |
| `balcon/` — Balabolka command-line TTS engine | External tool | Bundled |
| Calibre `ebook-convert.exe` + KFX Output plugin | External tool | Installed separately |

### Current Exported Functions (EbookAutomation module)

- `Invoke-EbookPipeline` — Main inbox scan + convert loop (resilient per-book error handling)
- `Convert-ToTTS` — PDF/EPUB → Balabolka TXT (optional OutputDir, defaults from config)
- `Convert-ToKindle` — PDF → clean text → KFX via Calibre (text extraction + metadata)
- `Convert-BriefToYouTube` — MP3 segments + cover image → YouTube-ready MP4s
- `Install-EbookScheduledTask` / `Uninstall-EbookScheduledTask` — Windows Task Scheduler integration
- `Get-EbookTaskStatus` — Check scheduled task state
- `Initialize-EbookAutomation` — First-run setup (dependency check + folder creation)
- `Write-EbookLog` / `Get-EbookConfig` — Shared utilities
- `Get-EbookMetadataFromFilename` — Parse title/author from common ebook filename patterns
- `Send-ToKindle` — Deliver ebooks to Kindle via USB (Calibre) or email (SMTP)
- `Send-ToClaudeAPI` — General-purpose Anthropic Messages API wrapper
- `Get-ChapterStructure` — Claude-assisted chapter/part detection from book text
- `Test-EbookPipeline` — Run pdfminer HTML extraction regression test suite
- `Test-ConversionQuality` — Visual QA on converted ebooks via Claude Vision API
- `Invoke-ConvergeLoop` — Autonomous conversion pipeline with iteration

### Internal Functions (not exported)

- `Resolve-ProjectPath` — Resolve relative paths against project root
- `Send-EbookNotification` — Windows toast notifications
- `Get-ProcessedManifest` / `Add-ProcessedFile` / `Test-AlreadyProcessed` — File tracking

---

## Task Backlog

### 1. Expand Format Support in PDF-to-Balabolka Converter

**Priority:** High
**Status:** ✅ Done (2026-03-22)
**Component:** `pdf_to_balabolka.py`

**Current state:** All major ebook formats now supported natively.

**Goals:**
- [x] Add native EPUB text extraction (via `ebooklib` + `BeautifulSoup`) — **done 2026-03-22**
- [x] Add MOBI support (Calibre CLI intermediate conversion) — **done 2026-03-22**
- [x] Add AZW/AZW3 support (Calibre CLI intermediate) — **done 2026-03-22**
- [x] Add DJVU support (Calibre conversion path) — **done 2026-03-22**
- [x] Update the Tkinter GUI file dialog filters to show all supported formats — **done 2026-03-22**
- [x] Update `settings.json` → `tts.input_formats` to reflect newly supported types — **done 2026-03-22**
- [x] Update `--help` text and docstrings — **done 2026-03-22**

**Notes:**
Architecture: EPUB uses native Python extraction via ebooklib + BeautifulSoup (best quality). MOBI/AZW/AZW3/DJVU route through Calibre CLI intermediate conversion (broad coverage, less code). New `extract_text_auto()` dispatcher routes by file extension. `--calibre-path` CLI argument added. PowerShell EPUB→PDF intermediate step removed in favor of native extraction.

---

### 2. ~~Reorganize Directory Structure~~

**Priority:** ~~High~~ → **COMPLETED 2026-03-17**  
**Status:** ✅ Done

See Completed Work section below for details.

---

### 3. Improve PowerShell Module & Help System

**Priority:** Medium  
**Status:** Not Started  
**Component:** `EbookAutomation.psm1`, `EbookAutomation.psd1`

**Current state:** Functions have basic `.SYNOPSIS` comments but no full comment-based help (no `.DESCRIPTION`, `.PARAMETER`, `.EXAMPLE` blocks). No wrapper module exists for the Balabolka CLI (`balcon.exe`). Default paths now work from settings.json (added in v1.1.0).

**Goals:**

#### 3a. Comment-Based Help
- [ ] Add full `<# .SYNOPSIS .DESCRIPTION .PARAMETER .EXAMPLE .NOTES #>` blocks to all exported functions
- [ ] Add module-level help (about_EbookAutomation help topic)
- [ ] Ensure `Get-Help Convert-ToTTS -Full` produces useful output

#### 3b. Balabolka (balcon.exe) PowerShell Wrapper
- [ ] Create `Invoke-Balabolka` cmdlet wrapping `balcon.exe` with typed parameters
- [ ] Support key balcon switches: `-f` (input file), `-w` (output WAV), `-n` (voice name), `-s` (speed), `-v` (volume), `-enc` (encoding), `--lrc` (subtitle generation)
- [ ] Add `-Voice` parameter with tab-completion (query installed SAPI voices)
- [ ] Add `-DictionaryFile` parameter pointing to `dictionaries\` by default
- [ ] Export from module manifest

#### 3c. Default Path Configuration
- [x] Wire default paths into CLI parameters (`Convert-ToTTS` / `Convert-ToKindle` without `-OutputDir` use configured defaults) — **done 2026-03-17**
- [ ] Add `Set-EbookDefaults` / `Get-EbookDefaults` cmdlets that read/write user preferences (default input folder, output folder, voice, etc.)
- [ ] Store defaults in `config\user-defaults.json` (separate from `settings.json` so project config stays clean)
- [ ] Support `$env:EBOOK_AUTOMATION_ROOT` override for portability

---

### 4. End-to-End Automation Pipeline

**Priority:** Medium  
**Status:** Partially Implemented  
**Component:** `EbookAutomation.psm1`, Windows Task Scheduler, potentially Claude API

**Current state:** `Invoke-EbookPipeline` scans `inbox\`, runs both TTS and Kindle conversion, archives originals, and has per-book error isolation with detailed logging. The scheduled task infrastructure exists but has not been fully tested or configured.

**Goals:**

#### 4a. Full Inbox-to-MP3 Pipeline
- [ ] After TTS text generation, automatically invoke `balcon.exe` to convert TXT → WAV → MP3
- [ ] Add MP3 encoding step (via `ffmpeg` or `lame`, both already referenced in config)
- [ ] Support batch processing: queue multiple books, process sequentially
- [ ] Add progress tracking / estimated time remaining for long conversions
- [ ] Add configurable voice and speed per-book (or use global defaults)

#### 4b. Staging Area Workflow
- [x] Formalize the `inbox\` folder as the staging area — **done 2026-03-17**
- [ ] Add file validation on drop (check format, file size, corruption)
- [ ] Optional: watch folder with `FileSystemWatcher` for real-time trigger instead of polling interval
- [ ] Add a `processing\` status file so the user can see what's currently being converted

#### 4c. Scheduled Task Improvements
- [ ] Fully test and configure `Install-EbookScheduledTask` — not yet validated end-to-end
- [ ] Review and test the 15-minute polling interval — is it appropriate or should it be event-driven?
- [ ] Add error retry logic (if conversion fails, retry N times before giving up)
- [ ] Add daily summary email/notification of what was processed

#### 4d. Claude API Integration
- [ ] Research Anthropic API for potential use cases:
  - Automated book summarization before/after conversion
  - **Pronunciation dictionary generation** (send a chapter, get back proper noun pronunciations)
  - **Chapter detection and TOC generation from extracted text** (much more accurate than regex — see Task 6)
  - Chapter detection and metadata extraction from raw text
  - Content tagging and library cataloging
  - **Balabolka voice tag injection** for book conversions (see Task 7)
- [ ] Evaluate cost vs. value for API calls on a per-book basis
- [ ] Prototype a `Send-ToClaudeAPI` cmdlet if viable
- [ ] Investigate whether Claude can help clean OCR artifacts in extracted text

---

### 5. Kindle Conversion Quality Improvements

**Priority:** Medium
**Status:** Mostly Done (2026-03-24)
**Component:** `pdf_to_balabolka.py`, `EbookAutomation.psm1`

**Current state:** Full pipeline operational: pdfminer HTML extraction with font-based heading detection, bookmark reconciliation, endnote linking, conversion profiles, metadata capture, email-to-Kindle delivery, tiered extraction with quality gates. 50-book baseline established with 74% structural pass rate. TOC detection significantly improved by SCRUM-126 (pattern promotion + hierarchy normalization).

**Goals:**
- [x] Extract clean text from PDF before Calibre conversion (instead of raw PDF) — **done 2026-03-17**
- [x] Parse title/author metadata from common ebook filename patterns — **done 2026-03-17**
- [x] KFX output format for Kindle Scribe — **done 2026-03-17**
- [x] Two-level heading detection (Parts + Chapters) — **done 2026-03-17**
- [ ] Improve chapter/TOC detection accuracy — current regex approach misidentifies footnotes as headings in academic texts. Consider Claude API for this (see Task 4d).
- [ ] Extract cover images from PDFs and pass to Calibre
- [ ] Investigate Calibre's `--cover` flag for injecting cover art
- [ ] Add publisher and year extraction from filename patterns
- [ ] Support manual TOC override via a sidecar file (e.g., `book_toc.json`)

---

### 6. Claude API-Driven Chapter Detection (NEW)

**Priority:** Low (waiting on Task 4d research)  
**Status:** Proposed  
**Component:** `pdf_to_balabolka.py` or new `chapter_detector.py`

**Current state:** Regex-based chapter detection works for simple books but fails on academic texts with numbered footnotes, inline references, and multi-format heading styles. A Claude API call with a few pages of extracted text could return accurate chapter boundaries.

**Goals:**
- [ ] Design a prompt template that sends extracted text sections to Claude and gets back structured chapter data
- [ ] Prototype as a post-processing step: extract text → send to Claude → receive chapter JSON → apply to TXT
- [ ] Evaluate token costs per book (a 300-page book might need 2-3 API calls)
- [ ] Fall back to regex detection if API is unavailable or budget is exceeded

---

### 7. Balabolka Voice Tags for Book Conversions (NEW)

**Priority:** Low  
**Status:** Proposed  
**Component:** Post-processing step for `output\balabolka-txt\`

**Current state:** The FOH daily brief generator includes SSML voice tags, pacing adjustments, and silence markers. Book conversions produce clean text but lack these TTS enhancements. Adding them would improve audiobook quality.

**Goals:**
- [ ] Design a voice tag template for book-length content (chapter silence, narrator voice, rate adjustments)
- [ ] Optionally integrate with Claude API to determine appropriate voice assignments
- [ ] Add as an optional post-processing step in the pipeline or as a standalone command

---

### 8. GitHub Repository Setup (NEW)

**Priority:** Low
**Status:** Proposed
**Component:** Project-wide

Set up a GitHub repository for version control. Goals:
- [ ] Initialize git repo and create `.gitignore` (exclude `output/`, `archive/`, `processing/`, `tools/data/*.json` credentials, `tools/balcon/`, `__pycache__`, `*.mp3`, `*.wav`, `*.mp4`, `*.kfx`)
- [ ] Create initial commit with current stable codebase
- [ ] Push to private GitHub repo
- [ ] Establish a branching workflow (`main` for stable, `dev` for active work)
- [ ] Consider GitHub Actions for basic linting (PSScriptAnalyzer, pylint)

**Notes:** Hold off until the codebase stabilizes and major features are in place. The `.gitignore` is the most important piece — keep binary outputs and credentials out of the repo.

---

### 10. Wire -UseClaudeChapters into Kindle Conversion Path

**Priority:** Medium
**Status:** ✅ Done (2026-03-18)
**Component:** tools/pdf_to_balabolka.py, module/EbookAutomation.psm1

The `-UseClaudeChapters` two-pass chapter detection currently only works with the TTS/Balabolka path (`Convert-ToTTS` → `process_pdf()`). The Kindle path (`Convert-ToKindle` → `process_kindle()`) uses regex-only chapter detection and doesn't accept `--chapter-hints`, so KFX output typically contains only 4-5 chapters instead of the full structure.

Port the same approach:

**Tasks:**
- [ ] Add `--chapter-hints` support to `process_kindle()` in `pdf_to_balabolka.py` (use `apply_chapter_hints()` then format with `# ` / `## ` Markdown headings instead of ALL-CAPS)
- [ ] Add `-UseClaudeChapters` switch to `Convert-ToKindle` in `EbookAutomation.psm1` (same two-pass pattern: run once, detect chapters via Claude, re-run with hints)
- [ ] Wire raw first-30-pages extraction and `Get-ChapterStructure` call into `Convert-ToKindle`
- [ ] Pass `-UseClaudeChapters` through from `Invoke-EbookPipeline` to `Convert-ToKindle`
- [ ] Test with Oil Kings PDF — verify Calibre builds correct multi-level TOC in KFX output
- [ ] Test TOC navigation on Kindle Paperwhite
- [ ] Test with 2-3 other books to confirm no regressions on the Kindle path

**Notes:**
This is a direct port of the work already done for `Convert-ToTTS`. The core logic (`Get-ChapterStructure`, hints JSON writing, title-presence check) can be reused with minimal changes. Key difference: `process_kindle()` emits `# Chapter` / `## Part` Markdown headings (for Calibre TOC detection) rather than ALL-CAPS headings used in the TTS path.

---

### 9. Improve clean_and_join() Heading Preservation

**Priority:** Medium
**Status:** Partially Implemented (2026-03-18)
**Component:** tools/pdf_to_balabolka.py

The `clean_and_join()` function merges short lines into surrounding paragraphs, which destroys chapter headings that pypdf extracted correctly. This is the root cause of missing chapters in the `-UseClaudeChapters` pipeline — Claude can identify the chapters from the TOC, but `apply_chapter_hints()` can't find them in the cleaned text because they were merged away.

Fix: Before merging short lines, check if they look like structural headings. Preserve these as standalone paragraphs instead of merging them.

**Tasks:**
- [x] Add `_looks_like_heading()` helper and heading-detection check in `clean_and_join()` loop — **done 2026-03-18** (rules 1-4: keyword-prefixed, numbered, Roman numeral, Part+number)
- [x] Add Strategy 4 to `apply_chapter_hints()` — first-4-words fuzzy match for split headings — **done 2026-03-18**
- [ ] Test with Oil Kings PDF (should preserve all 12 chapter headings + 2 Parts)
- [ ] Test with 2-3 other books to ensure no false positives (short prose lines kept as headings)
- [ ] Remove or simplify `inject_missing_hints()` once direct matching works reliably

**Notes:** Title Case heuristic (rule 5) was implemented and then removed — it produced 848 false positives. Only strong pattern-match rules (1-4) are kept.

---

### 11. HTML Output with Professional Styling & Themes (NEW)

**Priority:** High
**Status:** In Progress
**Component:** tools/pdf_to_balabolka.py, module/EbookAutomation.psm1

Switch from plain Markdown TXT output to styled HTML for Kindle conversion. HTML gives full control over typography, layout, and theming via embedded CSS. Calibre converts HTML → KFX/EPUB with CSS preserved.

**Tasks:**

#### 11a. Core HTML Output
- [ ] Replace Markdown heading output (`## Chapter Title`) with HTML (`<h1>`, `<h2>`) in `process_kindle()`
- [ ] Wrap body paragraphs in `<p>` tags
- [ ] Add embedded `<style>` block with base typography (font families, sizes, spacing)
- [ ] Add `page-break-before: always` on chapter headings for clean page breaks
- [ ] Update Calibre invocation in `Convert-ToKindle` to accept HTML input instead of TXT
- [ ] Test KFX output on Kindle Paperwhite

#### 11b. Style Enhancements
- [ ] **Subtitles/Section headings** — detect and style with `<h3>` (lighter weight, italic, or smaller)
- [ ] **Block quotes** — detect quoted passages and wrap in `<blockquote>` with indented italic styling
- [ ] **Quote detection signals**: long passages in quotation marks, attribution phrases ("Darwin writes:", "Augustine argues:"), indented text from PDF
- [ ] **Drop caps** — first letter of each chapter opener styled large/decorative via CSS `::first-letter`
- [ ] **Epigraphs** — detect and style chapter-opening quotes differently from body block quotes
- [ ] **Dialogue formatting** — preserve tab/indent for dialogue lines (Koko/Barbara style)
- [ ] **Smart typography** — ensure proper em-dashes, smart quotes, ellipses throughout
- [ ] **Small caps** — apply CSS small-caps to "AD", "BC", "BCE", "CE" and similar abbreviations
- [ ] **Consistent paragraph style** — configurable: indent-first-line vs space-between (per theme)

#### 11c. Theme System
- [ ] Add `-Theme` parameter to `Convert-ToKindle` (values: Classic, Modern, Minimal, Custom)
- [ ] **Classic** — serif body (Georgia/Palatino), traditional academic feel, first-line indent, subtle heading ornaments
- [ ] **Modern** — clean sans-serif headings (Helvetica/Arial), serif body, generous whitespace, space-between paragraphs
- [ ] **Minimal** — stripped down, just clean typography with subtle heading differentiation, maximum readability
- [ ] **Custom** — reads from a user-provided CSS file path (e.g., `config\custom-theme.css`)
- [ ] Store theme CSS templates in `config\themes\` directory
- [ ] Default theme configurable in `settings.json` under `kindle.default_theme`

#### 11d. Structural Enhancements
- [ ] Half-title page at book start (title + author, styled, before first chapter)
- [ ] Styled table of contents page with clickable links
- [ ] Chapter number + title on separate lines with distinct styling
- [ ] Footnotes as endnotes (optional — collect stripped footnote refs and append per chapter)

**Notes:**
This is the single biggest quality differentiator vs. other PDF-to-ebook converters. Most tools produce ugly, unstyled output. Professional-grade HTML with themes makes the conversions look like commercially published ebooks.

---

### 12. Cover Image Handling Improvements (NEW)

**Priority:** Medium
**Status:** Proposed
**Component:** module/EbookAutomation.psm1

**Current state:** Cover extraction tries to render PDF page 1 as JPEG via pdf2image/Poppler. This fails for some PDFs and produces text-page images for books without graphical covers.

**Goals:**
- [ ] Add `-Cover` parameter to `Convert-ToKindle` with values: `auto`, `none`, `extract`, `<path>`
- [ ] `auto` (default) — extract if PDF page 1 looks graphical (low text density), skip otherwise
- [ ] `none` — skip cover entirely
- [ ] `extract` — force extraction of page 1 regardless
- [ ] `<path>` — use user-provided image file
- [ ] Add heuristic to detect whether page 1 is a graphical cover vs text page (check text extraction word count on page 1 — if < 20 words, likely a cover image)
- [ ] Support common image formats: JPEG, PNG, WebP
- [ ] Add cover image to settings.json as optional per-book override

---

### 13. Comprehensive PDF Conversion Testing (NEW)

**Priority:** High
**Status:** In Progress (50-book baseline established 2026-03-24)
**Component:** All conversion components, `tools/batch_qa.py`

Systematic testing of the conversion pipeline against diverse PDF types to identify and fix format-specific issues. Batch QA system (SCRUM-87) processes entire folders with structured diagnostics and cross-book pattern analysis. 50-book baseline run completed 2026-03-24 with 74% structural pass rate (37/50 PASS). VQA baseline on 37 passing books: avg 57.9, median 58, range 33-81. Text integrity identified as #1 weakness (11/33 books below 70).

**Test Library:**

| Book | Pages | Bookmarks | Type | Status |
|---|---|---|---|---|
| Reading Genesis After Darwin | 270 | 20 | Academic, bookmarked | ✅ Score 65→84 — chapters aligned, "Modern Science" bookmark fix, author names preserved (Watson, Louth, Wilkinson). pdfminer path: 1.3 MB KFX, 211 running headers stripped, 869 fragments rejoined, 293 `<em>`, 8 blockquotes. |
| Return of the Gods | 289 | 26 | Popular theology | ✅ Tested |
| Dionysius the Areopagite | 148 | 42 | Theology, CCEL digitization | ✅ Score ~85 — 27 content-aligned, 145 headers stripped, 3 heuristic promotions. pdfminer path: 454 per-page footnotes linked (Strategy 3, was 13 false matches), 21 blockquotes, 36 h3. Bookmark reconciliation (FIX 6) applied. Known: source PDF has broken bookmark levels. |
| Mexico's Illicit Drug Networks | 209 | 14 | Academic, Georgetown UP | ✅ Score 49→69 — 497 auto-fixes (41x amplification), 51 headers stripped, 2,759 ligature fixes. pdfminer path: 377 endnotes linked, 810 ligature fixes, dedication demotion guard ("To my family"), long-sentence heading guard (80+ char). Multi-fragment ligature merges (2-4 parts) applied. Known: chapters nesting under Abbreviations (bookmark level mapping). |
| The Oil Kings | 406 | 21 | History, Simon & Schuster | ✅ Score 77 — Introduction in TOC, correct Part nesting, 36 ALL-CAPS section breaks, 318 headers stripped. pdfminer path: 2.4 MB KFX, 7 h1 + 15 h2 + 91 h3, 4 blockquotes, 866 `<em>`, 4 attributions, 2,053 fragments rejoined. |
| Brother of Jesus | ~200 | 35 | Popular archaeology | ✅ Score 80→94 — all 20 chapters with content, correct Part nesting, image-only page forwarding, 37 global fixes. pdfminer path: 1.0 MB KFX, 7 h1 + 29 h2 + 26 h3, 11 blockquotes, 1,185 fragments rejoined, 559 ligature fixes. |
| Jesus and the Land | ~180 | 13 | Academic theology, Baker | ✅ Score 61→79 — 113 fragments rejoined, 22 subheadings detected (no-bookmark path). pdfminer path: 509 fragments rejoined, 65 h3, start-reading-at fixed (was pointing to ch6). Known: Front Matter section contains leaked TOC entries, some italic page-boundary fragments. |
| The Khazars | 48 | 0 | Illustrated military, Osprey | ✅ Score 73→83 — no bookmarks, heuristic detection. AI caught source spelling errors ("pensinsula", "millenium"). |
| Nicaea and Its Legacy | ~490 | 0 | Dense academic, NO bookmarks | ✅ Score ~80 — pdfminer extraction, 21/22 chapters matched via Claude hints, quality-scored monotonic matching. Spaced-letter artifacts fixed by Phase 8. |
| Secret Societies of All Ages | 417 | 0 | 1875 scan, image-only PDF | ✅ Score ~70 — Tesseract OCR extraction (10.8 min, 300 DPI). 409/417 pages with text, 63,733 words, 16 chapters detected. Victorian typography causes expected OCR artifacts (ligature garbling in headings). Body text highly legible. First image-only PDF successfully processed. |
| Justinian's Novella 146 | 26 | 0 | Short legal/historical | ✅ 275 KB KFX. Clean pass but per-page footnote issues remain. |
| Civilta Cattolica | ? | ? | Journal article | ❌ Failed — spaceless text layer, pdfminer gets concatenated text. Needs word-boundary reconstruction. |
| Ezekiel II (Hermeneia) | 637 | ? | Dense academic commentary, two-column | ✅ Extracted in 155s. PyMuPDF column extraction. Hebrew/Greek garbled (non-Latin scripts). AZW3 fallback (KFX crash). Regression target in test suite. |
| Gospel of Nicodemus | 72 | 0 | Short, no bookmarks | ⬜ Partially tested |
| Dumitru Duduman Prophecies | 39 | 0 | Very short, no bookmarks | ⬜ Not tested |
| S. K. Bain — Most Dangerous Book | ? | 0 | No bookmarks, many chapters | ✅ Pattern promotion rescued 0→76 chapters (SCRUM-126). Regression target. |
| Texe Marrs — Codex Magica | ? | 0 | No bookmarks | ✅ Pattern promotion rescued 0→18 chapters (SCRUM-126). Regression target. |
| Ann Coulter — Various | ? | ? | Scanned PDFs | ✅ Tier 2 re-OCR auto-escalation: quality score 64→100 (SCRUM-122). |
| Fruchtenbaum | ? | 0 | Single-column OCR/scanned PDF | ✅ Core regression test book. pdfminer+OCR path. |
| Burge | ? | ? | Paragraph flow, mid-sentence breaks | ✅ Core regression test book. pdfminer path. |

**Tasks:**
- [ ] Test each book in the archive and document results
- [ ] For each failure, identify which cleanup phase caused the issue
- [ ] Gate aggressive cleanup phases behind bookmark availability (0-bookmark books get lighter processing)
- [ ] Build a regression test script that runs all archive books and checks for known issues
- [ ] Add test results to this table as books are processed

**Known Issues:**
- Nicaea (0 bookmarks, 492 pages) — aggressive cleanup without bookmark guidance produces poor results
- Books with 0 bookmarks fall through to regex chapter detection, which may miss chapters or produce false positives
- OCR quality varies dramatically between books — scanned 19th-century texts will need much heavier correction

---

### 14. Conversion Profiles for Different Book Types (NEW)

**Priority:** Medium
**Status:** ✅ Done (2026-03-23)
**Component:** tools/pdf_to_balabolka.py, tools/content_filter.py, module/EbookAutomation.psm1

Profile system implemented with auto-detection and per-profile content filtering. `-Profile` parameter on `Convert-ToKindle` and `Invoke-EbookPipeline`. Content filter script with profile-specific rules and tests. `-No*` skip parameters for individual pipeline stages.

**Proposed Profiles:**
- **Academic** — running headers with page numbers, footnote references, dense bibliography, multi-level TOC (Parts/Chapters), author names in TOC
- **Fiction** — minimal headers, dialogue in quotes (protect ALL-CAPS in dialogue), simple chapter structure, no footnotes
- **Scanned/OCR** — heavy OCR artifacts, garbled characters, no bookmarks, no metadata
- **Self-published** — inconsistent formatting, may lack bookmarks, simple structure

**Auto-detection signals:**
- Bookmark count and structure (academic = many levels; fiction = flat)
- Footnote density (academic = high; fiction = zero)
- Running header pattern detection (academic = common; fiction = rare)
- OCR artifact density (scanned = high)
- Font diversity from PDF metadata (academic = many; fiction = few)

**Tasks:**
- [ ] Define profile settings (which cleanup phases to enable/disable, aggressiveness levels)
- [ ] Build auto-detection function that scores book against each profile
- [ ] Add `--profile auto|academic|fiction|scanned` CLI flag
- [ ] Add `-BookProfile` parameter to PowerShell functions
- [ ] Test each profile against representative books
- [ ] Allow manual override when auto-detection is wrong

---

### 15. Master OCR Substitution Table (NEW)

**Priority:** Medium
**Status:** Proposed
**Component:** config/ocr_substitutions.json, tools/pdf_to_balabolka.py

Replace ad-hoc OCR correction patterns scattered across fix_ocr_artifacts() phases with a data-driven substitution table. Build from established OCR correction resources.

**Sources to incorporate:**
- Distributed Proofreaders wiki (pgdp.net/wiki/Common_errors_proofers_find) — 20+ years of book OCR correction patterns
- Community History Archives A-Z character confusion map (communityhistoryarchives.com)
- Daniel Lopresti's OCR error taxonomy paper (Lehigh University)
- GitHub OCR-Character-Confusion project (Tesseract confusion matrices)

**Known substitution categories:**
- **Digit↔Letter**: 0↔O, 1↔l↔I↔!, 5↔S, 8↔B, 2↔Z, 6↔b, 9↔g/q
- **Letter pairs**: rn↔m, cl↔d, li↔h, vv↔w, ri↔n
- **Ligatures/encoding**: fi→`, fl→`, ff→`, backtick corruption from font encoding
- **Case confusion**: W/w, S/s, C/c (same shape uppercase/lowercase)
- **Punctuation**: period↔comma, semicolon↔colon, hyphen insertion/deletion
- **Spacing**: word merging ("ofthe"→"of the"), word splitting ("sym bolic"→"symbolic")
- **Legal word errors**: OCR produces valid but wrong word (ease↔case, Cod↔God, churl↔church) — hardest to detect, requires context

**File format (proposed):**
```json
{
  "digit_letter": {
    "o_to_0": {"pattern": "\\b(\\d+[o]+\\d*|\\d*[o]+\\d+)\\b", "note": "lowercase o in numbers"},
    "i_to_1": {"pattern": "\\bi(\\d{3,4})\\b", "note": "i before 3-4 digits = year"},
    "l_to_1": {"pattern": "\\bl(\\d{3})\\b", "note": "l before 3 digits = year"}
  },
  "letter_pairs": {
    "rn_m": {"note": "context-dependent, use spellchecker"},
    "cl_d": {"note": "less common, validate with dictionary"}
  }
}
```

**Tasks:**
- [ ] Compile master substitution table from the four sources listed above
- [ ] Store as `config/ocr_substitutions.json`
- [ ] Refactor fix_ocr_artifacts() to load substitutions from the JSON file
- [ ] Add per-book confusion matrix generation (run OCR-Character-Confusion against a PDF, output book-specific corrections)
- [ ] Integrate with conversion profiles (Task 14) — different profiles load different substitution sets
- [ ] Add "legal word error" detection using bigram/trigram context (hardest category)
- [ ] Add `-OCRTable` parameter to allow user-provided substitution overrides

**Notes:**
This is the data-driven evolution of the current regex-heavy approach. The JSON table makes it easy to add new patterns without touching code, and per-book confusion matrices could dramatically improve accuracy for problematic scans. The "legal word errors" category (valid-but-wrong words) will likely require Claude API context analysis to solve reliably.

---

### 16. Refactor apply_chapter_hints() for Precise Heading Matching

**Priority:** High
**Status:** ✅ Mostly Complete (refactored 2026-03-19)
**Component:** tools/pdf_to_balabolka.py

The current `apply_chapter_hints()` uses substring matching which can match chapter titles inside body sentences instead of finding the actual standalone heading paragraphs. This causes ordering issues and incorrect chapter boundaries.

**Known issues (from Nicaea testing):**
- "1. Points of Departure" matches lowercase "points of departure" in a body sentence instead of the heading
- Chapters 2 and 3 both match "Theological Trajectories In the Early Fourth" because Strategy 4 (first 4 words) can't distinguish them
- "Introduction" matches a chapter 8 sub-section instead of the book's Introduction
- Chapter 10 matches ALL-CAPS running header "VICTORY AND THE STRUGGLE FOR DEFINITION" instead of the properly-cased heading
- Chapter 15 loses its number when matching a stripped title variant

**Proposed multi-pass architecture:**
1. **Pass 1 — Exact paragraph match:** Look for paragraphs that are an exact (or near-exact) match to the hint title. These are the real headings.
2. **Pass 2 — Short paragraph substring:** Only if Pass 1 fails, try substring matching in paragraphs under 120 chars.
3. **Pass 3 — Embedded match (last resort):** Only try matching inside long paragraphs if no shorter match exists.
4. **Never match** inside a paragraph longer than 200 chars unless no shorter match exists.
5. **Strategy 4 refinement:** When first 4 words match, verify the paragraph doesn't also match a different hint (disambiguate chapters with similar titles like "Theological Trajectories... I" vs "... II").

**Additional improvements:**
- [ ] Preserve original hint title casing on the matched paragraph (don't use the body text's casing)
- [ ] Handle en-dash vs hyphen mismatch in post-check validation (Claude returns "--", body has "-")
- [ ] Log matched paragraph index alongside strategy for debugging
- [ ] Consider using the Part I/II/III headings from Claude hints even when body text doesn't have standalone Part paragraphs

**Remaining refinements:**
- [x] Front matter detection for non-bookmark books: detect title/copyright/dedication before first chapter hint and insert "Front Matter" section heading — **done 2026-03-19**
- [x] Fixed `--start-reading-at` in PSM1 to target first content chapter instead of front matter entry — **done 2026-03-19**
- [ ] Handle "Preface and Acknowledgements" hint when no standalone body heading exists (consider fuzzy matching against preface-like paragraphs)
- [x] pdfminer spaced-letter artifact: certain fonts extract as "t h e F a t h e r" — Phase 8 added to fix_ocr_artifacts() with greedy dictionary word-splitting — **done 2026-03-20**

---

### 17. Post-Processing Text Cleanup Pipeline (Updated)

**Priority:** High
**Status:** ✅ Done (2026-03-18/19/20) — 11 phases implemented (Phase 0-7 + Phase 8 spaced-letter collapse)

See Completed Work changelog for the full list of `fix_ocr_artifacts()` phases implemented across the 2026-03-18, 2026-03-19, and 2026-03-20 sessions.

---

### 18. Automated Visual QA for Ebook Conversions (NEW)

**Priority:** Medium
**Status:** In Progress (Phase 1 complete — 2026-03-22)
**Component:** tools/visual_qa.py, tools/visual_qa_rubric.md, module/EbookAutomation.psm1

Automated visual quality assurance pass for ebook conversions. Converts output files (KFX/AZW3/EPUB) to PDF via Calibre, renders sampled pages to PNG, sends to Claude Vision API for structured evaluation against a rubric, and produces a machine-readable JSON report.

**Phase 1 (Core) — Done:**
- [x] Rubric prompt template (`tools/visual_qa_rubric.md`) — 6 evaluation categories with weights
- [x] Python script (`tools/visual_qa.py`) — full pipeline: CLI args, Calibre PDF conversion, page sampling, PNG rendering, Claude Vision API, JSON report
- [x] PowerShell orchestrator (`Test-ConversionQuality`) — calls Python script, logs results, returns summary
- [x] Module export in `.psm1` and `.psd1`
- [x] `visual_qa` section in `settings.json`

**Phase 2 (Pipeline Integration) — Done (2026-03-22):**
- [x] Add `-ValidateVisual` switch to `Convert-ToKindle` — **done 2026-03-22**
- [x] Wire into `Invoke-EbookPipeline` — **done 2026-03-22**
- [x] Test in pipeline mode on a batch — **done 2026-03-24** (37-book VQA baseline run)

**Phase 3 (Refinement) — Done (2026-03-22, SCRUM-74):**
- [x] Tune rubric based on real QA results across book types — **done 2026-03-22**
- [x] Add fix-and-retry loop for traceable HTML issues (cap at 3 iterations) — **done 2026-03-22**
- [x] Batch summary report across multiple books — **done 2026-03-22** (via batch_qa.py)
- [ ] Adapt for Balabolka TXT QA (TXT → PDF → PNG → evaluate) — future

**Dependencies:** Calibre (installed), poppler (installed in tools/poppler), pdf2image (installed), ANTHROPIC_API_KEY env var (configured).

---

## Completed Work (Changelog)

| Date | Item |
|---|---|
| 2026-03-14 | Initial project structure, settings.json, README |
| 2026-03-14 | FOH scraper + parser created |
| 2026-03-15 | pdf_to_balabolka.py — GUI + CLI converter working for PDFs |
| 2026-03-15 | FOH daily brief MP3 generation |
| 2026-03-16 | EbookAutomation.psm1 — full module with pipeline, scheduling, logging, notifications |
| 2026-03-16 | Multiple audiobook TXT files generated (Kabbalah Unveiled, Oil Kings, Twilight War, etc.) |
| 2026-03-16 | FOH episode MP4s generated (Politics Brief, Juicing Wealth & Power) |
| 2026-03-16 | Pronunciation dictionary system (`master_pronunciation.dic`) |
| **2026-03-17** | **Directory reorganization — complete restructure from chaotic layout to clean tree** |
| 2026-03-17 | Migration script (`Migrate-EbookProject.ps1`) to move all files safely |
| 2026-03-17 | `settings.json` updated with new path keys: `balabolka_txt`, `dictionaries`, `episodes`, `data`, `balcon` |
| 2026-03-17 | Module files moved to `module\` subfolder; `launch.bat` updated |
| 2026-03-17 | `foh_scraper.py` patched: credential/session files resolve to `tools\data\`, `--out` defaults to `tools\data\` |
| 2026-03-17 | `pdf_to_balabolka.py` — argparse CLI added (`--input`, `--output-dir`, `--mode`, `--suffix`, `--quiet`) |
| 2026-03-17 | `pdf_to_balabolka.py` — Kindle mode (`--mode kindle`): preserves full content, Markdown chapter headings |
| 2026-03-17 | `pdf_to_balabolka.py` — improved paragraph detection (full-width line fix + lowercase merge) |
| 2026-03-17 | `pdf_to_balabolka.py` — two-level heading detection (Parts + Chapters), numbered chapter support |
| 2026-03-17 | `pdf_to_balabolka.py` — UTF-8 stdout fix for Windows/PowerShell encoding compatibility |
| 2026-03-17 | `Convert-ToTTS` / `Convert-ToKindle` — OutputDir now optional (defaults from settings.json) |
| 2026-03-17 | `Convert-ToKindle` — PDF text extraction before Calibre (clean text instead of raw PDF) |
| 2026-03-17 | `Convert-ToKindle` — metadata extraction from filenames (title, author → Calibre flags) |
| 2026-03-17 | `Convert-ToKindle` — KFX output format, `Start-Process` for reliable Calibre invocation |
| 2026-03-17 | `Invoke-EbookPipeline` — per-book try/catch isolation (one failure doesn't stop the batch) |
| 2026-03-17 | `Invoke-EbookPipeline` — detailed logging with timing, per-step status, summary table |
| 2026-03-17 | `EbookAutomation.psd1` — v1.1.0, `Convert-BriefToYouTube` added to exports |
| 2026-03-17 | `Get-EbookMetadataFromFilename` — new helper for parsing Anna's Archive / libgen filenames |
| 2026-03-17 | DeDRM plugin removed from Calibre (corrupted zip was blocking all conversions) |
| 2026-03-17 | Deleted `EbookAutomationOld` backup after successful migration |
| 2026-03-17 | `Invoke-Balabolka` — new function wrapping balcon.exe + ffmpeg (TXT → WAV → MP3 pipeline) |
| 2026-03-17 | `Invoke-Balabolka` — progress monitoring (polls WAV file growth every 3s during synthesis) |
| 2026-03-17 | `Invoke-EbookPipeline` — MP3 generation step (`-GenerateMP3` switch, `mp3` config block in settings.json) |
| 2026-03-17 | `Send-ToClaudeAPI` — general-purpose Anthropic Messages API wrapper (supports all Claude models) |
| 2026-03-17 | `Get-ChapterStructure` — Claude-assisted chapter/part detection from book text |
| 2026-03-17 | `Convert-ToTTS` — `-UseClaudeChapters` two-pass pipeline: regex extraction → Claude chapter detection → re-run with hints |
| 2026-03-17 | `pdf_to_balabolka.py` — `--chapter-hints` CLI argument for pre-detected chapter titles (JSON input) |
| 2026-03-17 | `pdf_to_balabolka.py` — `apply_chapter_hints()` with 3-strategy fuzzy matching (exact, stripped prefix, key phrase) |
| 2026-03-17 | `pdf_to_balabolka.py` — `inject_missing_hints()` positional fallback for chapters not found in cleaned text |
| 2026-03-17 | `pdf_to_balabolka.py` — `format_output_with_levels()` for Part vs Chapter heading distinction |
| 2026-03-17 | `pdf_to_balabolka.py` — heading detection made conservative (keyword-only, no numbered/roman numeral false positives) |
| 2026-03-17 | `Convert-ToTTS` — raw PDF TOC extraction (first 30 pages) for Claude chapter detection pre-pass |
| 2026-03-17 | `EbookAutomation.psd1` — exports updated: `Invoke-Balabolka`, `Send-ToClaudeAPI`, `Get-ChapterStructure` |
| 2026-03-17 | Project tracker — added tasks 8 (GitHub repo), 9 (clean_and_join heading preservation), 10 (Kindle UseClaudeChapters) |
| **2026-03-18** | **`pdf_to_balabolka.py` — `_looks_like_heading()` helper + heading preservation in `clean_and_join()` (rules 1-4: keyword, numbered, Roman numeral, Part+number)** |
| 2026-03-18 | `pdf_to_balabolka.py` — Title Case heuristic (rule 5) added then removed due to 848 false positives |
| 2026-03-18 | `pdf_to_balabolka.py` — `apply_chapter_hints()` Strategy 4: first-4-words fuzzy match for split headings from pypdf |
| 2026-03-18 | `pdf_to_balabolka.py` — `extract_bookmarks()` new function: reads PDF outline/bookmarks with page numbers |
| 2026-03-18 | `pdf_to_balabolka.py` — `extract_text()` now inserts `<<PAGE:N>>` markers between pages for bookmark mapping |
| 2026-03-18 | `pdf_to_balabolka.py` — `map_bookmarks_to_paragraphs()` new function: maps bookmark page numbers to paragraph indices via page markers |
| 2026-03-18 | `pdf_to_balabolka.py` — `process_pdf()` + `process_kindle()` — bookmark-based chapter detection as primary strategy (falls back to regex/hints for PDFs without bookmarks) |
| 2026-03-18 | Project tracker — added tasks 11 (bookmark enhancements), 12 (PDF metadata), 13 (page-level analysis) |
| **2026-03-18** | **PDF bookmark-based chapter detection — primary strategy (zero API calls for bookmarked PDFs)** |
| 2026-03-18 | `extract_bookmarks()` — reads PDF outline/bookmarks with page numbers, filters non-content entries (copyright, index, etc.) |
| 2026-03-18 | `map_bookmarks_to_paragraphs()` — maps bookmark page numbers to paragraph positions using `<<PAGE:N>>` markers |
| 2026-03-18 | Page marker system in `extract_text()` — inserts `<<PAGE:N>>` between pages, preserved through `clean_and_join()`, stripped after mapping |
| 2026-03-18 | `clean_and_join()` — preserves `<<PAGE:N>>` markers through paragraph merging, short-fragment filtering, and lowercase continuation |
| 2026-03-18 | `clean_and_join()` — `_looks_like_heading()` helper preserves structural heading lines (Chapter/Part keywords, numbered headings) |
| 2026-03-18 | `apply_chapter_hints()` — Strategy 4 added: first-4-words matching for split headings (pypdf line breaks in titles) |
| 2026-03-18 | `process_pdf()` — bookmark path: extract bookmarks → map to paragraphs → format ALL-CAPS → skip front/back matter detection and regex |
| 2026-03-18 | `process_kindle()` — bookmark path: extract bookmarks → map to paragraphs → format Markdown `## ` headings → skip regex detection |
| 2026-03-18 | `process_kindle()` — `--chapter-hints` support added (Claude-detected chapters with `# `/`## ` Markdown formatting) |
| 2026-03-18 | `Convert-ToTTS` — bookmark detection skip: checks Pass 1 log for "Placed N bookmarks", skips Claude API call if bookmarks sufficient |
| 2026-03-18 | `Convert-ToKindle` — `-UseClaudeChapters` switch added with full two-pass pipeline (bookmark check → Claude fallback → hints re-run) |
| 2026-03-18 | `Convert-ToKindle` — dynamic TOC level detection: uses `--level1-toc "//h:h1" --level2-toc "//h:h2"` when both exist, `--level1-toc "//h:h2"` when h2-only |
| 2026-03-18 | `Convert-ToKindle` — removed `--quiet` from Python extraction to allow bookmark log passthrough for skip detection |
| 2026-03-18 | `Invoke-EbookPipeline` — passes `-UseClaudeChapters` through to `Convert-ToKindle` |
| 2026-03-18 | Embedded `<<PAGE:N>>` marker cleanup in `map_bookmarks_to_paragraphs()` — strips markers merged into paragraph text |
| 2026-03-18 | `extract_bookmarks()` — improved skip filters: `©` prefix, `'index'` substring, `'e n d'` variant |
| 2026-03-18 | Project tracker — added tasks 11 (bookmark enhancements), 12 (PDF metadata extraction), 13 (page-level analysis) |
| 2026-03-18 | Tested: Reading Genesis (14 bookmarks, perfect TOC in KFX/AZW3), Gospel of Nicodemus (0 bookmarks, Claude fallback), Secret Societies (0 bookmarks, scanned OCR) |
| 2026-03-18 | `extract_cover_image()` — renders first PDF page as JPEG cover using pdf2image + poppler |
| 2026-03-18 | `Convert-ToKindle` — cover extraction with safe temp path (handles Unicode filenames), passes `--cover` to Calibre |
| 2026-03-18 | poppler-utils installed to `tools\poppler\` — auto-discovered at runtime via `pdftoppm.exe` search, no PATH changes needed |
| 2026-03-18 | `pdf2image` Python dependency added for cover rendering |
| 2026-03-18 | `extract_bookmarks()` — front matter bookmarks (Title Page, Copyright, Contents) kept with `front_matter` flag instead of skipped |
| 2026-03-18 | `extract_bookmarks()` — back matter bookmarks (Notes, Index, Bibliography, About) kept with `back_matter` flag for navigable TOC entries |
| 2026-03-18 | `extract_bookmarks()` — top-level promotion for Epilogue, Prologue, About, Afterword, Conclusion (not nested under last Part) |
| 2026-03-18 | `process_kindle()` — synthetic "Front Matter" h1 heading inserted, front matter entries nested as h2 underneath |
| 2026-03-18 | `process_pdf()` — front matter trimmed for TTS, back matter trimmed at first back matter bookmark |
| 2026-03-18 | `Convert-ToKindle` — `--start-reading-at "//h:h2[1]"` sets Kindle "Beginning" landmark at first chapter |
| 2026-03-18 | `Convert-ToKindle` — dynamic TOC: 2-level (`h1`+`h2`) when Parts exist, 1-level (`h2`) for chapter-only books |
| 2026-03-18 | `Get-EbookMetadataFromFilename` — Pattern 0 added for libgen `{Author}(Year, Publisher){ID}` format |
| 2026-03-18 | `Get-EbookMetadataFromFilename` — Publisher, Year, ISBN extraction added to all patterns |
| 2026-03-18 | `Convert-ToKindle` — passes `--publisher`, `--pubdate`, `--isbn`, `--language en` to Calibre from parsed metadata |
| 2026-03-18 | `Convert-ToKindle` — clean output filenames: "Title - Author.kfx" format, strips libgen/Anna's Archive noise |
| 2026-03-18 | Tested: Return of the Gods — 10 Parts + 52 Chapters nested TOC, Epilogue/Notes/About top-level, Front Matter section, cover image, clean metadata |
| 2026-03-18 | Post-processing OCR cleanup pipeline (fix_ocr_artifacts) — 7 phases of text quality improvement |
| 2026-03-18 | fix_ocr_artifacts() Phase 0: Running header/footer detection and removal — standalone ALL-CAPS lines with page numbers appearing 3+ times (48-51 headers per book) |
| 2026-03-18 | fix_ocr_artifacts() Phase 0b: Merged running header stripping — headers stuck to paragraph starts (e.g., "134 UNDERSTANDING THE HISTORY the landscape...") with OCR-aware page numbers (I→1, O→0) |
| 2026-03-18 | fix_ocr_artifacts() Phase 0c: Mid-paragraph header stripping — headers embedded within sentence text |
| 2026-03-18 | fix_ocr_artifacts() Phase 0d: Orphaned sentence fragment rejoining — lowercase-starting paragraphs stitched back to previous paragraph after header removal |
| 2026-03-18 | fix_ocr_artifacts() Phase 0e: General ALL-CAPS sequence stripping — any 3+ uppercase words embedded in prose, with safeguards for quoted dialogue, acronyms, and short paragraphs. Adjacent orphaned page numbers also stripped. Second-pass orphan rejoining after CAPS cleanup. |
| 2026-03-18 | fix_ocr_artifacts() Phase 1: Unicode normalization — smart quotes, em/en dashes, ellipsis |
| 2026-03-18 | fix_ocr_artifacts() Phase 2: rn↔m OCR correction using pyspellchecker with word frequency comparison (5x threshold for ambiguous cases like modem→modern) |
| 2026-03-18 | fix_ocr_artifacts() Phase 3: Ligature decomposition — fi, fl, ff, ffi, ffl Unicode ligatures |
| 2026-03-18 | fix_ocr_artifacts() Phase 3b: Hyphen-split word rejoining — "sym bolic"→"symbolic", "particu lar"→"particular" using dictionary validation with 7-char fragment threshold |
| 2026-03-18 | fix_ocr_artifacts() Phase 4: Inline footnote/endnote reference stripping — removes superscript numbers extracted as full-size digits (e.g., "theology.5Not"→"theology. Not") |
| 2026-03-18 | fix_ocr_artifacts() Phase 5: Orphaned character fragment cleanup — single stray characters left after header stripping (e.g., "C its parameters"→"its parameters") |
| 2026-03-18 | fix_ocr_artifacts() Phase 6: Duplicate title fragment removal — body paragraphs that repeat bookmark heading text, with heading index protection to prevent deleting actual chapter headings |
| 2026-03-18 | fix_ocr_artifacts() accepts bookmark_titles and heading_indices parameters for targeted cleanup |
| 2026-03-18 | map_bookmarks_to_paragraphs() — duplicate title fragment detection moved to fix_ocr_artifacts Phase 6 for better accuracy after all text cleanup |
| 2026-03-18 | pyspellchecker Python dependency added for OCR correction and hyphen-split detection |
| 2026-03-18 | Task 15 (Post-Processing Text Cleanup) status updated to Done |
| 2026-03-18 | Task 16 added: Conversion Profiles for Different Book Types (auto-detect academic/fiction/scanned/self-published and adjust cleanup aggressiveness) |
| 2026-03-18 | Tested: Reading Genesis — 51 headers removed, 20 OCR corrections, 368 paragraphs footnote-stripped, 15 duplicate titles removed, hyphen-split words rejoined |
| 2026-03-18 | Known issue: Nicaea and Its Legacy (0 bookmarks, 492 pages) — aggressive cleanup without bookmark guidance produces poor results. Candidate for profile-based gating. |
| **2026-03-18** | **Post-processing OCR cleanup pipeline (fix_ocr_artifacts) — 10+ phases of text quality improvement** |
| 2026-03-18 | Phase 0: Running header/footer detection and removal (standalone ALL-CAPS lines with page numbers, 3+ occurrences) |
| 2026-03-18 | Phase 0b: Merged running header stripping (headers stuck to paragraph starts, OCR-aware page numbers I→1, O→0) |
| 2026-03-18 | Phase 0c: Mid-paragraph header stripping |
| 2026-03-18 | Phase 0d: Orphaned sentence fragment rejoining (lowercase-starting paragraphs stitched back after header removal) |
| 2026-03-18 | Phase 0e: General ALL-CAPS sequence stripping with safeguards for quoted dialogue, acronyms, known headers override |
| 2026-03-18 | Phase 0e-b: Orphaned mid-paragraph page number stripping + wedged page numbers between words |
| 2026-03-18 | Phase 0f: Standalone ALL-CAPS header paragraph removal |
| 2026-03-18 | Phase 0g: Title-based running header removal (case-insensitive, uses bookmark title fragments including quoted portions and word prefixes) |
| 2026-03-18 | Phase 1: Unicode normalization (smart quotes, em/en dashes, ellipsis) |
| 2026-03-18 | Phase 1b: pypdf backtick corruption fix (dictionary-validated ligature reconstruction) |
| 2026-03-18 | Phase 2: rn↔m OCR correction using pyspellchecker |
| 2026-03-18 | Phase 2b: OCR "i" → "1" in years/numbers + standalone "i" after book/chapter names |
| **2026-03-19** | **Phase 2c: OCR lowercase "o" → "0" in numbers (the "6o"/"8o" breakthrough)** |
| 2026-03-18 | Phase 3: Ligature decomposition (fi, fl, ff, ffi, ffl) |
| 2026-03-18 | Phase 3b: Hyphen-split word rejoining ("sym bolic" → "symbolic") |
| 2026-03-18 | Phase 4: Inline footnote/endnote reference stripping |
| 2026-03-18 | Phase 5: Orphaned character/number fragment cleanup (Unicode chars, leading page numbers, stray punctuation) with heading-aware rejoining |
| 2026-03-18 | Phase 6: Duplicate title fragment removal with heading index protection |
| 2026-03-18 | Phase 7: Dialogue line indentation (cluster-based detection) |
| 2026-03-18 | Final pass: Safety-net leading page number removal after all phases |
| 2026-03-18 | fix_ocr_artifacts() accepts bookmark_titles, heading_indices, and known_headers parameters |
| 2026-03-18 | pyspellchecker Python dependency added |
| 2026-03-19 | Reading Genesis fully tested: 102 merged headers, 28 CAPS headers, 395 mid-para page numbers, 71 title-based headers, 200 footnote-stripped paragraphs, 96 dialogue lines indented |
| 2026-03-19 | Tasks 11-14 added: HTML output with themes, cover image handling, comprehensive testing, conversion profiles |
| **2026-03-19** | **pdfminer.six auto-detection and fallback extraction** |
| 2026-03-19 | `extract_text()` now samples 30 pages and scores pypdf's word-merge rate; switches to pdfminer.six when rate > 2.0/1000 chars |
| 2026-03-19 | `_extract_with_pdfminer()` — full pdfminer.six extraction backend with per-page error handling |
| 2026-03-19 | Nicaea PDF: pypdf had 195 camelCase merges per 20 pages; pdfminer had 0 (98% improvement) |
| **2026-03-19** | **Printed TOC detection and chapter heading improvements** |
| 2026-03-19 | `detect_toc_section()` — detects printed Table of Contents by structure (cluster of short paragraphs with trailing page numbers) |
| 2026-03-19 | `detect_chapters()` accepts `toc_indices` parameter to skip printed TOC entries |
| 2026-03-19 | Sanity filter: when > 50 chapters detected, filters by title length, deduplication, citation patterns, running header fragments |
| 2026-03-19 | Content validation: drops headings with < 50 words before next heading (kills TOC-only entries) |
| 2026-03-19 | TOC rescue: uses dropped TOC titles as search keys to find body locations, with period normalization ("1." = "1") and 80% prefix matching |
| 2026-03-19 | Tightened `is_strong_chapter_heading()`: requires period after number, 3+ words, max 2 periods in title; Roman numerals require 4+ words |
| **2026-03-19** | **apply_chapter_hints() improvements** |
| 2026-03-19 | `search_start` skip: hints matching starts at paragraph 120+ to avoid matching in TOC/front matter area |
| 2026-03-19 | Short-first search order: prefers short standalone paragraphs over embedded matches in long paragraphs |
| 2026-03-19 | ALL-CAPS deprioritization: running headers searched last to prefer properly-cased headings |
| **2026-03-19** | **Dependencies and documentation** |
| 2026-03-19 | Created `EbookAutomation_Dependencies.md` — comprehensive external dependency reference |
| 2026-03-19 | Added dependency reference pointer to `CLAUDE.md` |
| 2026-03-19 | pdfminer.six added as required Python dependency (install via `python -m pip install pdfminer.six`) |
| **2026-03-19** | **Refactored `apply_chapter_hints()` — quality-scored matching with monotonic ordering** |
| 2026-03-19 | Replaced strategy-based matching (1/2/3/4) with quality-scored system (Q0-Q4): Q4=exact match, Q3=exact ALL-CAPS or near-exact prefix, Q2=near-exact ALL-CAPS, Q1=substring in short paragraph, Q0=embedded in long paragraph |
| 2026-03-19 | Monotonic ordering constraint: each hint must match at a paragraph index strictly after the previous hint's match, preventing out-of-order chapter detection |
| 2026-03-19 | Matched paragraphs replaced with Claude hint title text, preserving proper casing and numbering (fixes lowercase headings, missing chapter numbers) |
| 2026-03-19 | `_norm()` helper: strips markdown `##` markers, normalises Unicode dashes/quotes to ASCII, strips leading numbering/roman numerals/chapter prefixes |
| 2026-03-19 | Body-words scoring: prefers candidates with substantial prose after them (real chapters) over TOC entries (no body text) |
| 2026-03-19 | Lowered prefix match threshold from 75% to 60% to catch line-wrapped titles (ch8 "Basil of Caesarea and the Development of" and ch14 "On Not Three Gods: Gregory of Nyssa's") |
| 2026-03-19 | Result: Nicaea 21/22 chapters matched in correct reading order with proper titles |
| **2026-03-19** | **Fixed `<<PAGE:N>>` marker insertion and stripping** |
| 2026-03-19 | `extract_text()` and `_extract_with_pdfminer()` now insert `<<PAGE:N>>` markers before each page's text — required by `map_bookmarks_to_paragraphs()` |
| 2026-03-19 | Fixed Genesis regression: all bookmarks were mapping to `para 0` because page markers were missing from refactored extraction |
| 2026-03-19 | Added page marker stripping in `process_kindle()` and `process_pdf()` for the non-bookmark path (hints/heuristic), preventing `<<_9>>` artifacts in KFX output |
| 2026-03-19 | Genesis: 95 page markers found, 20 bookmarks mapped to correct paragraph indices |
| 2026-03-19 | Nicaea: 490 page markers stripped, zero remaining in output |
| **2026-03-19** | **Front matter detection for non-bookmark books** |
| 2026-03-19 | `process_kindle()` non-bookmark path: scans paragraphs before first chapter heading for title, copyright, dedication, acknowledgements, preface, foreword sections |
| 2026-03-19 | Inserts synthetic `# Front Matter` h1 at document start with detected sections as `## ` sub-headings — mirrors bookmark-path behavior for books without PDF outlines |
| 2026-03-19 | Nicaea: detected Title, Copyright, Acknowledgements as front matter sub-sections |
| **2026-03-19** | **Fixed `--start-reading-at` in PSM1 — targets first content chapter instead of first front matter entry** |
| 2026-03-19 | Old behavior: `--start-reading-at "//h:h2[1]"` matched "Title" (front matter h2), causing Calibre/KFX to treat front matter as pre-content and suppress it from sidebar navigation |
| 2026-03-19 | New behavior: scans text for first `## ` heading that doesn't match front matter patterns (Title, Copyright, Acknowledgements, Introduction, Foreword, Preface, Dedication, Contents), uses XPath `normalize-space()` match on heading text |
| 2026-03-19 | Nicaea: `--start-reading-at` now targets "1. Points of Departure" instead of "Title" |
| 2026-03-19 | Fallback chain: first non-FM h2 → first non-"Front Matter" h1 → h2[1] (h2-only books) → h1[1] (h1-only books) |
| **2026-03-19** | **Installed Claude Code for VS Code as primary development tool. Installed Node.js 24.14.0 LTS. Configured Context7 MCP server for live API documentation lookups.** |
| **2026-03-20** | **Phase 8: Spaced-letter artifact collapse in `fix_ocr_artifacts()`** |
| 2026-03-20 | Phase 8: detects runs of single characters separated by spaces from pdfminer font extraction artifacts (`"e x a c t h a r m o n y"` → `"exact harmony"`), collapses via greedy longest-match dictionary lookup with pyspellchecker |
| 2026-03-20 | Phase 8: theological vocabulary (~40 terms: homoousios, hypostasis, consubstantial, Nicaea, etc.) added to spellchecker for domain accuracy |
| 2026-03-20 | Phase 8: improved word-splitter fallback — unknown chunks consumed as units until next known word starts (keeps `"simi"` intact instead of `"si mi"`) |
| 2026-03-20 | Phase 8: false-positive filter — requires 3+ distinct letter characters in collapsed run. Eliminates TOC dot leaders (`'. . . . .'`) and digit sequences (`'9 8 7 6 5 4 3 2'`). Nicaea: 28 → 11 collapses, Mexico: 42 → 25 |
| 2026-03-20 | Nicaea spaced-letter artifacts: 11 collapsed, 0 remaining in output |
| **2026-03-20** | **Fixed PowerShell 5.1 `Start-Process` ExitCode null bug in `EbookAutomation.psm1`** |
| 2026-03-20 | Added `$proc.WaitForExit()` after polling loops at 4 call sites: `Convert-ToTTS` extraction, `Convert-ToKindle` Pass 1, Pass 2, and Calibre invocation |
| 2026-03-20 | Was causing false "text extraction failed (exit )" and "Calibre exited with code " errors on successful conversions — `Start-Process -PassThru` doesn't populate `ExitCode` without explicit `WaitForExit()` in PS 5.1 |
| **2026-03-20** | **Comprehensive conversion testing: Dionysius, Mexico, Secret Societies** |
| 2026-03-20 | Dionysius the Areopagite: pypdf extraction, 42 bookmarks, 42 chapters placed, 784 KB KFX. Clean conversion with cover image, 2-level TOC |
| 2026-03-20 | Mexico's Illicit Drug Networks: pypdf extraction, 14 bookmarks, 14 chapters placed, 1.5 MB KFX. Clean conversion with cover image, 2-level TOC |
| 2026-03-20 | Secret Societies of All Ages (1875 scan): FAILED — image-only PDF, pypdf extracts only Google Books boilerplate (7 paragraphs). Needs Tesseract OCR integration |
| 2026-03-20 | Context7 MCP server confirmed working for live pdfminer.six API documentation lookups |
| **2026-03-20** | **Phase 3b/3c/3d: Ligature split fixes in `fix_ocr_artifacts()`** |
| 2026-03-20 | Phase 3b fix: multi-space normalization before hyphen-split rejoining — pypdf double-space ligature artifacts were breaking word-pair detection. Mexico: 1,827 words rejoined (was ~0 before) |
| 2026-03-20 | Phase 3c: "Th e/is/at" ligature split fix — merges `Th ` + word when result is a valid dictionary word. Both "th" and "e" are valid words so Phase 3b skipped them. Mexico: 708 fixes (The, This, Thus, There, That, Three, Through, etc.) |
| 2026-03-20 | Phase 3d: fi/fl/ffi/ffl compound ligature split fix — targeted regex merges split ligature fragments in compounds and hyphenated words. Mexico: 224 fixes (trafficking, conflict, influence, profit, etc.) |
| **2026-03-20** | **Phase 9: Repeated-fragment running header detector** |
| 2026-03-20 | Pre-scans all paragraphs before any phase runs to detect text strings 15+ chars appearing 5+ times. Strips standalone and embedded occurrences before Phase 0g can mangle them |
| 2026-03-20 | Also groups by text with trailing page numbers stripped (catches mixed-case headers with varying page numbers like "State Reaction and Illicit-Network Resilience 21/27/33...") |
| 2026-03-20 | Dionysius: 145 headers stripped (98 standalone + 47 embedded "C.E. RoltDionysius the Areopagite..."). Mexico: 51 headers stripped (10 standalone + 41 embedded) |
| 2026-03-20 | Ordering fix: pre-scan runs before Phase 0g to prevent partial stripping that leaves orphaned fragments (Dionysius "C.E. Rolt...On and the", Mexico "ience 21") |
| **2026-03-20** | **Content-alignment pass in `map_bookmarks_to_paragraphs()`** |
| 2026-03-20 | After initial page-to-paragraph mapping, searches forward within 2-page window for body paragraphs matching bookmark titles. Fixes content offset where chapters start mid-page |
| 2026-03-20 | 4 quality levels: Q4 exact match, Q3 ALL-CAPS match, Q2 prefix match (60%+), Q1 word-overlap match (60%+ of title words) |
| 2026-03-20 | Dionysius: 27/42 bookmarks realigned to correct content paragraphs. Genesis: 5 bookmarks realigned |
| **2026-03-20** | **Heuristic bookmark level promotion/demotion** |
| 2026-03-20 | L2→L1 promotion: promotes L2 bookmarks to Part (h1) when followed by 3+ sub-items and title doesn't match front/back matter or numbered chapters. Dionysius: promoted Introduction, The Divine Names, Influence of Dionysius |
| 2026-03-20 | L1→L2 demotion: demotes numbered L1 bookmarks when siblings in the numbered sequence are L2. Dionysius: demoted "10. Bibliography" to match "1. The Author" through "9. Conclusion" |
| **2026-03-20** | **Phase 10: Page-boundary sentence rejoining** |
| 2026-03-20 | Detects paragraphs ending mid-sentence (no terminal punctuation) and merges with the next paragraph. Protects heading paragraphs and new-section patterns. Dionysius: 107 merges. Genesis: 546 merges. Mexico: 563 merges |
| **2026-03-20** | **Other fixes** |
| 2026-03-20 | FINAL PASS extended to strip single-digit leading footnote numbers (was 2-3 digits only). Guards: skip headings, skip numbered lists (digit + period). Mexico: 17 stripped |
| 2026-03-20 | Added Project Principles section to ProjectTracker: AI-first for ambiguous problems, layered processing, generic over specific |
| **2026-03-20** | **AI Quality Pass Phase 1: Quality Scan MVP** |
| 2026-03-20 | `ai_quality_pass()` in `pdf_to_balabolka.py` — samples 10-20 paragraphs from evenly spaced positions, sends to Claude API for quality analysis |
| 2026-03-20 | Deterministic scoring: severity-weighted penalties (critical=-10, moderate=-3, minor=-1) with gentle frequency multiplier based on estimated total occurrences |
| 2026-03-20 | Back-matter exclusion: prompt instructs Claude to ignore index entries, bibliographic citations, and footnote references when flagging issues |
| 2026-03-20 | Quality report saved as JSON alongside KFX output: score, issues with severity/type/fix/estimated_total, recommendations |
| 2026-03-20 | PowerShell integration: `-ValidateQuality` switch on `Convert-ToKindle`, auto-enables when `ANTHROPIC_API_KEY` env var is set |
| 2026-03-20 | Test results: Mexico 71/100 (systematic ligature splits correctly detected), Genesis 80/100 (clean body text, minor soft-hyphen artifacts) |
| **2026-03-20** | **AI Quality Pass Phase 2: Auto-Fix with Global Pattern Propagation** |
| 2026-03-20 | Sample-based fixes: for each issue with a "fix" field, verifies text exists in paragraph (with case-insensitive fallback), applies replacement |
| 2026-03-20 | Global pattern propagation: collects all successful `split_word` and `encoding_artifact` fixes into a pattern dictionary, applies them across ALL paragraphs (not just sampled ones) |
| 2026-03-20 | Verification pass (Call 3): sends fixed paragraphs with surrounding context back to Claude to verify correctness and catch remaining issues |
| 2026-03-20 | Mexico results: 12 sample fixes amplified to 497 total fixes (485 global), score improved 52→88. Key patterns: `T eo`→`Teo` (62 paragraphs), `htt p://`→`http://` (276 paragraphs), `aft er`→`after` (29 paragraphs) |
| 2026-03-20 | Report fields: `original_score`, `final_score`, `sample_fixes`, `global_fixes`, `total_fixes`, `fixes_flagged` |
| **2026-03-20** | **AI Quality Pass design doc created at `docs/AI_Quality_Pass_Design.md`** |
| **2026-03-20** | **Installed and configured Atlassian MCP server for Jira integration** |
| 2026-03-20 | Created 5 Epics and 10 Tasks in Jira (SCRUM project) covering all workstreams: PDF extraction, AI integration, Kindle conversion, infrastructure, Tesseract OCR |
| **2026-03-20** | **AI Quality Pass Bug Fix 1: Hallucination guard** |
| 2026-03-20 | Fixes for `orphaned_fragment` type now limited to ≤3 characters added beyond original text. Prevents AI from inventing sentence continuations (e.g., "the r" → "the rock" OK, but "the r" → "the rock face of the mountain" blocked). Fragments exceeding threshold flagged for manual review. Jesus and the Land: score improved from 64→72 (was 64→30 before guard) |
| **2026-03-20** | **AI Quality Pass Bug Fix 2: Double-application guard** |
| 2026-03-20 | Global propagation now checks `if replacement in para and pattern in replacement: continue` to prevent stutter corruptions where a pattern is a substring of its own replacement (e.g., "Ultimate"→"Ultimately" re-matching inside already-fixed "Ultimately" → "Ultimatelyly"). Also tracks globally-modified paragraphs to prevent re-application. Khazars: zero stutter patterns after fix |
| **2026-03-20** | **Tested 4 new books with AI Quality Pass** |
| 2026-03-20 | Oil Kings (406pp, 21 bookmarks): score 94 — cleanest conversion, 318 headers stripped, 5 AI fixes |
| 2026-03-20 | Brother of Jesus (~200pp, 35 bookmarks): score 84 — 25 headers stripped, 4 AI fixes (hyphen splits) |
| 2026-03-20 | Jesus and the Land (~180pp, 13 bookmarks): score 72 — severe page-boundary truncation, 4 safe AI fixes, 8 flagged for review |
| 2026-03-20 | Khazars (48pp, 0 bookmarks): score 83 — heuristic chapter detection, AI caught source spelling errors ("pensinsula", "millenium") |
| **2026-03-20** | **Phase 9: Leading page number normalization in pre-scan** |
| 2026-03-20 | Pre-scan now strips leading digits+whitespace before grouping repeated fragments. "4 the brother of jesus" and "66 the brother of jesus" normalize to "the brother of jesus" → 21 occurrences detected. Brother of Jesus: 166 embedded running headers stripped (was 0 before). Generic fix for any book with "page_number + header_text" pattern |
| **2026-03-20** | **TOC numbered entry stripping** |
| 2026-03-20 | Extends TOC detection to match "digit. Title text digit" patterns within TOC regions (between Contents heading and first chapter). Conservative — only strips within detected TOC boundaries. Brother of Jesus: 8 numbered TOC entries stripped |
| **2026-03-20** | **Introduction promotion guard** |
| 2026-03-20 | Never promotes L2→L1 bookmark if preceding L1 is a "Part" heading. An L2 after a Part is correctly nested as a chapter within that part. Fixed "Introduction-In His End, a Beginning" being incorrectly promoted out of Part Two in Brother of Jesus |
| **2026-03-20** | **Footnote stripping unit word guard** |
| 2026-03-20 | FINAL PASS now protects statistical content from false-positive footnote stripping. Guards: unit words ("percent", "million", "barrels", etc.) and lowercase-start words after the number. Oil Kings: eliminated 23 false positive strips (29→6), preserving content like "90 percent of Japan's petroleum supplies" |
| **2026-03-20** | **Deterministic AI Quality Pass scoring** |
| 2026-03-20 | Set `temperature: 0` on both API calls (scan + verification). Same book now produces identical scores across runs. Oil Kings: 77/77/77 across 3 consecutive runs. Score changes now only reflect pipeline improvements, not sampling luck |
| 2026-03-20 | Deterministic baseline scores established: Oil Kings 77, Brother of Jesus 86, Jesus/Land 75, Khazars 68, Mexico 70, Dionysius 70, Genesis 58 |
| **2026-03-20** | **AI-powered paragraph rejoining (`ai_rejoin_fragments`)** |
| 2026-03-20 | Detects page-boundary sentence splits using heuristics (truncated endings, lowercase continuations, split words), sends candidate pairs to Claude API for verification, joins confirmed pairs. Uses `temperature:0` for deterministic results, batches 15 pairs per API call, caps at 10 calls (150 pairs) per book |
| 2026-03-20 | Jesus and the Land: 113 joins from 146 candidates. Oil Kings: 119 joins from 824 candidates (150 processed). Genesis: 96 joins from 121 candidates |
| 2026-03-20 | Rejoin stats added to quality_report.json: `rejoin_candidates`, `rejoin_applied`, `rejoin_skipped`, `rejoin_beyond_cap` |
| **2026-03-20** | **Bookmark Unicode cleanup + heading order fix** |
| 2026-03-20 | `extract_bookmarks()` now strips U+FFFD, control chars, and collapses whitespace in bookmark titles. Jesus and the Land: "1\ufffd\ufffd\ufffdThe biblical heritage" → "1 The biblical heritage" |
| 2026-03-20 | Post-alignment page-order enforcement: swaps heading paragraph contents when content alignment reverses original page order. Fixed Introduction appearing after Chapter 1 in Jesus and the Land |
| **2026-03-20** | **AI Quality Pass Phase 3: Sub-heading Detection (`ai_detect_subheadings`)** |
| 2026-03-20 | Heuristic pre-filter identifies short non-sentence paragraphs as heading candidates (ALL CAPS, Title Case, colon patterns, 10-100 chars, no sentence-ending punctuation). Claude API verifies each candidate with surrounding context. Confirmed headings promoted to `###` (h3) |
| 2026-03-20 | Calibre `--level3-toc "//h:h3"` added for 3-level KFX TOC hierarchy (`# Parts > ## Chapters > ### Sub-sections`). PSM1 auto-detects h3 headings and adds level3-toc arg |
| 2026-03-20 | Results: Brother of Jesus 38 headings from 89 candidates (score 94), Jesus/Land 22 from 39, Genesis 18 from 63 (score 84), Mexico 14 from 149 (score 69). Total: 92 headings detected across 4 books |
| 2026-03-20 | Known: 2-3 false positives in Genesis — running headers with page numbers ("GENESIS I-3 AND MODERN SCIENCE 133") and long sentence fragments promoted to headings. Future: exclude paragraphs ending with trailing page numbers and sentences over 60 chars |
| 2026-03-20 | Sub-heading detection disabled for books WITH PDF bookmarks (source-first principle). Only activates for no-bookmark books |
| **2026-03-20** | **CRITICAL: Page marker isolation in `clean_and_join()`** |
| 2026-03-20 | Added blank line BEFORE `<<PAGE:N>>` markers (not just after). Root cause of chapter misalignment: markers were being absorbed into preceding paragraphs during paragraph assembly. Genesis: 0 embedded / 253 standalone (was 158 embedded / 95 standalone) |
| **2026-03-20** | **Pipeline reorder: rejoin BEFORE bookmark mapping** |
| 2026-03-20 | NEW ORDER: `fix_ocr_artifacts()` → `ai_rejoin_fragments()` → `map_bookmarks_to_paragraphs()` → `ai_quality_pass()`. Heading indices now calculated on FINAL paragraph state after all merges. Eliminates stale-index chapter content drift |
| **2026-03-20** | **Bookmark handling fixes** |
| 2026-03-20 | Image-only page forwarding: when bookmark page has no extractable text (decorative chapter opener), forward to next page with content. Brother of Jesus: 26 of 35 bookmarks forwarded |
| 2026-03-20 | 0-indexed to 1-indexed page number fix in `extract_bookmarks()` — pypdf returns 0-indexed, page markers use 1-indexed |
| 2026-03-20 | Bookmark collision resolution: forward search for title text when multiple bookmarks map to same paragraph |
| 2026-03-20 | Pre-Part promotion guard: don't promote L2→L1 bookmarks before the first Part heading ("A Note on..." stays h2 in Oil Kings) |
| 2026-03-20 | Front Matter insertion disabled for books with 5+ bookmarks (source-first principle) |
| 2026-03-20 | Start-reading-at logic: prefer first non-FM heading (Introduction) over first numbered chapter |
| 2026-03-20 | Bookmark "m"→"rn" OCR correction with context-aware dictionary check ("Modem Science" → "Modern Science") |
| **2026-03-20** | **Title fragment and author name preservation** |
| 2026-03-20 | Protection window expanded from 4 to 8 paragraphs after page markers. Covers full chapter title page pattern: marker → number → title → subtitle → author → body |
| 2026-03-20 | Author names (2-word: "Andrew Louth", "Francis Watson", "David Wilkinson") no longer dropped by 4-word artifact filter |
| 2026-03-20 | Subtitle fragments separated from body text near page markers |
| **2026-03-20** | **Formatting improvements** |
| 2026-03-20 | ALL CAPS section break visual separation: blank line before short ALL-CAPS paragraphs between chapter headings. Oil Kings: 36 separations |
| 2026-03-20 | Epigraph quote/attribution detection: blank line after attribution paragraphs (em-dash patterns) near chapter headings |
| **2026-03-20** | **Updated Project Principles** |
| 2026-03-20 | Added: "Source-first, then heuristics, then AI" and "Fix the foundation before adding compensating layers" |
| **2026-03-20** | **HTML-Based Extraction Refactor Phase 1 COMPLETE — pdfminer.six integration with font metadata extraction** |
| 2026-03-20 | `extract_with_pdfminer_html()` captures font name, size, bold/italic, positioning for every text span. `format_paragraphs_as_html()` converts to semantic HTML with `<h1>`/`<h2>`/`<h3>` from font size hierarchy, `<blockquote><em>` for italic epigraphs, attribution detection, `<em>` for all italic text |
| 2026-03-20 | Oil Kings: 3-tier heading hierarchy (25pt/21pt/15pt), 866 italic spans, 4 blockquotes, 91 section breaks. KFX: 2.4 MB, 22 TOC entries |
| 2026-03-20 | Genesis: 211 running headers auto-stripped from 19 font patterns, Front Matter h1 inserted, 300 italic spans, 14 blockquotes. KFX: 1.3 MB |
| 2026-03-20 | Whitespace normalization in `_flush_line_group()` — collapses pdfminer multi-space character positioning to single spaces |
| 2026-03-20 | Epigraph detection from italic font metadata: italic paragraphs after headings wrapped in `<blockquote><em>`, attribution lines (em-dash prefix) get `class="attribution"` |
| 2026-03-20 | Back matter h3 suppression: section headings in Notes/Bibliography/Index use `<p><strong>` instead of `<h3>` to avoid KFX TOC nesting errors |
| 2026-03-20 | `-UsePdfminer` parameter (alias for `-UseHtmlExtraction`) wired into `Convert-ToKindle` in PSM1 |
| 2026-03-20 | Start-reading-at logic updated to skip front matter headings (Introduction, A Note, Acknowledgments, etc.) and target first content chapter |
| **2026-03-20** | **Superscript footnote detection from pdfminer font size metadata** |
| 2026-03-20 | Character-level superscript detection in `extract_with_pdfminer_html()`: digits with `font_size < dominant_size * 0.8` wrapped in `<sup>` tags. Mexico: 714 `<sup>` tags, 0 false positives. Oil Kings: 0 (no footnotes — correct). Guard: `dominant_size >= 9pt` prevents false positives on small-font lines |
| 2026-03-20 | `_html_escape()` updated to preserve `<sup>`, `<em>`, `<strong>` tags through HTML encoding |
| **2026-03-20** | **Bidirectional endnote linking (`_link_endnotes()`)** |
| 2026-03-20 | Two strategies: (1) collected endnotes under a "Notes" heading — single-scope linking; (2) per-chapter endnote clusters — detected by 3+ consecutive numbered paragraphs, chapter-scoped IDs to avoid collisions |
| 2026-03-20 | Body refs: `<sup><a id="noteref_X" href="#endnote_X">N</a></sup>`. Endnotes: `<a id="endnote_X"></a><a href="#noteref_X">N.</a> text`. Tap footnote → jump to note, tap note number → jump back |
| 2026-03-20 | Mexico: 377 endnotes parsed across 6 chapter clusters, 306 superscripts bidirectionally linked. KFX: 1.6 MB, links functional |
| **2026-03-20** | **Attribution splitting, TOC expansion, bookmark OCR fix refinements** |
| 2026-03-20 | Attribution splitting: blockquote paragraphs containing em-dash split into quote + `<p class="attribution">`. Oil Kings: 4 attributions cleanly separated from epigraph poetry |
| 2026-03-20 | TOC page range expansion: scan-based detection of TOC-like content on subsequent pages (short lines ending with digits, ≥30% of paragraphs). Genesis: pages 8–9 detected (was 8 only), 6 leaked TOC entries eliminated |
| 2026-03-20 | Bookmark m→rn OCR fix: replaced academic context word list with body text lookup. If "Modern" appears in body but "Modem" in bookmark, fix it. Genesis: "Index of Modem Authors" → "Index of Modern Authors", heading text corrected from bookmark metadata |
| **2026-03-20** | **Updated `-UsePdfminer` test library results** |
| 2026-03-20 | Oil Kings: 2.4 MB KFX, 7 h1 + 15 h2 + 91 h3, 4 blockquotes, 866 `<em>`, 4 attributions. Production quality |
| 2026-03-20 | Genesis: 1.3 MB KFX, Front Matter h1 inserted, 211 running headers stripped, "Modern" fixed throughout. Clean |
| 2026-03-20 | Mexico: 1.6 MB KFX, 714 `<sup>` tags, 306 bidirectional footnote links, 377 endnotes across 6 chapters. Footnote linking working |
| **2026-03-20** | **Ligature cleanup ported to pdfminer path** |
| 2026-03-20 | `_fix_ligature_splits()` extracted as reusable function. Applied to pdfminer paragraph text after extraction, before HTML formatting. Mexico: 810 paragraphs fixed ("th e"→"the", "fi gures"→"figures") |
| **2026-03-20** | **Fragment rejoining in pdfminer path** |
| 2026-03-20 | `rejoin_html_fragments()` merges page-boundary sentence splits. Handles hyphen breaks ("chal-" + "lenge" → "challenge") and lowercase continuations. Oil Kings: 2,053 merged. Brother of Jesus: 1,185. Jesus/Land: 509. Genesis: 869 |
| **2026-03-20** | **Duplicate heading demotion** |
| 2026-03-20 | `format_paragraphs_as_html()` detects consecutive h2 headings with 80%+ word overlap and demotes duplicates to `<p>`. Prevents decorative title pages and body text titles from creating double TOC entries |
| **2026-03-20** | **Standalone page number stripping** |
| 2026-03-20 | Paragraphs consisting of only 1-3 digit numbers (page numbers from headers/footers) stripped from pdfminer output |
| **2026-03-20** | **Hyphen-break and Unicode whitespace normalization** |
| 2026-03-20 | `_flush_line_group()` handles within-page hyphen breaks at line boundaries ("chal-" + "lenge" → "challenge"). Unicode whitespace characters (U+00A0, U+2000-U+200B, tabs) normalized to regular spaces. Mexico: 0 double spaces, 0 non-breaking spaces remaining |
| **2026-03-20** | **Per-chapter endnote linking improvement** |
| 2026-03-20 | `_link_endnotes()` per-chapter strategy: only splits at numbered chapter headings (Introduction, numbered chapters, Conclusion), not sub-section h2s. Accent normalization for bookmark matching (Félix→Felix). Heading line merge for bold text. Mexico: 377/377 superscripts linked (was 233) |
| **2026-03-20** | **Batch pdfminer testing: 4 additional books** |
| 2026-03-20 | Brother of Jesus: 1.0 MB KFX, 7 h1 + 29 h2 + 26 h3, 11 blockquotes, 1,185 fragments rejoined, 559 ligature fixes |
| 2026-03-20 | Dionysius: 0.8 MB KFX, 0 h1 + 21 h2 + 36 h3, 21 blockquotes, 365 fragments rejoined. 1,105 unlinked superscripts (per-page footnote format) |
| 2026-03-20 | Jesus and the Land: 1.8 MB KFX, 3 h1 + 15 h2 + 65 h3, 509 fragments rejoined. Front Matter h1 inserted. Known: --start-reading-at pointed to chapter 6 |
| 2026-03-20 | Khazars: image-only PDF, pdfminer extracted 51 empty paragraphs (same as pypdf). Needs Tesseract OCR |
| **2026-03-20** | **Test harness (`tools/test_pipeline.py`)** |
| 2026-03-20 | 5 hardcoded test cases with 42 total assertions (heading counts, content checks, formatting quality). CLI: `--quick` (HTML only), `--list`, `--recapture`, `--capture-only`, `--verbose`. PowerShell wrapper: `Test-EbookPipeline` exported from module |
| 2026-03-20 | Auto-capture baselines to `tools/test_cases.json` — every future book becomes a permanent regression test. Baseline validation: heading counts ±2 tolerance, footnote linking can't regress, ligature splits can't increase, chapter openings must match, KFX size within 10% |
| 2026-03-20 | All 5 books pass in both quick and full modes (42/42 checks). Oil Kings: 17/17, Genesis: 8/8, Mexico: 8/8, Brother of Jesus: 5/5, Dionysius: 4/4 |
| **2026-03-20** | **CLAUDE.md and developer tooling updates** |
| 2026-03-20 | CLAUDE.md: added Environment, Pipeline Architecture, Post-Change Verification Rules, Testing, Common Mistakes sections |
| 2026-03-20 | `.claude/skills/test-pipeline/SKILL.md` — custom skill for running regression tests |
| 2026-03-20 | `.claude/settings.json` — postToolUse hook: `python -m py_compile` runs automatically after Edit/Write on .py files |
| 2026-03-20 | `.claude/settings.json` — permissions: `Bash(*)`, `Edit`, `Write`, `mcp__claude_ai_Atlassian__*` for auto-approval |
| **2026-03-21** | **Start-reading-at fix for pdfminer path** |
| 2026-03-21 | HTML path: added duplicate heading detection — TOC entries appearing twice (once in FM, once as real chapter) are skipped. Expanded FM pattern list. Removed "Introduction" from FM exclusions (valid start heading) |
| 2026-03-21 | Markdown path: added `$inFrontMatter` flag tracking — h2 headings nested under `# Front Matter` section are skipped |
| 2026-03-21 | Jesus and the Land: `--start-reading-at` now correctly targets "The Holy Land in the first century" (was "6 Paul and the promises to Abraham") |
| **2026-03-21** | **Mexico heading misclassification fixes** |
| 2026-03-21 | Dedication pattern guard: h2 headings matching "To my/For my/In memory of/Dedicated to" within first 10% of document demoted to `<p><em>`. Mexico: "To my family: Sofia, Ethan, and Sean." correctly demoted |
| 2026-03-21 | Long sentence guard: h2 candidates over 80 chars that read as complete sentences (contain verbs, end with punctuation) demoted to `<p>`. Mexico: "networks that use their high profits..." correctly demoted |
| **2026-03-21** | **Dionysius per-page footnote linking (Strategy 3)** |
| 2026-03-21 | New `_link_per_page_footnotes()` — identifies footnote paragraphs starting with `<p><sup>N</sup>`, classifies all `<sup>` inside as footnote text, matches each body ref to nearest forward footnote within 5,000 chars. Creates bidirectional links with unique `fn_N` IDs |
| 2026-03-21 | `_link_endnotes()` wrapper: tries Strategies 1/2 first. If they link ≤20% of `<sup>` tags, discards output and runs Strategy 3 on original HTML |
| 2026-03-21 | Dionysius: 454 pairs linked (was 13 false matches). 87 false endnote anchors from numbered text paragraphs eliminated. 197 remaining unlinked (extraction-level edge cases) |
| 2026-03-21 | All 5 test cases pass (42/42 checks) — zero regressions |
| **2026-03-21** | **Bookmark Reconciliation (FIX 6)** |
| 2026-03-21 | h2 demotion for non-bookmark headings: headings detected by font size but absent from PDF bookmarks demoted to avoid false TOC entries |
| 2026-03-21 | h3 promotion for bookmark matches: bookmarks matching sub-section text promoted to h3 for navigable TOC |
| 2026-03-21 | h1 reconciliation: smart guards for generic bookmarks (e.g., single-word titles that could be body text). Improved `_match_bookmark()` with reverse lookup, Roman numeral matching, space-collapsed comparison |
| 2026-03-21 | Front Matter subtitle guard: detects ALL CAPS subtitle before title h1, skips synthetic FM insertion |
| **2026-03-21** | **Multi-fragment ligature merges (2-4 parts)** |
| 2026-03-21 | Extended `_fix_ligature_splits()` to handle 2-4 part splits: "att en tion"→"attention", "traf fi cking"→"trafficking", "eff ort"→"effort" |
| 2026-03-21 | Ligature function-word guard: protects "as a", "in a", "to live" from false merging |
| **2026-03-21** | **Cross-paragraph hyphen skip** |
| 2026-03-21 | `rejoin_html_fragments()` now skips footnotes/running headers to find the real continuation paragraph for hyphen breaks |
| **2026-03-21** | **TOC page scope limit (15%)** |
| 2026-03-21 | Prevents false TOC detection on content pages — TOC scanning restricted to first 15% of document |
| **2026-03-21** | **FIX 5 exclusion list expanded** |
| 2026-03-21 | Further Reading, References, Glossary, Appendix, Abbreviation, Table of Contents added to back-matter exclusion list |
| **2026-03-21** | **Italic page-boundary rejoin relaxation** |
| 2026-03-21 | Allows italic mismatch when font size/bold match for short fragments — prevents orphaned italic sentence endings |
| **2026-03-21** | **Fragment rejoin improvement** |
| 2026-03-21 | Non-body-sized paragraphs skipped when finding merge candidates, preventing false joins with footnotes/headers |
| **2026-03-21** | **CLAUDE.md and developer tooling** |
| 2026-03-21 | Syntax check hook in `.claude/settings.json` — `python -m py_compile` runs after .py edits |
| 2026-03-21 | `Bash(*)` permission added to user-level settings.json |
| **2026-03-21** | **New test results** |
| 2026-03-21 | Justinian's Novella 146: 26 pages, 0 bookmarks, 275 KB KFX. Clean pass, per-page footnote issues |
| 2026-03-21 | Civilta Cattolica: FAILED — spaceless text layer, pdfminer gets concatenated text. Needs word-boundary reconstruction |
| 2026-03-21 | Secret Societies: CONFIRMED image-only on pdfminer (same as pypdf). Needs Tesseract OCR |
| 2026-03-21 | Ezekiel II: 637 pages extracted in 155s. KFX filename bug (special chars) + false success reporting bug found. Hebrew/Greek garbled. Per-page footnotes not linked. Future priority |
| **2026-03-21** | **Tesseract OCR integration for scanned/image-only PDFs (SCRUM-9/SCRUM-14)** |
| 2026-03-21 | `detect_pdf_type()` — samples 5-10 pages evenly, classifies as `"structured"` (≥50 avg chars/page) or `"image"` (<50). Zero false positives across 22 test PDFs |
| 2026-03-21 | `extract_text_ocr()` — batch OCR via pdf2image + pytesseract, 25 pages/batch for memory safety, returns `<<PAGE:N>>` format matching `extract_text()`. Early Tesseract validation prevents per-page error spam |
| 2026-03-21 | Pipeline routing in `process_pdf()`: auto-detect by default, `--ocr` to force, `--no-ocr` to skip. Standard structured-PDF path completely untouched |
| 2026-03-21 | CLI flags: `--ocr`, `--no-ocr`, `--tesseract-path`, `--poppler-path`, `--ocr-dpi` |
| 2026-03-21 | PowerShell: `-UseOCR` switch on `Convert-ToTTS` and `Invoke-EbookPipeline`. Auto-resolves tesseract/poppler paths from `settings.json` |
| 2026-03-21 | `Initialize-EbookAutomation` — Tesseract check added (step 3/4), pytesseract Python package check added |
| 2026-03-21 | `settings.json` — `paths.tesseract` and `paths.poppler` added |
| 2026-03-21 | New dependencies: pytesseract 0.3.13, Tesseract OCR 5.5.0 (UB-Mannheim), pdf2image upgraded from optional to required-for-OCR |
| 2026-03-21 | Secret Societies test: 417 pages, 300 DPI, 10.8 min, 409/417 pages with text, 63,733 words, 16 chapters detected. Zero errors |
| 2026-03-21 | Regression verified: Reading Genesis (95,169 words, 14 chapters) and Brother of Jesus (101,479 words, 35 chapters) produce identical output with and without OCR auto-detection |
| **2026-03-22** | **Batch QA system (`tools/batch_qa.py`) — SCRUM-87** |
| 2026-03-22 | Process entire folders of ebooks with structured diagnostics, cross-book pattern analysis, failure clustering, and per-book overrides. Parallel processing with configurable concurrency. JSON report output with summary statistics |
| 2026-03-22 | Heading duplication bug fixed (SCRUM-75) — styled headings duplicated as garbled OCR text in body paragraphs. Font-based detection now suppresses duplicates |
| 2026-03-22 | Double spacing cleanup (SCRUM-49) — eliminated consecutive blank paragraphs and excessive `<br>` tags in pdfminer HTML output |
| 2026-03-22 | Ligature fix corruption guard — prevent `_fix_ligature_splits()` from corrupting inline HTML tags |
| 2026-03-22 | Character-weighted body size detection and prose heading guard — improved heading vs body text classification |
| 2026-03-22 | Chapter promotion for bookmark-less PDFs — heuristic detection of chapter patterns in unbookmarked books |
| 2026-03-22 | Test-corpus hot folder (`test-corpus/`) — drop-in regression testing with baseline capture/comparison |
| 2026-03-22 | Post-edit auto-test hook — `test_pipeline.py --quick` runs automatically after edits to core pipeline files |
| 2026-03-22 | Visual QA Phase 2 & 3 complete (SCRUM-74) — `-ValidateVisual` switch, pipeline integration, rubric tuning, auto-fix loop |
| 2026-03-22 | VQA API cost optimization (SCRUM-76) — reduced prompt size and response tokens |
| 2026-03-22 | EPUB/MOBI/AZW/DJVU native format support (SCRUM-62/67) — native EPUB extraction via ebooklib, Calibre intermediate for others |
| 2026-03-22 | AZW3 fallback when KFX conversion fails (SCRUM-59/63) |
| 2026-03-22 | Pipeline step timing instrumentation (SCRUM-60/64) |
| 2026-03-22 | PDF hyperlink preservation in Kindle output (SCRUM-61/65) |
| 2026-03-22 | Inline bold/italic preservation via per-span font analysis |
| 2026-03-22 | Baselines captured for 6 core regression test books |
| **2026-03-23** | **Email-to-Kindle delivery system (SCRUM-83/84/89)** |
| 2026-03-23 | `email_to_kindle.py` — SMTP delivery to Amazon Send-to-Kindle with format routing, error mapping, size limits |
| 2026-03-23 | `Send-ToKindle -Email` — PowerShell orchestrator with EPUB fallback chain, PDF splitting for large files |
| 2026-03-23 | `Convert-ToKindle -ProduceEpub` — EPUB generation from intermediate HTML |
| 2026-03-23 | `Invoke-EbookPipeline -EmailToKindle` — email delivery + EPUB production in pipeline |
| 2026-03-23 | Kindle email delivery config schema in settings.json |
| 2026-03-23 | `Initialize-EbookAutomation` — email config checks and approved sender reminder |
| **2026-03-23** | **Book metadata capture system (SCRUM-91)** |
| 2026-03-23 | `book_metadata` table in pattern database — stores merged metadata per book keyed on title_hash |
| 2026-03-23 | PDF metadata extraction via PyMuPDF, EPUB metadata extraction via ebooklib |
| 2026-03-23 | Metadata priority hierarchy: user override > pattern DB > EPUB OPF > PDF internal > filename parser |
| 2026-03-23 | CLI subcommands: extract-metadata, get-metadata, update-metadata, store-metadata |
| 2026-03-23 | Pipeline integration: `Convert-ToKindle` extracts + merges metadata before Calibre, `Convert-ToTTS` populates database |
| 2026-03-23 | `Send-ToKindle` email path injects metadata into PDFs with empty internal metadata |
| **2026-03-23** | **Conversion profiles system (SCRUM-92)** |
| 2026-03-23 | `-Profile` parameter on `Convert-ToKindle`, `Invoke-EbookPipeline`, `Invoke-ConvergeLoop` |
| 2026-03-23 | `content_filter.py` with profile-specific rules and tests |
| 2026-03-23 | `-No*` skip parameters for individual pipeline stages (NoFootnotes, NoHeadings, etc.) |
| **2026-03-23** | **Other March 23 work** |
| 2026-03-23 | Font-based heading detection spec and implementation (`detect_headings_font.py`) |
| 2026-03-23 | Converge loop — autonomous conversion pipeline (SCRUM-90) |
| 2026-03-23 | AI quality pass made detection-only by default with fix guardrails |
| 2026-03-23 | EPUB merge rewrites cross-file links and extracts images |
| 2026-03-23 | Smart Calibre TOC flags — detect h1/h2 hierarchy vs flat structure |
| 2026-03-23 | `Get-ChapterStructure` rewrite + EPUB heading detection (NCX/nav + HTML parsing) |
| **2026-03-24** | **50-book clean baseline + WARN/FAIL diagnosis** |
| 2026-03-24 | Batch QA overnight run: 50 books across 2 batches. After glob fix + timeout scaling + scan/DRM detection: 74% pass rate (was 36% with broken glob) |
| 2026-03-24 | Top failure clusters: footnotes not linked (11), no bold/italic (9), no chapters detected (5), encoding errors (3), scanned without OCR (2) |
| 2026-03-24 | Batch QA fixes: glob mismatch, scaled timeouts, scan detection, DRM detection |
| **2026-03-24** | **VQA quality baseline for 37 structurally-passing books** |
| 2026-03-24 | Full mode run (HTML + KFX + VQA): avg score 57.9, median 58, range 33-81. Only 5/34 (15%) scored above 70 |
| 2026-03-24 | Category averages: page_layout 89.9, cover_images 89.9, heading_formatting 88.7, paragraph_flow 84.6, text_integrity 75.9, toc_navigation 66.8 |
| 2026-03-24 | Key finding: structural extraction quality ≠ visual output quality. TOC navigation and text integrity are systemic weaknesses |
| **2026-03-24** | **Text integrity deep dive on 11 VQA-failing books (SCRUM-118)** |
| 2026-03-24 | Investigated all 11 books with text_integrity below 70. Dominant problems: word merges (4,969 occurrences) and OCR debris (2,911 occurrences), mostly originating in source PDFs |
| 2026-03-24 | Word spacing fix in pdfminer HTML extraction |
| 2026-03-24 | Column detection diagnostics added to batch_qa |
| **2026-03-24** | **Intelligent Extraction — Tiered system (SCRUM-120, phases 1-4 + 6)** |
| 2026-03-24 | Phase 1 (SCRUM-121): Text layer quality scorer — scores extracted text quality 0-100 for routing decisions. Done |
| 2026-03-24 | Phase 2 (SCRUM-122): Re-OCR with Tesseract 5 — auto-escalate when quality score ≤70. OCR-to-HTML bridge, score comparison keeps winner. Coulter: 64→100. Zero API cost |
| 2026-03-24 | Phase 3 (SCRUM-123): Claude Vision extraction — premium Tier 3 transcription for books defeating all other methods. Structured transcription prompt preserves headings, formatting, footnotes, non-Latin scripts. Cost management with `--vision-cost-limit`. Never auto-escalates — requires explicit `--use-vision` |
| 2026-03-24 | Phase 4 (SCRUM-124): Extraction cache — SHA-256 content-addressable storage in pattern database. `times_served` counter for commercial amortization tracking. Cache stats and invalidation CLI. `--no-cache` flag. Corpus tests served in <1s |
| 2026-03-24 | Phase 6 (SCRUM-126): TOC heading detection fix — pattern promotion ("Chapter X", "Part X" keywords → h2), heading hierarchy normalization (swap inverted h1/h2/h3), content-based backmatter detection. Bain: 0→76 chapters, Codex Magica: 0→18 |
| **2026-03-24** | **Data collection enrichment (SCRUM-133)** |
| 2026-03-24 | PDF producer/creator fingerprinting in books table and batch diagnostics |
| 2026-03-24 | Font inventory collection during pdfminer extraction, risky fonts flagged |
| 2026-03-24 | Unicode script detection identifies non-Latin content (Hebrew, Greek, CJK, etc.) |
| 2026-03-24 | `MULTI_SCRIPT_NO_VISION` failure pattern for books with >5% non-Latin content |
| **2026-03-24** | **Post-TOC fix structural comparison** |
| 2026-03-24 | Re-ran 37 books after SCRUM-126: total chapters 1,565→1,587 (+22), h3 headings 8,045→7,126 (-919 from hierarchy normalization), 5 books rescued from 1-chapter to multi-chapter detection |
| 2026-03-24 | Bain and Codex Magica added as regression targets with conservative thresholds |
| 2026-03-24 | test_pipeline.py: 14/14 pass across all regression books |

---

## Notes & Ideas (Parking Lot)

- **HTML-Based Extraction Refactor — Phase 1 COMPLETE (2026-03-20).** ~~Phase 2 remaining: internal links/footnote extraction.~~ Footnote linking done (Strategy 1/2/3). ~~Tesseract hOCR integration for scanned PDFs~~ — **DONE 2026-03-21** via `detect_pdf_type()` + `extract_text_ocr()` using standard Tesseract (not hOCR). See Completed Work changelog and SCRUM-26/SCRUM-30 in Jira.
- ~~**Multi-syllable ligature splits in pdfminer path**~~ — **DONE 2026-03-21.** Multi-fragment ligature merges (2-4 parts) implemented: "att en tion"→"attention", "traf fi cking"→"trafficking", "eff ort"→"effort". Function-word guard protects "as a", "in a" etc.
- ~~**Front Matter TOC leakage in pdfminer path**~~ — **DONE 2026-03-21** (SCRUM-41). Fixed guard ported to `format_paragraphs_as_html()`.
- **Chapter alignment verification function** — Post-conversion verification comparing kindle.txt chapter openings against source PDF page content using fuzzy matching. Catches misalignment automatically instead of during manual review. Compare first 200 chars of body text after each heading against raw pypdf extraction from the bookmark's page.
- **Bookmark whitespace matching** — Jesus/Land TOC missing chapters due to tab chars in bookmark titles breaking `_match_bookmark()`. High priority.
- **Bookmark level mapping** — Mexico chapters nesting under Abbreviations due to h1/h2 level mapping from bookmark levels. High priority.
- **KFX filename sanitization** — Ezekiel II exposed silent Calibre failure on special chars in filenames. Medium priority.
- **Per-page footnote separation** — Footnote-sized text at page bottoms mixed into body paragraphs (Justinian, Ezekiel). Medium priority.
- **Double spacing cleanup** — Extra blank lines between paragraphs in pdfminer output across multiple books. Medium priority.
- **Convert-ToKindle false success reporting** — Reports success even when KFX file doesn't exist (Ezekiel II). Medium priority.
- **Spaceless text layer reconstruction** — Civilta Cattolica has no word boundaries in text layer. Needs dictionary-based word splitting. Future.
- The FOH scraper/parser tooling may eventually warrant its own module separate from the ebook automation suite.
- Look into `Calibre`'s plugin system for additional format support rather than writing custom extraction code.
- Could the Balabolka TXT output be further improved with AI-driven text cleanup (removing OCR artifacts, fixing encoding issues, improving paragraph detection)?
- Kindle Scribe natively supports EPUB (since firmware 5.16.2.1.1) — could skip KFX entirely and output EPUB for simpler pipeline.
- Consider a `requirements.txt` for Python dependencies as the project grows (`pypdf` is currently the only dep, but more may come with EPUB/MOBI support).
- VS Code with Claude Code extension is now the primary development environment.
- PDF-to-EPUB/KFX is the core value proposition — focus on making this the best free converter available before expanding to other features.
- The HTML output with themes (Task 11) is the key differentiator vs existing tools like Calibre's built-in converter.
- Consider packaging as a standalone tool or even a web service once quality is proven across diverse PDFs.
- `python -m pip install` must be used for all package installs — the project uses Microsoft Store Python 3.8, and bare `pip install` targets a different Python installation.
- The `-UseClaudeChapters` pass 2 runs with `--quiet` which overwrites the pass 1 log. Consider writing pass 2 output to a separate log file for debugging.
- Nicaea conversion is the hardest test case: 492 pages, zero bookmarks, complex font encoding, dense footnotes. Any book that converts well on the heuristic path will be dramatically improved by `-UseClaudeChapters`.
- **Claude Code is now the primary development workflow** — format all future prompts as autonomous Claude Code tasks rather than manual paste-into-VS-Code instructions.
- **Context7 MCP server configured for live API documentation** — use when working with pdfminer, pypdf, Calibre CLI, or any dependency where training data may be outdated.
- **Tesseract OCR Integration (high priority future feature)** — Enable conversion of image-only scanned PDFs (like Secret Societies 1875, 417 pages). Pipeline: detect image-only PDF (pypdf extracts near-zero text) → run Tesseract on each page image → feed OCR text into existing fix_ocr_artifacts() pipeline → Claude chapter detection → KFX output. This is the key differentiator — modern books have EPUBs; old scanned books don't. The existing 8-phase OCR cleanup pipeline is already built for this. Needs: Tesseract installation, page image extraction (pdf2image/Poppler already bundled), confidence scoring to flag low-quality OCR pages, and possibly a two-pass approach (fast OCR first, then targeted re-OCR on low-confidence pages). Natural evolution of Task 16 (Conversion Profiles) — "scanned" profile would auto-enable OCR.
- **Book Metadata Cache (future)** — Shared database storing validated chapter structures (hints JSON), extraction backend preference (pypdf vs pdfminer), and conversion parameters per book. Keyed by content hash + ISBN. First conversion pays the detection cost; subsequent conversions get instant cached results. Could also store OCR artifact patterns, TOC structure, and user-reported corrections. Natural evolution of the conversion profiles system (Task 14). Would need: SQLite or cloud DB, content hashing, cache hit/miss logic in Convert-ToKindle, and an admin interface for reviewing/correcting entries.
- ~~**Claude API Quality Validation Pass — Phase 1 (scan) and Phase 2 (auto-fix with global propagation) IMPLEMENTED.** Remaining: Phase 3 (sub-heading detection) and Phase 4 (feedback loop).~~ — **Phases 1-3 DONE.** Phase 4 (feedback loop, SCRUM-13) is To Do. AI quality pass now detection-only by default with fix guardrails. See `docs/AI_Quality_Pass_Design.md` for architecture.
- **50-book baseline findings (2026-03-24):** Structural extraction is strong (74% pass) but visual output quality lags (avg VQA 57.9). The two systemic weaknesses are TOC navigation (avg 66.8) and text integrity (11/33 books below 70). Word merges (4,969 across failing books) and OCR debris (2,911) are the dominant text integrity problems, mostly originating in source PDFs. Tiered extraction (SCRUM-120) addresses this — Tier 2 re-OCR and Tier 3 Vision extraction can rescue the worst cases.
- **Intelligent Extraction (SCRUM-120) — 5 of 6 phases done.** Remaining: Phase 5 (SCRUM-125) multi-extractor comparison for borderline books. Commercial model: cache expensive Vision extractions, charge same rate regardless of tier, popular books amortize fast.
- **Image Preservation in PDF-to-Kindle Conversion (medium-high priority)** — Currently the pipeline strips all images during PDF text extraction. Books like Mexico's Illicit Drug Networks contain maps, organizational charts, photographs, and diagrams that are essential to understanding the content. Need to: (1) detect and extract embedded images from PDFs (pypdf can do this with page.images), (2) preserve image positioning relative to surrounding text, (3) embed images in the HTML intermediate output so Calibre includes them in the KFX, (4) handle caption text associated with images. This is a significant feature — image extraction, positioning, and HTML embedding are each non-trivial. May also need the Claude API to generate alt-text descriptions for images that don't have captions, which would also improve the TTS/audiobook output (narrator can describe what the image shows).
- **AI Vision TOC Extraction (high priority)** — When a PDF has no bookmarks, use Claude API vision to read the printed Table of Contents page and extract chapter structure. Pipeline: detect no-bookmark PDF → scan first 10-15% of pages for TOC page (look for "Contents" or "Table of Contents" heading) → extract page as image → send to Claude vision API → receive structured JSON with chapter titles, page numbers, and nesting levels → use as bookmark-equivalent data for chapter placement. Far more reliable than regex heuristic chapter detection, which produces garbage results on books like The Khazars (grabbed bibliography entries and index fragments as chapters). Natural extension of existing Claude API integration. Can combine with -UseClaudeChapters flag or replace the heuristic path entirely for no-bookmark books.
- **Hyperlink preservation in HTML output (low priority)** — When future HTML output mode is implemented, preserve PDF hyperlinks as `<a>` tags. Currently URLs in endnotes are extracted as plain text (5 instances in Oil Kings, all in Notes section). Not a body text issue — only affects endnotes/bibliography.
- **Cloud VM & Docker Migration (future infrastructure)** — Migrate the full EbookAutomation environment to a cloud-hosted VM with Docker containers. Goals: (1) disaster recovery — project currently lives on a single local drive with no redundancy, (2) deployment readiness — any monetization path (FastAPI web interface, StoryForge backend) requires cloud hosting, (3) learning opportunity — cloud engineering, containerization, CI/CD. Architecture: Docker containers for each pipeline component (Python text processing, Calibre conversion, Balabolka/balcon TTS, ffmpeg audio). Cloud provider TBD (Azure, AWS, or GCP). Needs: Dockerfile for each component, docker-compose for orchestration, persistent volume for book archive/output, environment variable management for API keys, CI/CD pipeline triggered by GitHub pushes. Natural prerequisite: GitHub repository setup (must complete first). Also enables horizontal scaling — multiple conversions in parallel.

---

*This document is maintained in the Claude Project for EbookAutomation. Update it as tasks are completed or new ideas are added.*
