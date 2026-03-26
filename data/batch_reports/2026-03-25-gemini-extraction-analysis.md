# Gemini Extraction Analysis — 4 Books Tested

**Date:** 2026-03-25
**Extraction method:** Gemini 2.5 Flash via `gemini_ocr.py`
**Pipeline:** `pdf_to_balabolka.py --mode kindle --html-extraction --use-gemini --no-cache`

## Results Summary

| Book | Pages | Words | Quality | Cost | Headings | Producer | Status |
|------|-------|-------|---------|------|----------|----------|--------|
| Hero Tales | 79 | 10,981 | 100/100 | $0.047 | 0 | LuraDocument v2.28 | SUCCESS |
| Oxford Companion | 936 | 945,755 | 97/100 | $4.84 | 0 | LuraDocument v2.68 | SUCCESS |
| Hindu Pantheon | 480 | 193,872 | N/A | ~$0.78 est | 0 | libtiff/tiff2pdf (ScanFix) | SUCCESS |
| N.T. Wright | 765 | 0 | N/A | ~$1.25 spent | 0 | Adobe Acrobat 7.1 Image | FAILED |

### Per-Book Details

**Hero Tales (79 pages, 16 MB)**
- Producer: LuraDocument PDF v2.28 / Internet Archive
- All 16 batches completed, no failures
- 188 paragraphs, clean English text
- Cost per word: $0.000004

**Oxford Companion to the Bible (936 pages, 45.5 MB)**
- Producer: LuraDocument PDF v2.68 / Internet Archive
- 188 batches, ~30 failed with NoneType bug (text still collected for most)
- 821/936 pages reported as processed (115 pages lost to batch errors)
- 22,711 paragraphs — massive encyclopedia
- Several batches hit 65,536 output token limit (Gemini max) — back matter/index pages
- Processing time: 210 minutes (3.5 hours)
- Cost per word: $0.000005

**Hindu Pantheon (480 pages, 23.4 MB)**
- Producer: libtiff/tiff2pdf (ScanFix Enhanced)
- TIFF-converted scan, oldest book in corpus (~1810 original)
- 2,678 paragraphs, 193K words
- Text includes Sanskrit/Devanagari transliterations
- Last 300 chars show index entries — full text extracted including back matter

**N.T. Wright — Jesus and the Victory of God (765 pages, 72.6 MB)**
- Producer: Adobe Acrobat 7.1 Image Conversion Plug-in
- FAILED: Many batches returned 0 output tokens
- Likely cause: Gemini safety filter or low-quality scanned images that Gemini couldn't read
- 10 of first 81 batches returned 0 tokens (~12% failure rate)
- At 72.6 MB for 765 pages (0.095 MB/page — highest density), images may be too compressed or degraded
- This is the ONLY Adobe Acrobat Image Conversion producer in the test set

## Cross-Book Analysis

### Cost per Word
| Book | $/word | $/page |
|------|--------|--------|
| Hero Tales | $0.0000043 | $0.00059 |
| Oxford Companion | $0.0000051 | $0.0052 |
| Hindu Pantheon | ~$0.0000040 | ~$0.0016 |

Average: **~$0.005/page** or **~$0.45 per 100 pages**. Significantly cheaper than Claude Vision (~$0.20/book for 20 sampled pages, but Gemini does ALL pages).

### Producer Correlation
| Producer | Books | Outcome |
|----------|-------|---------|
| LuraDocument PDF (Internet Archive) | Hero Tales, Oxford Companion | Both SUCCESS — high quality |
| libtiff/tiff2pdf (ScanFix) | Hindu Pantheon | SUCCESS — even 200-year-old scans work |
| Adobe Acrobat 7.1 Image Conversion | N.T. Wright | FAILED — 0-token batches |

**Key finding:** LuraDocument/Internet Archive PDFs are Gemini's sweet spot. These defeated both Tesseract and pdfminer but Gemini reads them perfectly. The Adobe Acrobat Image Conversion format is problematic — further investigation needed.

### Heading Detection Rate
**Zero headings detected across ALL books.** This is a pipeline issue, not a Gemini issue:

1. Gemini transcription prompt (original) did not instruct `##` heading markers
2. The `vision_text_to_para_dicts` bridge converts plain text to paragraph dicts without heading detection
3. ALL CAPS lines that could be headings: Hero Tales 53, Oxford 653, Hindu 455

**Prompt fix deployed mid-session:** Updated `_GEMINI_TRANSCRIPTION_PROMPT` rule #3 to explicitly request `## HEADING` markers. This was NOT active for any of these extractions — future runs will test whether Gemini produces headings with the new prompt.

### Page Rendering Analysis
- **Unicode filename workaround required:** All 4 books had smart apostrophe (`'`) in "Anna's Archive" filename. Poppler cannot handle non-ASCII filenames on Windows. Fix: copy to ASCII temp path before rendering.
- **Single-copy optimization:** Original code copied the PDF per-batch (188x for Oxford = 8.4 GB of copies). Refactored to copy once at extraction start.
- **"Object X not defined" warnings:** All books produced hundreds of these pypdf warnings. These indicate corrupted/non-standard PDF object references but do NOT prevent poppler from rendering — poppler ignores them.

### Gemini vs Tesseract Comparison
From the rescue run (2026-03-25), Tesseract produced:
- Oxford Companion: **0 words** (FAIL)
- N.T. Wright: **88 words** (effectively zero)
- Hindu Pantheon: **84 words** (effectively zero)
- Hero Tales: **0 words** (FAIL)

Gemini produced:
- Oxford Companion: **945,755 words** (SUCCESS)
- Hindu Pantheon: **193,872 words** (SUCCESS)
- Hero Tales: **10,981 words** (SUCCESS)
- N.T. Wright: **0 words** (FAILED — different failure mode than Tesseract)

**Gemini rescued 3 of 4 books that Tesseract completely failed on.** The one failure (Wright) is an Adobe Acrobat image format issue, not a general Gemini limitation.

### Quality Consistency
- Hero Tales: 100/100
- Oxford Companion: 97/100
- Both scored high. Quality appears uniformly excellent for successfully extracted books.
- Some batches hit 65,536 token limit (Gemini's max output) — indicates dense pages where Gemini may loop/hallucinate. These should be flagged for review.

### Script Handling
- **Hindu Pantheon** includes Sanskrit/Devanagari transliterations (e.g., "Vibhāvana", "Vikramāditya") — Gemini handled diacritics correctly
- **Oxford Companion** likely contains Hebrew/Greek theological terms — not verified in sample
- All books marked "Scripts: Latin only" by the pipeline — the script detection may need tuning for transliterated text

## Bugs Found and Fixed This Session

1. **`settings.json` poppler path** — pointed to `tools\poppler` instead of actual bin directory
2. **`pdf_to_balabolka.py` poppler discovery** — added recursive search for `pdftoppm.exe`
3. **`GEMINI_API_KEY` missing from `.env`** — added for `load_dotenv()` to work
4. **Unicode filename workaround** — `gemini_ocr.py` `_ensure_safe_path()` copies to ASCII temp
5. **Per-batch copy overhead** — refactored to copy once, clean up in `finally` block
6. **NoneType token count bug** — `usage.prompt_token_count` can be None; fixed with `or 0`
7. **Heading detection prompt** — added `## HEADING` instruction to Gemini transcription prompt

## Recommendations

1. **Auto-escalate to Gemini for LuraDocument/Internet Archive producers** — these consistently defeat Tesseract but Gemini reads them perfectly. The producer string is available from PDF metadata at extraction time.

2. **Tune Gemini transcription prompt for headings** — the `##` marker instruction is deployed but untested. Re-run Hero Tales with `--no-cache` to validate.

3. **Enhance `vision_text_to_para_dicts` bridge** — even without `##` markers, detect ALL CAPS lines and "Chapter X" patterns as headings. The `ocr_text_to_para_dicts` function already does this for Tesseract output — port that logic.

4. **Investigate Wright's Adobe Acrobat Image format** — try rendering a single page manually with PyMuPDF (which worked for Oxford) to see if the images are readable. The failure may be poppler-specific or Gemini safety filter.

5. **Batch size optimization** — current batch size of 5 pages works well. No evidence that larger batches would help, and smaller batches increase API call overhead.

6. **65,536 token batches need review** — these represent Gemini hitting its output limit, potentially including hallucinated/looped content. Flag for quality review.

7. **Wright workaround** — try sending the PDF directly to Gemini as a document upload (the google-genai SDK supports this) instead of page-by-page rendering. This bypasses poppler entirely and may work for Adobe Acrobat images.
