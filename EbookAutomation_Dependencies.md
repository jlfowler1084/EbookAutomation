# EbookAutomation — External Dependencies

> **Last updated:** 2026-04-21
> **Maintainer:** Joe
> **Project root:** `F:\Projects\EbookAutomation\`

Every external dependency the EbookAutomation suite relies on — languages, runtimes, pinned Python packages, standalone tools, API services, and PowerShell modules. Pinned versions are the source of truth in [`requirements.txt`](./requirements.txt); this file exists to describe *why* each dependency is here and where it gets used.

---

## Runtime Environment

| Dependency | Version | Purpose | Install |
|---|---|---|---|
| **Windows 10/11** | 10+ | Host OS for Scheduled Tasks, toast notifications, Microsoft Online SAPI voices | — |
| **PowerShell** | 5.1+ (ships with Windows) | Automation module, pipeline orchestration, cmdlet surface | Built-in |
| **Python** | 3.12 | Text extraction, vision QA, OCR, chapter detection, FOH scraper | [python.org](https://python.org) — tick "Add to PATH" |

---

## Python Packages

All packages are installed via `py -3.12 -m pip install -r requirements.txt`. The project pins exact versions — the table below reflects what's in `requirements.txt` at the time of writing. If you add or upgrade a dependency, update both this table and `requirements.txt`.

### Required (core pipeline fails without these)

| Package | Pinned Version | Purpose | Used By |
|---|---|---|---|
| **pypdf** | `6.9.2` | Primary PDF text extraction (fast digital PDFs) | `extract_tts_text.py` |
| **pdfminer.six** | `20260107` | Fallback PDF extraction for word-merging / column-bleed PDFs | `extract_tts_text.py` |
| **PyMuPDF** | `1.27.2.2` | Column-aware extraction for two-column academic PDFs | `extract_tts_text.py`, `visual_qa.py` |
| **pdf2image** | `1.17.0` | PDF → PNG rendering for cover extraction, OCR, Visual QA | `extract_tts_text.py`, `visual_qa.py`, `gemini_ocr.py` |
| **pytesseract** | `0.3.13` | Python ↔ Tesseract bridge for Tier 2 OCR | `extract_tts_text.py` |
| **EbookLib** | `0.20` | EPUB parsing for native EPUB extraction path | `extract_tts_text.py` |
| **beautifulsoup4** | `4.14.3` | HTML parsing for EPUB / Kindle HTML post-processing | `extract_tts_text.py` |
| **google-genai** | `1.68.0` | Gemini 2.5 Flash — Tier 2.5 OCR (10-20× cheaper than Claude Vision) | `gemini_ocr.py`, `visual_qa.py` fallback |
| **openai** | `1.109.1` | OpenAI-compatible client for OpenRouter (cloud VLMs) and local vLLM endpoints | `tools/llm_providers/` |
| **requests** | `2.33.0` | HTTP client — FOH forum scraping, Kindle email webhooks | `foh_scraper.py`, `email_to_kindle.py` |
| **pyspellchecker** | `0.9.0` | Dictionary validation for OCR artifact correction (rn ↔ m, ligature splits) | `extract_tts_text.py` → `fix_ocr_artifacts()` |
| **python-dotenv** | `1.2.2` | Loads API keys from `.env` at runtime | All tools that touch external APIs |

### Optional (features degrade gracefully when missing)

| Package | Pinned Version | Purpose | Used By |
|---|---|---|---|
| **pdfplumber** | `0.11.5` | Coordinate-based heading resolution for font-metadata heading detection | `extract_tts_text.py` → `detect_headings_font.py` |
| **tkinter** | (stdlib) | GUI mode for `extract_tts_text.py` | `extract_tts_text.py` |

### Transitive / required by other packages

| Package | Pinned Version | Required By |
|---|---|---|
| **lxml** | `6.0.2` | `EbookLib`, `pdfminer.six` |
| **pillow** | `12.1.1` | `pdf2image`, `pytesseract` |
| **charset-normalizer** | `3.4.6` | `requests` |

### Dev / test

Installed via `py -3.12 -m pip install -r dev-requirements.txt` (which also pulls in `requirements.txt`).

| Package | Pinned Version | Purpose |
|---|---|---|
| **pytest** | `9.0.2` | Unit test runner for `tests/` |

### Standard library (no install needed)

Used extensively: `argparse`, `re`, `statistics`, `os`, `sys`, `pathlib`, `threading`, `logging`, `json`, `time`, `datetime`, `glob`, `io`, `sqlite3`, `hashlib`, `concurrent.futures`, `html`.

---

## Python Tools Inventory (tools/)

Every Python script in `tools/` that ships with the project, grouped by role. Test scripts are listed in the **Testing** section further down.

### Extraction pipeline

| Script | Purpose |
|---|---|
| `extract_tts_text.py` | Core extraction engine (GUI + CLI). Routes through tiered extraction, heading detection, footnote handling, Balabolka/Kindle output. |
| `preflight_analysis.py` | Analyzes a source document in <10s, picks extraction strategy + conversion recipe. |
| `classify_source.py` | Classifies PDFs as digital / scan / OCR based on text density and producer metadata. |
| `detect_headings_font.py` | pdfplumber-based font-metadata heading detection. |
| `chapter_alignment.py` | Cross-references detected chapters against PDF bookmarks / TOC. |
| `filter_content.py` | Front-matter / back-matter trimming and footnote filtering. |
| `gemini_ocr.py` | Tier 2.5 OCR via Google Gemini 2.5 Flash (full-book or VQA-flagged page remediation). |
| `scan-image-density.py` | Heuristic: is this page image-heavy enough to warrant OCR? |

### Quality assurance

| Script | Purpose |
|---|---|
| `visual_qa.py` | Post-conversion VLM scoring against a rubric. Provider-pluggable (Claude / cloud VLM / local vLLM). |
| `batch_qa.py` | Runs the full pipeline across a folder of ebooks, produces HTML dashboards + summary reports. Supports resume, comparison, parallel execution. |
| `compare_vqa_reports.py` | Diff two VQA runs; baseline audit subcommand verifies page-sample parity. |
| `import_vqa_reports.py` | Import VQA JSON reports into the pattern database. |
| `analyze_vqa_mode_classification.py` | Offline analysis of VQA mode-classifier decisions for tuning. |
| `fix_engine.py` | Pattern-driven remediation — applies learned fix patterns to extraction outputs. |

### Learning / storage

| Script | Purpose |
|---|---|
| `pattern_db.py` | SQLite pattern database (books, attempts, issues, fixes, extraction cache, overrides). CLI subcommands: `init`, `stats`, `import-vqa`, `history`, `fixes`, `trend`, `cost`, `cache*`, `override*`. |

### Delivery

| Script | Purpose |
|---|---|
| `email_to_kindle.py` | Gmail SMTP delivery to a registered Kindle email address. |
| `send_to_kindle.py` | USB/Calibre-based side-load delivery. |

### Standalone features (not part of the ebook pipeline)

| Script | Purpose |
|---|---|
| `foh_scraper.py` | FOH (Friends of Habersham) forum scraper. |
| `foh_parser.py` | Daily-brief generator from scraped FOH content (uses Claude). |

### Shared infrastructure

| Path | Purpose |
|---|---|
| `tools/llm_providers/` | Vision-provider abstraction — Claude, cloud VLM (OpenRouter), local (vLLM). Routes visual-QA calls through a pluggable interface. |
| `tools/hooks/post-edit-test.ps1` | PostToolUse hook — auto-runs `test_pipeline.py --quick` after edits to core pipeline files. |
| `tools/verify-manifest.ps1` | Verifies `feature-manifest.json` against the current codebase. |

### Testing

| Script | Purpose |
|---|---|
| `test_pipeline.py` | 6-book baseline regression harness (Oil Kings, Mexico Illicit, Return of the Gods, Atomic Habits, Decline of the West, Python in Easy Steps). |
| `test_voice_tags.py` | 75-test SAPI XML regression suite enforcing the TTS contract with SecondBrain. |
| `test_preflight.py` | Unit tests for `preflight_analysis.py`. |
| `test_chapter_alignment.py` | Unit tests for `chapter_alignment.py`. |
| `test_filter_content.py` | Unit tests for content filtering. |
| `test_metadata.py` | Unit tests for metadata extraction. |
| `test_footnotes.py` | Unit tests for footnote handling. |
| `test_columns.ps1` | PowerShell driver for column detection tests. |
| `tests/validate_against_baseline.py` | Baseline validator used by the CI-style regression flow. |
| `tests/test_*.py` | Pytest unit tests (baseline audit, capture-pipeline derivation, fingerprint detector, local provider phase2, PDF↔KFX warning, vision provider, hybrid routing, VQA mode classifier). |

---

## Standalone Tools

| Tool | Path (from `config/settings.json`) | Purpose | Install |
|---|---|---|---|
| **Calibre** (`ebook-convert.exe`) | `C:\Program Files\Calibre2\ebook-convert.exe` | Converts TXT / HTML → KFX, AZW3, EPUB from the command line | `winget install calibre` |
| **Calibre KFX Output Plugin** | Calibre plugin manager | Enables KFX format output | MobileRead forums → Calibre plugin manager |
| **Balabolka CLI** (`balcon.exe`) | `tools\balcon\balcon.exe` | Text-to-speech audio generation (MP3 pipeline) | [cross-plus-a.com/balabolka.htm](http://cross-plus-a.com/balabolka.htm) |
| **FFmpeg** | `ffmpeg` (on PATH) | WAV → MP3 encoding, audio segment joining | `winget install ffmpeg` |
| **Poppler** (`pdftoppm.exe`) | `tools\poppler\*\pdftoppm.exe` | PDF → image rendering for cover extraction, OCR, Visual QA | Bundled in `tools/poppler/` |
| **Tesseract OCR** (`tesseract.exe`) | `C:\Program Files\Tesseract-OCR\tesseract.exe` | OCR text extraction from image-only / scanned PDFs | [UB-Mannheim releases](https://github.com/UB-Mannheim/tesseract/wiki) |

---

## API Services

All keys live in `.env` (see `.env.example`). All integrations degrade gracefully — the pipeline runs without any API keys, and AI-dependent features (Claude chapter detection, Visual QA, Gemini OCR, email delivery) silently skip when the relevant key is absent.

| Service | Env var | Purpose | Used By |
|---|---|---|---|
| **Anthropic Claude API** | `ANTHROPIC_API_KEY` | Chapter detection via `-UseClaudeChapters`, FOH daily-brief generation, Visual QA fallback for ambiguous pages, structure-analysis agent | `Send-ToClaudeAPI`, `Get-ChapterStructure`, `visual_qa.py` fallback, `foh_parser.py` |
| **Google Gemini API** | `GEMINI_API_KEY` | Gemini 2.5 Flash — Tier 2.5 OCR (full-book transcription or VQA page remediation) | `gemini_ocr.py` |
| **OpenRouter** | `OPENROUTER_API_KEY` | Qwen3-VL cloud VQA primary — cheaper than Claude for routine pages | `tools/llm_providers/CloudVLProvider` |
| **Local vLLM** | `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_VISION_MODEL` | Local Qwen3-VL on `sb-chat` — zero-cost VQA when available | `tools/llm_providers/LocalVisionProvider` |
| **Gmail SMTP** | `EBOOK_SMTP_PASSWORD` | Email-to-Kindle delivery (Gmail app password). SMTP user configured in `config/settings.json` → `kindle_delivery.email`. | `email_to_kindle.py`, `Send-ToKindle` cmdlet |

Model IDs are configured in `config/settings.json` → `api_models`. Current defaults:

```json
{
  "haiku":         "claude-haiku-4-5-20251001",
  "sonnet":        "claude-sonnet-4-20250514",
  "sonnet_latest": "claude-sonnet-4-6",
  "gemini_flash":  "gemini-2.5-flash"
}
```

Cloud VLM defaults (`config/settings.json` → `visual_qa`):

- Primary: `qwen/qwen3-vl-30b-a3b-instruct` via OpenRouter
- Fallback: `claude-sonnet-4-6` for fingerprinted pages where the VLM's accuracy is known-poor

---

## TTS Voices (Windows SAPI)

Not installable packages — required system-level resources. Only Microsoft **Online** (neural) voices are approved.

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
| **Node.js** | 24.14.0 LTS | Required for the Context7 MCP server and other Node-based MCP integrations | `winget install OpenJS.NodeJS.LTS` |

---

## Dependency Health Check

Run `Initialize-EbookAutomation` to verify core dependencies:

```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
Initialize-EbookAutomation
```

For a more thorough Python package check:

```powershell
py -3.12 -c "import pypdf; print(f'pypdf {pypdf.__version__}')"
py -3.12 -c "import pdfminer; print('pdfminer.six OK')"
py -3.12 -c "import fitz; print(f'PyMuPDF {fitz.__version__}')"
py -3.12 -c "import pdfplumber; print(f'pdfplumber {pdfplumber.__version__}')"
py -3.12 -c "from spellchecker import SpellChecker; print('pyspellchecker OK')"
py -3.12 -c "import pytesseract; print(f'pytesseract {pytesseract.__version__}')"
py -3.12 -c "from pdf2image import convert_from_path; print('pdf2image OK')"
py -3.12 -c "from google import genai; print('google-genai OK')"
py -3.12 -c "import openai; print(f'openai {openai.__version__}')"
py -3.12 -c "import ebooklib; print(f'EbookLib {ebooklib.VERSION}')"
```

---

## Adding New Dependencies

Before adding a new Python package or external tool:

1. **Call it out** — mention it in the chat / PR so it can be reviewed.
2. **Pin the version** — add `package==x.y.z` to `requirements.txt`.
3. **Update this file** — add the entry to the appropriate table above, including the pinned version.
4. **Add a graceful fallback** — degrade gracefully when the dependency is missing (see `_extract_with_pdfminer()` for the fallback-with-warning pattern).
5. **Update `Initialize-EbookAutomation`** — add a dependency check to the setup wizard.
6. **Update the feature manifest** — if the new package adds a public capability, add it to `feature-manifest.json`.

---

## Version History

| Date | Change |
|---|---|
| 2026-04-21 | SCRUM-297 — full reconciliation with `requirements.txt`; added pinned versions; documented every `tools/` script; added OpenRouter + local vLLM + Gmail SMTP API services; corrected Python version floor to 3.12 |
| 2026-03-25 | Added google-genai for Gemini Flash OCR (Tier 2.5). Requires `GEMINI_API_KEY` env var. |
| 2026-03-21 | Added pytesseract, Tesseract OCR 5.5.0, updated pdf2image and Poppler descriptions for OCR role |
| 2026-03-19 | Added pdfminer.six (fallback PDF extraction for word-merging PDFs) |
| 2026-03-19 | Initial document created |
| 2026-03-18 | Added pyspellchecker (OCR artifact correction) |
