# CLAUDE.md — EbookAutomation Project Context
<!-- This file contains EbookAutomation-specific rules only.
     Shared conventions are inherited from ~/.claude/CLAUDE.md -->
<!-- Global hooks inherited from: ~/.claude/settings.json -->
<!-- Project hooks in: .claude/settings.json -->

## Project Identity
EbookAutomation is a PowerShell + Python automation suite for:
- Converting ebooks to TTS-ready text for Balabolka
- Converting PDFs to Kindle-formatted KFX files via Calibre
- Generating podcast/audiobook MP3s
- FOH forum scraping and daily brief generation

**Location:** `F:\Projects\EbookAutomation\`
**Repo:** jlfowler1084/EbookAutomation (private), **Branch:** master

## Environment (Project-Specific Overrides)
- **Shell:** PowerShell 5.1+ — do NOT use bash syntax, `&` operator, or Unix-style paths
- **Python:** 3.12 (use `py -3.12 -m pip install`)

⚠️ This project runs on Windows with PowerShell as the primary shell. Use PowerShell syntax,
not bash/Unix syntax. Claude Code's default bash shell does NOT apply here.

## Testing
- Full suite: `python tools/test_pipeline.py`
- Single book: `python tools/test_pipeline.py "Oil Kings"`
- Quick (HTML only): `python tools/test_pipeline.py --quick`
- Columns: `powershell -File tools/test_columns.ps1`

After ANY pipeline code change:
1. Run `test_pipeline.py` against all test cases
2. Verify endnote link count hasn't decreased
3. Verify no body text tagged as headings
4. Verify chapter detection count is correct
5. Verify PAGE markers survive all processing phases

### Feature Manifest Verification

A machine-readable feature manifest at `feature-manifest.json` catalogs all exported functions,
CLI modes, critical files, and config schema. Run the verification script before and after
major changes:

```powershell
powershell -File tools\verify-manifest.ps1 -Verbose
```

If verification fails, a function, file, or config key has been removed or truncated —
investigate before proceeding.

### Post-Edit Auto-Test Hook
PostToolUse hook runs `test_pipeline.py --quick` after edits to core pipeline files.
Hook script: `tools/hooks/post-edit-test.ps1` (configured in `.claude/settings.json`).

### Test Corpus
| Book | Key Challenge | Regression Focus |
|------|---------------|------------------|
| Oil Kings | Complex endnotes, dual numbering | Endnote linking accuracy |
| Mexico Illicit | OCR artifacts, ligatures | Text cleanup fidelity |
| Lincoln Highway | Multi-narrator, stylistic chapters | Chapter detection |
| Atomic Habits | Dense formatting, callout boxes | Heading vs body classification |
| Sapiens | Long chapters, footnotes | TOC depth + footnote pairing |
| Extreme Ownership | Simple structure | Baseline regression canary |

### Regression Prevention (Project-Specific)
The #1 time sink is fix-then-regression cycles. Changes to heading levels cascade into TOC
nesting and Calibre compatibility. A fix for one book has broken 4 others multiple times.

Before modifying heading detection, TOC generation, bookmark reconciliation, footnote
linking, or OCR cleanup: analyze current behavior across ALL test books first. Do NOT
edit code until you've reported the diagnosis and proposed a fix strategy.

## Directory Structure
```
EbookAutomation/
├── EbookAutomation.psm1    # Main PowerShell module
├── settings.json            # Pipeline configuration (paths, voices, options)
├── tools/
│   ├── pdf_to_balabolka.py  # Core Python extraction engine
│   ├── test_pipeline.py     # Regression test harness
│   ├── test_columns.ps1     # Column detection tests
│   └── hooks/
│       └── post-edit-test.ps1  # Auto-test hook
├── inbox/                   # Drop PDFs here
├── processing/              # Active conversion workspace
├── archive/                 # Completed source PDFs
├── output/                  # Final KFX/MP3/TXT files
├── tests/
│   └── validate_against_baseline.py
├── prompts/                 # Session handoff prompts
├── docs/plans/              # CE implementation plans (archive)
├── docs/solutions/          # Knowledge compounding (solved problems)
├── .mcp.json                # MCP server configuration
└── .claude/
    ├── settings.json        # Project hooks (regression test runner)
    ├── settings.local.json  # Local permissions
    ├── hooks/
    │   └── log-billing-events.sh  # (superseded by global version)
    └── skills/
        └── test-pipeline/SKILL.md
```

## Code Conventions
### PowerShell
- Use Verb-Noun naming: `Convert-PdfToHtml`, `Export-AudioBook`, `Test-Pipeline`
- Use `Write-EbookLog` for structured logging (not `Write-Host`)
- Use `Export-ModuleMember` for public functions in `.psm1`
- Use `[CmdletBinding()]` and `param()` blocks in all functions
- Use `$ErrorActionPreference = 'Stop'` in scripts

### Python
- Use `argparse` for CLI interfaces
- Use `tkinter` for GUI components
- For new Python code, follow the `python-core` global skill (`~/.claude/skills/python-core/SKILL.md`)

## Key Components
### settings.json (Pipeline Config — NOT Claude Code settings)
Contains paths for Calibre, Balabolka, FFmpeg, inbox/output directories, voice settings.
**Do not confuse with `.claude/settings.json`** — they are completely different files.

### EbookAutomation.psm1
Main module exporting: `Convert-PdfToKindle`, `Convert-PdfToAudiobook`, `New-DailyBrief`,
`Import-EbookSettings`, `Write-EbookLog`, `Test-EbookPipeline`

### pdf_to_balabolka.py — Extraction Engine
Three extraction paths based on PDF characteristics:
1. **pdfminer** — default text extraction
2. **pypdf** — fallback for pdfminer failures
3. **PyMuPDF column-aware** — for multi-column layouts

Modes: `full` (default), `headings-only`, `toc-only`, `metadata`

### Pipeline Architecture
`inbox/ → pre-flight analysis → extraction → HTML generation → heading classification → TOC generation → bookmark reconciliation → footnote linking → Calibre conversion → KFX output → optional TTS`

### Pre-Flight Analysis
Automatic PDF analysis before extraction. Override with `-SkipPreflight` or `-IgnoreRecommendation`.

## External Dependencies
| Tool | Purpose | Install |
|------|---------|---------|
| Calibre | KFX conversion | `winget install calibre` |
| Balabolka | TTS engine | Manual install |
| FFmpeg | Audio processing | `winget install ffmpeg` |
| Poppler | PDF utilities | `choco install poppler` |
| pdfplumber | Coordinate-based PDF text extraction for bookmark heading resolution (optional — degrades gracefully) | `pip install pdfplumber` |

Install all Python dependencies: `py -3.12 -m pip install -r requirements.txt`
Dev/test dependencies: `py -3.12 -m pip install -r dev-requirements.txt`

## TTS Voice Configuration
| Voice | Use Case |
|-------|----------|
| Microsoft Online Mark | Default male narrator |
| Microsoft Online Jenny | Default female narrator |
| Microsoft Online Guy | Alternative male |
Microsoft Online voices ONLY — do not suggest cloud TTS services.

## Visual QA System
KFX → PDF (via Calibre) → PNG (via Poppler) → Claude Vision API for layout verification.
Checks: heading hierarchy, TOC accuracy, footnote rendering, page breaks, image placement.

## Chapter Alignment Verification
Cross-references detected chapters against source PDF TOC/bookmarks.
Flags: missed chapters, phantom chapters, misnumbered sequences.

## Claude API Integration
Used for: heading classification, chapter boundary detection, content type identification.
Model: configurable via `CLAUDE_MODEL` env var. Default: haiku for classification, sonnet for analysis.

## Gemini API Integration
Tier 2.5 OCR: For PDFs where pdfminer/pypdf/pymupdf all fail (scanned pages, complex layouts).
Model: `gemini-2.0-flash` via `google-genai` SDK. API key in `.env`.

## Book Metadata System
Priority hierarchy: CLI args → embedded PDF metadata → filename parsing → user prompt.
Fields: title, author, series, series_number, publisher, year.

## Kindle Email Delivery
Converts to KFX and emails to Kindle device via configured SMTP.
Config in `settings.json`: `kindle_email`, `smtp_server`, `smtp_port`.

## FOH Daily Brief Generation
Scrapes FOH (Friends of Habersham) forum, summarizes with Claude, generates formatted brief.
Standalone feature — uses its own schedule and output path.

## Agent Framework
- **Structure Analysis Agent:** Pre-extraction PDF structure analysis (headings, TOC, footnotes)
- **QA Evaluation Agent:** Post-conversion quality checks against baseline metrics

## Project-Specific Mistakes to Avoid
- Don't use Unix-style paths (`/home/...`) — use Windows paths (`C:\...`)
- Changes to regex phases affect downstream — always test full pipeline
- Ligature fixes can break endnote linking
- Heading classification changes can break Calibre TOC generation
- Don't suggest cloud TTS unless explicitly asked
- Don't confuse `settings.json` (pipeline config) with `.claude/settings.json` (Claude Code config)

## MCP Servers
Allowed: Atlassian Rovo, Context7
All other cloud MCP servers should be disabled in this project (`/mcp disable <name>`).
Source of truth: ClaudeInfra `configs/mcp-server-registry.json` (INFRA-70).

## Current Priorities
1. Stabilize 5-book regression suite — zero failures on all test cases
2. Column-aware extraction for multi-column PDFs
3. Gemini OCR fallback for scanned pages
4. Kindle email delivery pipeline
5. FOH daily brief automation
