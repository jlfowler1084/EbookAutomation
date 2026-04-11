---
title: "feat: Extract BookSmith PDF-to-ebook CLI from EbookAutomation"
type: feat
status: active
date: 2026-04-11
origin: docs/brainstorms/2026-04-10-kindlecraft-open-source-launch-requirements.md
---

# feat: Extract BookSmith PDF-to-ebook CLI from EbookAutomation

## Overview

Extract the core PDF-to-Kindle conversion engine from EbookAutomation (43k-line
private repo) into a new open-source Python CLI called **BookSmith**. The new project
lives in a separate GitHub repo (`jlfowler1084/booksmith`) with no PowerShell
dependency, cross-platform support, and zero AI/API requirements for v1.

This plan covers Phase 1a (extraction + core CLI) and Phase 1b (packaging + launch)
from the origin document.

## Problem Frame

EbookAutomation produces significantly better PDF-to-ebook conversions than raw
Calibre `ebook-convert` — multi-column detection, font-based heading classification,
9-phase OCR cleanup, footnote linking, and smart pre-flight analysis. But it's a
messy private repo intertwined with personal automation, PowerShell orchestration,
and AI API dependencies.

BookSmith extracts the non-AI extraction engine into a clean, portable Python CLI
that anyone can clone and use. (see origin: docs/brainstorms/2026-04-10-kindlecraft-open-source-launch-requirements.md)

## Requirements Trace

- R1. Multiple extraction backends (pdfminer, pypdf, PyMuPDF) with automatic fallback
- R2. Multi-column layout detection and correct reading order
- R3. Font-based heading detection from PDF font metadata
- R4. Chapter structure detection without AI (regex heuristics)
- R5. TOC generation with correct nesting depth
- R6. Footnote and endnote linking
- R7. OCR artifact cleanup (9-phase regex pipeline)
- R8. Pre-flight PDF classification and extraction recommendations
- R9. EPUB output via Calibre
- R10. KFX output via Calibre (with KFX plugin)
- R11. Output format selection via CLI flag
- R12. Content filter flags (--no-footnotes, --no-images)
- R13. `booksmith convert <input.pdf>` primary entry point
- R14. `booksmith info <input.pdf>` pre-flight analysis
- R15. Graceful degradation without API keys
- R16. Config file at `~/.booksmith/config.json` for non-sensitive settings
- R17-R21. New repo, pure Python, cross-platform, clone+pip install, README
- R22. Regression test suite with 6 freely available PDFs
- R24. Pre-launch secrets audit

## Scope Boundaries

**In scope:**
- PDF → EPUB/KFX conversion pipeline (non-AI path)
- CLI with `convert` and `info` subcommands
- Content filter flags
- Cross-platform tool resolution (Calibre, Poppler, Tesseract)
- Config file for persistent settings
- Regression tests with public domain PDFs
- GitHub Actions CI (Windows + Ubuntu + macOS)
- README with installation guide and quality comparison
- MIT license

**Out of scope (see origin doc):**
- AI/LLM features, email-to-Kindle, conversion profiles, pattern database, GUI,
  TTS, PyPI packaging, Docker, cloud deployment

## Context & Research

### Relevant Code and Patterns

**Extraction engine hub:** `tools/pdf_to_balabolka.py` (13,810 lines) is the
center of a hub-and-spoke architecture. All other tools import from it. No circular
dependencies exist. External imports (visual_qa, gemini_ocr, pattern_db) are all
lazy (inside functions) and wrapped in try/except, so they degrade gracefully.

**Function classification (from dependency analysis):**
- **Kindle-mode only (BookSmith core):** `process_kindle_html()`, `format_paragraphs_as_html()`,
  `format_kindle_html()`, `rejoin_html_fragments()`, `_extract_html_with_pymupdf_columns()`,
  `extract_with_pdfminer_html()`, footnote linking functions (`_link_endnotes()`, etc.)
- **TTS-mode only (exclude):** `process_pdf()`, `format_output()`, voice tag functions,
  dialogue detection, scene break detection
- **AI functions (exclude):** `ai_detect_subheadings()`, `ai_rejoin_fragments()`,
  `ai_quality_pass()`, `extract_text_vision()`
- **Shared (must include):** PDF analysis, text quality scoring, extraction core,
  bookmark handling, text cleanup (`fix_ocr_artifacts()` — 1,770 lines), chapter
  detection, image extraction, HTML helpers

**Standalone tools (copy directly):**
- `tools/classify_source.py` — PDF classification, lazy imports of pypdf + pymupdf
  (both already in BookSmith requirements)
- `tools/detect_headings_font.py` — font-based heading detection, imports pymupdf
  at module level + lazy imports of ebooklib and beautifulsoup4 for EPUB path
- `tools/filter_content.py` — HTML content filtering, standalone
- `tools/fix_engine.py` — rule-based HTML corrections, standalone
- `tools/chapter_alignment.py` — chapter verification, standalone

**Calibre orchestration:** `Convert-ToKindle` in `module/EbookAutomation.psm1`
(~1,800 lines starting at line 596). Key behaviors documented in research:
- TOC flag construction from heading analysis (lines 1708-1882)
- KFX → AZW3 three-tier fallback (lines 1999-2058)
- Metadata injection (lines 1884-1916)
- Filename sanitization (lines 954-978)
- Start-reading-at landmark detection
- h3 headings excluded from Kindle TOC (avoids E24011 nesting errors)

**Cross-platform issues identified:**
- `pdf_to_balabolka.py:2768` — hardcoded `C:\Program Files\Calibre2\ebook-convert.exe`
- `pdf_to_balabolka.py:13272-13278` — `pdftoppm.exe` detection with `.exe` extension
- `pdf_to_balabolka.py:1940` — `tesseract.exe` reference
- 11 Python files have `sys.platform == 'win32'` UTF-8 guards (keep these — harmless on Linux)
- `config/settings.json` has hardcoded `C:\Users\Joe\...` paths

### Institutional Learnings

Key findings from `docs/superpowers/` analysis documents:

1. **Column detection filters are critical:** Bottom 12% of page height must be excluded
   (footnote apparatus creates false column signals). Blocks spanning >70% page width
   must be excluded (cross-column titles skew counts). Do not simplify.
2. **h3 must NOT enter Kindle TOC:** Previous fix for KFX E24011 nesting errors. h3
   provides visual structure only.
3. **Heading level type inconsistency:** Font detector uses strings ("h1"), downstream
   code expects integers (1, 2, 3). BookSmith should pick one and be consistent.
4. **Pipeline introduces word merges in clean PDFs:** 6/11 text-integrity failures have
   clean source PDFs — the pdfminer HTML path's word boundary detection is the problem.
5. **Pre-flight should be opinionated:** Produce a complete conversion recipe, not just
   classification. "The difference between a tool and a product."
6. **InDesign metadata and running headers leak into text:** One-liner regex fixes that
   affect multiple books.
7. **Windows glob expansion:** Python doesn't expand `*` globs on Windows — input handlers
   must use `glob.glob()` internally.

## Key Technical Decisions

- **Thin wrapper, not refactor:** Copy `pdf_to_balabolka.py` into BookSmith as
  `booksmith/engine.py`. Fix the tkinter import (move to lazy/conditional). Remove
  the GUI class and TTS-only function bodies. Keep shared and Kindle-mode functions.
  Do not decompose `format_paragraphs_as_html` for v1 — it works as-is.
  Rationale: shipping speed over architectural purity. Refactor iteratively post-launch.

- **tkinter fix strategy:** Move lines 24-25 (`import tkinter as tk; from tkinter
  import ...`) into the `class App` constructor or behind `if __name__ == "__main__"`.
  This is minimal diff and makes the file importable on headless systems.

- **Config location:** `~/.booksmith/config.json` on all platforms. No XDG complexity
  for v1. Directory created on first run with mode 0o700.

- **Git history:** Clean `git init`. No history carried from EbookAutomation. Avoids
  any secrets-in-history risk and gives a clean first impression.

- **Calibre invocation:** Always via `ebook-convert` subprocess (never import Calibre
  Python modules). Resolved via `shutil.which()` first, platform-specific fallback
  paths second, user config third.

- **License:** MIT — maximum adoption, no GPL contamination since Calibre is invoked
  as external subprocess only.

- **Heading levels:** Use integers (1, 2, 3) throughout BookSmith. Convert string
  levels ("h1", "h2") at the boundary when importing from engine functions.

## Open Questions

### Resolved During Planning

- **How to handle tkinter import?** Move to lazy import inside GUI class / `__main__`
  block. Minimal diff to source file.
- **Config file location?** `~/.booksmith/config.json` — simple, cross-platform.
- **Git history?** Clean `git init` — no secrets risk.
- **Decompose format_paragraphs_as_html?** No — copy as-is for v1. Works fine, just large.
- **Which supporting tools to include?** classify_source.py, detect_headings_font.py,
  filter_content.py, fix_engine.py, chapter_alignment.py. All standalone.
- **Calibre orchestration port scope?** TOC flags, KFX/AZW3 fallback, metadata,
  filename handling. Skip VQA, pattern_db, email delivery.

### Deferred to Implementation

- Exact subset of `fix_ocr_artifacts()` phases needed (all 9 may not be relevant
  without the full EbookAutomation context)
- Whether `pyspellchecker` (~50MB) should be required or optional — may surprise users
- Optimal default values for CLI flags (best discovered through test corpus runs)
- Whether `pdfplumber` (optional in current code) should be a BookSmith dependency

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review,
> not implementation specification. The implementing agent should treat it as context,
> not code to reproduce.*

```
User runs: booksmith convert input.pdf --format epub

CLI (cli.py)
  │
  ├── Load config (~/.booksmith/config.json)
  ├── Resolve tools (Calibre, Poppler, Tesseract)
  │
  ├── Pre-flight Analysis (preflight.py → classify_source)
  │   └── Returns: classification, recommended_strategy, flags
  │
  ├── Extraction (engine.py — copied from pdf_to_balabolka.py)
  │   ├── Route by classification:
  │   │   ├── digital_native → extract_with_pdfminer_html()
  │   │   ├── two_column → _extract_html_with_pymupdf_columns()
  │   │   └── scan_no_text → warn + skip (OCR out of scope for v1)
  │   ├── fix_ocr_artifacts() — 9-phase cleanup
  │   ├── format_paragraphs_as_html() — heading detection + HTML output
  │   ├── detect_chapters() / apply_chapter_hints()
  │   └── _link_endnotes() / footnote linking
  │
  ├── Content Filtering (filter_content.py)
  │   └── Apply --no-footnotes, --no-images flags
  │
  ├── Calibre Conversion (calibre.py — ported from PowerShell)
  │   ├── Build TOC flags from heading analysis
  │   ├── Inject metadata (title, author, cover)
  │   ├── Set start-reading-at landmark
  │   ├── Run ebook-convert → EPUB or KFX
  │   └── KFX failure → AZW3 fallback → AZW3-to-KFX retry
  │
  └── Output: EPUB/KFX file in current directory or --output-dir
```

## Implementation Units

### Phase 1a: Extraction and Core CLI

- [ ] **Unit 1: Repository scaffold and package structure**

**Goal:** Create the BookSmith repo with proper Python package layout, dependencies,
and license.

**Requirements:** R17, R20

**Dependencies:** None

**Files:**
- Create: `booksmith/__init__.py`
- Create: `booksmith/__main__.py`
- Create: `requirements.txt`
- Create: `pyproject.toml` (minimal — name, version, entry point)
- Create: `LICENSE` (MIT)
- Create: `.gitignore`
- Create: `.github/workflows/ci.yml` (stub)
- Create: `tests/__init__.py`

**Approach:**
- Initialize with `git init` in a new directory (not inside EbookAutomation)
- Package entry point: `booksmith` CLI via `pyproject.toml` `[project.scripts]`
- `__main__.py` enables `python -m booksmith`
- `requirements.txt` includes only BookSmith dependencies (no AI SDKs, no google-genai,
  no requests): pypdf, pdfminer.six, PyMuPDF, beautifulsoup4, lxml, pillow,
  pdf2image, python-dotenv, pyspellchecker (optional group), pdfplumber (optional group).
  Note: EbookLib is NOT needed — it handles EPUB input parsing, not output generation.
  Calibre handles EPUB output via subprocess
- Python version: `>=3.10` (broader than EbookAutomation's 3.12 requirement)
- `.gitignore`: standard Python + `__pycache__`, `.env`, `*.pyc`, `dist/`, `build/`

**Patterns to follow:**
- EbookAutomation's `requirements.txt` for version pinning style
- Standard Python package layout conventions

**Test expectation:** none — scaffolding only

**Verification:**
- `pip install -e .` succeeds
- `python -m booksmith --help` prints usage (even if stub)

---

- [ ] **Unit 2: Extract engine from pdf_to_balabolka.py**

**Goal:** Copy the extraction engine into BookSmith, make it importable on all
platforms, and strip TTS/GUI/AI code.

**Requirements:** R1, R2, R3, R4, R5, R6, R7, R15, R18

**Dependencies:** Unit 1

**Files:**
- Create: `booksmith/engine.py` (derived from `tools/pdf_to_balabolka.py`)
- Create: `booksmith/classify.py` (derived from `tools/classify_source.py`)
- Create: `booksmith/headings.py` (derived from `tools/detect_headings_font.py`)
- Create: `booksmith/filters.py` (derived from `tools/filter_content.py`)
- Create: `booksmith/fixengine.py` (derived from `tools/fix_engine.py`)
- Create: `booksmith/alignment.py` (derived from `tools/chapter_alignment.py`)
- Test: `tests/test_engine.py`

**Approach:**
- Copy `pdf_to_balabolka.py` → `booksmith/engine.py` with these modifications:
  - Move tkinter imports (lines 24-25) into the `class App` block or behind
    `if __name__ == "__main__"` guard
  - Remove the entire `class App` GUI class (lines 13541-13810)
  - Remove TTS-only function bodies: `process_pdf()`, `format_output()`,
    `format_output_with_levels()`, all voice tag functions (`_silence_tag`,
    `_rate_wrap`, `_voice_wrap`, `detect_dialogue_spans`, `_build_voiced_paragraph`,
    `_apply_dialogue_voices`, `_replace_em_dashes_with_pause`, `apply_voice_tags`,
    `detect_scene_breaks`, `detect_emphatic_closers`)
  - Remove `run_cli()` (lines 13109+) — BookSmith builds its own CLI
  - **Surgery on `process_kindle_html()` (line 11650, ~700 lines):** This function
    has AI/Gemini/Vision/pattern_db code interleaved in its body, sharing local
    variables with non-AI paths. This is the highest-risk extraction task. Specific
    changes required:
    - Strip parameters from signature: `use_vision`, `use_gemini`,
      `gemini_remediate`, `gemini_cost_limit`, `gemini_model`,
      `_pending_corrections`, `export_corrections`
    - Remove the Tier 3 Vision extraction block (~70 lines at line 11700-11719)
    - Remove the Gemini remediation block
    - Remove `apply_corrections()` / `_collect_corrections()` calls (pattern_db)
    - Remove the pattern_db cache write code (lines 12300-12344)
    - Keep all non-AI extraction, heading detection, footnote linking, and HTML
      formatting paths intact
    - **Verification:** Before removing any block, grep for the variable names it
      sets to confirm no downstream non-AI code depends on them
  - AI lazy imports (visual_qa, gemini_ocr, pattern_db): already guarded with
    try/except and will not be called by any BookSmith code path — verify they
    log rather than crash if somehow triggered
  - Remove `_load_api_model()` (line 54) entirely — it reads
    `config/settings.json` relative to the script, which won't exist in BookSmith.
    Remove the `gemini_model = _load_api_model()` call from `process_kindle_html`
  - Remove `_PIPELINE_HASH = _compute_pipeline_hash()` module-level side effect
    (line 51) and the caching code that references it — extraction caching is
    out of scope for v1
  - Fix `load_dotenv()` call (line 32) to not require project-root `.env`
  - Fix `load_ocr_substitutions()` to resolve `config/ocr_substitutions.json`
    relative to the package, not the script location
  - Preserve the `import threading` (line 26) — it is used by extraction timeout
    protection (`_extract_page_with_timeout`), not just the GUI
  - Also exclude `process_kindle()` (line 12358) — this is the legacy TXT-output
    Kindle path; BookSmith uses only the HTML path (`process_kindle_html`)
- Copy standalone tools directly with minimal changes:
  - classify_source.py → booksmith/classify.py
  - detect_headings_font.py → booksmith/headings.py
  - filter_content.py → booksmith/filters.py
  - fix_engine.py → booksmith/fixengine.py
  - chapter_alignment.py → booksmith/alignment.py
- Copy `config/ocr_substitutions.json` → `booksmith/data/ocr_substitutions.json`
- Fix all internal imports between copied files to use package-relative imports
  (e.g., `from booksmith.classify import classify_pdf`)

**Patterns to follow:**
- Existing graceful degradation pattern for optional imports in `pdf_to_balabolka.py`
- `from __future__ import annotations` (already in newer files like filter_content.py)

**Test scenarios:**
- Happy path: `from booksmith.engine import extract_with_pdfminer_html` succeeds
  on a system without tkinter installed
- Happy path: `from booksmith.engine import process_kindle_html` succeeds and the
  function is callable
- Happy path: `from booksmith.classify import classify_pdf` classifies a digital
  native PDF correctly
- Edge case: Import on headless Linux (no tkinter) does not raise ImportError
- Edge case: Import without AI SDK packages (anthropic, google-genai, requests)
  does not raise ImportError
- Error path: `load_ocr_substitutions()` gracefully handles missing
  `ocr_substitutions.json` (returns empty dict, not crash)

**Verification:**
- All extraction functions are importable from `booksmith.engine`
- `python -c "from booksmith.engine import process_kindle_html"` works on clean install
- No tkinter, AI SDK, or pattern_db imports at module level

---

- [ ] **Unit 3: Cross-platform tool resolver**

**Goal:** Build a utility that finds Calibre, Poppler, and Tesseract on Windows,
macOS, and Linux without hardcoded paths.

**Requirements:** R18, R19

**Dependencies:** Unit 1

**Files:**
- Create: `booksmith/tools.py`
- Test: `tests/test_tools.py`

**Approach:**
- For each external tool (ebook-convert, pdftoppm, tesseract):
  1. Check `shutil.which()` first (works if tool is on PATH)
  2. Check platform-specific default install locations:
     - Windows: `C:\Program Files\Calibre2\`, `C:\Program Files\Tesseract-OCR\`
     - macOS: `/Applications/calibre.app/Contents/MacOS/`, Homebrew paths
     - Linux: typically on PATH already
  3. Check user config (`~/.booksmith/config.json` overrides)
  4. Return None if not found (caller decides whether to error or skip)
- Resolve binary names without `.exe` extension on non-Windows platforms
- Use `pathlib.Path` throughout
- Cache resolved paths for the duration of a run (don't re-resolve per file)
- Log which resolution method succeeded

**Patterns to follow:**
- Existing `find_poppler_path()` in `tools/visual_qa.py` (but cross-platform)
- Calibre path detection in `pdf_to_balabolka.py:2768` (but abstracted)

**Test scenarios:**
- Happy path: On a system with Calibre on PATH, `resolve_tool("ebook-convert")`
  returns the correct path
- Happy path: User config override takes precedence over auto-detection
- Edge case: Tool not installed returns None (not an exception)
- Edge case: Windows `.exe` extension handled transparently
- Integration: `resolve_tool("ebook-convert")` returns a path that is actually
  executable (`os.access(path, os.X_OK)`)

**Verification:**
- `resolve_tool("ebook-convert")` returns a valid path on the developer's machine
- Tool resolution works without any config file present

---

- [ ] **Unit 4: Port Calibre orchestration from PowerShell to Python**

**Goal:** Implement the `ebook-convert` subprocess orchestration that currently lives
in PowerShell's `Convert-ToKindle`, producing EPUB and KFX output.

**Requirements:** R9, R10, R11, R5

**Dependencies:** Unit 2, Unit 3

**Files:**
- Create: `booksmith/calibre.py`
- Test: `tests/test_calibre.py`

**Approach:**
Port the following behaviors from `Convert-ToKindle` (EbookAutomation.psm1 lines
596-2400):

1. **TOC flag construction** (PSM1 lines 1708-1882):
   - Inspect HTML for h1/h2 tags and their ordering
   - If h1 before h2: `--level1-toc "//h:h1" --level2-toc "//h:h2"` (Part/Chapter)
   - If h1 only after h2 (back-matter): flat `--level1-toc "//h:h1|//h:h2"`
   - h3 NEVER included in TOC flags (causes KFX E24011 nesting errors)
   - Strip `<a>` tags from inside headings before Calibre sees them

2. **Start-reading-at detection** (PSM1 line 1754):
   - Skip headings matching these patterns (complete list from PowerShell source):
     Front Matter, Contents, Table of Contents, Acknowledg*, Foreword, Preface,
     Dedication, Copyright, Title, Notes, Further reading, Bibliography, Index,
     Appendix
   - Find first non-matching h1 or h2 as `--start-reading-at` landmark
   - Construct XPath: `--start-reading-at "//h:h2[normalize-space()='<heading>']"`

3. **Metadata injection** (PSM1 lines 1884-1916):
   - `--title`, `--authors`, `--publisher`, `--pubdate`, `--isbn`, `--language en`
   - `--cover` for cover image
   - `--output-profile kindle_pw3 --embed-all-fonts`
   - `--input-encoding utf-8`

4. **KFX/AZW3 fallback** (PSM1 lines 1999-2058):
   - Attempt KFX conversion first
   - If KFX fails or output missing → try AZW3
   - If AZW3 succeeds and target was KFX → attempt AZW3-to-KFX conversion
   - Keep whichever format succeeds

5. **Filename handling** (PSM1 lines 954-978):
   - Sanitize title: remove `[]:*?"<>|{}()`, strip libgen/Archive noise
   - Build `Title - Author.{ext}` format, truncate to 200 chars

6. **KFX filename mismatch recovery** (PSM1 lines 1960-1981):
   - After ebook-convert exits successfully, if the expected output file is missing,
     scan the output directory for newly-created KFX files and rename to the
     expected path. The KFX plugin sometimes writes to a different filename than
     predicted

7. **Subprocess execution:**
   - Use `subprocess.run()` with `shell=False` and argument list (never string
     interpolation — security requirement from review)
   - Capture stderr to detect errors without raising
   - Log the full ebook-convert command at debug level
   - Note: XPath arguments with namespace prefixes (`h:h1`) and `normalize-space()`
     require careful translation from PowerShell's escaped-quote syntax to Python
     argument lists. Each flag and its value are separate list elements:
     `['--level1-toc', '//h:h1', '--level2-toc', '//h:h2']`

**Execution note:** Start with a spike — port only the EPUB happy path (HTML with
h1+h2 → `ebook-convert` → EPUB), test against one corpus PDF (FDA guidance — simple
structure), and compare output to EbookAutomation's EPUB output for the same PDF.
This validates the approach before committing to the full port with KFX fallback.
The spike should take less than a day and will surface integration issues early.

**Patterns to follow:**
- Existing `extract_text_via_calibre()` in `pdf_to_balabolka.py:2754` for subprocess
  invocation pattern
- EbookAutomation.psm1 Convert-ToKindle for exact flag construction logic

**Test scenarios:**
- Happy path: Given HTML with h1+h2 headings, TOC flags are constructed correctly
  with h1 as level1 and h2 as level2
- Happy path: Given metadata dict, ebook-convert argument list includes all metadata
  flags in correct format
- Happy path: Filename sanitization removes special characters and produces
  `Title - Author.epub` format
- Edge case: HTML with no headings produces no TOC flags (Calibre auto-detects)
- Edge case: HTML with h1 only in back-matter uses flat TOC flag
- Edge case: h3 headings present but NOT included in TOC flags
- Edge case: Title longer than 200 characters is truncated
- Error path: KFX conversion fails → AZW3 fallback triggered
- Error path: ebook-convert not found → clear error message naming the tool
- Error path: ebook-convert returns non-zero → error logged with stderr content
- Integration: Full conversion from HTML file to EPUB produces a valid file
  (file exists, non-zero size, starts with PK zip header)

**Verification:**
- `booksmith convert test.pdf --format epub` produces a valid EPUB
- `booksmith convert test.pdf --format kfx` attempts KFX with AZW3 fallback
- TOC entries match the heading structure of the input

---

- [ ] **Unit 5: CLI entry points and config**

**Goal:** Build the `booksmith convert` and `booksmith info` subcommands with
config file support.

**Requirements:** R11, R12, R13, R14, R15, R16

**Dependencies:** Unit 2, Unit 3, Unit 4

**Files:**
- Create: `booksmith/cli.py`
- Create: `booksmith/config.py`
- Create: `booksmith/convert.py` (orchestration — ties extract → filter → calibre)
- Modify: `booksmith/__main__.py` (wire to cli.py)
- Modify: `pyproject.toml` (add `[project.scripts] booksmith = "booksmith.cli:main"`)
- Test: `tests/test_cli.py`
- Test: `tests/test_config.py`

**Approach:**

**CLI structure (cli.py):**
- Use argparse with subcommands
- `booksmith convert <input> [--format epub|kfx] [--output-dir DIR] [--no-footnotes]
  [--no-images] [--force-columns] [--verbose] [--quiet]`
- `booksmith info <input>` — pre-flight analysis, human-readable output
- `booksmith --version`
- Input accepts a single file path. Use `glob.glob()` internally on Windows to
  expand wildcards (institutional learning: Windows doesn't expand globs for Python)

**Config (config.py):**
- Location: `~/.booksmith/config.json`
- Created on first access with mode 0o700 (directory) and 0o600 (file) on Unix;
  on Windows these modes are ignored (inherits directory ACLs, acceptable since
  config contains no credentials)
- Schema: `{ "calibre_path": null, "poppler_path": null, "default_format": "epub",
  "output_dir": null }`
- No credentials in config — environment variables only (R16)
- Config is optional — sensible defaults for everything

**Conversion orchestrator (convert.py):**
- Ties together the pipeline: preflight → extract → filter → calibre
- Follows the data flow from the High-Level Technical Design section
- Routes extraction strategy based on pre-flight classification
- Handles the logging callback pattern used by engine.py functions
- Reports progress to user (file being processed, extraction method chosen,
  headings detected, output location)

**Patterns to follow:**
- EbookAutomation's `Invoke-EbookPipeline` for pipeline orchestration flow
- `tools/classify_source.py` for argparse usage in this project

**Test scenarios:**
- Happy path: `booksmith convert test.pdf` with default settings produces EPUB output
- Happy path: `booksmith convert test.pdf --format kfx` produces KFX output
- Happy path: `booksmith info test.pdf` prints classification and recommendations
- Happy path: `booksmith convert test.pdf --no-footnotes` applies content filter
- Happy path: Config file at `~/.booksmith/config.json` is read and applied
- Edge case: No config file present — tool works with defaults
- Edge case: Input path with spaces is handled correctly
- Edge case: Input path with wildcard on Windows is expanded via glob
- Edge case: Output directory doesn't exist — created automatically
- Error path: Input file doesn't exist → clear error message
- Error path: Input file is not a PDF → clear error message
- Error path: Calibre not installed → error message with install instructions
- Error path: Scanned PDF with no text layer → warning about OCR, produces
  minimal output or skips gracefully

**Verification:**
- `booksmith convert ArXiv_Attention_Is_All_You_Need.pdf` produces EPUB with
  headings and footnotes
- `booksmith info NIST_SP_800_171r3.pdf` reports "digital_native" classification
- `booksmith --version` prints version string
- `booksmith --help` prints usage for all subcommands

---

- [ ] **Unit 6: Regression test suite**

**Goal:** Set up the test infrastructure with the validated freely available PDF
corpus, ensuring the pipeline works end-to-end.

**Requirements:** R22, R24

**Dependencies:** Unit 5

**Files:**
- Create: `tests/test_regression.py`
- Create: `tests/corpus/` (directory for test PDFs)
- Create: `tests/corpus/README.md` (download instructions for test PDFs)
- Create: `tests/conftest.py` (pytest fixtures)
- Create: `scripts/download_corpus.py` (downloads test PDFs)
- Modify: `.github/workflows/ci.yml` (full CI configuration)

**Approach:**
- Test PDFs are NOT committed to the repo (too large). Instead:
  - `scripts/download_corpus.py` downloads all 6 test PDFs from their public URLs
  - `tests/corpus/README.md` documents the URLs and expected checksums
  - CI workflow runs the download script before tests
  - `conftest.py` provides a `corpus_dir` fixture that skips tests if PDFs not present
- Regression tests verify:
  - Each PDF extracts without crashing
  - Expected number of headings detected (within a tolerance range)
  - Expected classification matches (digital_native, scan_with_text, scan_no_text)
  - Output HTML is valid and non-empty
  - EPUB conversion produces a valid file (if Calibre is available)
- CI matrix: Windows + Ubuntu + macOS, Python 3.10 + 3.12
- CI installs Calibre on each platform for integration tests
- Secrets audit: CI step runs `pip install trufflehog` and scans the repo

**Patterns to follow:**
- EbookAutomation's `tools/test_pipeline.py` for regression test structure
- Baseline JSON pattern from `test-corpus/*.baseline.json`

**Test scenarios:**
- Happy path: ArXiv paper extracts with ~19 headings and ~16 footnote references
- Happy path: NIST doc extracts with >100 headings and >200 footnote references
- Happy path: FDA guidance extracts with >30 headings
- Happy path: Gutenberg math book triggers column-aware extraction (two_column=True)
- Happy path: IPCC report extracts with >100 headings despite image-heavy layout
- Edge case: IA scanned book (scan_no_text) produces minimal output with warning,
  does not crash
- Integration: Full pipeline from PDF to EPUB produces valid EPUB for at least
  4 of 5 extractable test PDFs
- Error path: Test gracefully skips when corpus PDFs are not downloaded

**Verification:**
- `pytest tests/` passes on Windows
- GitHub Actions CI passes on all 3 platforms
- All 6 test PDFs are accounted for in the test suite

---

### Phase 1b: Packaging and Launch

- [ ] **Unit 7: README, documentation, and launch**

**Goal:** Create the documentation and final polish needed for a public GitHub launch.

**Requirements:** R21, R17, R19, R24

**Dependencies:** Unit 6

**Files:**
- Create: `README.md`
- Create: `CONTRIBUTING.md` (minimal)
- Create: `SECURITY.md` (disclosure policy)
- Modify: `.github/workflows/ci.yml` (finalize)

**Approach:**
- README sections:
  - What BookSmith does (one paragraph)
  - Why it's better than raw Calibre (side-by-side comparison screenshots)
  - Quick start (clone, pip install, booksmith convert)
  - Installation guide (Python 3.10+, Calibre, optional: Poppler, Tesseract)
  - Usage examples for `convert` and `info`
  - Supported PDF types and known limitations
  - Configuration
  - Contributing
  - License
- Side-by-side comparison: Convert one of the test corpus PDFs with both raw
  `ebook-convert` and BookSmith, screenshot the results, include in README
- CONTRIBUTING.md: How to set up dev environment, run tests, submit PRs
- SECURITY.md: Responsible disclosure email/process
- Final CI check: truffleHog scan passes
- Tag v0.1.0 and push to GitHub

**Test expectation:** none — documentation only

**Verification:**
- A person unfamiliar with the project can follow the README from clone to
  first conversion without assistance
- GitHub Actions CI badge shows passing
- Repository is public and accessible at github.com/jlfowler1084/booksmith

## System-Wide Impact

- **Interaction graph:** BookSmith is a new standalone project. It does not modify
  EbookAutomation. The extraction engine is copied, not linked — the two codebases
  will diverge over time.
- **Error propagation:** All extraction errors should be caught and reported as
  user-friendly messages. Calibre subprocess failures should include stderr output
  in the error message. No Python tracebacks in normal usage.
- **State lifecycle risks:** No persistent state beyond the config file. Each
  conversion is stateless. No database, no cache, no temporary files that outlive
  the process (use `tempfile.TemporaryDirectory` with context managers).
- **API surface parity:** Not applicable — new project.
- **Integration coverage:** The regression test suite (Unit 6) covers the full
  pipeline from PDF input to EPUB output. Unit tests alone cannot verify Calibre
  integration — the CI must have Calibre installed.
- **Unchanged invariants:** EbookAutomation continues to work independently.
  BookSmith does not import from or depend on EbookAutomation at runtime.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Calibre orchestration port takes longer than expected due to edge cases in TOC flag logic | Port the happy path first (h1/h2 headings → EPUB). Add fallback and KFX support incrementally. Ship with EPUB-only if KFX is not ready. |
| Cross-platform issues discovered during CI (path separators, encoding, binary names) | CI matrix catches these early. Windows is the primary tested platform. Document macOS/Linux as best-effort for v1. |
| Test corpus PDFs change at source URLs (government sites reorganize) | Store checksums in `tests/corpus/README.md`. CI fails fast if checksums don't match. |
| Large engine.py file (13k+ lines even after stripping TTS) makes contributions intimidating | Acknowledge in CONTRIBUTING.md. Post-launch refactoring into smaller modules is planned. |
| pyspellchecker adds ~50MB to install size | **CRITICAL:** `fix_ocr_artifacts()` currently early-returns entirely without pyspellchecker — all 9 phases are skipped, not just spell-check validation. This is BookSmith's core differentiator. Either make pyspellchecker a required dependency, or refactor `fix_ocr_artifacts()` to run regex-only phases (ligature normalization, smart quotes, Unicode cleanup) without it. Decision must be made during Unit 2 implementation. |

## Documentation / Operational Notes

- Push to `github.com/jlfowler1084/booksmith` as a public repo
- Tag `v0.1.0` for initial release
- After launch, monitor GitHub Issues for installation problems on macOS/Linux
- EbookAutomation remains the private development environment; BookSmith is the
  public-facing product

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-10-kindlecraft-open-source-launch-requirements.md](docs/brainstorms/2026-04-10-kindlecraft-open-source-launch-requirements.md)
- **Extraction engine:** `tools/pdf_to_balabolka.py` (13,810 lines)
- **Calibre orchestration:** `module/EbookAutomation.psm1` Convert-ToKindle (lines 596-2400)
- **Institutional learnings:** `docs/superpowers/analysis/2026-03-24-50book-baseline-diagnosis.md`, `docs/superpowers/specs/2026-03-23-font-heading-detection-design.md`, `docs/superpowers/analysis/2026-03-24-text-integrity-deep-dive.md`
- **Test corpus:** `test-corpus/candidates/` (6 validated PDFs)
