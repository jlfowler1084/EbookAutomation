# EB-86: Diagnose Coulter PDF Extraction Failure

## Session Name
Coulter Extraction Diagnosis

## Claude Code Model
Opus

## Jira
EB-86 — Investigate Coulter PDF extraction failure — text extraction returns empty

## Context

In batch_20260406_114131 (100-book Quick mode, HTML-only), this book was the **only FAIL** out of 100:

```
Coulter, Fred R. - Occult Holidays Or God's Holy Days - Which - Hour of the Time (2012) - libgen.li.pdf
```

- Status reason: "Text extraction failed"
- Processing time: 601s (suspiciously close to 600s default timeout)
- The PDF opens and reads fine in a PDF viewer — it is NOT corrupt

## Investigation Steps

### Phase 1: Gather Facts

1. **Find the file** — it should be in `F:\Books\`. Confirm exact path and file size.

2. **Check page count and basic PDF metadata:**
   ```powershell
   python tools/pdf_to_balabolka.py "<path_to_coulter_pdf>" --preflight-only
   ```
   If `--preflight-only` isn't a flag, use `tools/preflight_analysis.py` directly:
   ```powershell
   python tools/preflight_analysis.py "<path_to_coulter_pdf>"
   ```

3. **Run classify_source.py** to see what the pipeline thinks this PDF is:
   ```powershell
   python tools/classify_source.py "<path_to_coulter_pdf>"
   ```
   Record: source_type classification, chars_per_page, has_text_layer, any other signals.

### Phase 2: Reproduce the Failure

4. **Run the full extraction with verbose logging:**
   ```powershell
   python tools/pdf_to_balabolka.py "<path_to_coulter_pdf>" --html-extraction --verbose 2>&1 | Tee-Object -FilePath "F:\Projects\EbookAutomation\data\debug\coulter_verbose.log"
   ```
   Create `data\debug\` if it doesn't exist.

5. **Check the log for:**
   - Which extraction path was selected
   - Where processing stalls or errors
   - Whether the 601s runtime is a timeout (look for `TimeoutExpired` or similar)
   - Whether text was extracted but then discarded by a downstream check
   - Any encoding errors or empty-text warnings

### Phase 3: Try Alternate Paths

6. **Try pdfminer path (no --html-extraction):**
   ```powershell
   python tools/pdf_to_balabolka.py "<path_to_coulter_pdf>" --verbose 2>&1 | Tee-Object -FilePath "F:\Projects\EbookAutomation\data\debug\coulter_pdfminer.log"
   ```

7. **Try OCR path:**
   ```powershell
   python tools/pdf_to_balabolka.py "<path_to_coulter_pdf>" --ocr --verbose 2>&1 | Tee-Object -FilePath "F:\Projects\EbookAutomation\data\debug\coulter_ocr.log"
   ```

### Phase 4: Diagnose and Fix

8. Based on findings, determine root cause. Likely scenarios:
   - **Timeout**: The 601s runtime ≈ 600s timeout. If so, check if the file is unusually large or if a specific extraction step hangs. The fix may be increasing the timeout for this file size, or identifying the hung step.
   - **Empty extraction**: HTML extraction returns zero text. May need OCR fallback or a different extraction method. Check if `detect_pdf_type()` (from EB-83) should be routing this to OCR.
   - **Encoding issue**: pdfminer extracts text but it's garbled/empty after encoding checks. Related to EB-87.
   - **Structural**: Unusual PDF structure (e.g., all text in images, unusual font encoding, embedded forms) that causes the extractor to return empty.

9. **Apply the fix.** If it's a pipeline bug, fix it in the appropriate file. If it's a per-book issue, consider whether a `book_overrides` entry (EB-73) is appropriate.

10. **Verify the fix:**
    ```powershell
    python tools/pdf_to_balabolka.py "<path_to_coulter_pdf>" --html-extraction --verbose
    ```
    Confirm: non-empty output, chapters detected, no errors.

11. **Run the test suite** to confirm no regressions:
    ```powershell
    python tools/test_pipeline.py
    python tools/test_voice_tags.py
    ```
    Expected: 41/41 pipeline, 75/75 voice tags.

## Deliverables

- Root cause documented in a Jira comment on EB-86 (include the specific error, which path failed, why)
- Fix committed if it's a code change
- If fix is a per-book override, document that instead
- Test suite still green: 41/41 + 75/75

## Do NOT

- Skip straight to a fix without understanding the root cause
- Assume the issue without evidence — capture actual log output
- Modify batch_qa.py or test_pipeline.py — this is a diagnosis + extraction fix only
- Run a full batch — just this one book
