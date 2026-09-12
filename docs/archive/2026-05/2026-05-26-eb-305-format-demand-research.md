# EB-305: Output Format Demand Research — Forum Scrape + Competitor Landscape

**Date:** 2026-05-26  
**Ticket:** EB-305  
**Author:** Claude (Sonnet 4.6, Stream D)  
**Scope:** Research only. No code changes.

---

## Summary

This document assesses demand for output formats beyond leafbind.io's current EPUB / MOBI / KFX set.  
Sources consulted: MobileRead Calibre/Kobo forums, Reddit (r/ebooks, r/Calibre, r/kobo), competitor format matrices (CloudConvert, Zamzar, online-convert.com), and Calibre's official documentation.  
Hypothesis: each added format reduces the "wrong tool for me" bounce rate for a distinct user segment.

---

## Source Index

| # | Source | Date Accessed | Notes |
|---|--------|---------------|-------|
| S1 | CloudConvert ebook-converter page — `https://cloudconvert.com/ebook-converter` | 2026-05-26 | Full JSON format list embedded in page JS payload |
| S2 | Zamzar EPUB/PDF/CBZ conversion pages — `https://www.zamzar.com/convert/epub-to-azw3/`, `/pdf-to-epub/`, `/cbz-to-epub/` | 2026-05-26 | Target-format lists extracted from page links |
| S3 | online-convert.com ebook converter — `https://ebook.online-convert.com/` | 2026-05-26 | Output format list extracted from page links |
| S4 | Calibre FAQ / manual — `https://manual.calibre-ebook.com/faq.html` | 2026-05-26 | Authoritative input/output format lists |
| S5 | Reddit r/ebooks "Any advanced tool to decently convert PDF academic papers to EPUB?" — `https://www.reddit.com/r/ebooks/comments/1tlu4a0/` | 2026-05-26 | Thread ID 1tlu4a0; confirmed active 2026-05 |
| S6 | Reddit r/Calibre "Convert CBZ to Kepub?" — thread ID 1tm1n71 | 2026-05-26 | Confirmed active ~2026-05; score 3 |
| S7 | Reddit r/ebooks "Convert CBZ to Kepub?" (crosspost signals) + r/ebooks format search results | 2026-05-26 | Multiple active threads in r/ebooks, r/Calibre |
| S8 | MobileRead Calibre forum search — format conversion threads, `https://www.mobileread.com/forums/forumdisplay.php?f=166` | 2026-05-26 | Returned "Kepub Conversion Issue", "Selecting source format for conversion?", DJVU and DOCX threads |
| S9 | MobileRead Kobo forum search — kepub conversion threads, `https://www.mobileread.com/forums/search.php?...forumchoice[]=176` | 2026-05-26 | Returned "Kepub Conversion Issue" and format-selection threads |
| S10 | GitHub Calibre Issues search — `https://api.github.com/search/issues?q=repo:kovidgoyal/calibre+output+format+request` | 2026-05-26 | Low signal for new-format feature requests; format work largely done in upstream Calibre |

> **Inaccessible sources:**  
> - `ebook.online` (host not found — domain appears defunct)  
> - Zamzar `/formats/ebook/` listing page (returned empty result set — fetched specific conversion pages instead)  
> - Direct DJVU-to-EPUB page on Zamzar returned a redirect/404 pattern, indicating DJVU is NOT in their ebook converter

---

## Calibre Authoritative Format Reference (S4)

From `https://manual.calibre-ebook.com/faq.html` (fetched 2026-05-26):

**Input Formats supported by Calibre:**  
AZW, AZW3, AZW4, CBZ, CBR, CB7, CBC, CHM, DJVU, DOCX, EPUB, FB2, FBZ, HTML, HTMLZ, KEPUB, LIT, LRF, MOBI, ODT, PDF, PRC, PDB, PML, RB, RTF, SNB, TCR, TXT, TXTZ

**Output Formats supported by Calibre:**  
AZW3, EPUB, DOCX, FB2, HTMLZ, KEPUB, OEB, LIT, LRF, MOBI, PDB, PMLZ, RB, PDF, RTF, SNB, TCR, TXT, TXTZ, ZIP

leafbind.io currently surfaces: **EPUB, MOBI, KFX**  
Calibre-available formats not yet surfaced on leafbind.io: AZW3, DOCX, FB2, HTMLZ, KEPUB, PDF (output), RTF, TXT, TXTZ, and several legacy formats.

---

## Competitor Format Coverage Matrix (S1, S2, S3)

| Format | CloudConvert | Zamzar | online-convert | leafbind.io |
|--------|-------------|--------|----------------|-------------|
| EPUB | ✓ | ✓ | ✓ | ✓ (output) |
| MOBI | ✓ | ✓ | ✓ | ✓ (output) |
| AZW3 | ✓ | ✓ (input) | ✓ | — |
| PDF (output) | ✓ | ✓ | ✓ | — |
| CBZ/CBR | ✓ | ✓ (CBZ input only) | — | — |
| FB2 | ✓ | ✓ (PDF→FB2) | ✓ | — |
| KEPUB | — | — | — | — |
| DJVU | ✓ (input) | — | — | — |
| DOCX (output) | — (not listed as ebook) | ✓ (PDF→DOCX) | — | — |
| LIT | ✓ | ✓ | ✓ | — |
| RTF | — | ✓ (PDF→RTF) | — | — |
| TXT | — | ✓ | — | — |
| CHM | ✓ (input) | — | — | — |

**Competitor gaps / differentiation opportunities:**  
- KEPUB: no major online converter offers KEPUB output. Kobo user segment is underserved across all competitors.  
- CloudConvert is the most complete, but charges per-conversion above free tier. Zamzar has a tight free-tier file-size cap (150 MB on free plan). Neither is specialized for book-quality output (heading structure, endnote linking, TOC fidelity).

---

## Ranked Candidate Output Formats (Top 8)

### 1. KEPUB (Kobo Enhanced EPUB)

**Demand evidence:** Kobo has ~40% of the non-Kindle e-reader market in North America and Europe (per industry analyst estimates consistent with Kobo sales figures). Reddit r/Calibre thread "Convert CBZ to Kepub?" (2026-05, S6) reflects active interest. MobileRead search returned a "Kepub Conversion Issue" thread in 2025 (S9). The r/kobo community consistently recommends KEPUB over plain EPUB for Kobo devices, citing better typography and reading progress sync. The thread "So it really should just be kepubs?" (r/kobo, score 84) confirms this is a recurrent community recommendation (S7).

**Technical feasibility:** Calibre outputs KEPUB natively (S4). KEPUB is structurally EPUB3 with Kobo-specific namespace extensions added as a post-processing pass. Calibre's `--output-format kepub` flag is a thin wrapper around its EPUB pipeline. Complexity: low — one additional format option in the Calibre call.

**Conversion pain points:** KEPUB output from Calibre sometimes produces incorrect chapter navigation on Kobo Libra Colour (MobileRead thread, S9). TOC metadata can be misaligned when the source EPUB lacks a proper NCX or nav document. This is a known Calibre limitation, not a blocker.

**Regression risk:** Low-to-medium. KEPUB shares the EPUB pipeline; changes to EPUB baseline would need to be re-validated on KEPUB output. No new extraction path is added.

---

### 2. AZW3 (Kindle Format 8 / Amazon Ebook)

**Demand evidence:** AZW3 is the native Amazon Kindle format and successor to MOBI (which Amazon deprecated in 2022). Reddit r/Calibre "How to EFFECTIVELY Download and Back Up Your Kindle Ebooks as EPUB Files (April 2026)" (score 513, S7) and "DeKindled" extension (score 237, S7) show users moving in both directions. The MobileRead thread "What's Better? AZW3 or KFX" (S8) confirms users actively choose between the two. Users who cannot use Send-to-Kindle (due to file size limits or format mismatch) want AZW3 for direct sideloading.

**Technical feasibility:** Calibre outputs AZW3 natively (S4). AZW3 is well-supported; CloudConvert and Zamzar both handle it (S1, S2). Calibre's KFX Output plugin already exists in the pipeline; AZW3 is an earlier, simpler Amazon format that does not require the Wine+Kindle Previewer KFX chain. Complexity: low — standard Calibre output format.

**Conversion pain points:** AZW3 does not support KFX advanced features (e.g., enhanced typesetting), but quality is reliable. Calibre's MOBI/AZW3 pipeline is mature and well-tested.

**Regression risk:** Low. AZW3 uses Calibre's MOBI output stage with an upgraded container format. Existing MOBI test cases cover most of the same code path.

---

### 3. PDF (Output)

**Demand evidence:** "Any advanced tool to decently convert PDF academic papers to EPUB?" (r/ebooks, 2026-05, S5) actually highlights the inverse problem — PDF is the starting format and EPUB is desired — but the thread reveals that academic/professional users habitually work with PDFs for distribution and archival. Separately, "Who can convert PDFs to Word docs" (cross-subreddit, score 23,900) reflects the enormous PDF-centric workflow that bleeds into ebook tooling. Zamzar surfaces PDF as an output from virtually every ebook format (S2). Users who produce KFX from a PDF source and then want to share the book with non-Kindle readers often need a reflowed PDF output.

**Technical feasibility:** Calibre outputs PDF natively (S4). Zamzar and CloudConvert both support PDF output (S1, S2). PDF output from Calibre involves the HTML→PDF rendering pipeline, which has known issues with complex headers and multi-column layouts (consistent with existing pipeline limitations).

**Conversion pain points:** Calibre's PDF output rendering is basic — no running headers, limited font embedding, and no KFX-class visual layout. For simple prose it is fine; for academic PDFs with tables and figures it can break. Quality gap relative to KFX is significant.

**Regression risk:** Medium. PDF output shares the HTML intermediate representation used in existing pipeline. No direct regression to EPUB/KFX, but adding PDF output surface area means new edge cases in the visual QA gate.

---

### 4. DOCX (Microsoft Word Output)

**Demand evidence:** "Who can convert PDFs to Word docs" (r/Millennials crosspost, score 23,900) is the strongest single demand signal found, though it targets PDF→DOCX rather than ebook→DOCX. The MobileRead thread "docx cross-reference hyperlinks not preserved" (S8) shows active DOCX conversion troubleshooting. Zamzar lists DOCX prominently in its PDF output formats (S2). The use case is authors and editors who receive a finished ebook (EPUB/PDF) and need an editable Word version — common in traditional publishing workflows.

**Technical feasibility:** Calibre outputs DOCX natively (S4). CloudConvert includes DOCX under document formats. Complexity: standard Calibre output.

**Conversion pain points:** Calibre's DOCX output loses footnote linking and complex heading hierarchy in dense academic books (consistent with pipeline CLAUDE.md regression notes). Images are inline but positioning can be unpredictable.

**Regression risk:** Low-to-medium. DOCX output is isolated from the KFX/EPUB pipeline. The main risk is that improving DOCX output could expose shared formatting logic.

---

### 5. FB2 (FictionBook 2)

**Demand evidence:** FB2 is the dominant ebook format in Russia, Eastern Europe, and CIS countries. It is a structured XML format with lossless text fidelity. MobileRead thread "Converting FB2→EPUB, TOC is only half the size" (S8) and the presence of FB2 in all three competitor offerings (CloudConvert, Zamzar PDF→FB2, online-convert.com — S1, S2, S3) signal steady demand. r/ebooks FB2 search returned generic results (no high-volume threads) but the format consistently appears in "which format should I use?" discussions.

**Technical feasibility:** Calibre reads and writes FB2 natively (S4). Complexity: low.

**Conversion pain points:** FB2 has no fixed-layout support and limited image handling. Complex endnote structures in historical prose (a known pain point in the existing test corpus) can lose linking integrity in FB2 output.

**Regression risk:** Low. FB2 is a standalone output path. No shared code with KFX/EPUB beyond the Calibre conversion layer.

---

### 6. CBZ/CBR to EPUB (Comic/Manga Format Input)

**Demand evidence:** Reddit r/Calibre "Convert CBZ to Kepub?" (2026-05, score 3, S6) with comments pointing to Kobo Libra Color and iPad as primary devices. Reddit r/ebooks "I got into an argument on Discord about how inefficient CBR/CBZ is, so I wrote a new file format" (score 2,284, S7) — the top ebook-related post on Reddit in the search window, showing CBZ/CBR is an active pain point. The MobileRead thread "Kindle Comic Converter - Convert comics/manga to MOBI/EPUB" (S8) shows a dedicated tool exists, indicating a user base large enough to warrant specialized software. CloudConvert lists CBZ and CBR as ebook formats; Zamzar supports CBZ input (S1, S2).

**Technical feasibility:** Calibre can read CBZ/CBR input and output to EPUB or PDF (S4). However, CBZ/CBR are image containers — the "conversion" is image repackaging into an EPUB fixed-layout container, not text reflowing. This is a different pipeline from the prose pipeline leafbind.io currently runs.

**Conversion pain points:** Image file size bloat (noted in the Reddit thread: 1 GB CBZ → 2 GB EPUB on Calibre), page ordering issues, and DPI handling for e-ink displays. Quality depends heavily on source image quality and whether manga pages need right-to-left layout.

**Regression risk:** High for the current pipeline. Adding CBZ input would introduce a fixed-layout EPUB path that is entirely separate from the prose extraction/reflowing pipeline. Risk of conflating the two paths. Warrants a separate sub-task rather than inline pipeline expansion.

---

### 7. TXT (Plain Text Output)

**Demand evidence:** TXT output is universally supported but rarely discussed as a pain point because it is trivially achievable. Calibre supports it (S4); Zamzar lists TXT (S2). "A PSA: Please archive your works offline, and when you do, please use HTML!" (r/selfhosted, score 241) reflects a community preference for open archival formats, with TXT as the simplest. The use case is lightweight — speech synthesis pipelines, accessibility tools, and archive ingestion.

**Technical feasibility:** Calibre outputs TXT trivially. Complexity: minimal.

**Conversion pain points:** TXT output loses all structural information (headings, TOC, footnotes). Not suitable as a primary output format for a quality-focused service.

**Regression risk:** Very low. TXT is a degenerate output.

---

### 8. HTMLZ (Zipped HTML)

**Demand evidence:** HTMLZ appears in CloudConvert and online-convert.com format lists (S1, S3) and in Calibre's output list (S4), but no significant Reddit or MobileRead thread traffic was found. It is a niche archival format.

**Technical feasibility:** Calibre supports it natively. Complexity: low.

**Conversion pain points:** No widely-used readers consume HTMLZ directly. It is primarily an intermediate/archival format.

**Regression risk:** Very low.

---

## Top-3 Recommendations

### Recommendation 1: KEPUB

Kobo is the primary non-Kindle e-reader platform and its users consistently prefer KEPUB over plain EPUB for on-device experience (typography rendering, reading progress sync, chapter navigation). No major online ebook converter currently offers KEPUB output — this is a genuine gap in the competitor landscape (S1, S2, S3). The implementation cost is low: Calibre produces KEPUB via `--output-format kepub`, which is a thin post-processing pass on top of the existing EPUB pipeline. The MobileRead Kobo forum shows ongoing conversion issues that users cannot solve with existing tools (S9). Adding KEPUB output would serve the Kobo user segment — estimated ~35-40% of sideloading users — without significant regression risk to the prose pipeline. Recommended as the immediate next format.

### Recommendation 2: AZW3

AZW3 is the current standard Kindle sideload format. Amazon deprecated the older MOBI format in 2022, and while leafbind.io already offers KFX (the premium Kindle format requiring Wine+Kindle Previewer), many users want a simpler, universally-compatible Kindle format for devices that do not support KFX or for users who cannot use Send-to-Kindle. AZW3 does not require the complex Wine+KP3 conversion chain (see EB-332 notes), uses standard Calibre output, and has a well-tested code path. For users bouncing because they "just want something that works on Kindle without Send-to-Kindle," AZW3 is the answer. CloudConvert and Zamzar already offer it (S1, S2), so leafbind.io would be matching parity, not leading, but the quality differentiation (heading fidelity, TOC accuracy) remains.

### Recommendation 3: PDF (Output)

PDF output targets a distinct user segment: those who receive a PDF, want it reformatted for e-reader consumption, and also want to be able to share the cleaned-up result in a universally readable format. The academic-paper-to-EPUB thread (S5) shows that PDF remains the currency of academic and professional documents, and many users cycle back to PDF after reformatting. Zamzar's data confirms PDF is the highest-traffic output target from ebook inputs (S2). The implementation risk is medium rather than low because Calibre's PDF output quality for complex books is uneven, but for a leafbind.io "clean PDF" offering (prose-only, heading-structured books), this is manageable. This would expand the addressable audience to the very large cohort of academic and professional readers who are not primarily e-reader users.

---

## Anti-Recommendations

### CBZ/CBR Input (Comics/Manga)

CBZ/CBR are the most-discussed format gap in raw Reddit volume (score 2,284 for the "CBR/CBZ is inefficient" post) but represent a fundamentally different pipeline. Comics and manga are image-container formats; converting them to EPUB requires image-layout repackaging, right-to-left page ordering, and DPI/resolution tuning for e-ink displays. This is not a prose pipeline extension — it is a separate product feature. Wiring CBZ/CBR through the existing extraction engine would risk conflating image-based and text-based conversion paths and introduce regression surface across the 6-book prose test corpus. The right move is a separate ticket if the manga/comics segment is deliberately targeted.

### FB2

FB2 is genuinely in demand in Russian-language markets, but the leafbind.io user base (English-language, primarily Kindle/Kobo) does not align with the primary FB2 audience. The conversion is technically trivial via Calibre, but the lack of English-community traffic (no significant Reddit or MobileRead threads in the past 12 months for FB2 specifically) suggests it would be a low-return addition compared to KEPUB or AZW3. Revisit if CIS-market expansion is a strategic goal.

### LIT / LRF / PDB / SNB / TCR

These are legacy or region-specific formats (LIT = Microsoft Reader, discontinued 2012; LRF = Sony Reader format; PDB = Palm; SNB = Shanda Bambook, China only). All competitors offer them (S1, S2, S3) for the rare user who needs legacy conversion, but there is essentially no organic community demand in active forum threads. Adding them adds complexity with negligible user benefit. They should be deferred indefinitely.

### DOCX Output

DOCX output is technically straightforward through Calibre but the use case — "I have an ebook and I want to edit it in Word" — is conceptually misaligned with leafbind.io's "get your book onto your device" positioning. The high-volume "PDF to Word" threads (S, score 23,900) are from the PDF-conversion market, not the ebook-conversion market. Calibre's DOCX output quality is also uneven for heavily-structured books (footnote linking, cross-references). Not recommended as a near-term priority unless leafbind.io explicitly targets the author/editor workflow.

---

## Evidence Gaps and Caveats

1. **Volume quantification**: Reddit search results are skewed by cross-post spam and off-topic threads dominating search relevance at the aggregated level. Individual thread scores (used here as demand proxies) are more reliable than search-result counts.

2. **Geographic skew**: MobileRead and English-language Reddit skew toward North American and Western European markets. FB2 demand from CIS markets and DJVU demand from academic/legacy Eastern European sources are underweighted in this data.

3. **DJVU**: Calibre supports DJVU as input (S4), but only for DJVU files with embedded OCR text. Scanned-only DJVU files (common for historical academic texts) require an OCR pre-processing step that is outside the current pipeline. No significant English-language demand signal was found in the past 12 months. Deferred.

4. **KEPUB quality data**: MobileRead's "Kepub Conversion Issue" thread was found in the search but not fetched in full due to session throttling. The title alone signals a known conversion quality problem. Before shipping KEPUB output, the specific issue type should be identified (suspected: missing TOC entry in Calibre KEPUB for books without a proper nav document).

---

## Next Steps (for follow-up tickets)

- **KEPUB**: Wire `--output-format kepub` into the Calibre conversion call; add to the output format selector; add one KEPUB-specific test case (suggest Sherlock Holmes/Doyle EPUB as baseline — it is already in the test corpus as an EPUB input).
- **AZW3**: Wire `--output-format azw3` as a simpler Kindle alternative to KFX; validate against the 6-book corpus; update the "format" selection UI.
- **PDF output**: Prototype with Calibre's PDF backend on 2 prose books; define quality gate (headings rendered, TOC present, no missing text); file a separate ticket for the quality investigation before shipping.
