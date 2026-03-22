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

## Requirements

- Python 3.8+
- pypdf, pdfminer.six, pymupdf (fitz)
- PowerShell 5.1+ (for EbookAutomation.psm1)
- Calibre (for ebook format conversion)
- Balabolka (for TTS playback)

## Status

Active development. Private repo — may go public eventually.
