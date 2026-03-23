# Email-to-Kindle Delivery — Design Spec

**Date:** 2026-03-23
**Branch:** master (new feature)
**Status:** Approved design, pending implementation

## Overview

Extend `Send-ToKindle` with an `-Email` delivery path that sends converted ebooks to a Kindle device via Amazon's Send-to-Kindle email service. This complements the existing USB/MTP path with cloud-synced delivery supporting EPUB and PDF formats.

The feature adds EPUB generation to `Convert-ToKindle`, format-aware compression and splitting for files exceeding Amazon's 50MB email limit, and SMTP-based delivery via Python's stdlib.

## Constraints

- **Supported email formats (Amazon, current):** PDF, EPUB, DOC, DOCX, TXT, RTF, HTM, HTML, PNG, GIF, JPG, JPEG, BMP. KFX is **not** accepted via email. MOBI/PRC/AZW support was discontinued by Amazon in 2022 for new uploads — treated as unsupported in this implementation.
- **Size limit:** 50MB per email (Amazon's limit). Gmail imposes a 25MB attachment limit but Amazon accepts ZIP files and auto-unpacks them.
- **200MB web app limit** is not automatable (requires browser auth, no public API, ToS concerns). Not pursued.
- **Zero new Python dependencies.** SMTP uses `smtplib` + `email.mime` from stdlib. Compression uses PyMuPDF (already installed). Ghostscript is an optional upgrade detected at runtime.

## Config Schema

Expand the existing `kindle_delivery` block in `config/settings.json`:

```json
"kindle_delivery": {
    "enabled": true,
    "calibre_library": "C:\\Users\\Joe\\Calibre Library",
    "auto_send": false,
    "delete_from_library_after_send": true,
    "email": {
        "kindle_address": "",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_app_password_env": "EBOOK_SMTP_PASSWORD",
        "convert_subject": true,
        "max_email_size_mb": 50
    }
}
```

### Field definitions

| Field | Purpose |
|---|---|
| `kindle_address` | The Kindle's `@kindle.com` Send-to-Kindle email address |
| `smtp_server` | SMTP server hostname (default: Gmail) |
| `smtp_port` | SMTP port (587 for STARTTLS, 465 for SSL) |
| `smtp_user` | Sender's email address. **Must** be on Amazon's Approved Personal Document E-mail List |
| `smtp_app_password_env` | Name of the environment variable holding the SMTP password. Default: `EBOOK_SMTP_PASSWORD`. Code reads `$env:EBOOK_SMTP_PASSWORD` at runtime. No plaintext fallback in config — the config file is committed to Git. If the env var is not set, the email path fails with a clear error message directing the user to set it |
| `convert_subject` | When true, adds "Convert" to the email subject for EPUB/DOCX (tells Amazon to convert to Kindle format for better reading experience). **Behavioral note:** this setting is always suppressed for PDF regardless of its value, since PDFs are better kept as-is on Scribe for annotation |
| `max_email_size_mb` | Ceiling for the size auto-routing logic. Default: 50. This is Amazon's limit; the Gmail 25MB attachment limit is handled separately by the ZIP step for PDF files |

### Ghostscript (optional)

Add `paths.ghostscript` to the paths block in settings.json. If absent, the code probes for `gswin64c` / `gs` on PATH. If not found, PDF compression falls back to PyMuPDF.

## Command Interface

### Send-ToKindle — new parameters

```powershell
# Existing USB path (unchanged)
Send-ToKindle -InputFile "book.kfx"

# Email path — sends EPUB by default
Send-ToKindle -InputFile "book.epub" -Email

# Email as PDF (for Scribe annotation)
Send-ToKindle -InputFile "book.pdf" -Email -EmailFormat PDF

# Compress before emailing
Send-ToKindle -InputFile "book.pdf" -Email -Compress

# Split large files into parts
Send-ToKindle -InputFile "book.pdf" -Email -SplitMaxMB 45
```

| Parameter | Type | Description |
|---|---|---|
| `-Email` | switch | Send via email instead of USB |
| `-EmailFormat` | ValidateSet('EPUB','PDF') | Format to email. Default: EPUB |
| `-Compress` | switch | Compress the file before sending |
| `-SplitMaxMB` | int | Split files exceeding this size into parts. Overrides `max_email_size_mb` from config |

`-Email` and USB delivery are mutually exclusive on `Send-ToKindle` (single file, single delivery method).

**Parameter validation:** `-Compress` and `-SplitMaxMB` require `-Email`. If passed without `-Email`, the function warns *"Ignoring -Compress/-SplitMaxMB: only applicable with -Email delivery"* and proceeds with USB delivery.

**Unsupported formats for email:** If the input file is `.azw3`, `.mobi`, or any format not in Amazon's supported list, and `-Email` is set, the function errors with *"Format .azw3 is not supported for email delivery. Supported formats: EPUB, PDF. Use -EmailFormat to specify, or omit -Email for USB delivery."*

**WhatIf behavior:** When `-Email` is active, the `ShouldProcess` confirmation message reads *"Email 'BookName.epub' to Kindle via SMTP"* instead of the USB message *"Send to Kindle device"*.

### Invoke-EbookPipeline — new switch

```powershell
Invoke-EbookPipeline -EmailToKindle           # email each book after conversion
Invoke-EbookPipeline -SendToKindle            # USB (existing)
Invoke-EbookPipeline -SendToKindle -EmailToKindle  # both — USB the KFX, email the EPUB
```

`-SendToKindle` and `-EmailToKindle` can coexist. USB sends the KFX; email sends the EPUB. Both results tracked independently in the per-book `$resultLog`:

The existing `$resultLog` PSCustomObject (`File, TTS, Kindle, MP3, Status, Time`) gains two new fields: `DeviceSend` and `EmailSend`, each showing 'OK', 'FAILED', 'skipped', or 'n/a'. The final summary table displays these alongside existing columns.

### Convert-ToKindle — EPUB generation

New parameter:

| Parameter | Type | Description |
|---|---|---|
| `-ProduceEpub` | switch | After KFX conversion, also produce an EPUB from the intermediate HTML |

**Placement constraint:** The EPUB generation step must execute **inside the existing `try` block** of `Convert-ToKindle`, after the Calibre KFX conversion succeeds but **before** the `return $true` statement. The `finally` block deletes `$tempDir`, so the HTML intermediate is gone after that point.

When `-ProduceEpub` is active and KFX conversion succeeds:

1. Check if the intermediate HTML file exists in `$tempDir` (the `$tempOutput` or `$htmlFile` variable from earlier in the function)
2. Derive the EPUB filename from the same `$outName` variable used for the KFX output (e.g., if KFX is `Oil Kings - Cooper, Andrew Scott.kfx`, EPUB is `Oil Kings - Cooper, Andrew Scott.epub`). This ensures consistent naming and enables the fallback lookup in `Send-ToKindle`
3. Run Calibre: `ebook-convert $htmlFile $epubFile` with the same `$tocArgs`, metadata flags, and `--cover` arguments already built in `$argString` for the KFX conversion
4. Save the EPUB to `output\kindle\Oil Kings - Cooper, Andrew Scott.epub`
5. Copy the intermediate HTML to `output\kindle\.intermediates\Oil Kings - Cooper, Andrew Scott_kindle.html` (create `.intermediates\` directory if it doesn't exist). This allows future `Send-ToKindle -Email` calls to regenerate the EPUB without re-running the full extraction pipeline
6. EPUB generation failure is non-blocking — log a warning, but still return `$true` since the KFX succeeded

`Convert-ToKindle` continues to return `$true`/`$false` (boolean, not a path). The pipeline locates output files by searching the output directory.

`Invoke-EbookPipeline` passes `-ProduceEpub` to `Convert-ToKindle` when `-EmailToKindle` is active.

### Pipeline EPUB file location

`Convert-ToKindle` returns a boolean. The pipeline locates output files by stem-matching in the kindle output directory (same pattern used for KFX at line ~2416 of the psm1):

```powershell
# After Convert-ToKindle returns $true:
$stem = [System.IO.Path]::GetFileNameWithoutExtension($workCopy)
$epubFile = Get-ChildItem -Path $kindleDir -Filter "$stem*.epub" -File |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($epubFile -and $emailActive) {
    Send-ToKindle -InputFile $epubFile.FullName -Email
}
```

### Standalone Send-ToKindle -Email on a pre-built KFX

When called directly with a KFX file and `-Email -EmailFormat EPUB`:

1. Derive the expected EPUB name from the KFX filename stem (same stem + `.epub`)
2. Check for a matching EPUB in the same directory
3. If found, email that
4. If not found, check for matching HTML intermediate in `.intermediates\` (same stem + `_kindle.html`)
5. If found, generate EPUB from it via Calibre, then email
6. If neither found, warn: *"No EPUB or intermediate HTML available for 'BookName'. For best quality, re-run the full pipeline with -EmailToKindle. Attempting KFX→EPUB conversion via Calibre (quality may vary)."* Then try `ebook-convert book.kfx book.epub` as a lossy fallback.

This fallback path is documented as unreliable because KFX is Amazon's compiled format and Calibre's KFX→EPUB conversion depends on the KFX Input plugin and often produces lossy results.

When called with an EPUB file directly (`Send-ToKindle -InputFile "book.epub" -Email`), skip all conversion — email the EPUB as-is.

When called with a PDF file and `-Email -EmailFormat PDF`, skip all conversion — email the PDF as-is (with compression/splitting if requested).

## Format Routing for Email

### EPUB path (default)

EPUB is the preferred email format. Amazon converts it to Kindle format server-side, giving the best reading experience with adjustable fonts and layout.

### PDF path (`-EmailFormat PDF`)

For Scribe annotation workflows. The source PDF is sent as-is. The `convert_subject` flag is always suppressed for PDF regardless of config, since PDFs should be kept as native PDF on the Scribe.

### KFX is never emailed

KFX is excluded from the email format priority entirely. Amazon does not accept KFX uploads. The pipeline converts to EPUB for the email path.

## Size Auto-Routing

Format-aware logic applied after format selection, before sending. All thresholds derive from `max_email_size_mb` config (default 50MB). The 25MB Gmail attachment limit is a separate, hardcoded threshold that triggers the ZIP step for uncompressed formats — if the user changes SMTP servers, this threshold may need adjusting via a future config field, but Gmail is the primary target.

### EPUB path (already ZIP-compressed internally)

```
≤ max_email_size_mb  → email directly (no ZIP — EPUB is already compressed)
> max_email_size_mb  → re-generate EPUB with Calibre image compression:
                       ebook-convert input.epub output.epub --compress-images --jpeg-quality 60
                       retry size check
still > max_email_size_mb → split by chapter ranges into parts, email each
```

Note: An EPUB over 50MB from this pipeline is rare since text extraction strips most images. This is a defensive measure.

### PDF path (compressible)

```
≤ 25MB              → email directly
25MB-max_email_size  → ZIP the PDF, email the ZIP (Amazon auto-unpacks)
ZIP > max_email_size → compress via Ghostscript (if available) or PyMuPDF:
                       Ghostscript: gs -sDEVICE=pdfwrite -dPDFSETTINGS=/ebook
                                    -dDownsampleColorImages=true -dColorImageResolution=150
                       (Note: forward-slash flags are correct Ghostscript syntax even on Windows)
                       PyMuPDF: doc.save(deflate=True, garbage=4, clean=True)
                       retry size check
still > max_email_size → split by page ranges, email each part
```

### Splitting guardrails

- Minimum 10 pages per part
- Maximum 5 parts per book (effective max book size for email: 5 x max_email_size_mb = 250MB default)
- If the file would need more than 5 parts: abort with *"File too large for email delivery (would need X parts). Use Send-ToKindle without -Email for USB delivery."*
- Part naming: `BookName_part1.pdf`, `BookName_part2.pdf`, etc.
- Part subjects: `"The Oil Kings (Part 1 of 3)"`

## Email Sending Implementation

### Script: `tools/email_to_kindle.py`

A single Python script handling the full email pipeline: compression, ZIP, splitting, and SMTP send. Called from PowerShell via standard Python (not `calibre-debug`).

```
python tools/email_to_kindle.py
    --file "book.epub"
    --kindle-address "...@kindle.com"
    --smtp-server smtp.gmail.com
    --smtp-port 587
    --smtp-user "user@gmail.com"
    --book-title "The Oil Kings"
    [--convert-subject]
    [--compress]
    [--split-max-mb 50]
    [--ghostscript-path "path/to/gs"]
```

**Password handling:** The script reads `os.environ['EBOOK_SMTP_PASSWORD']` directly — no `--password` CLI flag. This is consistent with how `ANTHROPIC_API_KEY` is handled in `pdf_to_balabolka.py`. The env var name is passed from the PowerShell side via `--password-env-var` flag (defaults to `EBOOK_SMTP_PASSWORD`) so the config's `smtp_app_password_env` field is respected. Environment variables are inherited by child processes on Windows by default.

Outputs JSON on stdout for PowerShell to parse (same pattern as `send_to_kindle.py`).

Compression logic lives inside this script (not a separate file). When `--compress` is passed, the script handles the compress-then-send pipeline internally. PowerShell calls one script, Python handles orchestration — keeps the logic in one language.

### Subject line logic

| Scenario | Subject |
|---|---|
| EPUB/DOCX + `convert_subject: true` | `"Convert: The Oil Kings"` |
| PDF (always, regardless of config) | `"The Oil Kings"` |
| `convert_subject: false` | `"The Oil Kings"` |
| Split parts | `"The Oil Kings (Part 1 of 3)"` |

### SMTP error handling

One retry after 5 seconds on transient failures, then fail with a mapped error message.

| SMTP Code | User Message |
|---|---|
| 535 | `"SMTP authentication failed — check EBOOK_SMTP_PASSWORD env var and ensure it's a Gmail App Password, not your regular password"` |
| 550 | `"Amazon rejected the email — verify your sender address is on Amazon's Approved Personal Document E-mail List (amazon.com/manageyourkindle)"` |
| 552 | `"Attachment exceeds server limit — file size: X MB (possible size-check bug)"` |
| Timeout | `"SMTP connection timed out — check network and smtp_server/smtp_port in settings.json"` |
| SSL error | `"TLS handshake failed — check smtp_port (587 for STARTTLS, 465 for SSL)"` |
| Other | `"SMTP error [code]: [message]"` with full details logged |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Config/argument error |
| 2 | Auth failure |
| 3 | Recipient rejected |
| 4 | Size error |
| 5 | Network/timeout error |
| 6 | Unknown error |

## Initialize-EbookAutomation Updates

When `kindle_delivery.email.smtp_user` is non-empty, print:

```
[Optional] Send-to-Kindle email configured
  + SMTP server: smtp.gmail.com:587
  + Sender: user@gmail.com
  + Kindle: ...@kindle.com
  ! REMINDER: Your sender address (user@gmail.com) must be on Amazon's
    Approved Personal Document E-mail List. Configure at:
    amazon.com/manageyourkindle → Preferences → Personal Document Settings
  + Ghostscript: [detected at C:\path\gs.exe / not found (PDF compression will use PyMuPDF)]
```

## Files Summary

| File | Change |
|---|---|
| `tools/email_to_kindle.py` | **NEW** — SMTP email sender with compression, ZIP, splitting |
| `module/EbookAutomation.psm1` | **MODIFY** — `Send-ToKindle`: add `-Email`, `-EmailFormat`, `-Compress`, `-SplitMaxMB` params and email delivery path; update `ShouldProcess` message for email. `Convert-ToKindle`: add `-ProduceEpub` param and EPUB generation step (inside `try` block, before `return $true`). `Invoke-EbookPipeline`: add `-EmailToKindle` switch; add `DeviceSend`/`EmailSend` fields to `$resultLog`. `Initialize-EbookAutomation`: add email config checks and approved sender reminder |
| `module/EbookAutomation.psd1` | No changes needed — parameter additions don't require manifest updates, only new function exports do |
| `config/settings.json` | **MODIFY** — expand `kindle_delivery.email` block, add optional `paths.ghostscript` |
| `CLAUDE.md` | **MODIFY** — document email delivery config, `EBOOK_SMTP_PASSWORD` env var, EPUB intermediate path in `.intermediates\`, supported email formats |

## Design Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| EPUB generation approach | Option A: separate Calibre run from intermediate HTML | Avoids changing the KFX pipeline (Option B risk), provides better quality than raw PDF (Option C limitation) |
| Compression dependency | PyMuPDF default, Ghostscript optional upgrade | Works immediately with no new installs; Ghostscript adds value mainly for scanned PDFs on the raw PDF email path |
| Compression orchestration | All inside `email_to_kindle.py` | Keeps orchestration in one language; PowerShell calls one script with `--compress` |
| EPUB vs KFX for email | Always EPUB | KFX is not accepted by Amazon's email service |
| Convert subject for PDF | Always suppressed | PDFs are better kept as native format on Scribe for annotation |
| USB + Email coexistence | Allowed on pipeline, mutually exclusive on Send-ToKindle | Pipeline may want both (KFX locally + EPUB in cloud); single-file delivery is one-or-the-other |
| KFX→EPUB fallback | Warn and attempt, document as unreliable | KFX is a compiled format; Calibre's reverse conversion is lossy. Preferred path is HTML→EPUB |
| Password storage | Environment variable only, no plaintext config fallback | Config file is committed to Git; env var follows existing `ANTHROPIC_API_KEY` pattern. Removed config fallback to prevent accidental credential commits |
| ZIP step | Format-aware: PDF yes (25-50MB), EPUB no | EPUB is already ZIP-compressed internally; zipping it again provides negligible benefit. ZIP helps PDFs bridge the Gmail 25MB → Amazon 50MB gap |
| Split limits | Min 10 pages/part, max 5 parts | Prevents pathological splitting; effective max 250MB for email delivery; beyond that falls back to USB recommendation |
| MOBI/PRC/AZW for email | Rejected with error | Amazon discontinued these formats for Send-to-Kindle in 2022. Intentionally conservative |
| -Compress/-SplitMaxMB without -Email | Warn and ignore | These parameters only make sense for the email path; silently proceeding with USB avoids confusing the user |
