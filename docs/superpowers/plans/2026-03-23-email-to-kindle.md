# Email-to-Kindle Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add email-based delivery to `Send-ToKindle` so converted ebooks can be sent to a Kindle via Amazon's Send-to-Kindle email service, with format-aware compression, splitting, and EPUB generation.

**Architecture:** Extends the existing `Send-ToKindle` PowerShell function with an `-Email` switch that routes to a new `email_to_kindle.py` Python script for SMTP delivery. `Convert-ToKindle` gains a `-ProduceEpub` switch to generate EPUB alongside KFX from the same intermediate HTML. Compression and splitting are handled entirely in Python.

**Tech Stack:** PowerShell 5.1+, Python 3.8+ (smtplib, email.mime, zipfile — all stdlib), PyMuPDF (fitz — already installed), Calibre ebook-convert, optional Ghostscript for PDF compression.

**Spec:** `docs/superpowers/specs/2026-03-23-email-to-kindle-design.md`

**Branch:** `feature/email-to-kindle` (create from master before starting)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tools/email_to_kindle.py` | CREATE | SMTP sending, PDF compression (PyMuPDF/Ghostscript), ZIP wrapping, PDF splitting, JSON output |
| `module/EbookAutomation.psm1` | MODIFY | `Send-ToKindle`: add `-Email` params and email routing. `Convert-ToKindle`: add `-ProduceEpub` and EPUB generation. `Invoke-EbookPipeline`: add `-EmailToKindle`. `Initialize-EbookAutomation`: add email config checks |
| `config/settings.json` | MODIFY | Add `kindle_delivery.email` block, optional `paths.ghostscript` |
| `CLAUDE.md` | MODIFY | Document email delivery config, env var, formats, `.intermediates\` path |

---

## Task 1: Create feature branch and update config

**Files:**
- Modify: `config/settings.json`

- [ ] **Step 1: Create feature branch**

```bash
git checkout master
git pull origin master
git checkout -b feature/email-to-kindle
```

- [ ] **Step 2: Add email config block to settings.json**

Merge the `email` sub-object into the existing `kindle_delivery` block. Add `paths.ghostscript` as empty string.

In `config/settings.json`, change the `kindle_delivery` block to:

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

Also add to the `paths` block:

```json
"ghostscript": ""
```

- [ ] **Step 3: Verify JSON is valid**

```bash
python -c "import json; json.load(open('config/settings.json')); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add config/settings.json
git commit -m "feat: add kindle_delivery.email config schema and paths.ghostscript"
```

---

## Task 2: Create email_to_kindle.py — core SMTP sending

**Files:**
- Create: `tools/email_to_kindle.py`

This is the largest single file. Build it incrementally: first the argument parser and SMTP send, then compression, then splitting.

- [ ] **Step 1: Create email_to_kindle.py with argparse and basic SMTP send**

Create `tools/email_to_kindle.py`. The script must:

1. Parse args: `--file`, `--kindle-address`, `--smtp-server`, `--smtp-port`, `--smtp-user`, `--book-title`, `--convert-subject` (flag), `--compress` (flag), `--split-max-mb` (int), `--ghostscript-path` (str), `--password-env-var` (str, default `EBOOK_SMTP_PASSWORD`)
2. Read password from `os.environ[args.password_env_var]` — fail with exit code 2 and clear message if not set
3. Build MIME multipart email: attach the file, set subject per spec rules (Convert prefix for EPUB if `--convert-subject`, never for PDF)
4. Connect to SMTP with STARTTLS (port 587) or SSL (port 465), authenticate, send
5. On SMTP error: retry once after 5 seconds for transient failures. Map error codes to messages per spec table (535→auth, 550→recipient rejected, 552→size, timeout, SSL)
6. Output JSON to stdout: `{"success": true/false, "error": "...", "file": "...", "size_mb": ...}`
7. Exit codes per spec: 0=success, 1=config, 2=auth, 3=rejected, 4=size, 5=network, 6=unknown
8. UTF-8 stdout/stderr reconfiguration for Windows (same pattern as `pdf_to_balabolka.py`)
9. `if __name__ == '__main__': main()` guard

Key implementation details:
- Use `email.mime.multipart.MIMEMultipart`, `email.mime.base.MIMEBase`, `email.encoders.encode_base64`
- Subject line: if `--convert-subject` and file is not PDF → `"Convert: {title}"`; otherwise `"{title}"`
- SMTP connection: `smtplib.SMTP(server, port)` then `.starttls()` for port 587; `smtplib.SMTP_SSL(server, port)` for port 465
- Error mapping: catch `smtplib.SMTPAuthenticationError` (exit 2), `smtplib.SMTPRecipientsRefused` (exit 3), `smtplib.SMTPDataError` with code 552 (exit 4), `socket.timeout` / `ConnectionRefusedError` (exit 5), `ssl.SSLError` (exit 5)

- [ ] **Step 2: Test SMTP send manually**

Set up the env var and test with a small file:

```powershell
$env:EBOOK_SMTP_PASSWORD = "your-app-password"
python tools/email_to_kindle.py --file "output\kindle\SomeSmallBook.epub" --kindle-address "your-kindle-address@kindle.com" --smtp-server smtp.gmail.com --smtp-port 587 --smtp-user "your-email@gmail.com" --book-title "Test Book" --convert-subject
```

Expected: JSON output with `"success": true`. Check Kindle for delivery.

- [ ] **Step 3: Commit**

```bash
git add tools/email_to_kindle.py
git commit -m "feat: email_to_kindle.py — core SMTP sending with error mapping"
```

---

## Task 3: Add compression and ZIP to email_to_kindle.py

**Files:**
- Modify: `tools/email_to_kindle.py`

- [ ] **Step 1: Add PDF compression function**

Add a `compress_pdf(input_path, output_path, ghostscript_path=None)` function to `email_to_kindle.py`:

1. If `ghostscript_path` is not provided, probe PATH via `shutil.which('gswin64c')` then `shutil.which('gs')`. If found, use that.
2. If `ghostscript_path` is provided (or found on PATH) and the executable exists, use it:
   ```
   gswin64c -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook
            -dDownsampleColorImages=true -dColorImageResolution=150
            -dNOPAUSE -dBATCH -sOutputFile=output input
   ```
   Use `subprocess.run()` with timeout of 300 seconds.
2. Otherwise, fall back to PyMuPDF:
   ```python
   import fitz
   doc = fitz.open(input_path)
   doc.save(output_path, deflate=True, garbage=4, clean=True)
   doc.close()
   ```
3. Return the output file size in bytes.
4. Log which compression method was used.

- [ ] **Step 1b: Add EPUB compression function**

Add a `try_compress_epub(input_path, max_size_mb, calibre_path=None)` function:

1. If `calibre_path` is not provided, probe PATH via `shutil.which('ebook-convert')`. If not found, return None.
2. Run: `ebook-convert input.epub output_compressed.epub --compress-images --jpeg-quality 60`
3. Check output size. If smaller than `max_size_mb`, return the compressed path.
4. Otherwise return None (compression wasn't enough).

Also add `--calibre-path` to the argparse in Task 2 (PowerShell passes this from `$cfg.paths.calibre`).

- [ ] **Step 2: Add ZIP wrapping function**

Add a `zip_file(input_path, output_path)` function:
```python
import zipfile
with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write(input_path, os.path.basename(input_path))
```
Return the ZIP file size.

- [ ] **Step 3: Add size auto-routing to main()**

After file selection but before sending, implement the format-aware size routing from the spec:

```python
file_size_mb = os.path.getsize(file_to_send) / (1024 * 1024)
is_pdf = file_to_send.lower().endswith('.pdf')
is_epub = file_to_send.lower().endswith('.epub')
max_size = args.split_max_mb or 50  # from config via PowerShell

if is_epub:
    if file_size_mb > max_size:
        # Try Calibre image compression first (spec: --compress-images --jpeg-quality 60)
        # Note: requires ebook-convert on PATH or passed via --calibre-path
        compressed = try_compress_epub(file_to_send, max_size)
        if compressed:
            file_to_send = compressed
            file_size_mb = os.path.getsize(file_to_send) / (1024 * 1024)
        if file_size_mb > max_size:
            # Still too large — abort (no EPUB splitting in v1)
            print(json.dumps({"success": False, "error": "epub_too_large",
                  "message": f"EPUB too large for email ({file_size_mb:.1f} MB after compression). Use USB delivery."}))
            sys.exit(4)
elif is_pdf:
    if args.compress or file_size_mb > 25:
        # Try compression and/or ZIP
        # ... routing logic per spec
```

The full flow for PDF:
1. `≤ 25MB` → send as-is
2. `25-50MB` → ZIP it, send the ZIP
3. `ZIP > 50MB` → compress (Ghostscript/PyMuPDF), re-ZIP, retry
4. `still > 50MB` → go to splitting (Task 4)

- [ ] **Step 4: Test compression manually**

```bash
python tools/email_to_kindle.py --file "some-large.pdf" --kindle-address "..." --smtp-server smtp.gmail.com --smtp-port 587 --smtp-user "..." --book-title "Test" --compress
```

Verify the JSON output shows compression was applied and the file was sent.

- [ ] **Step 5: Commit**

```bash
git add tools/email_to_kindle.py
git commit -m "feat: email_to_kindle.py — PDF compression (PyMuPDF/Ghostscript) and ZIP wrapping"
```

---

## Task 4: Add PDF splitting to email_to_kindle.py

**Files:**
- Modify: `tools/email_to_kindle.py`

- [ ] **Step 1: Add PDF splitting function**

Add `split_pdf(input_path, max_size_mb, output_dir)` function:

1. Open with PyMuPDF: `doc = fitz.open(input_path)`
2. Calculate pages per part to stay under `max_size_mb`, with minimum 10 pages per part
3. Calculate total parts needed. If > 5, return an error (don't split)
4. Split into parts using `doc.select(page_range)` and `doc.save()`
5. Name parts: `BookName_part1.pdf`, `BookName_part2.pdf`, etc.
6. Return list of part file paths

Key guardrails:
```python
total_pages = doc.page_count
avg_page_size = os.path.getsize(input_path) / total_pages
pages_per_part = max(10, int(max_size_mb * 1024 * 1024 / avg_page_size))
num_parts = math.ceil(total_pages / pages_per_part)
if num_parts > 5:
    return None, f"File too large for email (would need {num_parts} parts). Use USB delivery."
```

- [ ] **Step 2: Wire splitting into main() send loop**

When splitting is triggered, send each part as a separate email:
- Subject: `"{title} (Part {n} of {total})"`
- Convert-subject prefix still applies per format rules
- JSON output includes all parts: `{"success": true, "parts_sent": 3, "parts": [...]}`

- [ ] **Step 3: Test splitting manually**

Find or create a PDF > 50MB and test:

```bash
python tools/email_to_kindle.py --file "large-book.pdf" --kindle-address "..." --smtp-server smtp.gmail.com --smtp-port 587 --smtp-user "..." --book-title "Large Book" --split-max-mb 45
```

- [ ] **Step 4: Commit**

```bash
git add tools/email_to_kindle.py
git commit -m "feat: email_to_kindle.py — PDF splitting with guardrails (10pp min, 5 parts max)"
```

---

## Task 5: Add -ProduceEpub to Convert-ToKindle

**Files:**
- Modify: `module/EbookAutomation.psm1` (Convert-ToKindle function, lines ~543-1872)

- [ ] **Step 1: Add -ProduceEpub parameter**

Add after the last existing parameter (`$VqaReportPath` on line 572). You must add a comma after the existing `[string]$VqaReportPath` line to separate it from the new parameter:

```powershell
        [string]$VqaReportPath,

        [Parameter(HelpMessage = 'Also produce an EPUB from the intermediate HTML (for email delivery).')]
        [switch]$ProduceEpub
```

Note: The comma after `$VqaReportPath` is critical — without it the param block won't parse.

- [ ] **Step 2: Add EPUB generation logic before `return $true`**

Insert the following block **before** line 1854 (`return $true`), inside the existing `try` block. This must be after the Calibre KFX conversion succeeds and after the pattern database write-back:

```powershell
        # ── EPUB generation (for email delivery) ──────────────────────────
        if ($ProduceEpub -and $tempDir) {
            # $convertInput is always set by this point (the HTML/TXT path used for KFX).
            # Use it instead of $htmlFile/$tempOutput which are path-dependent variables.
            $htmlSource = if ($convertInput -and (Test-Path $convertInput) -and $convertInput -like '*.html') {
                              $convertInput
                          } else { $null }

            if ($htmlSource) {
                $epubFile = Join-Path $OutputDir "$outName.epub"
                # Build EPUB args: reuse the same TOC flags, metadata, and cover from KFX conversion
                $epubArgs = "`"$htmlSource`" `"$epubFile`" --input-encoding utf-8"
                if ($tocArgs) { $epubArgs += $tocArgs }
                if ($meta.Title) { $epubArgs += " --title `"$($meta.Title -replace '"', "'")`"" }
                if ($meta.Authors) { $epubArgs += " --authors `"$($meta.Authors -replace '"', "'")`"" }
                if ($meta.Publisher) { $epubArgs += " --publisher `"$($meta.Publisher -replace '"', "'")`"" }
                if ($meta.Year) { $epubArgs += " --pubdate `"$($meta.Year)-01-01`"" }
                if ($meta.ISBN) { $epubArgs += " --isbn `"$($meta.ISBN)`"" }
                $epubArgs += " --language en"
                if ($coverImage -and (Test-Path $coverImage)) {
                    $epubArgs += " --cover `"$coverImage`""
                }

                Write-EbookLog "Kindle: generating EPUB for email delivery..."
                try {
                    $epubProc = Start-Process -FilePath $calibre -ArgumentList $epubArgs `
                                              -PassThru -NoNewWindow `
                                              -RedirectStandardOutput (Join-Path $env:TEMP 'epub_out.txt') `
                                              -RedirectStandardError (Join-Path $env:TEMP 'epub_err.txt')
                    $epubProc.WaitForExit()

                    if (($epubProc.ExitCode -eq 0 -or $null -eq $epubProc.ExitCode) -and (Test-Path $epubFile)) {
                        $epubMB = [math]::Round((Get-Item $epubFile).Length / 1MB, 1)
                        Write-EbookLog "Kindle: EPUB generated -> $epubFile ($epubMB MB)" -Level SUCCESS
                    } else {
                        Write-EbookLog "Kindle: EPUB generation failed (non-blocking)" -Level WARN
                    }
                } catch {
                    Write-EbookLog "Kindle: EPUB generation exception (non-blocking) -- $_" -Level WARN
                }

                # Preserve intermediate HTML for future EPUB regeneration
                $intermediatesDir = Join-Path $OutputDir '.intermediates'
                if (-not (Test-Path $intermediatesDir)) {
                    New-Item $intermediatesDir -ItemType Directory -Force | Out-Null
                    # Set Hidden attribute on Windows
                    $dirInfo = Get-Item $intermediatesDir -Force
                    $dirInfo.Attributes = $dirInfo.Attributes -bor [System.IO.FileAttributes]::Hidden
                }
                $htmlDest = Join-Path $intermediatesDir "${outName}_kindle.html"
                Copy-Item $htmlSource $htmlDest -Force -ErrorAction SilentlyContinue
            } else {
                Write-EbookLog "Kindle: no intermediate HTML available for EPUB generation" -Level WARN
            }
        }
```

- [ ] **Step 3: Verify PSM1 parses**

```powershell
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile("$PWD\module\EbookAutomation.psm1", [ref]$tokens, [ref]$errors)
if ($errors.Count -eq 0) { "PSM1 parses OK" } else { $errors }
```

Expected: `PSM1 parses OK`

- [ ] **Step 4: Test EPUB generation**

```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
Convert-ToKindle -InputFile "inbox\some-book.pdf" -UseHtmlExtraction -ProduceEpub -NoCache
```

Verify:
- KFX is produced as normal
- EPUB appears in `output\kindle\` alongside the KFX
- `.intermediates\` directory is created with the HTML file
- `.intermediates\` is hidden in Explorer

- [ ] **Step 5: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: Convert-ToKindle -ProduceEpub — EPUB generation from intermediate HTML"
```

---

## Task 6: Add -Email path to Send-ToKindle

**Files:**
- Modify: `module/EbookAutomation.psm1` (Send-ToKindle function, lines ~1878-2130)

- [ ] **Step 1: Add new parameters to Send-ToKindle param block**

Add after the existing `$DeviceTimeout` parameter (line ~1934):

```powershell
        [switch]$Email,

        [ValidateSet('EPUB','PDF')]
        [string]$EmailFormat = 'EPUB',

        [switch]$Compress,

        [int]$SplitMaxMB
```

- [ ] **Step 2: Add email validation to the `begin` block**

After the existing `kindle_delivery.enabled` check, add:

```powershell
        # ── Email path validation ──
        if ($Email) {
            $emailCfg = $cfg.kindle_delivery.email
            if (-not $emailCfg -or -not $emailCfg.kindle_address) {
                Write-EbookLog "SendToKindle: kindle_delivery.email.kindle_address not configured in settings.json" -Level ERROR
                return
            }
            if (-not $emailCfg.smtp_user) {
                Write-EbookLog "SendToKindle: kindle_delivery.email.smtp_user not configured" -Level ERROR
                return
            }
            $passwordEnvVar = if ($emailCfg.smtp_app_password_env) { $emailCfg.smtp_app_password_env } else { 'EBOOK_SMTP_PASSWORD' }
            if (-not [System.Environment]::GetEnvironmentVariable($passwordEnvVar)) {
                Write-EbookLog "SendToKindle: environment variable '$passwordEnvVar' not set — required for email delivery" -Level ERROR
                Write-EbookLog "SendToKindle: set it with: `$env:$passwordEnvVar = 'your-gmail-app-password'" -Level ERROR
                return
            }
            $emailScript = Join-Path $script:ModuleRoot 'tools\email_to_kindle.py'
            if (-not (Test-Path $emailScript)) {
                Write-EbookLog "SendToKindle: email_to_kindle.py not found at $emailScript" -Level ERROR
                return
            }
        }

        # Warn if -Compress/-SplitMaxMB used without -Email
        if (-not $Email -and ($Compress -or $SplitMaxMB)) {
            Write-EbookLog "SendToKindle: ignoring -Compress/-SplitMaxMB (only applicable with -Email delivery)" -Level WARN
        }
```

- [ ] **Step 3: Add the email delivery process block**

In the `process` block, after the existing `ShouldProcess` check and before the USB path, add an early branch for `-Email`:

```powershell
        # ── Email delivery path ──
        if ($Email) {
            $fileExt = [System.IO.Path]::GetExtension($InputFile).TrimStart('.').ToUpper()
            $supportedEmailFormats = @('EPUB','PDF','DOC','DOCX','TXT','RTF','HTM','HTML','PNG','GIF','JPG','JPEG','BMP')

            # Determine the file to email
            $emailFile = $InputFile
            if ($EmailFormat -eq 'EPUB' -and $fileExt -eq 'KFX') {
                # Look for existing EPUB or intermediate HTML
                $stem = [System.IO.Path]::GetFileNameWithoutExtension($InputFile)
                $dir = Split-Path $InputFile -Parent
                $epubCandidate = Get-ChildItem -Path $dir -Filter "$stem*.epub" -File -ErrorAction SilentlyContinue |
                                 Sort-Object LastWriteTime -Descending | Select-Object -First 1
                if ($epubCandidate) {
                    $emailFile = $epubCandidate.FullName
                    Write-EbookLog "SendToKindle: found EPUB for email: $($epubCandidate.Name)"
                } else {
                    # Check .intermediates for HTML
                    $intermediatesDir = Join-Path $dir '.intermediates'
                    $htmlCandidate = Get-ChildItem -Path $intermediatesDir -Filter "${stem}*_kindle.html" -File -ErrorAction SilentlyContinue |
                                     Select-Object -First 1
                    if ($htmlCandidate) {
                        Write-EbookLog "SendToKindle: generating EPUB from intermediate HTML..."
                        $epubFile = Join-Path $dir "$stem.epub"
                        $calibre = Resolve-ProjectPath $cfg.paths.calibre
                        $epubArgs = "`"$($htmlCandidate.FullName)`" `"$epubFile`" --input-encoding utf-8"
                        $epubProc = Start-Process -FilePath $calibre -ArgumentList $epubArgs -PassThru -NoNewWindow -Wait
                        if ((Test-Path $epubFile)) {
                            $emailFile = $epubFile
                        } else {
                            Write-EbookLog "SendToKindle: EPUB generation from HTML failed" -Level WARN
                        }
                    }
                    if ($emailFile -eq $InputFile) {
                        # Last resort: KFX→EPUB via Calibre (lossy)
                        Write-EbookLog "SendToKindle: no EPUB or intermediate HTML available. Attempting KFX->EPUB (quality may vary)" -Level WARN
                        Write-EbookLog "SendToKindle: for best quality, re-run pipeline with -EmailToKindle" -Level WARN
                        $calibre = Resolve-ProjectPath $cfg.paths.calibre
                        $epubFile = [System.IO.Path]::ChangeExtension($InputFile, '.epub')
                        $lossyArgs = "`"$InputFile`" `"$epubFile`""
                        Start-Process -FilePath $calibre -ArgumentList $lossyArgs -NoNewWindow -Wait
                        if (Test-Path $epubFile) { $emailFile = $epubFile }
                    }
                }
            }

            # Validate the email file format
            $emailExt = [System.IO.Path]::GetExtension($emailFile).TrimStart('.').ToUpper()
            if ($emailExt -notin $supportedEmailFormats) {
                Write-EbookLog "SendToKindle: format .$emailExt is not supported for email delivery. Supported: EPUB, PDF" -Level ERROR
                return
            }

            $emailFileName = [System.IO.Path]::GetFileName($emailFile)
            if (-not $PSCmdlet.ShouldProcess($emailFileName, "Email to Kindle via SMTP")) {
                return
            }

            # Build Python args
            $bookTitle = [System.IO.Path]::GetFileNameWithoutExtension($emailFile)
            $pyArgs = "`"$emailScript`" --file `"$emailFile`" --kindle-address `"$($emailCfg.kindle_address)`""
            $pyArgs += " --smtp-server `"$($emailCfg.smtp_server)`" --smtp-port $($emailCfg.smtp_port)"
            $pyArgs += " --smtp-user `"$($emailCfg.smtp_user)`" --book-title `"$bookTitle`""
            $pyArgs += " --password-env-var `"$passwordEnvVar`""

            if ($emailCfg.convert_subject -and $emailExt -ne 'PDF') {
                $pyArgs += " --convert-subject"
            }
            if ($Compress) { $pyArgs += " --compress" }
            $maxMB = if ($SplitMaxMB) { $SplitMaxMB } else { $emailCfg.max_email_size_mb }
            if ($maxMB) { $pyArgs += " --split-max-mb $maxMB" }

            # Ghostscript path
            $gsPath = $cfg.paths.ghostscript
            if ($gsPath -and (Test-Path $gsPath)) {
                $pyArgs += " --ghostscript-path `"$gsPath`""
            }

            Write-EbookLog "SendToKindle: emailing '$emailFileName' to $($emailCfg.kindle_address)..."
            $python = $cfg.paths.python
            $outFile = Join-Path $env:TEMP 'kindle_email_out.txt'
            $errFile = Join-Path $env:TEMP 'kindle_email_err.txt'

            $proc = Start-Process -FilePath $python -ArgumentList $pyArgs `
                                  -PassThru -NoNewWindow `
                                  -RedirectStandardOutput $outFile `
                                  -RedirectStandardError $errFile
            $proc.WaitForExit()

            $output = if (Test-Path $outFile) { Get-Content $outFile -Raw } else { '' }
            $errOut = if (Test-Path $errFile) { Get-Content $errFile -Raw } else { '' }

            if ($proc.ExitCode -eq 0) {
                $lastJson = ($output -split "`n" | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
                if ($lastJson) {
                    try {
                        $result = $lastJson | ConvertFrom-Json
                        if ($result.success) {
                            Write-EbookLog "SendToKindle: EMAIL SUCCESS — '$emailFileName' sent to $($emailCfg.kindle_address)" -Level SUCCESS
                            Send-EbookNotification -Title 'Emailed to Kindle' -Message "$emailFileName -> Kindle" -Type Success
                        }
                    } catch {
                        Write-EbookLog "SendToKindle: email completed but could not parse result" -Level WARN
                    }
                }
            } else {
                Write-EbookLog "SendToKindle: EMAIL FAILED (exit code $($proc.ExitCode))" -Level ERROR
                if ($errOut) {
                    $errOut -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 5 | ForEach-Object {
                        Write-EbookLog "SendToKindle:   $_" -Level ERROR
                    }
                }
                # Throw so the pipeline's try/catch can detect the failure
                throw "Email delivery failed (exit code $($proc.ExitCode))"
            }

            # Cleanup temp files
            foreach ($f in @($outFile, $errFile)) {
                if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
            }

            return  # Email path complete — don't fall through to USB
        }
```

- [ ] **Step 4: Verify PSM1 parses**

```powershell
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile("$PWD\module\EbookAutomation.psm1", [ref]$tokens, [ref]$errors)
if ($errors.Count -eq 0) { "PSM1 parses OK" } else { $errors }
```

- [ ] **Step 5: Test email delivery end-to-end**

```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
# Test with an existing EPUB
Send-ToKindle -InputFile "output\kindle\SomeBook.epub" -Email
# Test with a KFX (should find the EPUB or intermediate HTML)
Send-ToKindle -InputFile "output\kindle\SomeBook.kfx" -Email
```

- [ ] **Step 6: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: Send-ToKindle -Email — SMTP delivery with format routing and EPUB fallback chain"
```

---

## Task 7: Add -EmailToKindle to Invoke-EbookPipeline

**Files:**
- Modify: `module/EbookAutomation.psm1` (Invoke-EbookPipeline function)

- [ ] **Step 1: Add -EmailToKindle switch to param block**

Add after the existing `-SendToKindle` parameter:

```powershell
        [switch]$EmailToKindle
```

- [ ] **Step 2: Add $emailActive variable and logging**

After the existing `$sendActive` line, add:

```powershell
    $emailActive = $EmailToKindle -or ($cfg.kindle_delivery.email -and $cfg.kindle_delivery.email.auto_send)
```

After the existing `if ($sendActive)` log line, add:

```powershell
    if ($emailActive) { Write-EbookLog "  Email to Kindle: ENABLED" }
```

- [ ] **Step 3: Pass -ProduceEpub to Convert-ToKindle**

In the per-book Kindle conversion call, add `-ProduceEpub:$emailActive`:

```powershell
$kindleOk = Convert-ToKindle -InputFile $workCopy -OutputDir $kindleDir -UseClaudeChapters:$UseClaudeChapters -ForceColumns:$ForceColumns -ValidateVisual:$ValidateVisual -NoCache:$NoCache -ProduceEpub:$emailActive
```

- [ ] **Step 4: Add email delivery after Kindle conversion**

After the existing USB send block (`if ($kindleOk -and $sendActive)`), add:

```powershell
        # Email to Kindle
        $emailedToKindle = $false
        if ($kindleOk -and $emailActive) {
            $stem = [System.IO.Path]::GetFileNameWithoutExtension($workCopy)
            $epubFile = Get-ChildItem -Path $kindleDir -Filter "$stem*.epub" -File -ErrorAction SilentlyContinue |
                        Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($epubFile) {
                try {
                    Write-EbookLog "  Emailing to Kindle..."
                    Send-ToKindle -InputFile $epubFile.FullName -Email
                    $emailedToKindle = $true
                } catch {
                    Write-EbookLog "  Email to Kindle failed: $_" -Level WARN
                    $emailedToKindle = $false
                }
            } else {
                Write-EbookLog "  Email to Kindle: no EPUB found for email delivery" -Level WARN
            }
        }
```

- [ ] **Step 5: Add DeviceSend and EmailSend to ALL $resultLog entries**

There are multiple places where `$resultLog` entries are created. ALL must include the new fields to avoid `$null` column values in the summary table.

**Main success-path entry** (the one that includes `$ttsMsg`, `$kindleMsg`, etc.):

```powershell
        $resultLog += [PSCustomObject]@{
            File = $file.Name; TTS = $ttsMsg; Kindle = $kindleMsg; MP3 = $mp3Msg
            DeviceSend = if ($sendActive -and $kindleOk) { if ($sentToKindle) { 'OK' } else { 'FAILED' } } elseif ($sendActive) { 'skipped' } else { 'n/a' }
            EmailSend = if ($emailActive -and $kindleOk) { if ($emailedToKindle) { 'OK' } else { 'FAILED' } } elseif ($emailActive) { 'skipped' } else { 'n/a' }
            Status = $bookStatus; Time = $bookTime
        }
```

**Early-exit entries** (skip, dry-run, copy-fail — search for other `$resultLog +=` assignments in `Invoke-EbookPipeline`). Add `DeviceSend = 'n/a'; EmailSend = 'n/a'` to each. For example:

```powershell
        # Skip entry
        $resultLog += [PSCustomObject]@{
            File = $file.Name; TTS = 'skip'; Kindle = 'skip'; MP3 = 'skip'
            DeviceSend = 'n/a'; EmailSend = 'n/a'
            Status = 'SKIP'; Time = '—'
        }
```

Find all `$resultLog +=` lines in `Invoke-EbookPipeline` and ensure every one has both fields.

- [ ] **Step 6: Update the summary display line**

Find the summary output line (around line 2503) that formats the table:

```powershell
Write-EbookLog "  $icon $shortName  |  TTS: $($entry.TTS)  |  Kindle: $($entry.Kindle)  |  MP3: $($entry.MP3)" -Level $level
```

Add the new fields conditionally (only show when relevant — don't clutter the output when USB/email weren't requested):

```powershell
        $deliveryInfo = ''
        if ($sendActive)  { $deliveryInfo += "  |  USB: $($entry.DeviceSend)" }
        if ($emailActive) { $deliveryInfo += "  |  Email: $($entry.EmailSend)" }
        Write-EbookLog "  $icon $shortName  |  TTS: $($entry.TTS)  |  Kindle: $($entry.Kindle)  |  MP3: $($entry.MP3)$deliveryInfo" -Level $level
```

- [ ] **Step 7: Verify and commit**

```powershell
# Parse check
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile("$PWD\module\EbookAutomation.psm1", [ref]$tokens, [ref]$errors)
if ($errors.Count -eq 0) { "OK" } else { $errors }
```

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: Invoke-EbookPipeline -EmailToKindle — email delivery + EPUB production in pipeline"
```

---

## Task 8: Update Initialize-EbookAutomation

**Files:**
- Modify: `module/EbookAutomation.psm1` (Initialize-EbookAutomation function)

- [ ] **Step 1: Add email config checks**

After the existing calibredb/calibre-debug check block (inside the `if (Test-Path $calibrePath)` section), add:

```powershell
    # Check email delivery configuration
    $emailCfg = $cfg.kindle_delivery.email
    if ($emailCfg -and $emailCfg.smtp_user) {
        Write-Host "`n  [Optional] Send-to-Kindle email configured" -ForegroundColor White
        Write-Host "    + SMTP server: $($emailCfg.smtp_server):$($emailCfg.smtp_port)" -ForegroundColor Green
        Write-Host "    + Sender: $($emailCfg.smtp_user)" -ForegroundColor Green
        if ($emailCfg.kindle_address) {
            Write-Host "    + Kindle: $($emailCfg.kindle_address)" -ForegroundColor Green
        } else {
            Write-Host "    ! Kindle address not configured (kindle_delivery.email.kindle_address)" -ForegroundColor Yellow
        }
        Write-Host "    ! REMINDER: Your sender address ($($emailCfg.smtp_user)) must be on Amazon's" -ForegroundColor Yellow
        Write-Host "      Approved Personal Document E-mail List. Configure at:" -ForegroundColor Yellow
        Write-Host "      amazon.com/manageyourkindle -> Preferences -> Personal Document Settings" -ForegroundColor Yellow

        # Check Ghostscript
        $gsPath = $cfg.paths.ghostscript
        $gsFound = $false
        if ($gsPath -and (Test-Path $gsPath)) {
            Write-Host "    + Ghostscript: $gsPath" -ForegroundColor Green
            $gsFound = $true
        } else {
            # Probe PATH
            $gsProbe = Get-Command 'gswin64c' -ErrorAction SilentlyContinue
            if (-not $gsProbe) { $gsProbe = Get-Command 'gs' -ErrorAction SilentlyContinue }
            if ($gsProbe) {
                Write-Host "    + Ghostscript: $($gsProbe.Source) (found on PATH)" -ForegroundColor Green
                $gsFound = $true
            }
        }
        if (-not $gsFound) {
            Write-Host "    [Optional] Ghostscript not found (PDF compression will use PyMuPDF)" -ForegroundColor DarkGray
        }
    }
```

- [ ] **Step 2: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: Initialize-EbookAutomation — email config checks and approved sender reminder"
```

---

## Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add email delivery documentation**

Add a new section after the existing "Claude API Integration" section:

```markdown
## Kindle Email Delivery

Send converted ebooks to Kindle via Amazon's Send-to-Kindle email service.

### Environment Variable

`EBOOK_SMTP_PASSWORD` — Gmail App Password for SMTP authentication. Set as a permanent user environment variable (same pattern as `ANTHROPIC_API_KEY`). The env var name is configurable via `kindle_delivery.email.smtp_app_password_env` in settings.json.

### Config (settings.json)

```json
"kindle_delivery": {
    "email": {
        "kindle_address": "user_XXXX@kindle.com",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "user@gmail.com",
        "smtp_app_password_env": "EBOOK_SMTP_PASSWORD",
        "convert_subject": true,
        "max_email_size_mb": 50
    }
}
```

### Supported Email Formats

Amazon accepts: PDF, EPUB, DOC, DOCX, TXT, RTF, HTM, HTML, image files. KFX and MOBI are **not** accepted via email.

### EPUB Intermediate Files

When `-ProduceEpub` or `-EmailToKindle` is active, `Convert-ToKindle` saves:
- `output\kindle\BookName.epub` — the EPUB for email delivery
- `output\kindle\.intermediates\BookName_kindle.html` — preserved HTML for future EPUB regeneration

The `.intermediates\` directory is hidden on Windows.

### Usage

```powershell
Send-ToKindle -InputFile "book.epub" -Email                    # email EPUB
Send-ToKindle -InputFile "book.pdf" -Email -EmailFormat PDF    # email PDF
Invoke-EbookPipeline -EmailToKindle                            # email after conversion
Invoke-EbookPipeline -SendToKindle -EmailToKindle              # USB + email
```
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Kindle email delivery section to CLAUDE.md"
```

---

## Task 10: End-to-end integration test

- [ ] **Step 1: Test full pipeline with -EmailToKindle**

```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
# Place a test PDF in the inbox
Copy-Item "archive\SomeBook.pdf" "inbox\" -ErrorAction SilentlyContinue
Invoke-EbookPipeline -EmailToKindle -NoCache
```

Verify:
- KFX is produced in `output\kindle\`
- EPUB is produced in `output\kindle\`
- `.intermediates\` directory is created with HTML
- Email is sent successfully (check Kindle device)
- Pipeline summary shows `EmailSend: OK`

- [ ] **Step 2: Test both delivery methods**

```powershell
Invoke-EbookPipeline -SendToKindle -EmailToKindle -NoCache
```

Verify both `DeviceSend: OK` and `EmailSend: OK` in the summary (requires Kindle connected via USB).

- [ ] **Step 3: Test standalone email with compression**

```powershell
Send-ToKindle -InputFile "output\kindle\SomeBook.epub" -Email -Compress
```

- [ ] **Step 4: Run Initialize-EbookAutomation to verify email config display**

```powershell
Initialize-EbookAutomation
```

Verify the email configuration section appears with SMTP server, sender, Kindle address, and the approved sender reminder.

- [ ] **Step 5: Push feature branch**

```bash
git push origin feature/email-to-kindle
```
