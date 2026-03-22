# EbookAutomation — External Dependencies

> **Last updated:** 2026-03-21
> **Maintainer:** Joe  
> **Project root:** `F:\Projects\EbookAutomation\`

This document tracks every external dependency the EbookAutomation suite relies on — languages, runtimes, Python packages, standalone tools, and PowerShell modules. If a dependency is added or removed, update this file.

---

## Runtime Environment

| Dependency | Version | Purpose | Install |
|---|---|---|---|
| **Windows 10/11** | 10+ | Host OS for scheduled tasks, toast notifications, SAPI voices | — |
| **PowerShell** | 5.1+ (ships with Windows) | Automation module, pipeline orchestration | Built-in |
| **Python** | 3.8+ | Text extraction, OCR cleanup, FOH scraper | [python.org](https://python.org) — tick "Add to PATH" |

---

## Python Packages

### Required (core pipeline will fail without these)

| Package | PyPI Name | Purpose | Used By | Install |
|---|---|---|---|---|
| **pypdf** | `pypdf` | PDF text extraction (primary backend, fast) | `pdf_to_balabolka.py` | `pip install pypdf` |
| **pdfminer.six** | `pdfminer.six` | PDF text extraction (fallback for PDFs with word-merging issues) | `pdf_to_balabolka.py` | `pip install pdfminer.six` |
| **pyspellchecker** | `pyspellchecker` | Dictionary validation for OCR artifact correction (rn↔m, backtick ligatures) | `pdf_to_balabolka.py` → `fix_ocr_artifacts()` | `pip install pyspellchecker` |
| **requests** | `requests` | HTTP requests for FOH forum scraping | `foh_scraper.py` | `pip install requests` |

### Optional (specific features degrade gracefully without these)

| Package | PyPI Name | Purpose | Used By | Install |
|---|---|---|---|---|
| **pytesseract** | `pytesseract` | Python↔Tesseract bridge for OCR text extraction from image-only PDFs | `pdf_to_balabolka.py` → `extract_text_ocr()` | `pip install pytesseract` |
| **pdf2image** | `pdf2image` | PDF page→image rendering for Kindle cover extraction AND Tesseract OCR page rendering | `pdf_to_balabolka.py` → `extract_cover_image()`, `extract_text_ocr()` | `pip install pdf2image` |
| **tkinter** | (ships with Python) | GUI mode for `pdf_to_balabolka.py` (not used in CLI/pipeline mode) | `pdf_to_balabolka.py` | Included with standard Python install |
| **PyMuPDF** | `pymupdf` | Two-column PDF layout detection and column-ordered text extraction | `pdf_to_balabolka.py` → `detect_column_layout()`, `extract_text_columns()` | `pip install pymupdf` |

### Standard Library (no install needed)

These are used extensively but ship with Python: `argparse`, `re`, `statistics`, `os`, `sys`, `pathlib`, `threading`, `logging`, `json`, `time`, `datetime`, `glob`, `io`.

---

## Standalone Tools

| Tool | Path (from settings.json) | Purpose | Install |
|---|---|---|---|
| **Calibre** (`ebook-convert.exe`) | `C:\Program Files\Calibre2\ebook-convert.exe` | Converts TXT/HTML → KFX, AZW3, EPUB via command line | [calibre-ebook.com](https://calibre-ebook.com) |
| **Calibre KFX Output Plugin** | Calibre plugin manager | Enables KFX format output (required for `-OutputFormat kfx`) | MobileRead forums → Calibre plugin manager |
| **Balabolka CLI** (`balcon.exe`) | `tools\balcon\balcon.exe` | Text-to-speech audio generation (MP3 pipeline) | [cross-plus-a.com/balabolka.htm](http://cross-plus-a.com/balabolka.htm) |
| **ffmpeg** | `ffmpeg` (on PATH) | Audio encoding/concatenation for MP3 output | [ffmpeg.org](https://ffmpeg.org) |
| **Poppler** (`pdftoppm.exe`) | `tools\poppler\*\pdftoppm.exe` | PDF page-to-image rendering for cover extraction and Tesseract OCR | [poppler releases on GitHub](https://github.com/oschwartz10612/poppler-windows/releases) |
| **Tesseract OCR** (`tesseract.exe`) | `C:\Program Files\Tesseract-OCR\tesseract.exe` | OCR text extraction from image-only/scanned PDFs | [UB-Mannheim releases](https://github.com/UB-Mannheim/tesseract/wiki) |

---

## API Services

| Service | Auth | Purpose | Used By | Setup |
|---|---|---|---|---|
| **Anthropic Claude API** | `$env:ANTHROPIC_API_KEY` (permanent user env var) | Chapter detection via AI when `-UseClaudeChapters` is passed; FOH daily brief generation | `Send-ToClaudeAPI`, `Get-ChapterStructure` | Set env var: `[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', '<key>', 'User')` |

---

## TTS Voices (Windows SAPI)

These are not installable packages but are required system-level resources. Only Microsoft **Online** (neural) voices are approved.

| Voice | Role | How to Enable |
|---|---|---|
| **Microsoft Steffan Online** | Main narrator (default, no SSML tags needed) | Settings → Time & Language → Speech → Add voices |
| **Microsoft Guy Online** | Male quotes / forum poster voice | Same |
| **Microsoft Aria Online** | Female official statements, female tweeters | Same |
| **Microsoft Jenny Online** | Warmer female / conversational | Same |

> **Never use** Zira, Hazel, David, or any voice without "Online" in the name — these are older SAPI voices with robotic quality.

---

## Development Tools

| Tool | Version | Purpose | Install |
|---|---|---|---|
| **Node.js** | 24.14.0 LTS | Required for Context7 MCP server and future MCP integrations | `winget install OpenJS.NodeJS.LTS` |

---

## Dependency Health Check

Run `Initialize-EbookAutomation` to verify the core dependencies:

```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
Initialize-EbookAutomation
```

This checks Python, pypdf, pytesseract, Calibre, and Tesseract OCR. For a more thorough check of all Python packages:

```powershell
python -c "import pypdf; print(f'pypdf {pypdf.__version__}')"
python -c "import pdfminer; print('pdfminer.six OK')"
python -c "from spellchecker import SpellChecker; print('pyspellchecker OK')"
python -c "import requests; print(f'requests {requests.__version__}')"
python -c "from pdf2image import convert_from_path; print('pdf2image OK')"
python -c "import pytesseract; print(f'pytesseract {pytesseract.__version__}')"
```

---

## Adding New Dependencies

Before adding a new Python package or external tool:

1. **Call it out** — mention it in the chat/PR so it can be reviewed
2. **Update this file** — add the entry to the appropriate table above
3. **Add a graceful fallback** — if possible, degrade gracefully when the dependency is missing (see `_extract_with_pdfminer()` for an example of fallback-with-warning)
4. **Update `Initialize-EbookAutomation`** — add a check for the new dependency to the setup wizard
5. **No `requirements.txt` yet** — dependencies are installed manually; a `requirements.txt` is a backlog item

---

## Version History

| Date | Change |
|---|---|
| 2026-03-19 | Initial document created |
| 2026-03-21 | Added pytesseract, Tesseract OCR 5.5.0, updated pdf2image and Poppler descriptions for OCR role |
| 2026-03-19 | Added pdfminer.six (fallback PDF extraction for word-merging PDFs) |
| 2026-03-18 | Added pyspellchecker (OCR artifact correction) |
