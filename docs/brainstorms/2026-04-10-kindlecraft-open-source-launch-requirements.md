---
date: 2026-04-10
topic: booksmith-open-source-launch
---

# BookSmith — Open-Source PDF-to-Ebook Tool

## Problem Frame

EbookAutomation is a 43k-line PDF-to-Kindle conversion pipeline that produces
significantly better results than raw Calibre `ebook-convert` — handling multi-column
layouts, font-based heading detection, chapter structure, footnote linking, and OCR
cleanup. However, it's currently a messy private repo intertwined with personal
automation (FOH scraping, interview prep, personal configs) and requires PowerShell
on Windows.

The goal is to extract the core conversion engine into a new, clean, open-source
project called **BookSmith** (working title — see trademark note in Outstanding
Questions) — a Python CLI tool that anyone can clone and use. The target audience is
technical/power readers initially (GitHub repo), with a broader audience later (GUI
app, audiobook pipeline).

The original freemium SaaS direction was abandoned in April 2026 after recognizing
market saturation for generic PDF-to-Kindle tools. The differentiation is better
served by an open-source model where users can run everything locally.

### v1 Value Proposition (without AI)

Even without AI features, BookSmith's extraction pipeline is substantially better
than raw `ebook-convert` because of capabilities Calibre does not have:

- **Multi-column layout detection:** PyMuPDF coordinate-based extraction preserves
  reading order in two-column academic papers and textbooks — Calibre's converter
  interleaves columns into garbled text
- **Font-based heading detection:** PDF font metadata (size, weight, family) drives
  heading classification — Calibre relies on HTML structure that PDFs don't have
- **9-phase OCR artifact cleanup:** Ligature splits (`traffi cking` → `trafficking`),
  orphaned fragments, running header removal, encoding artifact repair — Calibre
  passes these through unchanged
- **Footnote/endnote linking:** Reference relationships from the source PDF are
  preserved as navigable links — Calibre strips or ignores these
- **Pre-flight analysis:** Automatic PDF classification recommends the best extraction
  strategy per document — Calibre uses one-size-fits-all

These are the non-AI features that produce the quality difference. AI features (v2)
will add chapter structure refinement and quality scoring on top.

## Requirements

**Core Extraction Engine**

- R1. BookSmith must extract text from PDFs using multiple extraction backends
  (pdfminer, pypdf, PyMuPDF) with automatic fallback based on extraction quality
- R2. Multi-column PDF layouts must be detected and extracted with correct reading
  order using the existing PyMuPDF column-aware path
- R3. Font-based heading detection must identify chapter titles, section headers, and
  sub-headings from PDF font metadata — not just regex patterns
- R4. Chapter structure detection must work without AI — regex-based detection with
  the existing heuristics for numbered chapters, named parts, and common patterns
- R5. TOC generation must produce a navigable table of contents from detected headings
  with correct nesting depth
- R6. Footnote and endnote linking must preserve reference relationships from the
  source PDF
- R7. OCR artifact cleanup must handle ligature splits, orphaned fragments, running
  headers, and encoding artifacts through the existing regex phase pipeline
- R8. Pre-flight analysis must classify PDFs (digital text vs. scanned, single vs.
  multi-column, complexity level) and recommend extraction parameters

**Output Formats**

- R9. Primary output: EPUB via Calibre (cross-platform, best reading experience)
- R10. Secondary output: KFX via Calibre (Kindle-native, requires Calibre KFX plugin)
- R11. Users must be able to choose output format via CLI flag

**Content Filters**

- R12. Content filters must allow excluding footnotes and images via CLI flags.
  Additional filters (front matter, back matter, bibliography, index, block quotes,
  hyperlinks) are available but not prominently documented until user demand surfaces

**CLI Interface**

- R13. Primary entry point: `booksmith convert <input.pdf>` — converts a PDF to
  Kindle-ready format with sensible defaults
- R14. `booksmith info <input.pdf>` — runs pre-flight analysis and reports PDF
  characteristics without converting
- R15. All features must work without API keys. When no API key or local LLM is
  available: chapter detection falls back to regex heuristics (R4), AI quality pass
  is skipped with a log message, visual QA is disabled. The tool produces valid
  output in all cases
- R16. Configuration via a config file (`~/.booksmith/config.json` or similar) for
  persistent settings (default output format, Calibre path). Credentials (API keys,
  SMTP passwords) must be supplied via environment variables — never stored in the
  config file

**Packaging and Distribution**

- R17. New GitHub repo (name TBD — see Outstanding Questions), separate from
  EbookAutomation
- R18. Pure Python codebase — no PowerShell dependency. Calibre orchestration moves
  into Python
- R19. Tested on Windows (primary). macOS and Linux are best-effort for v1 with a
  GitHub Actions CI matrix (Windows + Ubuntu + macOS) to catch cross-platform issues
- R20. Installation: clone + `pip install -r requirements.txt` + install Calibre.
  No PyPI packaging required for v1
- R21. Proper README with installation guide, usage examples, feature overview, and
  comparison to plain Calibre conversion showing specific quality differences

**Quality and Testing**

- R22. Regression test suite covering 6 representative PDFs validated against the
  pipeline on 2026-04-11 (candidates in `test-corpus/candidates/`):

  | PDF | Source | Pages | Classification | Capabilities Tested |
  |-----|--------|-------|----------------|---------------------|
  | ArXiv "Attention Is All You Need" | arxiv.org/pdf/1706.03762 | 15 | scan_with_text | Footnotes (16), LaTeX academic formatting, 19 headings |
  | NIST SP 800-171r3 | nvlpubs.nist.gov | 120 | digital_native | Dense formatting, deep heading hierarchy (170), 236 footnotes |
  | FDA CGMP Guidance | fda.gov/media/71021 | 22 | digital_native | Structured headings (34), Word-produced gov doc, 26 footnotes |
  | Gutenberg "Foundations of Geometry" | gutenberg.org/files/17384 | 101 | digital_native (two_column) | Multi-column layout, math formatting, column-aware extraction |
  | IPCC AR6 Summary for Policymakers | ipcc.ch AR6 SYR SPM | 42 | scan_with_text | Image-heavy, complex layout, 164 headings, 58 footnotes |
  | IA "First Book of Maccabees" | archive.org (Google scan) | 292 | scan_no_text | No text layer, OCR-required, tests graceful degradation |

  All PDFs are freely available from government, academic, or public domain sources
- R24. Pre-launch security gate: run truffleHog or gitleaks against any exported git
  history before making the repo public

## Success Criteria

- A user with Python 3.10+ and Calibre already installed can clone the repo, install
  pip dependencies, and successfully convert a PDF to a readable EPUB/KFX within 15
  minutes of first encounter
- Conversion quality on complex PDFs (multi-column, academic papers, books with
  footnotes) is visibly better than raw `ebook-convert input.pdf output.epub` — the
  README includes side-by-side comparison screenshots demonstrating the difference
- The tool handles at least 5 structurally different PDFs without crashing or
  producing garbled output
- A person unfamiliar with the codebase can follow the README from clone to
  successful conversion without assistance

## Scope Boundaries

**In scope for v1:**
- PDF → EPUB/KFX conversion with smart extraction
- Content filters (via CLI flags)
- Pre-flight PDF analysis
- CLI interface (`convert`, `info`)
- GitHub Actions CI for cross-platform smoke tests

**Explicitly out of scope for v1:**
- AI/LLM features (Claude, Gemini, local LLM) — graceful degradation only
- Email-to-Kindle delivery (v1.1 — existing `email_to_kindle.py` is ready to port)
- Named conversion profiles (v1.1 — ship with sensible defaults first, derive
  profiles from real user usage patterns)
- Pattern database for book-specific overrides (v1.1)
- GUI application
- TTS / audiobook pipeline (v2)
- PyPI packaging / `pip install booksmith`
- Docker image
- Cloud deployment / web service
- User accounts, billing, or any SaaS infrastructure
- USB/MTP Kindle delivery (`send_to_kindle.py` uses Calibre's internal Python
  via `calibre-debug`, not standard Python)

**Future roadmap (not v1):**
- v1.1: Email-to-Kindle (`booksmith send`), conversion profiles, pattern database
- v2: Local LLM integration (Ollama/vLLM) for heading detection, quality pass, and
  chapter structure — enabled by user's incoming Blackwell Pro 5000 72GB GPU
- v2: TTS/audiobook pipeline (`booksmith audio <input>`)
- v3: GUI desktop application (Tauri or Electron)
- v3: Docker image for dependency-free usage

## Key Decisions

- **Open source over SaaS:** Market for generic PDF-to-Kindle tools is saturated.
  The real value is in extraction quality, which is better served by open-source
  where users run everything locally. Monetization was never the primary motivation.
- **New repo over sanitize-and-publish:** EbookAutomation is too intertwined with
  personal automation, half-finished features, and Windows-specific tooling. A clean
  extraction produces a better first impression and a more maintainable codebase.
- **Python core over PowerShell:** Cross-platform reach requires pure Python. The
  PowerShell orchestration layer stays in EbookAutomation for personal use.
- **Thin CLI wrapper strategy:** Rather than refactoring the entire 13.8k-line
  extraction engine upfront, ship a CLI that imports and calls the existing Python
  extraction functions directly. The Calibre orchestration port (PowerShell → Python)
  is the real work. Refactoring into a clean library structure happens iteratively
  after v1 ships, not before.
- **v1 ships non-AI features only:** The extraction pipeline's quality advantage
  comes from multi-column detection, font-based headings, OCR cleanup, and footnote
  linking — not from AI. AI features (v2) add refinement on top of an already-strong
  foundation.
- **Blackwell GPU is a v2 concern:** The incoming 72GB GPU enables local LLM
  inference. This does not affect v1 architecture. No AI abstraction layer is designed
  until v2 work begins with concrete requirements and actual hardware.
- **License required before Phase 1 ships:** Must be selected before the
  repo goes public — an unlicensed repo is legally all-rights-reserved,
  contradicting the open-source goal. Calibre is GPL-licensed; BookSmith
  invokes it as an external subprocess (not importing Calibre Python modules),
  so MIT or Apache 2.0 are viable without GPL contamination.
- **Credential security:** SMTP passwords and API keys use environment variables
  only. The config file stores non-sensitive settings (paths, preferences, output
  format defaults). No plaintext credentials in any file that could be committed
  to a repo.

## Dependencies / Assumptions

- Calibre must be installed separately by users (not bundleable due to GPL licensing)
- The existing Python extraction engine (`pdf_to_balabolka.py`, 13.8k lines) is the
  primary source — v1 imports its functions directly via a thin CLI wrapper rather
  than fully refactoring the monolith upfront
- `tools/email_to_kindle.py` (928 lines) already implements complete SMTP delivery
  with format-aware size routing, PDF compression, and splitting — ready to port
  for v1.1
- `tools/filter_content.py` already implements content filters and profile presets
  (`full`, `clean-read`, `text-only`) — R12 requires CLI flag wiring, not building
  from scratch
- When extracting from `pdf_to_balabolka.py`, tkinter imports (lines 24-25) and
  the GUI class (lines 13541+) must be excluded — they cause ImportError on headless
  Linux systems without python3-tk
- `format_paragraphs_as_html` (~1,000 lines at line 6167) combines heading
  classification, bookmark reconciliation, and HTML rendering in one function —
  decomposing this is a significant work item for the extraction
- `Convert-ToKindle` in the PowerShell module (~1,500 lines) contains non-trivial
  Calibre orchestration: smart TOC flag construction, KFX-to-AZW3 fallback chains,
  start-reading-at landmark detection, cover image injection, and filename mismatch
  recovery — this port is a distinct work stream, not a line item
- Hardcoded Windows paths in the extraction engine (Calibre at
  `C:\Program Files\Calibre2\`, Poppler searching for `.exe` extensions) require
  a cross-platform tool resolver

## Outstanding Questions

### Resolved

- ~~[Affects R17][User decision] **Project name.**~~ Resolved 2026-04-11.
  Chose "BookSmith" — a smith who crafts books. PyPI: available. GitHub:
  `jlfowler1084/booksmith`. No trademark risk (avoids "Kindle" mark).
  Alternatives considered: KindleCraft (trademark risk), PageCraft (PyPI taken),
  Folio (PyPI taken), Refolio, Bindery.
- ~~[Affects R22][User decision] **Test corpus validation.**~~ Resolved 2026-04-11.
  Downloaded 6 candidate PDFs from arXiv, NIST, FDA, Gutenberg, IPCC, and Internet
  Archive. All ran through the pipeline successfully. Corpus exercises multi-column
  detection, font-based heading detection (19-170 headings), footnote linking
  (16-236 refs), OCR classification, and graceful degradation (scan-only PDF).
  Candidates stored in `test-corpus/candidates/`

### Deferred to Planning

- [Affects R18][Technical] Port the Calibre orchestration from PowerShell to Python.
  Key behaviors to port: TOC detection from heading analysis, KFX output with AZW3
  fallback, start-reading-at landmark selection, metadata injection, and filename
  mismatch recovery
- [Affects R1][Technical] Dependency analysis of `pdf_to_balabolka.py`: map which
  functions are Kindle-mode-only vs TTS-mode-only vs shared. Quantify the extraction
  surface before starting
- [Affects R16][Technical] Config file format and location — should it follow
  XDG conventions on Linux, `%APPDATA%` on Windows, or use a simpler
  `~/.booksmith/` approach?
- [Affects R17][Technical] Git history strategy — clean `git init` recommended
  (avoids secrets-in-history risk entirely), but assess whether any commit history
  is worth preserving
- [Affects R3][Technical] Decomposition of `format_paragraphs_as_html` to separate
  heading classification from HTML rendering — this is the most complex extraction
  task

## Phased Delivery

### Phase 1a: Extraction and Core CLI (Weeks 1-3)
- Dependency analysis of `pdf_to_balabolka.py` (Kindle-only vs TTS vs shared)
- Extract Kindle-mode functions into `booksmith/` package via thin wrapper
- Port Calibre orchestration from PowerShell to Python (distinct work stream)
- Audit and abstract platform-specific paths (Calibre, Poppler, Tesseract)
- Write `booksmith convert` and `booksmith info` CLI entry points
- Wire content filter flags from `filter_content.py`

### Phase 1b: Packaging and Launch (Week 4)
- Choose license (MIT or Apache 2.0)
- Set up regression tests with freely available PDFs
- Validate first working conversion from clone to EPUB/KFX
- Create README with installation guide, usage examples, and quality comparison
- Set up GitHub Actions CI (Windows + Ubuntu + macOS)
- Run secrets audit (truffleHog/gitleaks) on any exported history
- Push public repo

### v1.1: Email-to-Kindle + Profiles (after launch feedback)
- Extract `tools/email_to_kindle.py` into `booksmith send` subcommand
- Add named conversion profiles based on real user usage patterns
- Pattern database for book-specific overrides
- Wire SMTP configuration (env var for credentials)

### v2: Local LLM + Audiobook (after Blackwell GPU arrives)
- Design AI abstraction layer based on concrete requirements and actual hardware
- Add optional AI features (chapter detection, quality pass)
- TTS/audiobook pipeline (`booksmith audio`)

## Next Steps

-> All blocking questions resolved. Ready for `/ce:plan` for Phase 1a
   implementation planning.
