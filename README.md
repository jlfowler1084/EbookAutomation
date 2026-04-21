# EbookAutomation

Personal automation pipeline that converts PDF / EPUB / MOBI / AZW3 / DJVU books into Kindle-ready files and TTS-ready text, with a self-improving quality-assurance loop built on top.

Primary use cases:

- **Kindle delivery** — PDF or EPUB in, KFX/AZW3 out, emailed to a Kindle device or side-loaded via USB.
- **Audiobook pipeline** — extract → clean → voice-tag → render per-chapter MP3s via Balabolka + Microsoft Online neural voices.
- **Batch quality assurance** — drop a folder of ebooks in, get a ranked diagnostic report with visual-QA screenshots per book.

---

## Highlights

| Area | What's in the repo |
|---|---|
| **Extraction** | Four-tier PDF text engine (pypdf → pdfminer.six → PyMuPDF column-aware → Tesseract/Gemini OCR), with pre-flight classification that picks the right tier per book |
| **Heading & structure detection** | Font-metadata heading detection (pdfplumber), scholarly-footnote filtering, bookmark-to-paragraph alignment, optional Claude-assisted chapter boundary classification |
| **Output formats** | Voice-tagged Balabolka TXT, Kindle HTML (Calibre-ready), KFX/AZW3 via Calibre, per-chapter MP3 via balcon + FFmpeg |
| **Visual QA** | VLM-based post-conversion scoring (Qwen3-VL via OpenRouter → Claude Sonnet fallback on known-ambiguous pages) with JSON reports and HTML dashboards |
| **Learning loop** | SQLite pattern database tracks fix patterns, extraction cache hits, and score trends; converge loop iterates extract → score → fix until quality plateaus |
| **Regression discipline** | 6-book baseline test suite (`test_pipeline.py`) + 75-test voice-tag regression suite (`test_voice_tags.py`) + machine-readable feature manifest verified on each run |
| **Integrations** | Anthropic Claude (Haiku / Sonnet), Google Gemini 2.5 Flash, OpenRouter (cloud VLMs), local vLLM, Gmail SMTP (email-to-Kindle), Calibre, Balabolka, FFmpeg, Tesseract, Poppler |
| **Automation** | Windows Scheduled Task, inbox-driven batch processing, toast notifications, end-to-end PowerShell orchestration |

## What this project demonstrates

- **Multi-provider AI routing** with graceful degradation — each tier has a cheaper fallback, and the system prefers the cheapest tier that clears a quality gate.
- **Production-style regression testing** against real artifacts — every pipeline change runs against a fixed 6-book corpus, with a feature manifest that catches deleted exports before they ship.
- **Persistent learning** via a SQLite pattern database that tracks which fixes work, which books are in which extraction tier, and when to invalidate an extraction cache entry.
- **Cross-language orchestration** — PowerShell 5.1+ drives the user-facing pipeline; Python 3.12 does the heavy lifting for text/vision work; both share a single `config/settings.json`.
- **Pragmatic scope discipline** — this is a personal tool, so the codebase picks its battles: regression tests where the pain has been highest, quality gates where the cost of a bad output is highest, and plain scripts everywhere else.

---

## Architecture

```
inbox/                                   ← drop a PDF / EPUB / MOBI / AZW3 / DJVU here
  │
  ▼
preflight_analysis.py                    ← classify source (digital / scan / OCR),
                                           pick extraction strategy + recipe
  │
  ▼
pdf_to_balabolka.py                      ← tiered extraction:
  │                                        pypdf → pdfminer.six → PyMuPDF → OCR
  │                                        (Tesseract → Gemini Flash)
  ▼
heading / structure classification       ← font metadata + heuristics +
                                           optional Claude chapter-boundary pass
  │
  ├──▶  balabolka-txt/   (voice-tagged TXT)  ──▶  balcon.exe  ──▶  audiobooks/*.mp3
  │
  └──▶  kindle HTML       ──▶  ebook-convert.exe (Calibre)  ──▶  kindle/*.kfx
                                                                      │
                                                                      ▼
                                                          visual_qa.py  ← VLM scoring
                                                             │             (Qwen3-VL
                                                             │              → Claude)
                                                             ▼
                                                     pattern_db.py         ← learned
                                                     (SQLite cache          fix patterns,
                                                      + scores)             trend data
```

The PowerShell module (`module/EbookAutomation.psm1`) orchestrates this end-to-end and exposes it as cmdlets: `Invoke-EbookPipeline`, `Convert-ToTTS`, `Convert-ToKindle`, `Merge-ToKindle`, `Send-ToKindle`, `Invoke-BatchQA`, `Invoke-ConvergeLoop`, etc.

---

## Directory Structure

```
EbookAutomation/
├── config/
│   └── settings.json           # All paths and pipeline configuration
├── dictionaries/               # Pronunciation .dic files for Balabolka TTS
├── inbox/                      # Drop ebooks here — pipeline picks them up
├── processing/                 # Temp work area during conversion
├── archive/                    # Originals moved here after successful conversion
├── logs/                       # Daily log files + processed.txt manifest
├── output/
│   └── kindle/                 # KFX/AZW3 Kindle conversions
│                                # (audiobooks/, balabolka-txt/, episodes/ created on demand)
├── module/
│   ├── EbookAutomation.psm1    # Main PowerShell module (cmdlet surface)
│   ├── EbookAutomation.psd1    # Module manifest
│   ├── Run-Pipeline.ps1        # Scheduled-task entry point
│   └── launch.bat              # Quick-launch wrapper
├── tools/
│   ├── pdf_to_balabolka.py     # Core extraction engine (GUI + CLI)
│   ├── preflight_analysis.py   # Source classification + strategy recipe
│   ├── classify_source.py      # Digital / scan / OCR detection
│   ├── gemini_ocr.py           # Tier 2.5 OCR via Gemini Flash
│   ├── visual_qa.py            # VLM-based conversion scoring
│   ├── batch_qa.py             # Multi-book diagnostic pipeline
│   ├── pattern_db.py           # SQLite learning store
│   ├── chapter_alignment.py    # TOC / bookmark / heading cross-check
│   ├── fix_engine.py           # Pattern-driven remediation
│   ├── email_to_kindle.py      # Gmail SMTP delivery
│   ├── send_to_kindle.py       # Calibre USB delivery
│   ├── foh_scraper.py          # FOH forum scraper (standalone feature)
│   ├── foh_parser.py           # FOH daily-brief generator
│   ├── test_pipeline.py        # 6-book baseline regression harness
│   ├── test_voice_tags.py      # 75-test SAPI XML regression suite
│   ├── balcon/                 # Balabolka CLI engine (balcon.exe)
│   ├── poppler/                # Bundled Poppler utilities
│   ├── llm_providers/          # Vision-provider abstraction (cloud / local / Claude)
│   └── hooks/                  # Post-edit auto-test hook
├── tests/
│   ├── validate_against_baseline.py   # Baseline validator
│   ├── recapture_baselines.py         # Refresh baselines when intentionally changing
│   └── fixtures/
├── data/                       # SQLite pattern DB + VQA baselines
├── docs/                       # Design docs, plans, API registry
├── agents/                     # Claude agent prompts (structure, QA)
├── feature-manifest.json       # Machine-readable inventory of exported APIs
└── requirements.txt            # Python dependencies (Python 3.12)
```

---

## Usage

### Balabolka mode (plaintext with voice tags)

```powershell
py -3.12 tools\pdf_to_balabolka.py --input "book.pdf" --output-dir output\balabolka-txt
```

Output: `<title>_balabolka.txt` with ALL CAPS chapter headings, embedded SAPI voice tags, and silence markers. Feed it to Balabolka to split into per-chapter MP3s.

### Kindle HTML mode

```powershell
py -3.12 tools\pdf_to_balabolka.py --input "book.pdf" --mode kindle --html-extraction --output-dir output\kindle
```

Output: semantic HTML with proper heading hierarchy, blockquotes, and endnote links. Calibre converts it to KFX/AZW3.

### End-to-end via PowerShell

```powershell
Import-Module .\module\EbookAutomation.psd1

# Convert a single PDF to TTS-ready text
Convert-ToTTS -InputFile "book.pdf"

# Convert to Kindle (KFX) and email it
Convert-ToKindle -InputFile "book.pdf"
Send-ToKindle    -InputFile "output\kindle\book.kfx"

# Merge multiple markdown notes into one KFX
Merge-ToKindle -InputFiles note1.md, note2.md, note3.md -Title "My Collected Notes"

# Run the full inbox pipeline (scans inbox/, converts, archives originals)
Invoke-EbookPipeline

# Batch QA across a folder of ebooks
Invoke-BatchQA -FolderPath "test-corpus" -IncludeVQA
```

### Visual QA (post-conversion scoring)

```powershell
py -3.12 tools\visual_qa.py --input "output\kindle\book.kfx"
```

Produces a JSON report scoring heading hierarchy, TOC accuracy, footnote rendering, page breaks, and image placement. Uses Qwen3-VL (via OpenRouter) by default; falls back to Claude Sonnet for pages with known-ambiguous fingerprints.

---

## Requirements

### Runtime

- **Windows 10/11** — required for Microsoft Online neural voices, Scheduled Task integration
- **PowerShell 5.1+** — ships with Windows
- **Python 3.12** — all dependencies pinned in `requirements.txt`
- **Calibre** with KFX Output plugin — `winget install calibre`
- **Balabolka + balcon.exe** — [cross-plus-a.com/balabolka.htm](http://cross-plus-a.com/balabolka.htm)
- **FFmpeg** — `winget install ffmpeg`
- **Tesseract OCR** (optional, for Tier 2 image-PDFs) — [UB-Mannheim releases](https://github.com/UB-Mannheim/tesseract/wiki)
- **Poppler** — bundled in `tools/poppler/`

### Python packages

Install all dependencies:

```powershell
py -3.12 -m pip install -r requirements.txt
```

Dev / test dependencies (pytest):

```powershell
py -3.12 -m pip install -r dev-requirements.txt
```

Core packages: `pypdf`, `pdfminer.six`, `PyMuPDF`, `pdfplumber`, `pdf2image`, `pytesseract`, `EbookLib`, `beautifulsoup4`, `pyspellchecker`, `google-genai`, `openai`, `requests`, `python-dotenv`, `pillow`, `lxml`.

### Environment variables

Copy `.env.example` to `.env` and fill in the keys you plan to use:

```
ANTHROPIC_API_KEY    # Claude (chapter detection, VQA fallback)
OPENROUTER_API_KEY   # Qwen3-VL cloud VQA primary
GEMINI_API_KEY       # Gemini 2.5 Flash — Tier 2.5 OCR
EBOOK_SMTP_PASSWORD  # Email-to-Kindle delivery
```

All AI integrations degrade gracefully: extraction works without any API keys (local tiers only), and Visual QA / OCR fallback silently skip when keys are absent.

---

## First-time setup

1. Clone the repo and open PowerShell in the project root.
2. Install Python dependencies: `py -3.12 -m pip install -r requirements.txt`.
3. Copy `.env.example` → `.env` and set any API keys you want to use.
4. Edit `config/settings.json` — verify Calibre / Tesseract paths and choose Kindle output format (`kfx` or `azw3`).
5. Run the setup wizard:
   ```powershell
   Import-Module .\module\EbookAutomation.psd1
   Initialize-EbookAutomation
   ```
   Verifies dependencies, creates runtime folders, and optionally installs the Windows Scheduled Task.

---

## Testing

Full regression suite (6-book baseline, takes several minutes):

```powershell
py -3.12 tools\test_pipeline.py
```

Quick check (HTML pipeline only, fast):

```powershell
py -3.12 tools\test_pipeline.py --quick
```

Single book:

```powershell
py -3.12 tools\test_pipeline.py "Oil Kings"
```

Voice tag regression suite (SAPI XML format contract with SecondBrain):

```powershell
py -3.12 tools\test_voice_tags.py
```

Feature manifest verification (confirms no exported function / CLI mode / config key has been removed):

```powershell
pwsh -File tools\verify-manifest.ps1 -Verbose
```

Unit tests via pytest:

```powershell
py -3.12 -m pytest tests/
```

---

## Status

Active personal project. Not accepting contributions, but feel free to browse the code — the interesting bits are in `tools/pdf_to_balabolka.py` (tiered extraction), `tools/visual_qa.py` + `tools/llm_providers/` (multi-provider VLM routing), `tools/pattern_db.py` (the learning store), and `module/EbookAutomation.psm1` (the orchestration surface).
