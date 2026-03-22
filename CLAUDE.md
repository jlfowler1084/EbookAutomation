# CLAUDE.md — EbookAutomation Project Context

## Project Identity

EbookAutomation is a PowerShell + Python automation suite for:
- Converting ebooks (PDF, EPUB, MOBI, etc.) to TTS-ready text for Balabolka
- Converting PDFs to Kindle-formatted KFX files via Calibre
- Generating podcast/audiobook MP3s
- FOH (Fires of Heaven) forum scraping and daily brief generation

**Owner:** Joe
**Location:** `F:\Projects\EbookAutomation\`
**Platform:** Windows, PowerShell 5.1+, Python 3.8+

---

## Environment

- **OS:** Windows 10/11
- **Shell:** PowerShell 5.1+ (do NOT use bash syntax, `&` operator, or unix paths)
- **Python:** Microsoft Store Python 3.8+ (use `python -m pip install` not bare `pip`)
- **Node.js:** v24.14.0 (installed at `C:\Program Files\nodejs\`)
- **MCP config:** `.mcp.json` in project root (NOT settings.json)

This project runs on Windows. Use PowerShell syntax, not bash/Unix syntax. Do not use `&` pipe operators or Unix-style paths unless explicitly in WSL. Use backslash `\` path separators in PowerShell commands.

Use `python -m pip install` for package installs — bare `pip install` targets a different Python installation (project uses Microsoft Store Python 3.8).

Temp files may be cleaned up quickly by Windows — save diagnostic outputs to persistent locations (e.g., the project's `debug/` or `output/` directory), not system temp folders. When debugging, always verify you are looking at current output, not stale files from a previous run.

---

## Testing

Before modifying heading detection, TOC generation, bookmark reconciliation, footnote linking, or OCR cleanup logic, first analyze current behavior across all 5 test books and report findings. Do NOT edit code until you've reported the diagnosis and proposed a fix strategy.

After ANY change to pipeline code, run the full 5-book test suite. Never assume a fix is isolated — heading, TOC, footnote, and OCR systems are tightly coupled. Changes to heading levels cascade into TOC nesting and Calibre compatibility. A fix for one book has broken 4 others (Genesis, Oil Kings, Dionysius, Brother of Jesus) multiple times.

If a test book regresses, stop and diagnose before attempting another fix.

### Test Commands

- Run: `python tools/test_pipeline.py` (all books)
- Run: `python tools/test_pipeline.py "Oil Kings"` (single book)
- Run: `python tools/test_pipeline.py --quick` (HTML only, skip KFX)
- Run: `powershell -File tools/test_columns.ps1` (column detection + Ezekiel extraction)
- Test cases auto-captured in `tools/test_cases.json`
- NEVER report "no regression" without actually running the test suite

After ANY code change to the pipeline:
1. Run `test_pipeline.py` against all test cases
2. Verify endnote link count hasn't decreased
3. Verify no body text tagged as headings
4. Verify chapter detection count is correct
5. Verify PAGE markers survive all processing phases
6. Report results BEFORE telling the user "fix confirmed"

---

## Directory Structure

```
F:\Projects\EbookAutomation\
├── config\settings.json           ← central config, all paths defined here
├── dictionaries\                  ← pronunciation .dic files for Balabolka
├── inbox\                         ← drop ebooks here for pipeline processing
├── logs\                          ← daily logs + processed.txt manifest
├── module\                        ← PowerShell module (PSM1 + PSD1 + launch.bat)
├── output\
│   ├── audiobooks\                ← final MP3 audiobook files
│   ├── balabolka-txt\             ← Balabolka-ready TXT files
│   ├── episodes\                  ← FOH podcast MP4/MP3 episodes
│   └── kindle\                    ← KFX Kindle conversions
├── processing\                    ← temp work area during conversion
├── archive\                       ← originals moved here after conversion
└── tools\
    ├── balcon\                    ← Balabolka CLI engine (balcon.exe)
    ├── pdf_to_balabolka.py        ← PDF text extractor (GUI + CLI)
    ├── foh_scraper.py             ← FOH forum scraper
    ├── foh_parser.py              ← FOH data parser
    └── data\                      ← scraped JSON, credentials, session files
```

---

## Code Conventions

### PowerShell

- Functions follow **Verb-Noun** naming: `Convert-ToTTS`, `Invoke-EbookPipeline`
- Use **`Write-EbookLog`** for all logging — never `Write-Host` or `Write-Output` directly
- Export new functions through both the `.psm1` (`Export-ModuleMember`) and the `.psd1` manifest
- All paths come from `settings.json` via `Get-EbookConfig` and `Resolve-ProjectPath` — never hardcode absolute paths
- Error handling: wrap external tool calls in `try/catch`, return `$false` on failure
- Use `Start-Process` for Calibre/FFmpeg to isolate stderr from PowerShell's error system
- `$script:ModuleRoot` = project root (one level up from `module\`)

### Python

- Use `argparse` for CLI interfaces
- Use `tkinter` for GUI
- Include `if __name__ == "__main__":` guards
- Use `logging` module or explicit `log()` callback, not bare `print()`, for status output
- On Windows, reconfigure stdout/stderr to UTF-8 when output may be captured:
  ```python
  if sys.platform == 'win32':
      sys.stdout.reconfigure(encoding='utf-8', errors='replace')
      sys.stderr.reconfigure(encoding='utf-8', errors='replace')
  ```
- Resolve file paths relative to script location using `Path(__file__).resolve().parent`

### General

- All paths configurable via `config\settings.json` — reference paths relative to project root
- When generating code, produce **complete working files**, not fragments
- When modifying existing files, show specific changes with surrounding context

---

## Key Components

### settings.json paths

```json
{
  "paths": {
    "inbox": "inbox",
    "processing": "processing",
    "archive": "archive",
    "logs": "logs",
    "dictionaries": "dictionaries",
    "audiobooks": "output\\audiobooks",
    "balabolka_txt": "output\\balabolka-txt",
    "kindle": "output\\kindle",
    "episodes": "output\\episodes",
    "balcon": "tools\\balcon\\balcon.exe",
    "data": "tools\\data",
    "ffmpeg": "ffmpeg",
    "python": "python",
    "calibre": "C:\\Program Files\\Calibre2\\ebook-convert.exe"
  }
}
```

### EbookAutomation.psm1 (v1.1.0) — Exported Functions

| Function | Purpose |
|---|---|
| `Invoke-EbookPipeline` | Main inbox scan + convert loop (per-book error isolation) |
| `Convert-ToTTS` | PDF/EPUB → Balabolka TXT (OutputDir optional, defaults from config) |
| `Convert-ToKindle` | PDF → clean text → KFX via Calibre (text extraction + metadata) |
| `Convert-BriefToYouTube` | MP3 segments + cover → YouTube-ready MP4s via FFmpeg |
| `Install-EbookScheduledTask` | Register Windows Scheduled Task for pipeline |
| `Uninstall-EbookScheduledTask` | Remove the scheduled task |
| `Get-EbookTaskStatus` | Check scheduled task state |
| `Initialize-EbookAutomation` | First-run setup wizard |
| `Write-EbookLog` | Timestamped logging to file + console |
| `Get-EbookConfig` | Load and cache settings.json |
| `Get-EbookMetadataFromFilename` | Parse title/author from ebook filenames |

### pdf_to_balabolka.py — Modes

| Mode | Flag | Behavior |
|---|---|---|
| GUI | (no args) | Launches Tkinter GUI |
| Balabolka CLI | `--input book.pdf` | Extracts text from PDF/EPUB/MOBI/AZW/DJVU, strips front/back matter, ALL-CAPS chapter headings |
| Kindle CLI | `--input book.pdf --mode kindle` | Extracts text from PDF/EPUB/MOBI/AZW/DJVU, keeps full content, Markdown chapter headings for Calibre TOC |
| Kindle HTML | `--input book.pdf --mode kindle --html-extraction` | pdfminer font-metadata extraction → semantic HTML |
| Column-aware | `--force-columns` | Forces PyMuPDF column extraction regardless of detection confidence |

### Pipeline Architecture

Three extraction paths exist. Path selection happens inside `extract_text()` before any other logic:

**Auto-routing gate (in `extract_text()`):**
`detect_column_layout()` → if multi-column (confidence ≥ 60%): PyMuPDF path → else: pdfminer or pypdf path

1. **pdfminer (preferred, use `-UsePdfminer`):**
   `extract_with_pdfminer_html()` → `rejoin_html_fragments()` → `_fix_ligature_splits()` → `format_paragraphs_as_html()` → `_link_endnotes()`

2. **pypdf (legacy):**
   `extract_text()` → `clean_and_join()` → `fix_ocr_artifacts()` → AI rejoin → AI quality pass

3. **PyMuPDF column-aware (auto or `--force-columns`):**
   `detect_column_layout()` → `extract_text_columns()` → `clean_and_join()` → downstream unchanged
   Activated automatically when a PDF has ≥ 60% confidence of two-column layout (academic papers, commentaries).
   Use `--force-columns` / `-ForceColumns` to force this path regardless of detection confidence.

Changes to early phases cascade — always test downstream effects.

---

## External Dependencies

| Tool | Location | Purpose |
|---|---|---|
| Calibre (`ebook-convert.exe`) | `C:\Program Files\Calibre2\` | Ebook format conversion (KFX, AZW3, EPUB) |
| Calibre KFX Output plugin | Calibre plugins | Required for KFX output |
| Balabolka CLI (`balcon.exe`) | `tools\balcon\` | Text-to-speech engine |
| FFmpeg | PATH or `settings.json` | Audio/video encoding |
| Python 3.x | PATH | Script runtime |
| pypdf | pip package | PDF text extraction (MOBI/AZW/DJVU use Calibre intermediate) |
| ebooklib + BeautifulSoup | pip packages | Native EPUB text extraction |
| pymupdf | pip package | Two-column PDF layout detection and column-aware text extraction |

---

## MCP Servers

MCP configuration lives in `.mcp.json` at the project root — **not** in `settings.json` or `.claude/settings.json`.

### Prerequisites

| Requirement | Status | Details |
|---|---|---|
| Node.js | Installed | v24.14.0 at `C:\Program Files\nodejs\node.exe` |
| npx | Installed | `C:\Program Files\nodejs\npx.cmd` (bundled with Node.js) |

No global npm packages required — both servers are fetched via `npx -y` on first use.

### Context7 (`@upstash/context7-mcp`)

**Status:** Configured and operational

Provides up-to-date library documentation and code examples. Use when working with any third-party library (Python packages, PowerShell modules, etc.) to get current API docs rather than relying on training-data approximations.

**Config in `.mcp.json`:**
```json
"context7": {
  "command": "C:\\Program Files\\nodejs\\npx.cmd",
  "args": ["-y", "@upstash/context7-mcp@latest"]
}
```

- Downloads `@upstash/context7-mcp@latest` on first use per session — no persistent install needed
- No API key required
- **Fallback if unavailable:** Use web search for library docs, or consult `EbookAutomation_Dependencies.md` for known package versions

### Atlassian MCP

**Status:** Configured (remote server — requires internet + OAuth)

Connects to Atlassian Cloud (Jira, Confluence) via the official hosted MCP endpoint.

**Config in `.mcp.json`:**
```json
"atlassian": {
  "type": "url",
  "url": "https://mcp.atlassian.com/v1/mcp"
}
```

- Remote server — no local install; requires active internet connection
- Authenticates via browser OAuth on first use each session
- Permission `mcp__claude_ai_Atlassian__*` pre-allowed in `.claude/settings.local.json`
- **Fallback if unavailable:** Update Jira tickets manually via browser; no local fallback script exists yet

---

## Common Mistakes to Avoid

- Don't use bash syntax in PowerShell
- Changes to regex phases affect downstream phases — test the full pipeline
- Ligature fixes can break endnote linking (paragraph text changes shift cluster detection)
- Heading classification changes can break Calibre (invalid TOC nesting)

---

## TTS Voice Configuration

Voices in use (Microsoft Online voices only — never use SAPI/offline voices):

| Voice | Role |
|---|---|
| Microsoft Steffan Online | Main narrator (default, no tags needed) |
| Microsoft Guy Online | Male forum posters / quote voice |
| Microsoft Aria Online | Female official statements, female tweeters |
| Microsoft Jenny Online | Warmer female / conversational |

**Never reference** Zira, Hazel, or any voice without "Online" in the name.

## Dependencies Reference

A full list of all external dependencies (Python packages, standalone tools, API services, TTS voices) is maintained in `EbookAutomation_Dependencies.md` at the project root. Consult this document before adding new dependencies, and update it whenever a dependency is added or removed.

---

## FOH Daily Brief Generation

When generating FOH daily briefs from JSON data:
- Follow `FOH_Brief_Prompt_Template_v1_2.md` for format and voice tags
- Output `.txt` files with Balabolka SSML voice tags, ready to load directly
- Check the username pronunciation map and add new entries for unknown handles
- Word count targets vary by window size — refer to the length targets table

---

## Things to Avoid

- **Don't suggest cloud TTS** (Azure, ElevenLabs, etc.) unless specifically asked — local Balabolka workflow is intentional
- **Don't restructure `settings.json` schema** without discussion
- **Don't add Python dependencies** without calling them out — no `requirements.txt` yet, manual installs
- **Don't recommend rewriting** working components in a different language/framework without clear reason
- **Don't hardcode absolute paths** — everything goes through `settings.json`

---

## Current Priorities

See `EbookAutomation_ProjectTracker.md` for the full backlog. Key items:
1. ~~Expand `pdf_to_balabolka.py` to handle EPUB/MOBI/AZW natively~~ ✅ Done
2. Improve Kindle TOC detection (Claude API integration planned)
3. Add full comment-based help to all PowerShell functions
4. Complete the inbox-to-MP3 pipeline (TXT → balcon → WAV → MP3)
5. Test and configure the scheduled task
