# EbookAutomation

Personal automation pipeline for converting PDF and EPUB books into TTS-ready text files for Balabolka, with Kindle HTML output for e-readers.

## What It Does

EbookAutomation takes PDF and EPUB files and produces two kinds of output:

- **Balabolka mode** extracts text from PDF/EPUB, cleans OCR artifacts, detects chapters, strips front/back matter and footnotes, and outputs clean plaintext with ALL CAPS chapter headings. Balabolka uses these headings to split the text into separate MP3 tracks per chapter.
- **Kindle mode** runs the same extraction pipeline but outputs semantic HTML optimized for Kindle reading — proper heading hierarchy, blockquotes, and formatting that Calibre converts to KFX.

## Key Features

The extraction pipeline handles real-world PDFs that simple text extraction mangles. It detects PDF bookmarks and aligns them to paragraph positions, runs dual extraction via pypdf and pdfminer with automatic quality-based selection, and uses PyMuPDF for two-column academic PDFs. The HTML path uses font metadata for heading detection; the plaintext path uses heuristic chapter detection with scholarly footnote filtering.

Text cleanup covers the artifacts that OCR and PDF encoding leave behind: ligature splits (`ﬁ` → `fi`), merged word splitting, orphaned fragments, and hyphen rejoining across line breaks. Running headers and footers are detected and removed. Front matter (title pages, copyright, TOC) and back matter (indices, bibliographies) are trimmed automatically. Footnotes are stripped — both inline reference markers and trailing endnote text.

A 6-book baseline validation test suite catches regressions across all of these systems, since heading detection, TOC generation, footnote linking, and OCR cleanup are tightly coupled.

## Pipeline Components

- `tools/pdf_to_balabolka.py` — Main converter (GUI + CLI)
- `tools/test_pipeline.py` — Baseline validation test runner
- `EbookAutomation.psm1` — PowerShell module for inbox scanning, Calibre routing, scheduled task support
- `config/settings.json` — All paths and configuration

## Directory Structure

```
EbookAutomation/
├── config/
│   └── settings.json           # All paths and configuration
├── dictionaries/               # Pronunciation .dic files for Balabolka TTS
├── inbox/                      # Drop ebooks here — pipeline picks them up
├── logs/                       # Daily log files + processed.txt manifest
├── module/
│   ├── EbookAutomation.psm1    # PowerShell automation module
│   ├── EbookAutomation.psd1    # Module manifest
│   └── launch.bat              # Quick-launch wrapper
├── output/
│   ├── audiobooks/             # Final MP3 audiobook files
│   ├── balabolka-txt/          # Balabolka-ready TXT files with voice tags
│   └── kindle/                 # KFX/AZW3 Kindle conversions
├── processing/                 # Temp work area during conversion
├── archive/                    # Originals moved here after successful conversion
├── tests/                      # Baseline validation test suite
└── tools/
    ├── balcon/                 # Balabolka CLI engine (balcon.exe)
    ├── pdf_to_balabolka.py     # Main converter (GUI + CLI)
    ├── visual_qa.py            # Visual QA tool
    └── test_pipeline.py        # Pipeline test runner
```

## TTS Voice Configuration

All TTS output uses Microsoft Online voices via Balabolka/balcon. These are high-quality neural voices — older SAPI/offline voices (Zira, Hazel, etc.) are never used.

| Voice | Role |
|---|---|
| Microsoft Steffan Online | Main narrator (default) |
| Microsoft Guy Online | Male quotes / dialogue |
| Microsoft Aria Online | Female official / formal |
| Microsoft Jenny Online | Female conversational / warm |

Voice switching is handled through Balabolka SSML tags embedded in the output TXT files. The converter inserts appropriate voice tags, silence pauses between chapters, and rate adjustments automatically.

## MP3 / Audiobook Generation

The full pipeline from PDF to MP3 audiobook:

1. **Extract & clean** — `pdf_to_balabolka.py` produces a voice-tagged TXT file with chapter headings
2. **TTS render** — `balcon.exe` (Balabolka CLI) converts text to WAV using Microsoft Online voices
3. **Encode** — FFmpeg converts WAV segments to MP3
4. **Split** — Balabolka splits on ALL CAPS chapter headings, producing one MP3 per chapter

The PowerShell module orchestrates this end-to-end:

```powershell
# Convert a single PDF to TTS-ready text
Convert-ToTTS -InputFile "book.pdf"

# Run the full inbox pipeline (scans inbox/, converts all files, archives originals)
Invoke-EbookPipeline
```

### Tools involved

| Tool | Purpose |
|---|---|
| balcon.exe | Balabolka command-line TTS engine — renders text to WAV |
| FFmpeg | WAV → MP3 encoding, audio segment joining |
| Calibre (ebook-convert.exe) | EPUB/MOBI → intermediate format conversion |
| Balabolka (GUI) | Manual TTS preview, split-and-convert to MP3 per chapter |

## Usage

Balabolka mode (plaintext output):

```
python tools/pdf_to_balabolka.py --input book.pdf --output-dir output/
```

Kindle HTML mode:

```
python tools/pdf_to_balabolka.py --input book.pdf --mode kindle --html-extraction --output-dir output/
```

Run tests:

```
python tests/validate_against_baseline.py
```

## Setup

### Requirements

- Python 3.8+ with packages: `pypdf`, `pdfminer.six`, `pymupdf`
- PowerShell 5.1+ (ships with Windows 10/11)
- [Calibre](https://calibre-ebook.com) with KFX Output plugin
- [Balabolka](https://cross-plus-a.com/balabolka.htm) + `balcon.exe` CLI
- [FFmpeg](https://ffmpeg.org)
- Windows 10/11 (for Scheduled Task integration and Microsoft Online TTS voices)

### First-time setup

1. Clone the repo and open PowerShell in the project directory
2. Install Python dependencies:
   ```
   python -m pip install pypdf pdfminer.six pymupdf
   ```
3. Edit `config/settings.json` — verify the Calibre path and choose your Kindle output format (`kfx` or `azw3`)
4. Run the setup wizard:
   ```powershell
   Import-Module .\module\EbookAutomation.psd1
   Initialize-EbookAutomation
   ```
   This checks all dependencies, creates required folders, and optionally installs the Windows Scheduled Task.

## Status

Active development. Private repo — may go public eventually.
