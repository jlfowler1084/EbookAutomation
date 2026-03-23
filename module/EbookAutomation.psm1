# =============================================================================
#  EbookAutomation.psm1  v1.1.0
#  Automated PDF/EPUB -> TTS text + Kindle conversion pipeline
#
#  CHANGE LOG (v1.1.0 -- 2026-03-17):
#    - Module moved from scripts\ to module\ subfolder
#    - Convert-ToTTS / Convert-ToKindle: -OutputDir is now optional (defaults
#      from settings.json paths.balabolka_txt / paths.kindle)
#    - Invoke-EbookPipeline: TTS output routes to balabolka_txt, not audiobooks
#    - Install-EbookScheduledTask: paths updated for module\ subfolder
#    - Convert-BriefToYouTube: uses paths.episodes (was paths.youtube)
#    - Initialize-EbookAutomation: creates all new folders from settings.json
# =============================================================================

#region -- Module-level setup ------------------------------------------------

$script:ModuleRoot = $PSScriptRoot | Split-Path   # project root (one level up from module\)
$script:Config     = $null

function Get-EbookConfig {
    <#
    .SYNOPSIS  Load (and cache) settings.json from the project config folder.
    #>
    if ($script:Config) { return $script:Config }

    $configPath = Join-Path $script:ModuleRoot 'config\settings.json'
    if (-not (Test-Path $configPath)) {
        throw "settings.json not found at: $configPath"
    }
    $script:Config = Get-Content $configPath -Raw | ConvertFrom-Json
    return $script:Config
}

function Resolve-ProjectPath {
    param([string]$RelativeOrAbsolute)
    if ([System.IO.Path]::IsPathRooted($RelativeOrAbsolute)) {
        return $RelativeOrAbsolute
    }
    return Join-Path $script:ModuleRoot $RelativeOrAbsolute
}

function Get-EbookMetadataFromFilename {
    <#
    .SYNOPSIS  Extract title and author from common ebook filename patterns.
    .DESCRIPTION
        Parses filenames from Anna's Archive, libgen, and common naming conventions:
          "Author - Title (Year, Publisher) - libgen.li.pdf"
          "Title -- Author -- Publisher -- Year -- ISBN -- hash -- Anna's Archive.pdf"
          "Author_-_Title_Year_Publisher_-_libgenli.pdf"
        Returns a hashtable with Title and Authors keys (may be empty strings).
    #>
    param([string]$FileName)

    $stem = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    $title   = ''
    $authors = ''

    # Pattern 0: libgen curly-brace format
    # "Title{Author}(Year, Publisher){ID} libgen.li"
    if ($stem -match '^(.+?)\{(.+?)\}\((\d{4}),?\s*([^)]*)\)\{[^}]*\}\s*libgen') {
        $title   = $Matches[1].Trim()
        $authors = $Matches[2].Trim()
        $year    = $Matches[3]
        $publisher = $Matches[4].Trim()
    }
    # Pattern 0b: libgen curly-brace without publisher parens
    # "Title{Author}{ID} libgen.li"
    elseif ($stem -match '^(.+?)\{(.+?)\}\{[^}]*\}\s*libgen') {
        $title   = $Matches[1].Trim()
        $authors = $Matches[2].Trim()
    }
    # Pattern 1: Anna's Archive double-dash format
    # "Title -- Author -- Publisher -- ..."
    elseif ($stem -match '^(.+?)\s+--\s+(.+?)(\s+--\s+|$)') {
        $title   = $Matches[1].Trim()
        $authors = $Matches[2].Trim()
        # Clean up author field: remove trailing publisher/ISBN fragments
        $authors = ($authors -split '\s+--\s+')[0].Trim()
    }
    # Pattern 2: libgen "Author - Title (Year, Publisher)"
    elseif ($stem -match '^(.+?)\s+-\s+(.+?)(?:\s*[\(\[]|$)') {
        $authors = $Matches[1].Trim()
        $title   = $Matches[2].Trim()
    }
    # Pattern 3: underscored libgen "Author_-_Title_Year_Publisher"
    elseif ($stem -match '^(.+?)_-_(.+?)(?:_\d{4}_|_-_|$)') {
        $authors = ($Matches[1] -replace '_', ' ').Trim()
        $title   = ($Matches[2] -replace '_', ' ').Trim()
    }
    # Fallback: use the whole stem as title
    else {
        $title = ($stem -replace '_', ' ').Trim()
    }

    # Clean up common noise
    $title   = $title -replace '\s*-\s*libgen[\.\s]?li\s*$', '' -replace '\s+', ' '
    $authors = $authors -replace '\s*-\s*libgen[\.\s]?li\s*$', '' -replace '\s+', ' '
    # Remove trailing underscores, hashes, ISBN-like strings
    $title   = $title -replace '\s*[0-9a-f]{20,}\s*$', '' -replace '\s+$', ''
    $authors = $authors -replace '\s*[0-9a-f]{20,}\s*$', '' -replace '\s+$', ''
    # Remove "Anna's Archive" suffix
    $title   = $title -replace "\s*Anna'?s?\s*Archive\s*$", ''
    $authors = $authors -replace "\s*Anna'?s?\s*Archive\s*$", ''

    # Extract publisher, year, ISBN from filename patterns
    $publisher = ''
    $year = ''
    $isbn = ''

    # Year: 4-digit number between 1800-2099
    if ($stem -match '\b(1[89]\d{2}|20\d{2})\b') {
        $year = $Matches[1]
    }

    # ISBN: 10 or 13 digit number (with optional hyphens)
    if ($stem -match '(97[89][\-]?\d[\-]?\d{2}[\-]?\d{4}[\-]?\d[\-]?\d|[\-]?\d{9}[\dXx])') {
        $isbn = $Matches[1] -replace '-', ''
    }

    # Publisher from Anna's Archive format: "Title -- Author -- Publisher -- Year -- ISBN -- hash -- Anna's Archive"
    # The publisher is typically the 3rd segment in the double-dash format
    if ($stem -match '^.+?\s+--\s+.+?\s+--\s+(.+?)(\s+--\s+|$)') {
        $pub = $Matches[1].Trim()
        # Clean up: remove year, ISBN, hash-like strings
        $pub = $pub -replace '\b(1[89]\d{2}|20\d{2})\b', '' -replace '\b\d{10,13}\b', '' -replace '\b[0-9a-f]{20,}\b', ''
        $pub = ($pub -replace '\s+', ' ').Trim(' ,;-')
        if ($pub.Length -gt 2) { $publisher = $pub }
    }

    # --- Title cleanup ---
    if ($title) {
        # Replace underscore-as-colon: "Title_ Subtitle" -> "Title: Subtitle"
        # Only when _ is preceded by a word char and followed by a space + capital letter
        $title = $title -replace '(\w)_\s+([A-Z])', '$1: $2'
        # Replace double underscores used as separator
        $title = $title -replace '__+', ': '
        # Clean up multiple spaces
        $title = ($title -replace '\s{2,}', ' ').Trim()
    }

    # --- Author cleanup ---
    if ($authors) {
        # Strip "by " prefix if present
        $authors = $authors -replace '^by\s+', ''
        # Clean up multiple spaces
        $authors = ($authors -replace '\s{2,}', ' ').Trim()
    }

    return @{
        Title      = $title.Trim()
        Authors    = $authors.Trim()
        Publisher  = $publisher.Trim()
        Year       = $year
        ISBN       = $isbn
    }
}

#endregion

#region -- Logging -----------------------------------------------------------

function Write-EbookLog {
    <#
    .SYNOPSIS  Write a timestamped entry to the daily log file and console.
    #>
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet('INFO','WARN','ERROR','SUCCESS')][string]$Level = 'INFO'
    )

    $cfg      = Get-EbookConfig
    $logDir   = Resolve-ProjectPath $cfg.paths.logs
    $logFile  = Join-Path $logDir ("ebook-automation-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))
    $entry    = "[{0}] [{1,-7}] {2}" -f (Get-Date -Format 'HH:mm:ss'), $Level, $Message

    if (-not (Test-Path $logDir)) { New-Item $logDir -ItemType Directory | Out-Null }
    Add-Content -Path $logFile -Value $entry -Encoding UTF8

    $colour = switch ($Level) {
        'INFO'    { 'Cyan'    }
        'WARN'    { 'Yellow'  }
        'ERROR'   { 'Red'     }
        'SUCCESS' { 'Green'   }
    }
    Write-Host $entry -ForegroundColor $colour
}

#endregion

#region -- Toast notifications -----------------------------------------------

function Send-EbookNotification {
    param(
        [string]$Title   = 'Ebook Automation',
        [string]$Message = '',
        [ValidateSet('Info','Success','Warning','Error')][string]$Type = 'Info'
    )

    $cfg = Get-EbookConfig
    if (-not $cfg.notifications.enabled -or -not $cfg.notifications.show_toast) { return }

    try {
        $xml =[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]::new()
        $xml.LoadXml(@"
<toast>
  <visual>
    <binding template='ToastGeneric'>
      <text>$Title</text>
      <text>$Message</text>
    </binding>
  </visual>
</toast>
"@)
        $toast = [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime]::new($xml)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]::CreateToastNotifier('EbookAutomation')
        $notifier.Show($toast)
    }
    catch {
        # Toast not available in all environments -- silently skip
    }
}

#endregion

#region -- TTS Conversion ----------------------------------------------------

function Convert-ToTTS {
    <#
    .SYNOPSIS  Convert an ebook (PDF/EPUB/MOBI/AZW/DJVU) to Balabolka TTS text.
    .DESCRIPTION
        Extracts text from the input ebook using pdf_to_balabolka.py.
        PDF: native pypdf extraction. EPUB: native ebooklib extraction.
        MOBI/AZW/DJVU: converted via Calibre, then text extracted.
    .PARAMETER InputFile   Full path to the source ebook file.
    .PARAMETER OutputDir   Folder where the .txt file will be saved.
                           Defaults to output\balabolka-txt from settings.json.
    .PARAMETER UseClaudeChapters
        When set, runs a two-pass extraction:
          Pass 1 -- normal regex-based chapter detection (fast)
          Pass 2 -- if Claude API key is available, sends the extracted text to
                   Get-ChapterStructure for AI-assisted chapter detection, writes
                   a hints JSON, and re-runs the Python extractor with --chapter-hints.
        This catches chapters that the regex missed (e.g. headings that were
        merged into body paragraphs during PDF text extraction).
    .PARAMETER UseOCR
        Force Tesseract OCR extraction for scanned/image-only PDFs.
        When not specified, the Python script auto-detects whether OCR is needed.
        Use this switch to force OCR on a PDF that wasn't auto-detected.
    .EXAMPLE
        Convert-ToTTS -InputFile ".\book.pdf" -UseClaudeChapters
    .EXAMPLE
        Convert-ToTTS -InputFile ".\scanned_book.pdf" -UseOCR
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$InputFile,
        [string]$OutputDir,
        [switch]$UseClaudeChapters,
        [switch]$UseOCR,
        [switch]$ForceColumns
    )

    $cfg       = Get-EbookConfig

    # Default output directory from config if not specified
    if (-not $OutputDir) {
        $OutputDir = Resolve-ProjectPath $cfg.paths.balabolka_txt
    }

    $python    = $cfg.paths.python          # 'python' or full path
    $toolPath  = Join-Path $script:ModuleRoot 'tools\pdf_to_balabolka.py'
    $ext       = [System.IO.Path]::GetExtension($InputFile).TrimStart('.').ToLower()

    if ($ext -notin $cfg.tts.input_formats) {
        Write-EbookLog "TTS: skipping unsupported format .$ext  [$InputFile]" -Level WARN
        return $false
    }

    if (-not (Test-Path $toolPath)) {
        Write-EbookLog "TTS converter not found: $toolPath" -Level ERROR
        return $false
    }

    Write-EbookLog "TTS: converting '$([System.IO.Path]::GetFileName($InputFile))'"

    # All formats now handled natively by pdf_to_balabolka.py
    # PDF: pypdf extraction, EPUB: ebooklib, MOBI/AZW/DJVU: Calibre (called from Python)
    $workFile = $InputFile

    # Reconstruct the output TXT path so we can poll its size (mirrors safe_stem
    # logic in pdf_to_balabolka.py: strip non-word/space/hyphen chars, collapse spaces to _)
    $stem       = [System.IO.Path]::GetFileNameWithoutExtension($workFile)
    $safeStem   = ($stem -replace '[^\w\s\-]', '').Trim() -replace ' ', '_'
    $outputTxt  = Join-Path $OutputDir ($safeStem + $cfg.tts.output_suffix)

    $hintsJson   = $null   # will hold temp hints file path if Claude chapters are used
    $rawTextFile = $null   # will hold temp raw-PDF-text file for TOC extraction

    try {
        $env:PYTHONIOENCODING = 'utf-8'
        $errFile   = Join-Path $env:TEMP 'tts_err.txt'
        $outLog    = Join-Path $env:TEMP 'tts_out.txt'
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

        # Build OCR arguments if applicable
        $ocrArgs = ''
        if ($UseOCR) {
            $ocrArgs += ' --ocr'
            Write-EbookLog "TTS: OCR mode forced by -UseOCR switch"
        }

        # Add tesseract path from config if available
        if ($cfg.paths.tesseract) {
            $resolvedTesseract = if (Test-Path $cfg.paths.tesseract) { $cfg.paths.tesseract }
                                 else { Resolve-ProjectPath $cfg.paths.tesseract }
            if (Test-Path $resolvedTesseract) {
                $ocrArgs += " --tesseract-path `"$resolvedTesseract`""
            }
        }

        # Add poppler path from config if available
        if ($cfg.paths.poppler) {
            $popplerBinDir = Get-ChildItem (Resolve-ProjectPath $cfg.paths.poppler) -Recurse -Filter 'pdftoppm.exe' -ErrorAction SilentlyContinue |
                             Select-Object -First 1
            if ($popplerBinDir) {
                $ocrArgs += " --poppler-path `"$($popplerBinDir.DirectoryName)`""
            }
        }

        # Pass Calibre path for formats that need it (MOBI, AZW, DJVU)
        $calibrePath = Resolve-ProjectPath $cfg.paths.calibre
        if (Test-Path $calibrePath) {
            $ocrArgs += " --calibre-path `"$calibrePath`""
        }

        if ($ForceColumns -and $ext -eq 'pdf') {
            $ocrArgs += " --force-columns"
            Write-EbookLog "TTS: column-aware extraction forced by -ForceColumns switch"
        }

        # Pass 1: normal regex-based extraction
        $proc = Start-Process -FilePath $python `
                              -ArgumentList "$toolPath --input `"$workFile`" --output-dir `"$OutputDir`"$ocrArgs" `
                              -PassThru -NoNewWindow `
                              -RedirectStandardOutput $outLog `
                              -RedirectStandardError $errFile

        while (-not $proc.HasExited) {
            Start-Sleep -Seconds 3
            Write-EbookLog "TTS: extracting text... ($([math]::Round($stopwatch.Elapsed.TotalSeconds, 0))s elapsed)"
        }
        $proc.WaitForExit()   # ensures ExitCode is populated (PS 5.1 quirk)

        $elapsed = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)

        if ($proc.ExitCode -ne 0 -and $null -ne $proc.ExitCode) {
            Write-EbookLog "TTS: Python exited with code $($proc.ExitCode) after ${elapsed}s" -Level ERROR
            if (Test-Path $errFile) {
                $errText = Get-Content $errFile -Tail 5 -ErrorAction SilentlyContinue
                foreach ($line in $errText) {
                    if ($line.Trim()) { Write-EbookLog "TTS:   $line" -Level ERROR }
                }
            }
            return $false
        }

        $sizeMB = if (Test-Path $outputTxt) { [math]::Round((Get-Item $outputTxt).Length / 1MB, 2) } else { '?' }
        Write-EbookLog "TTS: pass 1 done -> $outputTxt ($sizeMB MB, ${elapsed}s)" -Level SUCCESS

        # Pass 2: Claude-assisted chapter detection (optional)
        if ($UseClaudeChapters -and (Test-Path $outputTxt)) {
            if (-not $env:ANTHROPIC_API_KEY) {
                Write-EbookLog 'TTS: -UseClaudeChapters requested but $env:ANTHROPIC_API_KEY is not set -- skipping' -Level WARN
            }
            else {
                $sw2 = [System.Diagnostics.Stopwatch]::StartNew()

                # Check if bookmarks already handled chapters in Pass 1
                $bookmarksUsed = $false
                if (Test-Path $outLog) {
                    $pass1Log = Get-Content $outLog -Raw -ErrorAction SilentlyContinue
                    if ($pass1Log -match 'Placed (\d+) bookmarks as chapter headings') {
                        $bookmarksUsed = $true
                        Write-EbookLog "TTS: PDF bookmarks placed $($Matches[1]) chapter headings in pass 1 -- skipping Claude detection"
                    }
                }

                if (-not $bookmarksUsed) {
                    Write-EbookLog 'TTS: pass 2 -- sending text to Claude for chapter detection...'

                    # Extract raw text from first 30 pages of original PDF (includes TOC)
                    $rawTextFile = Join-Path $env:TEMP ('raw_toc_{0}.txt' -f [System.IO.Path]::GetRandomFileName())
                    $extractCmd = @"
from pypdf import PdfReader
r = PdfReader(r'$workFile')
pages = min(30, len(r.pages))
text = '\n'.join(p.extract_text() or '' for p in r.pages[:pages])
with open(r'$rawTextFile', 'w', encoding='utf-8') as f:
    f.write(text)
"@
                    & $python -c $extractCmd 2>$null

                    if (Test-Path $rawTextFile) {
                        $rawText = Get-Content $rawTextFile -Raw -Encoding UTF8
                        Remove-Item $rawTextFile -Force
                        $rawTextFile = $null
                        Write-EbookLog "TTS: extracted raw text from first 30 PDF pages for TOC detection"

                        # Also append the full cleaned text so Claude can see actual chapter boundaries
                        $cleanedText  = Get-Content $outputTxt -Raw -Encoding UTF8
                        $combinedText = $rawText + "`n`n--- CLEANED BODY TEXT FOLLOWS ---`n`n" + $cleanedText
                        $chapters     = Get-ChapterStructure -TextContent $combinedText
                    } else {
                        Write-EbookLog "TTS: could not extract raw PDF text -- falling back to cleaned text" -Level WARN
                        $txtContent = Get-Content $outputTxt -Raw -Encoding UTF8
                        $chapters   = Get-ChapterStructure -TextContent $txtContent
                    }

                    if ($chapters -and $chapters.Count -gt 0) {
                        # Check how many of Claude's titles are MISSING from the pass 1 output.
                        # A title is "present" if it appears as an ALL-CAPS line in the cleaned text.
                        $cleanedUpper = ($cleanedText -split "`r?`n" | ForEach-Object { $_.Trim().ToUpper() }) -join "`n"
                        $missingCount = 0
                        $missingTitles = @()
                        foreach ($ch in $chapters) {
                            $titleUpper = $ch.title.Trim().ToUpper()
                            if ($cleanedUpper -notmatch [regex]::Escape($titleUpper)) {
                                $missingCount++
                                $missingTitles += $ch.title
                            }
                        }

                        Write-EbookLog "TTS: Claude found $($chapters.Count) chapters, $missingCount missing from pass 1 output"
                        if ($missingTitles.Count -gt 0) {
                            foreach ($mt in $missingTitles) {
                                Write-EbookLog "TTS:   missing: $mt"
                            }
                        }

                        if ($missingCount -gt 0) {

                            # Write hints JSON to temp
                            $hintsJson = Join-Path $env:TEMP ('chapter_hints_{0}.json' -f [System.IO.Path]::GetRandomFileName())
                            $chapters | ConvertTo-Json -Depth 3 | Set-Content $hintsJson -Encoding UTF8

                            # Re-run Python with --chapter-hints
                            $stopwatch.Restart()
                            $proc2 = Start-Process -FilePath $python `
                                                   -ArgumentList "$toolPath --input `"$workFile`" --output-dir `"$OutputDir`" --chapter-hints `"$hintsJson`"" `
                                                   -PassThru -NoNewWindow `
                                                   -RedirectStandardOutput $outLog `
                                                   -RedirectStandardError $errFile

                            while (-not $proc2.HasExited) {
                                Start-Sleep -Seconds 3
                                Write-EbookLog "TTS: re-extracting with hints... ($([math]::Round($stopwatch.Elapsed.TotalSeconds, 0))s elapsed)"
                            }

                            $elapsed2 = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)

                            if ($proc2.ExitCode -eq 0) {
                                $sizeMB2 = if (Test-Path $outputTxt) { [math]::Round((Get-Item $outputTxt).Length / 1MB, 2) } else { '?' }
                                Write-EbookLog "TTS: pass 2 done -> $outputTxt ($sizeMB2 MB, ${elapsed2}s)" -Level SUCCESS
                            }
                            else {
                                Write-EbookLog "TTS: pass 2 failed (exit $($proc2.ExitCode)) -- keeping pass 1 output" -Level WARN
                            }
                        }
                        else {
                            Write-EbookLog "TTS: all $($chapters.Count) Claude chapters already present in pass 1 -- no re-run needed"
                        }
                    }
                    else {
                        Write-EbookLog 'TTS: Claude returned no chapters -- keeping pass 1 output' -Level WARN
                    }
                }

                $sw2.Stop()
                Write-EbookLog "TTS: chapter enhancement took $([math]::Round($sw2.Elapsed.TotalSeconds, 1))s total"
            }
        }

        return $true
    }
    catch {
        Write-EbookLog "TTS: EXCEPTION running converter -- $_" -Level ERROR
        return $false
    }
    finally {
        if ($hintsJson   -and (Test-Path $hintsJson))   { Remove-Item $hintsJson   -Force }
        if ($rawTextFile -and (Test-Path $rawTextFile)) { Remove-Item $rawTextFile -Force }
    }
}

#endregion

#region -- Kindle Conversion -------------------------------------------------

function Convert-ToKindle {
    <#
    .SYNOPSIS  Convert an ebook to KFX or AZW3 via Calibre.
    .DESCRIPTION
        Multiple extraction paths for PDF input:

        HtmlExtraction (recommended) — uses pdfminer font metadata to produce
        semantic HTML with h1/h2/h3 headings, then converts via Calibre.
        Produces the best TOC and formatting.

        Legacy (default) — extracts via pypdf to Markdown-formatted TXT, with
        optional Claude AI chapter detection and quality validation.  This is
        the original path and remains the default so nothing breaks for
        existing callers.

        OCR (Tesseract) — for scanned/image-only PDFs with no text layer.
        Uses Tesseract OCR to extract text from page images. Slow but the
        only option for scan_no_text PDFs.

        For other formats (EPUB, MOBI, etc.): sends directly to Calibre.

        KFX output requires the KFX Output plugin for Calibre:
        https://www.mobileread.com/forums/showthread.php?t=272407

    .PARAMETER InputFile   Full path to the source file.
    .PARAMETER OutputDir   Folder where the Kindle file will be saved.
                           Defaults to output\kindle from settings.json.
    .PARAMETER UseHtmlExtraction
        Use the pdfminer-based HTML extraction path.  Mutually exclusive with
        the Legacy switch (ValidateQuality).
    .PARAMETER UseClaudeChapters
        Two-pass chapter detection: runs extraction normally, then sends the
        first 30 pages to Claude API to detect the full chapter structure,
        writes a hints JSON, and re-runs extraction with --chapter-hints for
        accurate TOC. Works with all extraction paths (HTML, Legacy,
        Column-aware). Requires ANTHROPIC_API_KEY environment variable.
        Cost: ~$0.05 per book (single API call).
    .PARAMETER ChapterHintsFile
        Path to a pre-built chapter-hints JSON file. When provided, skips
        the Claude API call and goes straight to pass 2 re-extraction with
        the supplied hints. Works with all extraction paths.
    .PARAMETER ValidateQuality
        (Legacy path) AI quality-scoring pass after text extraction.
    #>
    [CmdletBinding(DefaultParameterSetName = 'Legacy')]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$InputFile,

        [string]$OutputDir,

        # ── HtmlExtraction path ──
        [Parameter(ParameterSetName = 'HtmlExtraction')]
        [Alias('UsePdfminer')]
        [switch]$UseHtmlExtraction,

        # ── Legacy path ──
        [Parameter(ParameterSetName = 'Legacy')]
        [switch]$ValidateQuality,

        # ── Shared across all paths ──
        [switch]$UseClaudeChapters,
        [string]$ChapterHintsFile,
        [switch]$ForceColumns,
        [switch]$UseOCR,
        [switch]$DirectConversion,
        [switch]$ValidateVisual,
        [switch]$FullVQA,

        [Parameter(HelpMessage = 'Skip cache lookup and force a fresh conversion even if this book has been successfully converted before.')]
        [switch]$NoCache,

        [Parameter(HelpMessage = 'Path to VQA report from a previous iteration, used by the fix engine for targeted corrections.')]
        [string]$VqaReportPath
    )

    $cfg        = Get-EbookConfig
    $overallSw  = [System.Diagnostics.Stopwatch]::StartNew()
    $stepTimings = [ordered]@{}

    # Resolve glob patterns in InputFile (e.g. "Burge*.pdf" -> actual path)
    if ($InputFile -match '[*?]') {
        $resolved = Get-ChildItem -Path $InputFile -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($resolved) {
            if ((Get-ChildItem -Path $InputFile -ErrorAction SilentlyContinue).Count -gt 1) {
                Write-EbookLog "Kindle: glob matched multiple files, using: $($resolved.FullName)" -Level WARN
            }
            $InputFile = $resolved.FullName
        } else {
            Write-EbookLog "Kindle: no files match pattern: $InputFile" -Level ERROR
            return $false
        }
    }

    # Default output directory from config if not specified
    if (-not $OutputDir) {
        $OutputDir = Resolve-ProjectPath $cfg.paths.kindle
    }

    $calibre = Resolve-ProjectPath $cfg.paths.calibre
    $ext     = [System.IO.Path]::GetExtension($InputFile).TrimStart('.').ToLower()

    # Determine extraction path for database recording
    $extractionPath = if ($ext -ne 'pdf') {
        'direct'   # EPUB, MOBI, AZW go straight to Calibre
    } elseif ($UseHtmlExtraction) {
        'html_extraction'
    } elseif ($ForceColumns) {
        'column_aware'
    } elseif ($UseOCR) {
        'ocr'
    } else {
        'legacy'
    }

    if (-not $cfg.kindle.enabled) { return $true }   # silently skip if disabled

    if ($ext -notin $cfg.kindle.input_formats) {
        Write-EbookLog "Kindle: skipping unsupported format .$ext  [$InputFile]" -Level WARN
        return $false
    }

    if (-not (Test-Path $calibre)) {
        Write-EbookLog "Calibre not found at: $calibre -- skipping Kindle conversion" -Level WARN
        return $false
    }

    # Tesseract pre-check when OCR is requested
    if ($UseOCR) {
        $tesseractCmd = if ($cfg.paths.tesseract -and (Test-Path (Resolve-ProjectPath $cfg.paths.tesseract))) {
            Resolve-ProjectPath $cfg.paths.tesseract
        } else { 'tesseract' }
        try {
            $null = & $tesseractCmd --version 2>&1
        } catch {
            Write-EbookLog "Kindle: Tesseract OCR not found. Install from github.com/UB-Mannheim/tesseract/wiki or set paths.tesseract in settings.json" -Level ERROR
            return $false
        }
    }

    $outFmt   = $cfg.kindle.output_format          # 'kfx' or 'azw3'
    $stem     = [System.IO.Path]::GetFileNameWithoutExtension($InputFile)
    $fileName = [System.IO.Path]::GetFileName($InputFile)

    # Cache check — skip conversion if book was already processed successfully
    if ($NoCache) {
        Write-EbookLog "Kindle: cache BYPASSED (-NoCache flag)"
    } else {
        try {
            $python    = $cfg.paths.python
            $toolsDir  = Join-Path $script:ModuleRoot 'tools'
            $cacheThreshold = if ($cfg.visual_qa.pass_threshold) { $cfg.visual_qa.pass_threshold } else { 70 }
            $safeFileName = $fileName -replace "'", "''"
            $safeInputPath = $InputFile -replace "'", "''"

            # Two-phase cache check: first ANY record (min_score=0), then qualifying
            $cacheScript = @"
import sys, json
sys.path.insert(0, r'$toolsDir')
from pattern_db import get_cached_result
any_result = get_cached_result(filename='$safeFileName', source_file_path=r'$safeInputPath', min_score=0)
good_result = get_cached_result(filename='$safeFileName', source_file_path=r'$safeInputPath', min_score=$cacheThreshold)
output = {}
if good_result:
    output['hit'] = True
    output['score'] = good_result.get('vqa_score')
    output['output_path'] = good_result.get('output_file_path', '')
elif any_result:
    output['hit'] = False
    output['exists'] = True
    output['best_score'] = any_result.get('vqa_score')
else:
    output['hit'] = False
    output['exists'] = False
print(json.dumps(output))
"@
            $cacheCheck = & $python -c $cacheScript 2>$null

            if ($cacheCheck) {
                $cached = $cacheCheck | ConvertFrom-Json

                if ($cached.hit) {
                    Write-EbookLog "Kindle: cache HIT -- '$fileName' was previously converted (score: $($cached.score)/100)" -Level SUCCESS
                    Write-EbookLog "Kindle: cached output at: $($cached.output_path)"
                    Write-EbookLog "Kindle: use -NoCache to force re-conversion"
                    return $true
                } elseif ($cached.exists) {
                    if ($null -ne $cached.best_score -and $cached.best_score -gt 0) {
                        Write-EbookLog "Kindle: cache miss -- best prior score $($cached.best_score)/100 is below threshold $cacheThreshold for '$fileName'"
                    } else {
                        Write-EbookLog "Kindle: cache miss -- prior conversion exists but has no VQA score for '$fileName'"
                    }
                } else {
                    Write-EbookLog "Kindle: cache miss -- no prior conversion found for '$fileName'"
                }
            } else {
                Write-EbookLog "Kindle: cache miss -- no qualifying prior conversion found for '$fileName'"
            }
        } catch {
            # Cache check failed — continue with normal conversion (non-blocking)
            Write-EbookLog "Kindle: cache check failed (continuing with conversion) -- $_" -Level WARN
        }
    }

    # Parse metadata from filename for a clean output name and Calibre flags
    $meta = Get-EbookMetadataFromFilename $fileName
    $cleanStem = if ($meta.Title) {
        # Sanitize title for filesystem: remove illegal chars, brackets, colons
        ($meta.Title -replace '[\\/:*?"<>|]', '' -replace '[\(\)\[\]\{\}]', '' -replace '\s+', ' ').Trim()
    } else { $stem }

    # Further clean the stem: remove trailing noise like "libgen.li", hashes, underscores
    $cleanStem = $cleanStem -replace '\s*libgen[\.\s]?li\s*$', ''
    $cleanStem = $cleanStem -replace '\s*[0-9a-f]{20,}\s*$', ''
    $cleanStem = $cleanStem -replace "\s*Anna'?s?\s*Archive\s*$", ''
    $cleanStem = $cleanStem.Trim(' _-')

    # If we have author info, create "Title - Author" format for the filename
    if ($cleanStem -and $meta.Authors) {
        $cleanAuthors = $meta.Authors -replace '[\\/:*?"<>|]', '' -replace '[\(\)\[\]\{\}]', '' -replace '\s+', ' '
        $outName = "$cleanStem - $cleanAuthors"
    } else {
        $outName = $cleanStem
    }
    # Trim filename to 200 chars max to stay within Windows path limits
    if ($outName.Length -gt 200) { $outName = $outName.Substring(0, 200).TrimEnd(' -') }
    # Replace colons with dashes (belt-and-suspenders for metadata-derived titles)
    $outName = $outName -replace ':', ' -'
    # Clean libgen underscore-as-colon artifacts (e.g. "Title_ Subtitle" -> "Title - Subtitle")
    $outName = $outName -replace '_ ', ' - '
    $outFile = Join-Path $OutputDir "$outName.$outFmt"

    # For PDFs: extract clean text first, then convert the TXT
    $convertInput = $InputFile
    $tempDir      = $null
    $hintsJson    = $null
    $rawTextFile  = $null

    if ($ext -eq 'pdf') {
        Write-EbookLog "Kindle: extracting clean text from PDF (preserving full content)..."

        $python    = $cfg.paths.python
        $toolPath  = Join-Path $script:ModuleRoot 'tools\pdf_to_balabolka.py'

        if (-not (Test-Path $toolPath)) {
            Write-EbookLog "Kindle: text extractor not found at $toolPath -- falling back to raw PDF" -Level WARN
        } else {
            # Create a temp folder for the extraction output
            $tempDir = Join-Path $env:TEMP ("ebook_kindle_{0}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
            New-Item $tempDir -ItemType Directory -Force | Out-Null

            try {
                $env:PYTHONIOENCODING = 'utf-8'
                $pyErrFile  = Join-Path $env:TEMP 'kindle_py_err.txt'
                $pyOutFile  = Join-Path $env:TEMP 'kindle_py_out.txt'
                $pySw       = [System.Diagnostics.Stopwatch]::StartNew()

                # Build argument list
                $pyArgs = "$toolPath --input `"$InputFile`" --mode kindle --output-dir `"$tempDir`""
                # Add HTML extraction flag if requested
                if ($UseHtmlExtraction) {
                    $pyArgs += " --html-extraction"
                }
                if ($ForceColumns) {
                    $pyArgs += " --force-columns"
                }
                if ($UseOCR) {
                    $pyArgs += " --ocr"
                    Write-EbookLog "Kindle: OCR mode forced by -UseOCR switch"

                    # Add tesseract path from config if available
                    if ($cfg.paths.tesseract) {
                        $resolvedTesseract = if (Test-Path $cfg.paths.tesseract) { $cfg.paths.tesseract }
                                             else { Resolve-ProjectPath $cfg.paths.tesseract }
                        if (Test-Path $resolvedTesseract) {
                            $pyArgs += " --tesseract-path `"$resolvedTesseract`""
                        }
                    }

                    # Add poppler path from config if available
                    if ($cfg.paths.poppler) {
                        $popplerBinDir = Get-ChildItem (Resolve-ProjectPath $cfg.paths.poppler) -Recurse -Filter 'pdftoppm.exe' -ErrorAction SilentlyContinue |
                                         Select-Object -First 1
                        if ($popplerBinDir) {
                            $pyArgs += " --poppler-path `"$($popplerBinDir.DirectoryName)`""
                        }
                    }
                }
                # Add AI Quality Pass API key if requested
                if ($ValidateQuality -or $env:ANTHROPIC_API_KEY) {
                    $qualityKey = $env:ANTHROPIC_API_KEY
                    if ($qualityKey) {
                        $pyArgs += " --api-key `"$qualityKey`""
                    }
                }

                $pyProc = Start-Process -FilePath $python `
                                        -ArgumentList $pyArgs `
                                        -PassThru -NoNewWindow `
                                        -RedirectStandardOutput $pyOutFile `
                                        -RedirectStandardError $pyErrFile

                while (-not $pyProc.HasExited) {
                    Start-Sleep -Seconds 3
                    Write-EbookLog "Kindle: extracting text... ($([math]::Round($pySw.Elapsed.TotalSeconds, 0))s elapsed)"
                }
                $pyProc.WaitForExit()   # ensures ExitCode is populated (PS 5.1 quirk)

                if ($pyProc.ExitCode -eq 0 -or $null -eq $pyProc.ExitCode) {
                    # Find the output file in the temp folder (HTML or TXT)
                    $tempOutput = Get-ChildItem -Path $tempDir -Include '*.html','*.txt' -File -Recurse | Select-Object -First 1
                    if ($tempOutput) {
                        $txtSizeKB = [math]::Round($tempOutput.Length / 1KB, 0)
                        $extType = if ($tempOutput.Extension -eq '.html') { 'HTML' } else { 'text' }
                        Write-EbookLog "Kindle: extracted $txtSizeKB KB of clean $extType in $([math]::Round($pySw.Elapsed.TotalSeconds, 1))s" -Level SUCCESS
                        $stepTimings['TextExtraction'] = [math]::Round($pySw.Elapsed.TotalSeconds, 1)
                        $convertInput = $tempOutput.FullName
                    } else {
                        Write-EbookLog "Kindle: extraction produced no output file -- using raw PDF" -Level WARN
                    }
                } else {
                    Write-EbookLog "Kindle: text extraction failed (exit $($pyProc.ExitCode)) -- using raw PDF" -Level WARN
                    if (Test-Path $pyErrFile) {
                        $lastLines = Get-Content $pyErrFile -Tail 3 -ErrorAction SilentlyContinue
                        foreach ($line in $lastLines) { if ($line.Trim()) { Write-EbookLog "Kindle:   $line" -Level WARN } }
                    }
                }
            }
            catch {
                Write-EbookLog "Kindle: text extraction exception -- $_ -- using raw PDF" -Level WARN
            }
        }

        # Pass 2: Claude-assisted chapter detection (works with all extraction paths)
        $claudeSw = [System.Diagnostics.Stopwatch]::StartNew()
        if (($UseClaudeChapters -or $ChapterHintsFile) -and $ext -eq 'pdf' -and $convertInput -and (Test-Path $convertInput)) {
            # Check if bookmarks were already used in Pass 1
            $bookmarksUsed = $false
            $pyOutContent = if (Test-Path $pyOutFile) { Get-Content $pyOutFile -Raw -ErrorAction SilentlyContinue } else { '' }
            if ($pyOutContent -match 'Placed (\d+) bookmarks as chapter headings') {
                $bookmarksUsed = $true
                if ($UseClaudeChapters) {
                    Write-EbookLog "Kindle: PDF bookmarks placed $($Matches[1]) headings -- -UseClaudeChapters overrides, running font+Claude detection anyway"
                } else {
                    Write-EbookLog "Kindle: PDF bookmarks placed $($Matches[1]) chapter headings -- skipping Claude detection"
                }
            }

            if (-not $bookmarksUsed -or $UseClaudeChapters) {
                # Determine chapter hints: use provided file, or call Claude to detect
                $hintsJson = $null

                if ($ChapterHintsFile -and (Test-Path $ChapterHintsFile)) {
                    # Pre-built hints file provided — skip Claude API call
                    $hintsJson = $ChapterHintsFile
                    Write-EbookLog "Kindle: using pre-built chapter hints: $ChapterHintsFile"
                }
                elseif (-not $env:ANTHROPIC_API_KEY) {
                    Write-EbookLog 'Kindle: -UseClaudeChapters requested but $env:ANTHROPIC_API_KEY is not set -- skipping' -Level WARN
                }
                else {
                    Write-EbookLog 'Kindle: pass 2 -- sending text to Claude for chapter detection...'

                    # Extract raw text from first 30 pages of original PDF (includes TOC)
                    $rawTextFile = Join-Path $env:TEMP ('raw_toc_kindle_{0}.txt' -f [System.IO.Path]::GetRandomFileName())
                    $extractCmd = @"
from pypdf import PdfReader
r = PdfReader(r'$InputFile')
pages = min(30, len(r.pages))
text = '\n'.join(p.extract_text() or '' for p in r.pages[:pages])
with open(r'$rawTextFile', 'w', encoding='utf-8') as f:
    f.write(text)
"@
                    & $python -c $extractCmd 2>$null

                    if (Test-Path $rawTextFile) {
                        $rawText = Get-Content $rawTextFile -Raw -Encoding UTF8
                        Remove-Item $rawTextFile -Force
                        $rawTextFile = $null
                        Write-EbookLog "Kindle: extracted raw text from first 30 PDF pages for TOC detection"

                        $cleanedText = Get-Content $convertInput -Raw -Encoding UTF8
                        $combinedText = $rawText + "`n`n--- CLEANED BODY TEXT FOLLOWS ---`n`n" + $cleanedText
                        $chapters = Get-ChapterStructure -TextContent $combinedText -InputFile $InputFile
                    } else {
                        Write-EbookLog "Kindle: could not extract raw PDF text -- falling back to cleaned text" -Level WARN
                        $cleanedText = Get-Content $convertInput -Raw -Encoding UTF8
                        $chapters = Get-ChapterStructure -TextContent $cleanedText -InputFile $InputFile
                    }

                    if ($chapters -and $chapters.Count -gt 0) {
                        # Per-heading insertion for HTML output
                        if ($convertInput -like '*.html') {
                            $htmlContent = Get-Content $convertInput -Raw -Encoding UTF8
                            $insertedCount = 0
                            $skippedCount  = 0

                            foreach ($ch in $chapters) {
                                $title = $ch.title.Trim()
                                $level = $ch.level
                                $tag   = switch ($level) {
                                    1 { 'h1' }
                                    2 { 'h2' }
                                    3 { 'h3' }
                                    default { 'h2' }
                                }

                                $escapedTitle = [regex]::Escape($title)
                                if ($htmlContent -match "<h[123][^>]*>\s*$escapedTitle\s*</h[123]>") {
                                    $skippedCount++
                                    continue
                                }

                                $pattern = "(<(?:p|div)[^>]*>)\s*$escapedTitle\s*(</(?:p|div)>)"
                                $rx = [regex]::new($pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                                if ($rx.IsMatch($htmlContent)) {
                                    $htmlContent = $rx.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                                    $insertedCount++
                                    continue
                                }

                                $words = $title -split '\s+'
                                if ($words.Count -ge 5) {
                                    $fuzzyPrefix = [regex]::Escape(($words[0..4]) -join ' ')
                                    $fuzzyPattern = "(<(?:p|div)[^>]*>)\s*($fuzzyPrefix[^<]*)\s*(</(?:p|div)>)"
                                    $rxFuzzy = [regex]::new($fuzzyPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                                    if ($rxFuzzy.IsMatch($htmlContent)) {
                                        $htmlContent = $rxFuzzy.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                                        $insertedCount++
                                        continue
                                    }
                                }

                                Write-EbookLog "Kindle: heading not found in HTML: `"$title`"" -Level WARN
                            }

                            if ($insertedCount -gt 0) {
                                Set-Content $convertInput -Value $htmlContent -Encoding UTF8
                                Write-EbookLog "Kindle: inserted $insertedCount heading(s), skipped $skippedCount already present" -Level SUCCESS
                            } else {
                                Write-EbookLog "Kindle: all $($chapters.Count) headings already present in HTML"
                            }
                        }
                        else {
                            # TXT output: check if headings exist as Markdown headings (# / ## / ###)
                            if (-not $cleanedText) { $cleanedText = Get-Content $convertInput -Raw -Encoding UTF8 }
                            $txtLines = $cleanedText -split "`r?`n"
                            $missingCount = 0
                            $insertedMd   = 0

                            foreach ($ch in $chapters) {
                                $title = $ch.title.Trim()
                                $titleUpper = $title.ToUpper()
                                $escapedTitle = [regex]::Escape($titleUpper)
                                $level = $ch.level
                                $mdPrefix = switch ($level) {
                                    1 { '# ' }
                                    2 { '## ' }
                                    3 { '### ' }
                                    default { '## ' }
                                }

                                # Check if it already exists as a Markdown heading
                                $alreadyHeading = $false
                                foreach ($line in $txtLines) {
                                    if ($line.Trim() -match "^#{1,3}\s+" -and $line.Trim().ToUpper() -match $escapedTitle) {
                                        $alreadyHeading = $true
                                        break
                                    }
                                }

                                if ($alreadyHeading) { continue }

                                # Title exists as plain text — convert to Markdown heading
                                $foundPlain = $false
                                for ($li = 0; $li -lt $txtLines.Count; $li++) {
                                    if ($txtLines[$li].Trim().ToUpper() -match "^$escapedTitle$") {
                                        $txtLines[$li] = "$mdPrefix$title"
                                        $insertedMd++
                                        $foundPlain = $true
                                        break
                                    }
                                }

                                if (-not $foundPlain) {
                                    $missingCount++
                                }
                            }

                            # Write back if we inserted any Markdown headings
                            if ($insertedMd -gt 0) {
                                $cleanedText = $txtLines -join "`r`n"
                                Set-Content $convertInput -Value $cleanedText -Encoding UTF8
                                Write-EbookLog "Kindle: converted $insertedMd heading(s) to Markdown format" -Level SUCCESS
                            }

                            if ($missingCount -gt 0) {
                                $hintsJson = Join-Path $env:TEMP ('kindle_hints_{0}.json' -f [System.IO.Path]::GetRandomFileName())
                                $chapters | ConvertTo-Json -Depth 3 | Set-Content $hintsJson -Encoding UTF8
                                Write-EbookLog "Kindle: $missingCount of $($chapters.Count) headings not found in text -- writing hints for pass 2"
                            } elseif ($insertedMd -eq 0) {
                                Write-EbookLog "Kindle: all $($chapters.Count) Claude chapters already have Markdown heading format -- no changes needed"
                            }
                        }
                    } else {
                        Write-EbookLog 'Kindle: Claude returned no chapters -- keeping pass 1 output' -Level WARN
                    }
                }

                # Re-run extraction with chapter hints (if we have any to apply)
                if ($hintsJson -and (Test-Path $hintsJson)) {
                    Write-EbookLog "Kindle: re-extracting with chapter hints..."

                    # Build pass 2 args preserving extraction path flags from pass 1
                    $pass2Args = "$toolPath --input `"$InputFile`" --mode kindle --output-dir `"$tempDir`" --quiet --chapter-hints `"$hintsJson`""
                    if ($UseHtmlExtraction) { $pass2Args += " --html-extraction" }
                    if ($ForceColumns)      { $pass2Args += " --force-columns" }

                    $pyProc2 = Start-Process -FilePath $python `
                                             -ArgumentList $pass2Args `
                                             -PassThru -NoNewWindow `
                                             -RedirectStandardOutput $pyOutFile `
                                             -RedirectStandardError $pyErrFile

                    while (-not $pyProc2.HasExited) {
                        Start-Sleep -Seconds 3
                        Write-EbookLog "Kindle: re-extracting with hints... ($([math]::Round($pySw.Elapsed.TotalSeconds, 0))s elapsed)"
                    }
                    $pyProc2.WaitForExit()

                    if ($pyProc2.ExitCode -eq 0 -or $null -eq $pyProc2.ExitCode) {
                        $tempOutput2 = Get-ChildItem -Path $tempDir -Include '*.html','*.txt' -File -Recurse |
                                       Sort-Object LastWriteTime -Descending | Select-Object -First 1
                        if ($tempOutput2) {
                            $convertInput = $tempOutput2.FullName
                            Write-EbookLog "Kindle: pass 2 done -- updated input for Calibre" -Level SUCCESS
                        }
                    } else {
                        Write-EbookLog "Kindle: pass 2 failed -- keeping pass 1 output" -Level WARN
                    }
                }
            }
        }
        if ($UseClaudeChapters -or $ChapterHintsFile) {
            $stepTimings['ClaudeChapters'] = [math]::Round($claudeSw.Elapsed.TotalSeconds, 1)
        }
    }

    # For EPUBs: extract and merge chapter HTML (unless -DirectConversion forces passthrough)
    if ($ext -eq 'epub' -and -not $DirectConversion) {
        Write-EbookLog "Kindle: extracting HTML from EPUB (preserving formatting)..."

        $python   = $cfg.paths.python
        $toolPath = Join-Path $script:ModuleRoot 'tools\pdf_to_balabolka.py'

        if (Test-Path $toolPath) {
            $tempDir = Join-Path $env:TEMP ("ebook_kindle_{0}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
            New-Item $tempDir -ItemType Directory -Force | Out-Null

            try {
                $env:PYTHONIOENCODING = 'utf-8'
                $pyErrFile = Join-Path $env:TEMP 'kindle_epub_err.txt'
                $pyOutFile = Join-Path $env:TEMP 'kindle_epub_out.txt'
                $pySw      = [System.Diagnostics.Stopwatch]::StartNew()

                $pyArgs = "$toolPath --input `"$InputFile`" --mode kindle --output-dir `"$tempDir`" --epub-html"

                $pyProc = Start-Process -FilePath $python `
                                        -ArgumentList $pyArgs `
                                        -PassThru -NoNewWindow `
                                        -RedirectStandardOutput $pyOutFile `
                                        -RedirectStandardError $pyErrFile

                while (-not $pyProc.HasExited) {
                    Start-Sleep -Seconds 3
                    Write-EbookLog "Kindle: extracting EPUB HTML... ($([math]::Round($pySw.Elapsed.TotalSeconds, 0))s elapsed)"
                }
                $pyProc.WaitForExit()

                if ($pyProc.ExitCode -eq 0 -or $null -eq $pyProc.ExitCode) {
                    $htmlFile = Get-ChildItem -Path $tempDir -Filter '*.html' -File | Select-Object -First 1
                    if ($htmlFile) {
                        $convertInput   = $htmlFile.FullName
                        $extractionPath = 'epub_html'
                        $txtSizeKB = [math]::Round($htmlFile.Length / 1KB, 0)
                        Write-EbookLog "Kindle: extracted $txtSizeKB KB of HTML from EPUB in $([math]::Round($pySw.Elapsed.TotalSeconds, 1))s" -Level SUCCESS
                        $stepTimings['EpubExtraction'] = [math]::Round($pySw.Elapsed.TotalSeconds, 1)

                        # Parse JSON output for cover image path
                        if (Test-Path $pyOutFile) {
                            $pyOutLines = Get-Content $pyOutFile -ErrorAction SilentlyContinue
                            foreach ($outLine in $pyOutLines) {
                                if ($outLine -match '^\s*\{.*"cover_image"') {
                                    try {
                                        $epubResult = $outLine | ConvertFrom-Json
                                        if ($epubResult.cover_image -and (Test-Path $epubResult.cover_image)) {
                                            $coverImage = $epubResult.cover_image
                                            $coverSizeKB = [math]::Round((Get-Item $coverImage).Length / 1KB, 0)
                                            Write-EbookLog "Kindle: EPUB cover image found ($coverSizeKB KB)"
                                        }
                                    } catch {
                                        # JSON parse failed -- not critical
                                    }
                                    break
                                }
                            }
                        }
                    } else {
                        Write-EbookLog "Kindle: EPUB HTML extraction produced no output -- falling back to direct conversion" -Level WARN
                    }
                } else {
                    Write-EbookLog "Kindle: EPUB HTML extraction failed (exit $($pyProc.ExitCode)) -- falling back to direct conversion" -Level WARN
                    if (Test-Path $pyErrFile) {
                        $lastLines = Get-Content $pyErrFile -Tail 3 -ErrorAction SilentlyContinue
                        foreach ($line in $lastLines) { if ($line.Trim()) { Write-EbookLog "Kindle:   $line" -Level WARN } }
                    }
                }
            }
            catch {
                Write-EbookLog "Kindle: EPUB extraction error -- $_ -- falling back to direct conversion" -Level WARN
            }
        }
    }

    # EPUB chapter detection: run after EPUB HTML extraction
    if ($ext -eq 'epub' -and ($UseClaudeChapters -or $ChapterHintsFile) -and $convertInput -and (Test-Path $convertInput) -and $convertInput -like '*.html') {
        $cfg    = Get-EbookConfig
        $python = $cfg.paths.python

        # Early-exit: skip Claude if HTML already has sufficient chapter headings
        $epubHtml = Get-Content $convertInput -Raw -Encoding UTF8
        $existingH1 = [regex]::Matches($epubHtml, '(?s)<h1[^>]*>(.+?)</h1>')
        $backMatterKeywords = @('Notes','Bibliography','Index','Appendix','Glossary',
                                'References','Further Reading','Works Cited')
        $nonBackMatter = @($existingH1 | Where-Object {
            $text = $_.Groups[1].Value
            $isBM = $false
            foreach ($kw in $backMatterKeywords) {
                if ($text -match "^$kw$") { $isBM = $true; break }
            }
            -not $isBM
        })

        if ($nonBackMatter.Count -ge 5) {
            Write-EbookLog "Kindle: EPUB has $($nonBackMatter.Count) non-back-matter h1 headings -- skipping Claude chapter detection"
        } else {
            Write-EbookLog "Kindle: EPUB needs chapter detection ($($nonBackMatter.Count) non-back-matter h1 found)..."
            $epubText = Get-Content $convertInput -Raw -Encoding UTF8
            $chapters = Get-ChapterStructure -TextContent $epubText -InputFile $InputFile

            if ($chapters -and $chapters.Count -gt 0) {
                $htmlContent = Get-Content $convertInput -Raw -Encoding UTF8
                $insertedCount = 0
                $skippedCount  = 0

                foreach ($ch in $chapters) {
                    $title = $ch.title.Trim()
                    $level = $ch.level
                    $tag   = switch ($level) {
                        1 { 'h1' }
                        2 { 'h2' }
                        3 { 'h3' }
                        default { 'h2' }
                    }

                    $escapedTitle = [regex]::Escape($title)
                    if ($htmlContent -match "<h[123][^>]*>\s*$escapedTitle\s*</h[123]>") {
                        $skippedCount++
                        continue
                    }

                    $pattern = "(<(?:p|div)[^>]*>)\s*$escapedTitle\s*(</(?:p|div)>)"
                    $rx = [regex]::new($pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                    if ($rx.IsMatch($htmlContent)) {
                        $htmlContent = $rx.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                        $insertedCount++
                        continue
                    }

                    $words = $title -split '\s+'
                    if ($words.Count -ge 5) {
                        $fuzzyPrefix = [regex]::Escape(($words[0..4]) -join ' ')
                        $fuzzyPattern = "(<(?:p|div)[^>]*>)\s*($fuzzyPrefix[^<]*)\s*(</(?:p|div)>)"
                        $rxFuzzy = [regex]::new($fuzzyPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                        if ($rxFuzzy.IsMatch($htmlContent)) {
                            $htmlContent = $rxFuzzy.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                            $insertedCount++
                            continue
                        }
                    }

                    Write-EbookLog "Kindle: heading not found in HTML: `"$title`"" -Level WARN
                }

                if ($insertedCount -gt 0) {
                    Set-Content $convertInput -Value $htmlContent -Encoding UTF8
                    Write-EbookLog "Kindle: inserted $insertedCount heading(s), skipped $skippedCount already present" -Level SUCCESS
                } else {
                    Write-EbookLog "Kindle: all $($chapters.Count) headings already present in EPUB HTML"
                }
            } else {
                Write-EbookLog 'Kindle: Claude returned no chapters for EPUB -- keeping extracted HTML' -Level WARN
            }
        }
    }

    # Extract cover image from first PDF page (EPUB cover is extracted above)
    if (-not $coverImage) { $coverImage = $null }
    $coverSw = [System.Diagnostics.Stopwatch]::StartNew()
    if ($ext -eq 'pdf') {
        try {
            $coverImage = Join-Path $env:TEMP ('ebook_cover_{0}.jpg' -f [System.IO.Path]::GetRandomFileName())

            # Find poppler bin path in tools\poppler
            $popplerBin = Get-ChildItem (Join-Path $script:ModuleRoot 'tools\poppler') -Recurse -Filter 'pdftoppm.exe' -ErrorAction SilentlyContinue | Select-Object -First 1

            if ($popplerBin) {
                # Use a temp script + sys.argv to avoid Unicode filename issues in inline Python
                $coverScript = Join-Path $env:TEMP 'ebook_extract_cover.py'
                @"
from pdf2image import convert_from_path
import sys, os
images = convert_from_path(sys.argv[1], first_page=1, last_page=1, dpi=300, fmt='jpeg', poppler_path=sys.argv[2])
if images:
    images[0].save(sys.argv[3], 'JPEG', quality=90)
    kb = os.path.getsize(sys.argv[3]) / 1024
    print(f'Cover: {images[0].size[0]}x{images[0].size[1]}, {kb:.0f} KB')
else:
    print('No pages rendered')
    sys.exit(1)
"@ | Set-Content $coverScript -Encoding UTF8

                # Copy PDF to safe temp path to avoid Unicode filename issues with poppler
                $safePdfCopy = Join-Path $env:TEMP ('ebook_cover_src_{0}.pdf' -f [System.IO.Path]::GetRandomFileName())
                Copy-Item $InputFile $safePdfCopy -Force

                $coverOutput = & $python $coverScript $safePdfCopy $popplerBin.DirectoryName $coverImage 2>&1

                # Cleanup temp files
                Remove-Item $safePdfCopy -Force -ErrorAction SilentlyContinue
                Remove-Item $coverScript -Force -ErrorAction SilentlyContinue

                if (Test-Path $coverImage) {
                    $coverSizeKB = [math]::Round((Get-Item $coverImage).Length / 1KB, 0)
                    Write-EbookLog "Kindle: cover image extracted ($coverSizeKB KB)"
                    $stepTimings['CoverExtraction'] = [math]::Round($coverSw.Elapsed.TotalSeconds, 1)
                } else {
                    Write-EbookLog "Kindle: cover extraction returned no image -- $coverOutput" -Level WARN
                    $coverImage = $null
                }
            } else {
                Write-EbookLog "Kindle: poppler not found in tools\poppler -- skipping cover extraction" -Level WARN
                $coverImage = $null
            }
        } catch {
            Write-EbookLog "Kindle: cover extraction failed -- $_" -Level WARN
            $coverImage = $null
        }
    }

    # ── Apply rule-based fixes to intermediate text ──────────────────────────
    if ($convertInput -and ($convertInput -ne $InputFile) -and (Test-Path $convertInput)) {
        try {
            $fixEngPath = Join-Path $script:ModuleRoot 'tools' 'fix_engine.py'
            if (Test-Path $fixEngPath) {
                $fixGuid     = [guid]::NewGuid().ToString('N')
                $fixStdout   = Join-Path $env:TEMP "fix_stdout_$fixGuid.txt"
                $fixStderr   = Join-Path $env:TEMP "fix_stderr_$fixGuid.txt"

                $fixArgs = "`"$fixEngPath`" --input `"$convertInput`""

                if ($VqaReportPath -and (Test-Path $VqaReportPath)) {
                    $fixArgs += " --vqa-report `"$VqaReportPath`""
                }

                $fixArgs += " --verbose"

                $fixProc = Start-Process -FilePath $python -ArgumentList $fixArgs `
                                         -NoNewWindow -Wait -PassThru `
                                         -RedirectStandardOutput $fixStdout `
                                         -RedirectStandardError $fixStderr

                # Log fix engine stderr output
                if (Test-Path $fixStderr) {
                    $fixStderrContent = Get-Content $fixStderr -Raw -ErrorAction SilentlyContinue
                    foreach ($line in ($fixStderrContent -split "`n")) {
                        $trimmed = $line.Trim()
                        if ($trimmed) { Write-EbookLog "  $trimmed" }
                    }
                    Remove-Item $fixStderr -ErrorAction SilentlyContinue
                }

                # Parse JSON summary from stdout
                if (Test-Path $fixStdout) {
                    $fixStdoutContent = Get-Content $fixStdout -Raw -ErrorAction SilentlyContinue
                    Remove-Item $fixStdout -ErrorAction SilentlyContinue

                    if ($fixStdoutContent) {
                        try {
                            $fixResult = $fixStdoutContent | ConvertFrom-Json
                            if ($fixResult.total_fixes -gt 0) {
                                Write-EbookLog "Kindle: applied $($fixResult.total_fixes) rule-based fixes" -Level SUCCESS
                                $stepTimings['RuleBasedFixes'] = 'applied'
                            } else {
                                Write-EbookLog "Kindle: no rule-based fixes needed"
                            }
                        } catch { }
                    }
                }
            }
        } catch {
            # Fix engine failure is non-blocking
            Write-EbookLog "Kindle: fix engine failed (non-blocking) -- $_" -Level WARN
        }
    }

    # Run Calibre conversion
    Write-EbookLog "Kindle: converting '$fileName' -> .$outFmt via Calibre"

    # Build argument string with proper quoting for paths with spaces/special chars
    $argString = "`"$convertInput`" `"$outFile`""

    # Add configured options
    if ($cfg.kindle.calibre_options) {
        $argString += " $($cfg.kindle.calibre_options)"
    }

    # For HTML input, set up TOC detection from HTML heading tags
    if ($convertInput -like '*.html') {
        $argString += " --input-encoding utf-8"
        $htmlContent = Get-Content $convertInput -Raw -Encoding UTF8
        $hasH1 = $htmlContent -match '<h1[^>]*>'
        $hasH2 = $htmlContent -match '<h2[^>]*>'
        $tocArgs = ""
        if ($hasH1) { $tocArgs += " --level1-toc `"//h:h1`"" }
        if ($hasH2) { $tocArgs += " --level2-toc `"//h:h2`"" }
        # h3 tags provide visual structure but are excluded from the Kindle TOC
        # to avoid E24011 nesting errors in Kindle Previewer's KFX conversion.
        $argString += $tocArgs
        $levels = @()
        if ($hasH1) { $levels += "h1" }
        if ($hasH2) { $levels += "h2" }
        Write-EbookLog "Kindle: using HTML input with $($levels -join ' + ') TOC"

        # Start reading at first non-front-matter h2
        if ($hasH2) {
            $fmPatterns = @('Front Matter', 'Contents', 'Table of Contents', 'Acknowledg', 'Foreword', 'Preface', 'Dedication', 'Copyright', 'Title', 'Notes', 'Further reading', 'Bibliography', 'Index', 'Appendix')
            $h2Matches = [regex]::Matches($htmlContent, '<h2[^>]*>([^<]+)</h2>')
            # Collect all h2 texts to detect duplicates (TOC entries repeat as real chapters)
            $allH2Texts = @()
            foreach ($m in $h2Matches) {
                $allH2Texts += $m.Groups[1].Value.Trim()
            }
            $startHeading = $null
            foreach ($m in $h2Matches) {
                $h2Text = $m.Groups[1].Value.Trim()
                # Skip known front/back matter headings
                $isFM = $false
                foreach ($pat in $fmPatterns) {
                    if ($h2Text -like "$pat*") { $isFM = $true; break }
                }
                if ($isFM) { continue }
                # Skip duplicate headings — TOC entries that repeat later as real chapters
                $dupeCount = ($allH2Texts | Where-Object { $_ -eq $h2Text }).Count
                if ($dupeCount -gt 1) { continue }
                $startHeading = $h2Text
                break
            }
            if (-not $startHeading -and $h2Matches.Count -gt 0) {
                $startHeading = $h2Matches[0].Groups[1].Value.Trim()
            }
            if ($startHeading) {
                $safeHeading = $startHeading -replace "'", "\\'" -replace '"', ''
                $argString += " --start-reading-at `"//h:h2[normalize-space()='$safeHeading']`""
                Write-EbookLog "Kindle: start reading at: '$startHeading'"
            }
        }
    }

    # For TXT input, add encoding and enable markdown heading detection
    elseif ($convertInput -like '*.txt') {
        $argString += " --input-encoding utf-8 --formatting-type markdown"
        # Check if the text has h1 headings (# Title) or only h2 (## Title)
        $txtContent = Get-Content $convertInput -Raw -Encoding UTF8
        $hasH1 = $txtContent -match '(?m)^# [^#]'
        $hasH2 = $txtContent -match '(?m)^## '
        $hasH3 = $txtContent -match '(?m)^### '
        $h3Str = if ($hasH3) { " --level3-toc `"//h:h3`"" } else { "" }
        $h3Label = if ($hasH3) { " + h3" } else { "" }
        if ($hasH1 -and $hasH2) {
            $argString += " --level1-toc `"//h:h1`" --level2-toc `"//h:h2`"$h3Str"
            Write-EbookLog "Kindle: using TXT input with UTF-8 + Markdown + 2-level TOC (h1 + h2$h3Label)"
        } elseif ($hasH2) {
            $argString += " --level1-toc `"//h:h2`"$h3Str"
            Write-EbookLog "Kindle: using TXT input with UTF-8 + Markdown + 1-level TOC (h2 only$h3Label)"
        } elseif ($hasH1) {
            $argString += " --level1-toc `"//h:h1`"$h3Str"
            Write-EbookLog "Kindle: using TXT input with UTF-8 + Markdown + 1-level TOC (h1 only$h3Label)"
        } else {
            Write-EbookLog "Kindle: using TXT input with UTF-8 + Markdown (no headings found for TOC)"
        }
        # Set "start reading at" landmark — first real chapter heading (after front matter)
        # Front matter sections (Title, Copyright, Acknowledgements, etc.) are h2 entries
        # nested under a synthetic "# Front Matter" h1, so we must skip past them.
        $fmPatterns = @('Title', 'Copyright', 'Acknowledg', 'Foreword', 'Preface', 'Dedication', 'Contents', 'Front Matter')
        $startHeading = $null
        if ($hasH1 -and $hasH2) {
            # 2-level book: find first h2 that isn't a front matter section.
            # Prefer the first NUMBERED chapter heading (## 1. ..., ## Chapter ...) if any exist.
            $firstNumbered = $null
            $firstNonFM = $null
            $inFrontMatter = $false
            foreach ($line in ($txtContent -split "`n")) {
                # Track whether we're inside a "# Front Matter" section
                if ($line -match '^# ([^#].+)') {
                    $inFrontMatter = ($Matches[1].Trim() -eq 'Front Matter')
                }
                if ($line -match '^## (.+)') {
                    $heading = $Matches[1].Trim()
                    # Skip h2 headings nested under "# Front Matter" (TOC entries, etc.)
                    if ($inFrontMatter) { continue }
                    # Check if numbered chapter
                    if (-not $firstNumbered -and $heading -match '^\d+[\.\):]?\s') {
                        if ($heading.Length -le 120 -and $heading -notmatch '"' -and $heading -notmatch ',$' -and ($heading -split '\s+').Count -le 12) {
                            $firstNumbered = $heading
                        }
                    }
                    # Check if non-FM
                    if (-not $firstNonFM) {
                        $isFM = $false
                        foreach ($pat in $fmPatterns) {
                            if ($heading -like "$pat*") { $isFM = $true; break }
                        }
                        if (-not $isFM) {
                            if ($heading.Length -le 120 -and $heading -notmatch '"' -and $heading -notmatch ',$' -and ($heading -split '\s+').Count -le 12) {
                                $firstNonFM = $heading
                            }
                        }
                    }
                }
            }
            # Use the first non-FM heading (respects document order).
            # Introduction, A Note, etc. that appear before numbered chapters
            # are content headings and should be the start-reading-at target.
            $chosen = if ($firstNonFM) { $firstNonFM } else { $firstNumbered }
            if ($chosen) {
                $safeHeading = $chosen -replace "'", "\\'" -replace '"', ''
                $startHeading = "//h:h2[normalize-space()='$safeHeading']"
                Write-EbookLog "Kindle: start reading at first content heading: '$chosen'"
            }
            if (-not $startHeading) {
                # All h2s are front matter — fall back to first h1 that isn't "Front Matter"
                foreach ($line in ($txtContent -split "`n")) {
                    if ($line -match '^# ([^#].+)') {
                        $heading = $Matches[1].Trim()
                        if ($heading -ne 'Front Matter') {
                            $safeHeading = $heading -replace "'", "\\'" -replace '"', ''
                            $startHeading = "//h:h1[normalize-space()='$safeHeading']"
                            Write-EbookLog "Kindle: start reading at first content part: '$heading'"
                            break
                        }
                    }
                }
            }
        } elseif ($hasH2) {
            $startHeading = "//h:h2[1]"
            Write-EbookLog "Kindle: start reading at first chapter heading"
        } elseif ($hasH1) {
            $startHeading = "//h:h1[1]"
            Write-EbookLog "Kindle: start reading at first part heading"
        }
        if ($startHeading) {
            $argString += " --start-reading-at `"$startHeading`""
        }
    }

    # Apply metadata from filename
    if ($meta.Title) {
        $safeTitle = $meta.Title -replace '"', "'"
        $argString += " --title `"$safeTitle`""
        Write-EbookLog "Kindle: title  -> $($meta.Title)"
    }
    if ($meta.Authors) {
        $safeAuthors = $meta.Authors -replace '"', "'"
        $argString += " --authors `"$safeAuthors`""
        Write-EbookLog "Kindle: author -> $($meta.Authors)"
    }
    if ($meta.Publisher) {
        $safePub = $meta.Publisher -replace '"', "'"
        $argString += " --publisher `"$safePub`""
        Write-EbookLog "Kindle: publisher -> $($meta.Publisher)"
    }
    if ($meta.Year) {
        $argString += " --pubdate `"$($meta.Year)-01-01`""
        Write-EbookLog "Kindle: year -> $($meta.Year)"
    }
    if ($meta.ISBN) {
        $argString += " --isbn `"$($meta.ISBN)`""
        Write-EbookLog "Kindle: ISBN -> $($meta.ISBN)"
    }
    # Always set language to English (can be made configurable later)
    $argString += " --language en"

    # Add cover image if extracted
    if ($coverImage -and (Test-Path $coverImage)) {
        $argString += " --cover `"$coverImage`""
        Write-EbookLog "Kindle: using extracted cover image"
    }

    Write-EbookLog "Kindle: calibre args: $argString"

    try {
        # Use Start-Process to avoid PowerShell treating Calibre's stderr as exceptions
        $errFile   = Join-Path $env:TEMP 'calibre_err.txt'
        $outLog    = Join-Path $env:TEMP 'calibre_out.txt'

        # Snapshot existing KFX files so we can detect an unexpected-path output later
        # (filename prediction mismatch: code computes a different name than Calibre/KFX plugin uses)
        $existingKfxFiles = if (Test-Path $OutputDir) {
            @(Get-ChildItem -Path $OutputDir -Filter '*.kfx' -File -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty FullName)
        } else { @() }

        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

        $proc = Start-Process -FilePath $calibre `
                              -ArgumentList $argString `
                              -PassThru -NoNewWindow `
                              -RedirectStandardOutput $outLog `
                              -RedirectStandardError $errFile

        while (-not $proc.HasExited) {
            Start-Sleep -Seconds 3
            Write-EbookLog "Kindle: converting... ($([math]::Round($stopwatch.Elapsed.TotalSeconds, 0))s elapsed)"
        }
        $proc.WaitForExit()   # ensures ExitCode is populated (PS 5.1 quirk)

        $elapsed   = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
        $kfxFailed = $false

        if ($proc.ExitCode -eq 0 -or $null -eq $proc.ExitCode) {
            if (-not (Test-Path $outFile)) {
                # Calibre exited OK but the file isn't at the expected path.
                # Check if the KFX plugin wrote to a different filename (sanitization mismatch).
                $newKfx = Get-ChildItem -Path $OutputDir -Filter '*.kfx' -File -ErrorAction SilentlyContinue |
                           Where-Object { $existingKfxFiles -notcontains $_.FullName } |
                           Sort-Object LastWriteTime -Descending |
                           Select-Object -First 1
                if ($newKfx) {
                    Write-EbookLog "Kindle: KFX at unexpected path: $($newKfx.FullName)" -Level WARN
                    Write-EbookLog "Kindle: renaming to expected path"
                    Rename-Item $newKfx.FullName $outFile -Force -ErrorAction SilentlyContinue
                }
                if (-not (Test-Path $outFile)) {
                    if ($outFmt -eq 'kfx') {
                        Write-EbookLog "Kindle: KFX missing after successful Calibre run — trying AZW3 fallback" -Level WARN
                        $kfxFailed = $true
                    } else {
                        Write-EbookLog "Kindle: Calibre exited OK but output file not found: $outFile" -Level ERROR
                        return $false
                    }
                }
            }
        } else {
            Write-EbookLog "Kindle: Calibre exited with code $($proc.ExitCode)" -Level ERROR
            if (Test-Path $errFile) {
                $errText = Get-Content $errFile -Tail 10 -ErrorAction SilentlyContinue
                foreach ($line in $errText) {
                    if ($line.Trim()) { Write-EbookLog "Kindle:   $line" -Level ERROR }
                }
            }
            if ($outFmt -eq 'kfx') {
                Write-EbookLog "Kindle: KFX conversion failed — trying AZW3 fallback" -Level WARN
                $kfxFailed = $true
            } else {
                return $false
            }
        }

        # AZW3 fallback: triggered when KFX is missing or Calibre exited non-zero
        if ($kfxFailed) {
            $azw3OutFile = [IO.Path]::ChangeExtension($outFile, 'azw3')
            $azw3Args   = $argString.Replace("`"$outFile`"", "`"$azw3OutFile`"")
            $stopwatch.Restart()

            $proc2 = Start-Process -FilePath $calibre `
                                   -ArgumentList $azw3Args `
                                   -PassThru -NoNewWindow `
                                   -RedirectStandardOutput $outLog `
                                   -RedirectStandardError $errFile

            while (-not $proc2.HasExited) {
                Start-Sleep -Seconds 3
                Write-EbookLog "Kindle: AZW3 fallback converting... ($([math]::Round($stopwatch.Elapsed.TotalSeconds, 0))s elapsed)"
            }
            $proc2.WaitForExit()
            $elapsed = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)

            if (($proc2.ExitCode -eq 0 -or $null -eq $proc2.ExitCode) -and (Test-Path $azw3OutFile)) {
                Write-EbookLog "Kindle: AZW3 fallback succeeded" -Level SUCCESS
                $outFile = $azw3OutFile

                # Optional: try AZW3 -> KFX for better Kindle typography
                if ($outFmt -eq 'kfx') {
                    $kfxFromAzw3 = [System.IO.Path]::ChangeExtension($azw3OutFile, '.kfx')
                    Write-EbookLog "Kindle: attempting AZW3 -> KFX conversion for better typography..."
                    $stopwatch.Restart()
                    # Minimal args: Calibre embeds metadata in AZW3; the KFX plugin
                    # re-wraps it without needing profile/language flags from $argString.
                    $kfxArgs = "`"$azw3OutFile`" `"$kfxFromAzw3`""
                    $proc3 = Start-Process -FilePath $calibre `
                                           -ArgumentList $kfxArgs `
                                           -PassThru -NoNewWindow `
                                           -RedirectStandardOutput $outLog `
                                           -RedirectStandardError $errFile
                    while (-not $proc3.HasExited) {
                        Start-Sleep -Seconds 3
                        Write-EbookLog "Kindle: AZW3->KFX converting... ($([math]::Round($stopwatch.Elapsed.TotalSeconds, 0))s elapsed)"
                    }
                    $proc3.WaitForExit()
                    if (($proc3.ExitCode -eq 0 -or $null -eq $proc3.ExitCode) -and (Test-Path $kfxFromAzw3)) {
                        Write-EbookLog "Kindle: AZW3->KFX succeeded -- using KFX output" -Level SUCCESS
                        $elapsed = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
                        Remove-Item $azw3OutFile -ErrorAction SilentlyContinue
                        $outFile = $kfxFromAzw3
                    } else {
                        Write-EbookLog "Kindle: AZW3->KFX failed -- keeping AZW3" -Level WARN
                    }
                }
            } else {
                Write-EbookLog "Kindle: AZW3 fallback failed (exit $($proc2.ExitCode))" -Level ERROR
                if (Test-Path $errFile) {
                    $errText2 = Get-Content $errFile -Tail 5 -ErrorAction SilentlyContinue
                    foreach ($line in $errText2) {
                        if ($line.Trim()) { Write-EbookLog "Kindle:   $line" -Level ERROR }
                    }
                }
                return $false
            }
        }

        $stepTimings['CalibreConversion'] = $elapsed
        $sizeMB = [math]::Round((Get-Item $outFile).Length / 1MB, 1)
        Write-EbookLog "Kindle: done -> $outFile ($sizeMB MB, ${elapsed}s)" -Level SUCCESS

        # Check for AI Quality Report (saved alongside the kindle.txt by the Python script)
        if ($tempDir) {
            $qualityReport = Get-ChildItem -Path $tempDir -Filter '*_quality_report.json' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($qualityReport) {
                try {
                    $qr = Get-Content $qualityReport.FullName -Raw -Encoding utf8 | ConvertFrom-Json
                    $qOrigScore = if ($qr.original_score) { $qr.original_score } else { $qr.quality_score }
                    $qFinalScore = if ($qr.final_score) { $qr.final_score } else { $qr.quality_score }
                    $qIssues = @($qr.issues).Count
                    $qSampleFixes = if ($qr.sample_fixes) { $qr.sample_fixes } else { 0 }
                    $qGlobalFixes = if ($qr.global_fixes) { $qr.global_fixes } else { 0 }
                    $qFixed = if ($qr.total_fixes) { $qr.total_fixes } elseif ($qr.fixes_applied) { $qr.fixes_applied } else { 0 }
                    $qFlagged = if ($qr.fixes_flagged) { $qr.fixes_flagged } else { 0 }
                    $scoreStr = if ($qOrigScore -ne $qFinalScore) { "$qOrigScore -> $qFinalScore/100" } else { "$qFinalScore/100" }
                    $fixDetail = if ($qGlobalFixes -gt 0) { "$qSampleFixes sample + $qGlobalFixes global" } else { "$qFixed" }
                    $fixStr = if ($qFixed -gt 0 -or $qFlagged -gt 0) { " ($fixDetail fixed, $qFlagged flagged)" } else { "" }
                    if ($qFinalScore -lt 80) {
                        Write-EbookLog "Kindle: AI Quality Score: $scoreStr ($qIssues issues)$fixStr -- NEEDS REVIEW" -Level WARN
                    } else {
                        Write-EbookLog "Kindle: AI Quality Score: $scoreStr ($qIssues issues)$fixStr" -Level SUCCESS
                    }
                    foreach ($rec in @($qr.recommendations)) {
                        if ($rec) { Write-EbookLog "Kindle:   [rec] $rec" }
                    }
                    # Copy quality report to output directory alongside the KFX/AZW3
                    $reportDest = Join-Path (Split-Path $outFile) (
                        [System.IO.Path]::GetFileNameWithoutExtension($outFile) + '_quality_report.json'
                    )
                    Copy-Item $qualityReport.FullName $reportDest -Force -ErrorAction SilentlyContinue
                } catch {
                    Write-EbookLog "Kindle: failed to read quality report -- $_" -Level WARN
                }
            }
        }

        # Emit per-step timing summary
        $stepTimings['Total'] = [math]::Round($overallSw.Elapsed.TotalSeconds, 1)
        $bookTitle = if ($meta.Title) { $meta.Title } else { $stem }
        Write-EbookLog "Kindle: timing summary for '$bookTitle':"
        foreach ($key in $stepTimings.Keys) {
            Write-EbookLog ("  {0,-22} {1}s" -f "$key`:", $stepTimings[$key])
        }

        # Visual QA (warn-only, never blocks the pipeline)
        if ($ValidateVisual -and $outFile -and (Test-Path $outFile)) {
            Write-EbookLog "Kindle: running visual QA on $outFile..."
            $vqaResult = Test-ConversionQuality -InputFile $outFile -FullVQA:$FullVQA
            if ($vqaResult -and -not $vqaResult.overall_pass) {
                Write-EbookLog "Kindle: visual QA flagged issues (score $($vqaResult.overall_score)/100)" -Level WARN
            }
        }

        # ── Record conversion to pattern database ──────────────────────────
        try {
            $dbPython = $cfg.paths.python
            if (-not $dbPython) { $dbPython = "python" }

            # Collect conversion flags
            $flagsJson = @{
                UseHtmlExtraction = [bool]$UseHtmlExtraction
                ForceColumns      = [bool]$ForceColumns
                UseClaudeChapters = [bool]$UseClaudeChapters
                ValidateQuality   = [bool]$ValidateQuality
                ValidateVisual    = [bool]$ValidateVisual
                NoCache           = [bool]$NoCache
            } | ConvertTo-Json -Compress

            # Find VQA report if it exists
            $dbVqaReportPath = ""
            if ($ValidateVisual -and $outFile) {
                $dbReportFile = Join-Path (Split-Path $outFile) (
                    [System.IO.Path]::GetFileNameWithoutExtension($outFile) + '_visual_qa_report.json'
                )
                if (Test-Path $dbReportFile) {
                    $dbVqaReportPath = $dbReportFile
                }
            }

            # Get output file size
            $dbOutputSize = 0
            if ($outFile -and (Test-Path $outFile)) {
                $dbOutputSize = (Get-Item $outFile).Length
            }

            # Get source file hash (SHA-256)
            $dbSourceHash = ""
            try {
                $dbSourceHash = (Get-FileHash -Path $InputFile -Algorithm SHA256 -ErrorAction Stop).Hash
            } catch { }

            # Copy cover to persistent location before temp cleanup
            $dbCoverPath = ""
            if ($coverImage -and (Test-Path $coverImage)) {
                $coversDir = Join-Path $script:ModuleRoot "data" "covers"
                if (-not (Test-Path $coversDir)) { New-Item -ItemType Directory -Path $coversDir -Force | Out-Null }
                $coverDest = Join-Path $coversDir ([System.IO.Path]::GetFileNameWithoutExtension($outFile) + '.jpg')
                Copy-Item $coverImage $coverDest -Force -ErrorAction SilentlyContinue
                if (Test-Path $coverDest) { $dbCoverPath = $coverDest }
            }

            # Escape single quotes for Python string literals
            $dbOutLeaf = ($outFile | Split-Path -Leaf) -replace "'", "''"
            $dbTitle = if ($meta.Title) { $meta.Title -replace "'", "''" } else { "" }
            $dbAuthor = if ($meta.Authors) { $meta.Authors -replace "'", "''" } else { "" }
            $dbPublisher = if ($meta.Publisher) { $meta.Publisher -replace "'", "''" } else { "" }
            $dbYear = if ($meta.Year) { $meta.Year } else { "None" }
            $dbISBN = if ($meta.ISBN) { $meta.ISBN -replace "'", "''" } else { "" }
            $dbPages = if ($vqaResult -and $vqaResult.pages_total) { $vqaResult.pages_total } else { "None" }
            $dbOutExt = [System.IO.Path]::GetExtension($outFile).TrimStart('.').ToLower()
            $dbDuration = [math]::Round($overallSw.Elapsed.TotalSeconds, 1)

            # Paths passed via r'...' raw strings — no escaping needed
            $dbInputPathEsc = $InputFile
            $dbOutPathEsc = $outFile
            $dbVqaPathEsc = $dbVqaReportPath
            $dbCoverPathEsc = $dbCoverPath
            $dbToolsPath = Join-Path $script:ModuleRoot "tools"

            $dbScript = @"
import sys, json, os
sys.path.insert(0, r'$dbToolsPath')
from pattern_db import get_or_create_book, add_conversion, add_issues_from_vqa_report, update_source_profile_from_book

book_id = get_or_create_book(
    filename='$dbOutLeaf',
    title='$dbTitle' or None,
    author='$dbAuthor' or None,
    publisher='$dbPublisher' or None,
    year=$dbYear,
    format='$dbOutExt',
    page_count=$dbPages,
    isbn='$dbISBN' or None,
    source_file_path=r'$dbInputPathEsc',
    source_file_hash='$dbSourceHash' or None,
    cover_image_path=r'$dbCoverPathEsc' or None,
)

conv_kwargs = dict(
    book_id=book_id,
    extraction_path='$extractionPath',
    duration_seconds=$dbDuration,
    output_file_path=r'$dbOutPathEsc',
    output_file_size=$dbOutputSize,
    conversion_flags='$($flagsJson -replace "'", "''")',
)

vqa_report_path = r'$dbVqaPathEsc'
if vqa_report_path and os.path.isfile(vqa_report_path):
    with open(vqa_report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    tu = report.get('token_usage', {})
    conv_kwargs['vqa_score'] = report.get('overall_score')
    conv_kwargs['vqa_report_path'] = vqa_report_path
    conv_kwargs['api_input_tokens'] = tu.get('input_tokens', 0)
    conv_kwargs['api_output_tokens'] = tu.get('output_tokens', 0)
    conv_kwargs['cost_usd'] = tu.get('estimated_cost_usd', 0)
    cs = report.get('category_scores')
    if cs:
        conv_kwargs['category_scores'] = cs

conv_id = add_conversion(**conv_kwargs)

issue_count = 0
if vqa_report_path and os.path.isfile(vqa_report_path):
    issue_count = add_issues_from_vqa_report(conv_id, book_id, report)

# Update publisher/source_type aggregate profiles
try:
    update_source_profile_from_book(book_id)
except Exception:
    pass  # non-blocking

result = {'book_id': book_id, 'conversion_id': conv_id, 'issues': issue_count}
if conv_kwargs.get('vqa_score') is not None:
    result['vqa_score'] = conv_kwargs['vqa_score']
print(json.dumps(result))
"@

            $dbResult = & $dbPython -c $dbScript 2>$null
            if ($dbResult) {
                $dbParsed = $dbResult | ConvertFrom-Json
                $dbMsg = "Kindle: recorded in pattern database (book=$($dbParsed.book_id), conv=$($dbParsed.conversion_id)"
                if ($dbParsed.vqa_score) { $dbMsg += ", score=$($dbParsed.vqa_score)" }
                if ($dbParsed.issues -gt 0) { $dbMsg += ", issues=$($dbParsed.issues)" }
                $dbMsg += ")"
                Write-EbookLog $dbMsg
            }
        } catch {
            Write-EbookLog "Kindle: pattern database write-back failed (non-blocking) -- $_" -Level WARN
        }

        return $true
    }
    catch {
        Write-EbookLog "Kindle: EXCEPTION launching Calibre -- $_" -Level ERROR
        return $false
    }
    finally {
        # Clean up temp text extraction folder and log files
        if ($tempDir -and (Test-Path $tempDir)) {
            Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        foreach ($f in @($errFile, $outLog)) {
            if ($f -and (Test-Path $f)) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
        }
        if ($hintsJson -and (Test-Path $hintsJson)) { Remove-Item $hintsJson -Force -ErrorAction SilentlyContinue }
        if ($rawTextFile -and (Test-Path $rawTextFile)) { Remove-Item $rawTextFile -Force -ErrorAction SilentlyContinue }
        if ($coverImage -and (Test-Path $coverImage)) { Remove-Item $coverImage -Force -ErrorAction SilentlyContinue }
    }
}

#endregion

#region -- Send to Kindle Device ---------------------------------------------

function Send-ToKindle {
    <#
    .SYNOPSIS
        Send a converted ebook file to a connected Kindle device via Calibre.
    .DESCRIPTION
        Uses Calibre's library infrastructure and device drivers to send an ebook
        to a USB-connected Kindle.  This replicates the behavior of Calibre's GUI
        "Send to device" button -- including cover images, thumbnails, and metadata.

        The process:
        1. Adds the book to a Calibre library via calibredb
        2. Runs send_to_kindle.py through calibre-debug to detect the Kindle
           and transfer the file with covers/thumbnails
        3. Optionally removes the book from the Calibre library after sending

        Requires:
        - Calibre installed (same location as ebook-convert.exe in settings.json)
        - A Kindle device connected via USB and recognized by Windows
        - Calibre GUI must NOT be running (exclusive device access)

    .PARAMETER InputFile
        Full path to the ebook file to send (.kfx, .azw3, .epub, .mobi, .pdf).
        Accepts pipeline input (e.g. from Convert-ToKindle output path).

    .PARAMETER CoverImage
        Optional path to a cover image (.jpg/.png) to embed with the book.
        If not specified, Calibre will try to extract one from the ebook.

    .PARAMETER DeleteFromLibrary
        Remove the book from the Calibre library after successfully sending
        to the device.  Default: uses kindle_delivery.delete_from_library_after_send
        from settings.json.

    .PARAMETER DeviceTimeout
        Seconds to wait for Kindle device detection. Default: 60.

    .PARAMETER WhatIf
        Check if a Kindle is connected without sending anything.

    .EXAMPLE
        Send-ToKindle -InputFile "F:\Projects\EbookAutomation\output\kindle\MyBook.kfx"
    .EXAMPLE
        Convert-ToKindle -InputFile ".\inbox\book.pdf" | Send-ToKindle
    .EXAMPLE
        Send-ToKindle -InputFile ".\output\kindle\book.kfx" -WhatIf
    .EXAMPLE
        Invoke-EbookPipeline -SendToKindle
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory, ValueFromPipeline, ValueFromPipelineByPropertyName)]
        [Alias('Path','FullName')]
        [string]$InputFile,

        [string]$CoverImage,
        [switch]$DeleteFromLibrary,
        [int]$DeviceTimeout = 60
    )

    begin {
        $cfg = Get-EbookConfig

        # Validate kindle_delivery config exists
        if (-not $cfg.kindle_delivery) {
            Write-EbookLog "SendToKindle: 'kindle_delivery' section missing from settings.json" -Level ERROR
            Write-EbookLog "SendToKindle: Add kindle_delivery config block -- see CLAUDE.md for schema" -Level ERROR
            return
        }

        if (-not $cfg.kindle_delivery.enabled) {
            Write-EbookLog "SendToKindle: disabled in settings.json (kindle_delivery.enabled = false)" -Level WARN
            return
        }

        # Resolve Calibre paths -- calibredb and calibre-debug are in the same folder as ebook-convert
        $calibreDir = Split-Path (Resolve-ProjectPath $cfg.paths.calibre) -Parent
        $calibreDb  = Join-Path $calibreDir 'calibredb.exe'
        $calibreDbg = Join-Path $calibreDir 'calibre-debug.exe'

        if (-not (Test-Path $calibreDb)) {
            Write-EbookLog "SendToKindle: calibredb.exe not found at $calibreDb" -Level ERROR
            return
        }
        if (-not (Test-Path $calibreDbg)) {
            Write-EbookLog "SendToKindle: calibre-debug.exe not found at $calibreDbg" -Level ERROR
            return
        }

        # Resolve library path
        $libraryPath = $cfg.kindle_delivery.calibre_library
        if (-not $libraryPath -or -not (Test-Path $libraryPath)) {
            Write-EbookLog "SendToKindle: Calibre library path not found: $libraryPath" -Level ERROR
            Write-EbookLog "SendToKindle: Set kindle_delivery.calibre_library in settings.json to your Calibre library folder" -Level ERROR
            return
        }

        # Check if Calibre GUI is running -- device access is exclusive
        $calibreProc = Get-Process -Name 'calibre' -ErrorAction SilentlyContinue
        if ($calibreProc) {
            Write-EbookLog "SendToKindle: Calibre GUI is running -- please close it first (device access is exclusive)" -Level ERROR
            return
        }

        $sendScript = Join-Path $script:ModuleRoot 'tools\send_to_kindle.py'
        if (-not (Test-Path $sendScript)) {
            Write-EbookLog "SendToKindle: send_to_kindle.py not found at $sendScript" -Level ERROR
            return
        }

        $deleteAfter = if ($DeleteFromLibrary) { $true }
                       elseif ($cfg.kindle_delivery.delete_from_library_after_send) { $true }
                       else { $false }
    }

    process {
        if (-not (Test-Path $InputFile)) {
            Write-EbookLog "SendToKindle: file not found: $InputFile" -Level ERROR
            return
        }

        $fileName = [System.IO.Path]::GetFileName($InputFile)
        $sw = [System.Diagnostics.Stopwatch]::StartNew()

        Write-EbookLog "SendToKindle: preparing to send '$fileName'..."

        if (-not $PSCmdlet.ShouldProcess($fileName, 'Send to Kindle device')) {
            return
        }

        # --- Step 1: Add book to Calibre library ---
        Write-EbookLog "SendToKindle: adding to Calibre library..."
        $addErrFile = Join-Path ([System.IO.Path]::GetTempPath()) 'calibredb_add_err.txt'
        $addOutFile = Join-Path ([System.IO.Path]::GetTempPath()) 'calibredb_add_out.txt'

        $addArgs = "add `"$InputFile`" --library-path `"$libraryPath`""

        # Add cover if provided
        if ($CoverImage -and (Test-Path $CoverImage)) {
            $addArgs += " --cover `"$CoverImage`""
            Write-EbookLog "SendToKindle: using cover image: $CoverImage"
        }

        $addProc = Start-Process -FilePath $calibreDb `
                                 -ArgumentList $addArgs `
                                 -PassThru -NoNewWindow `
                                 -RedirectStandardOutput $addOutFile `
                                 -RedirectStandardError $addErrFile
        $addProc.WaitForExit()

        $addOutput = if (Test-Path $addOutFile) { Get-Content $addOutFile -Raw } else { '' }
        $addError  = if (Test-Path $addErrFile) { Get-Content $addErrFile -Raw } else { '' }

        # Parse the book ID from calibredb output -- it prints "Added book ids: 42"
        $bookId = $null
        if ($addOutput -match 'Added book ids:\s*(\d+)') {
            $bookId = [int]$Matches[1]
            Write-EbookLog "SendToKindle: added to library as ID $bookId"
        }
        elseif ($addOutput -match 'book ids:\s*(\d+)') {
            $bookId = [int]$Matches[1]
            Write-EbookLog "SendToKindle: added to library as ID $bookId"
        }
        else {
            Write-EbookLog "SendToKindle: failed to parse book ID from calibredb output" -Level ERROR
            Write-EbookLog "SendToKindle: stdout: $addOutput" -Level ERROR
            Write-EbookLog "SendToKindle: stderr: $addError" -Level ERROR
            # Cleanup temp files
            foreach ($f in @($addErrFile, $addOutFile)) {
                if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
            }
            return
        }

        # --- Step 2: Send to device via calibre-debug ---
        Write-EbookLog "SendToKindle: sending to Kindle device (timeout: ${DeviceTimeout}s)..."

        $sendErrFile = Join-Path ([System.IO.Path]::GetTempPath()) 'kindle_send_err.txt'
        $sendOutFile = Join-Path ([System.IO.Path]::GetTempPath()) 'kindle_send_out.txt'

        $sendArgs = "-e `"$sendScript`" -- --library-path `"$libraryPath`" --book-id $bookId --timeout $DeviceTimeout"
        if ($deleteAfter) {
            $sendArgs += " --delete-after"
        }

        $sendProc = Start-Process -FilePath $calibreDbg `
                                  -ArgumentList $sendArgs `
                                  -PassThru -NoNewWindow `
                                  -RedirectStandardOutput $sendOutFile `
                                  -RedirectStandardError $sendErrFile

        # Monitor progress
        while (-not $sendProc.HasExited) {
            Start-Sleep -Seconds 3
            if (Test-Path $sendOutFile) {
                $currentOutput = Get-Content $sendOutFile -Tail 1 -ErrorAction SilentlyContinue
                if ($currentOutput -and $currentOutput -match '\[SendToKindle\]') {
                    Write-EbookLog "  $($currentOutput.Trim())"
                }
            }
        }
        $sendProc.WaitForExit()

        $sendOutput = if (Test-Path $sendOutFile) { Get-Content $sendOutFile -Raw } else { '' }
        $sendError  = if (Test-Path $sendErrFile) { Get-Content $sendErrFile -Raw } else { '' }

        $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1)

        # Check result
        if ($sendProc.ExitCode -eq 0) {
            # Try to parse JSON result from last line
            $lastLine = ($sendOutput -split "`n" | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
            if ($lastLine) {
                try {
                    $result = $lastLine | ConvertFrom-Json
                    if ($result.success) {
                        Write-EbookLog "SendToKindle: SUCCESS -- '$($result.title)' sent as $($result.format) to $($result.device) (${elapsed}s)" -Level SUCCESS
                        Send-EbookNotification -Title 'Sent to Kindle' -Message "$fileName -> $($result.device)" -Type Success
                    }
                } catch {
                    Write-EbookLog "SendToKindle: completed (${elapsed}s) -- could not parse result JSON" -Level WARN
                }
            } else {
                Write-EbookLog "SendToKindle: completed (${elapsed}s)" -Level SUCCESS
            }
        }
        elseif ($sendProc.ExitCode -eq 2) {
            Write-EbookLog "SendToKindle: No Kindle device detected -- is it plugged in via USB?" -Level ERROR
            # Clean up the library entry if device wasn't found
            if (-not $deleteAfter) {
                Write-EbookLog "SendToKindle: removing book from library (send failed)..."
                $rmArgs = "remove $bookId --library-path `"$libraryPath`" --permanent"
                Start-Process -FilePath $calibreDb -ArgumentList $rmArgs -NoNewWindow -Wait
            }
        }
        else {
            Write-EbookLog "SendToKindle: FAILED (exit code $($sendProc.ExitCode), ${elapsed}s)" -Level ERROR
            if ($sendError) {
                $sendError -split "`n" | Where-Object { $_.Trim() } | ForEach-Object {
                    Write-EbookLog "SendToKindle:   $_" -Level ERROR
                }
            }
            # Clean up library on failure
            Write-EbookLog "SendToKindle: removing book from library (send failed)..."
            $rmArgs = "remove $bookId --library-path `"$libraryPath`" --permanent"
            Start-Process -FilePath $calibreDb -ArgumentList $rmArgs -NoNewWindow -Wait
        }

        # Cleanup temp files
        foreach ($f in @($addErrFile, $addOutFile, $sendErrFile, $sendOutFile)) {
            if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
        }
    }
}

#endregion

#region -- File tracking (prevent re-processing) -----------------------------

function Get-ProcessedManifest {
    $path = Join-Path $script:ModuleRoot 'logs\processed.txt'
    if (Test-Path $path) {
        return (Get-Content $path -Encoding UTF8 | Where-Object { $_ -ne '' } | ForEach-Object { $_.Trim() })
    }
    return @()
}

function Add-ProcessedFile {
    param([string]$FilePath)
    $path = Join-Path $script:ModuleRoot 'logs\processed.txt'
    $hash = (Get-FileHash $FilePath -Algorithm MD5).Hash
    $entry = "$hash|$([System.IO.Path]::GetFileName($FilePath))|$(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    Add-Content $path $entry -Encoding UTF8
}

function Test-AlreadyProcessed {
    param([string]$FilePath)
    $manifest = Get-ProcessedManifest
    if (-not $manifest) { return $false }
    $hash = (Get-FileHash $FilePath -Algorithm MD5).Hash
    return ($manifest | Where-Object { $_ -like "$hash|*" }).Count -gt 0
}

#endregion

#region -- Main pipeline -----------------------------------------------------

function Invoke-EbookPipeline {
    <#
    .SYNOPSIS  Scan the inbox, process any new files through TTS and Kindle converters.
    .DESCRIPTION
        Picks up every supported file in the inbox folder, skips already-processed
        files, runs TTS and/or Kindle conversion, archives the original, and logs
        everything.  Each book is processed independently -- a failure on one book
        does not stop the remaining books from being processed.

    .PARAMETER DryRun
        Log what would happen without actually converting anything.

    .PARAMETER GenerateMP3
        Generate MP3 audio from the TTS text output via Invoke-Balabolka.
        Overrides the mp3.enabled setting in settings.json.

    .PARAMETER UseClaudeChapters
        Pass -UseClaudeChapters through to Convert-ToTTS and Convert-ToKindle
        for AI-assisted chapter detection on all extraction paths.

    .PARAMETER UseOCR
        Pass -UseOCR through to Convert-ToTTS and Convert-ToKindle to force
        Tesseract OCR extraction for scanned/image-only PDFs.

    .EXAMPLE
        Invoke-EbookPipeline
    .EXAMPLE
        Invoke-EbookPipeline -DryRun
    .EXAMPLE
        Invoke-EbookPipeline -GenerateMP3 -UseClaudeChapters
    #>
    [CmdletBinding()]
    param(
        [switch]$DryRun,
        [switch]$GenerateMP3,
        [switch]$UseClaudeChapters,
        [switch]$UseOCR,
        [switch]$ForceColumns,
        [switch]$ValidateVisual,
        [switch]$NoCache,
        [switch]$SendToKindle
    )

    $pipelineStart  = Get-Date
    $cfg            = Get-EbookConfig
    $inboxDir       = Resolve-ProjectPath $cfg.paths.inbox
    $archiveDir     = Resolve-ProjectPath $cfg.paths.archive
    $ttsOutDir      = Resolve-ProjectPath $cfg.paths.balabolka_txt
    $kindleDir      = Resolve-ProjectPath $cfg.paths.kindle
    $audiobooksDir  = Resolve-ProjectPath $cfg.paths.audiobooks
    $procDir        = Resolve-ProjectPath $cfg.paths.processing

    Write-EbookLog "--------------------------------------------------------"
    Write-EbookLog "Pipeline started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-EbookLog "  Inbox:         $inboxDir"
    Write-EbookLog "  TTS output:    $ttsOutDir"
    Write-EbookLog "  Kindle output: $kindleDir"
    Write-EbookLog "  MP3 output:    $audiobooksDir"
    Write-EbookLog "  Archive:       $archiveDir"
    $mp3Active = $GenerateMP3 -or $cfg.mp3.enabled
    $sendActive = $SendToKindle -or ($cfg.kindle_delivery -and $cfg.kindle_delivery.auto_send)
    Write-EbookLog "  TTS enabled:   $($cfg.tts.enabled)   |  Kindle enabled: $($cfg.kindle.enabled)   |  MP3 enabled: $mp3Active$(if ($GenerateMP3) { ' (-GenerateMP3)' })"
    if ($UseClaudeChapters) { Write-EbookLog "  Claude chapter detection: ENABLED" }
    if ($UseOCR) { Write-EbookLog "  Tesseract OCR: FORCED" }
    if ($ValidateVisual) { Write-EbookLog "  Visual QA: ENABLED" }
    if ($ForceColumns) { Write-EbookLog "  Column-aware extraction: FORCED (-ForceColumns)" }
    if ($NoCache) { Write-EbookLog "  Cache bypass: ENABLED (-NoCache)" }
    if ($sendActive) { Write-EbookLog "  Send to Kindle: ENABLED" }
    if ($DryRun) { Write-EbookLog "  MODE: DRY RUN -- no files will be modified" -Level WARN }
    Write-EbookLog "--------------------------------------------------------"

    # Ensure directories exist
    foreach ($dir in @($inboxDir, $archiveDir, $ttsOutDir, $kindleDir, $audiobooksDir, $procDir)) {
        if (-not (Test-Path $dir)) { New-Item $dir -ItemType Directory | Out-Null }
    }

    # Scan inbox
    $allFormats  = ($cfg.tts.input_formats + $cfg.kindle.input_formats | Select-Object -Unique)
    $files       = Get-ChildItem -Path $inboxDir -File |
                   Where-Object { $_.Extension.TrimStart('.').ToLower() -in $allFormats }

    if (-not $files) {
        Write-EbookLog "Inbox scan: no supported files found in $inboxDir"
        Write-EbookLog "  Supported formats: $($allFormats -join ', ')"
        return
    }

    Write-EbookLog "Inbox scan: found $($files.Count) file(s)"

    # Tracking
    $processed    = 0
    $skipped      = 0
    $errors       = 0
    $bookNumber   = 0
    $resultLog    = @()   # collect per-book summaries for final report

    foreach ($file in $files) {
        $bookNumber++
        $bookLabel = "[$bookNumber/$($files.Count)]"
        $bookStart = Get-Date

        # Skip already-processed
        if (Test-AlreadyProcessed $file.FullName) {
            Write-EbookLog "$bookLabel SKIP (already processed): $($file.Name)" -Level WARN
            $skipped++
            $resultLog += [PSCustomObject]@{
                File = $file.Name; TTS = 'skip'; Kindle = 'skip'; MP3 = 'skip'; Status = 'skipped'; Time = '-'
            }
            continue
        }

        $sizeMB = [math]::Round($file.Length / 1MB, 1)
        $ext    = $file.Extension.TrimStart('.').ToLower()
        Write-EbookLog "----------------------------------------------------"
        Write-EbookLog "$bookLabel $($file.Name)  ($sizeMB MB, .$ext)"

        if ($DryRun) {
            Write-EbookLog "  DRY RUN: would process this file" -Level WARN
            $resultLog += [PSCustomObject]@{
                File = $file.Name; TTS = 'dry-run'; Kindle = 'dry-run'; MP3 = 'dry-run'; Status = 'dry-run'; Time = '-'
            }
            continue
        }

        # Copy to processing dir
        $workCopy = Join-Path $procDir $file.Name
        try {
            Copy-Item $file.FullName $workCopy -Force
            Write-EbookLog "  Copied to processing: $procDir"
        }
        catch {
            Write-EbookLog "  Failed to copy to processing dir: $_" -Level ERROR
            $errors++
            $resultLog += [PSCustomObject]@{
                File = $file.Name; TTS = 'n/a'; Kindle = 'n/a'; MP3 = 'n/a'; Status = 'COPY FAILED'; Time = '-'
            }
            continue
        }

        $ttsOk     = $false
        $ttsMsg    = 'disabled'
        $kindleOk  = $false
        $kindleMsg = 'disabled'
        $mp3Ok     = $false
        $mp3Msg    = 'disabled'

        # TTS conversion
        if ($cfg.tts.enabled) {
            if ($ext -notin $cfg.tts.input_formats) {
                Write-EbookLog "  TTS: skipping -- .$ext not in supported formats ($($cfg.tts.input_formats -join ', '))" -Level WARN
                $ttsMsg = "skipped (.$ext)"
            } else {
                Write-EbookLog "  TTS: starting conversion..."
                $ttsStart = Get-Date
                try {
                    $ttsOk = Convert-ToTTS -InputFile $workCopy -OutputDir $ttsOutDir -UseClaudeChapters:$UseClaudeChapters -UseOCR:$UseOCR -ForceColumns:$ForceColumns
                    $ttsDuration = (Get-Date) - $ttsStart

                    if ($ttsOk) {
                        Write-EbookLog "  TTS: SUCCESS ($([math]::Round($ttsDuration.TotalSeconds, 1))s)" -Level SUCCESS
                        $ttsMsg = "OK ($([math]::Round($ttsDuration.TotalSeconds, 1))s)"
                    } else {
                        Write-EbookLog "  TTS: converter returned failure (exit code non-zero)" -Level ERROR
                        $ttsMsg = 'FAILED (exit code)'
                    }
                }
                catch {
                    $ttsDuration = (Get-Date) - $ttsStart
                    Write-EbookLog "  TTS: EXCEPTION after $([math]::Round($ttsDuration.TotalSeconds, 1))s -- $_" -Level ERROR
                    Write-EbookLog "  TTS: $($_.ScriptStackTrace)" -Level ERROR
                    $ttsMsg = 'EXCEPTION'
                }
            }
        }

        # MP3 generation
        if (($GenerateMP3 -or $cfg.mp3.enabled) -and $ttsOk) {
            if ($GenerateMP3 -and -not $cfg.mp3.enabled) {
                Write-EbookLog "  MP3: enabled via -GenerateMP3 flag"
            } else {
                Write-EbookLog "  MP3: enabled via settings.json"
            }
            # Reconstruct the TXT filename that Convert-ToTTS produced.
            # Mirrors the safe_stem logic in pdf_to_balabolka.py.
            $stem     = [System.IO.Path]::GetFileNameWithoutExtension($workCopy)
            $safeStem = ($stem -replace '[^\w\s\-]', '').Trim() -replace ' ', '_'
            $txtFile  = Join-Path $ttsOutDir ($safeStem + $cfg.tts.output_suffix)
            $mp3File  = Join-Path $audiobooksDir ([System.IO.Path]::ChangeExtension(
                            (Split-Path $txtFile -Leaf), '.mp3'))

            if (-not (Test-Path $txtFile)) {
                Write-EbookLog "  MP3: TXT file not found -- $txtFile" -Level WARN
                $mp3Msg = 'skipped (txt missing)'
            } else {
                Write-EbookLog "  MP3: starting generation..."
                $mp3Start = Get-Date
                try {
                    $mp3Ok = Invoke-Balabolka -InputFile $txtFile -OutputFile $mp3File `
                                              -Voice   $cfg.mp3.voice  `
                                              -Speed   $cfg.mp3.speed  `
                                              -Volume  $cfg.mp3.volume `
                                              -Bitrate $cfg.mp3.bitrate

                    $mp3Duration = (Get-Date) - $mp3Start
                    if ($mp3Ok) {
                        Write-EbookLog "  MP3: SUCCESS ($([math]::Round($mp3Duration.TotalSeconds, 1))s)" -Level SUCCESS
                        $mp3Msg = "OK ($([math]::Round($mp3Duration.TotalSeconds, 1))s)"
                    } else {
                        Write-EbookLog "  MP3: generation failed" -Level ERROR
                        $mp3Msg = 'FAILED'
                    }
                } catch {
                    $mp3Duration = (Get-Date) - $mp3Start
                    Write-EbookLog "  MP3: EXCEPTION after $([math]::Round($mp3Duration.TotalSeconds, 1))s -- $_" -Level ERROR
                    $mp3Msg = 'EXCEPTION'
                }
            }
        }

        # Kindle conversion
        if ($cfg.kindle.enabled) {
            if ($ext -notin $cfg.kindle.input_formats) {
                Write-EbookLog "  Kindle: skipping -- .$ext not in supported formats ($($cfg.kindle.input_formats -join ', '))" -Level WARN
                $kindleMsg = "skipped (.$ext)"
            } else {
                Write-EbookLog "  Kindle: starting conversion..."
                $kindleStart = Get-Date
                try {
                    $kindleOk = Convert-ToKindle -InputFile $workCopy -OutputDir $kindleDir -UseClaudeChapters:$UseClaudeChapters -UseOCR:$UseOCR -ForceColumns:$ForceColumns -ValidateVisual:$ValidateVisual -NoCache:$NoCache
                    $kindleDuration = (Get-Date) - $kindleStart

                    if ($kindleOk) {
                        Write-EbookLog "  Kindle: SUCCESS ($([math]::Round($kindleDuration.TotalSeconds, 1))s)" -Level SUCCESS
                        $kindleMsg = "OK ($([math]::Round($kindleDuration.TotalSeconds, 1))s)"
                    } else {
                        Write-EbookLog "  Kindle: converter returned failure" -Level ERROR
                        $kindleMsg = 'FAILED'
                    }
                }
                catch {
                    $kindleDuration = (Get-Date) - $kindleStart
                    Write-EbookLog "  Kindle: EXCEPTION after $([math]::Round($kindleDuration.TotalSeconds, 1))s -- $_" -Level ERROR
                    Write-EbookLog "  Kindle: $($_.ScriptStackTrace)" -Level ERROR
                    $kindleMsg = 'EXCEPTION'
                }
            }
        }

        # Send to Kindle device
        $sentToKindle = $false
        if ($kindleOk -and $sendActive) {
            $stem = [System.IO.Path]::GetFileNameWithoutExtension($workCopy)
            $kindleOutputFile = Get-ChildItem -Path $kindleDir -Filter "$stem*" -File |
                                Sort-Object LastWriteTime -Descending |
                                Select-Object -First 1
            if ($kindleOutputFile) {
                try {
                    Write-EbookLog "  Sending to Kindle device..."
                    Send-ToKindle -InputFile $kindleOutputFile.FullName
                    $sentToKindle = $true
                } catch {
                    Write-EbookLog "  Send to Kindle failed: $_" -Level WARN
                    $sentToKindle = $false
                }
            }
        }

        # Per-book result
        $bookDuration = (Get-Date) - $bookStart
        $bookTime     = "$([math]::Round($bookDuration.TotalSeconds, 1))s"
        $anySuccess   = $ttsOk -or $kindleOk   # MP3 failure does not affect this

        if ($anySuccess) {
            # Archive the original
            Add-ProcessedFile $file.FullName

            if ($cfg.archive_originals) {
                try {
                    $archiveDest = Join-Path $archiveDir $file.Name
                    if (Test-Path $archiveDest) {
                        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                        $archiveDest = Join-Path $archiveDir ("{0}_{1}{2}" -f $file.BaseName, $stamp, $file.Extension)
                    }
                    Move-Item $file.FullName $archiveDest -Force
                    Write-EbookLog "  Archived original -> $archiveDest"
                }
                catch {
                    Write-EbookLog "  Archive failed (original left in inbox): $_" -Level WARN
                }
            }

            $processed++
            $bookStatus = if ($ttsOk -and $kindleOk) { 'OK' }
                          elseif ($ttsOk)              { 'TTS only' }
                          else                         { 'Kindle only' }

            Write-EbookLog "  Result: $bookStatus  ($bookTime)" -Level SUCCESS
        } else {
            $errors++
            $bookStatus = 'FAILED'
            Write-EbookLog "  Result: ALL STEPS FAILED -- file left in inbox ($bookTime)" -Level ERROR
        }

        $resultLog += [PSCustomObject]@{
            File = $file.Name; TTS = $ttsMsg; Kindle = $kindleMsg; MP3 = $mp3Msg; Status = $bookStatus; Time = $bookTime
        }

        # Cleanup processing copy
        if (Test-Path $workCopy) {
            try { Remove-Item $workCopy -Force } catch {}
        }
    }

    # Final summary
    $totalDuration = (Get-Date) - $pipelineStart
    $totalTime     = "$([math]::Round($totalDuration.TotalSeconds, 1))s"

    Write-EbookLog "--------------------------------------------------------"
    Write-EbookLog "PIPELINE SUMMARY  ($totalTime total)"
    Write-EbookLog "  Books processed:  $processed"
    Write-EbookLog "  Books skipped:    $skipped"
    Write-EbookLog "  Books failed:     $errors"
    Write-EbookLog "  Total scanned:    $($files.Count)"
    Write-EbookLog "--------------------------------------------------------"

    foreach ($entry in $resultLog) {
        $icon = switch ($entry.Status) {
            'OK'          { '+' }
            'TTS only'    { '~' }
            'Kindle only' { '~' }
            'skipped'     { '-' }
            'dry-run'     { '?' }
            default       { 'x' }
        }
        $level = if ($entry.Status -like 'FAIL*') { 'ERROR' }
                 elseif ($entry.Status -eq 'OK')  { 'SUCCESS' }
                 else                              { 'INFO' }

        $shortName = if ($entry.File.Length -gt 55) { $entry.File.Substring(0, 52) + '...' } else { $entry.File }
        Write-EbookLog "  $icon $shortName  |  TTS: $($entry.TTS)  |  Kindle: $($entry.Kindle)  |  MP3: $($entry.MP3)" -Level $level
    }

    Write-EbookLog "--------------------------------------------------------"

    # Notifications
    if ($processed -gt 0) {
        Send-EbookNotification -Title 'Ebook Automation' `
            -Message "$processed book(s) converted successfully" -Type Success
    }
    if ($errors -gt 0) {
        Send-EbookNotification -Title 'Ebook Automation -- errors' `
            -Message "$errors file(s) failed -- check the log" -Type Warning
    }
}

#endregion

#region -- Scheduled task management -----------------------------------------

function Install-EbookScheduledTask {
    <#
    .SYNOPSIS  Register a Windows Scheduled Task that runs the pipeline automatically.
    .DESCRIPTION
        Creates a task that fires every N minutes (from settings.json).
        Requires running PowerShell as Administrator once to register.
    #>
    [CmdletBinding()]
    param(
        [switch]$Force   # Replace existing task if present
    )

    $cfg          = Get-EbookConfig
    $taskName     = $cfg.scheduler.task_name
    $intervalMins = $cfg.scheduler.interval_minutes
    $modulePath   = Join-Path $script:ModuleRoot 'module\EbookAutomation.psm1'
    $runnerScript = Join-Path $script:ModuleRoot 'module\Run-Pipeline.ps1'

    if ((Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) -and -not $Force) {
        Write-EbookLog "Scheduled task '$taskName' already exists. Use -Force to replace." -Level WARN
        return
    }

    # Write the launcher script that the task will call
    $launcherContent = @"
# Auto-generated launcher -- do not edit
Import-Module '$modulePath' -Force
Invoke-EbookPipeline
"@
    Set-Content $runnerScript $launcherContent -Encoding UTF8

    $action    = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument "-NonInteractive -NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`""

    $triggers = @(
        New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes $intervalMins) -Once -At (Get-Date)
    )

    if ($cfg.scheduler.run_on_login) {
        $triggers += New-ScheduledTaskTrigger -AtLogOn
    }

    $settings  = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -RunOnlyIfNetworkAvailable:$false `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew

    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType InteractiveToken `
        -RunLevel Highest

    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }

    Register-ScheduledTask `
        -TaskName  $taskName `
        -Action    $action `
        -Trigger   $triggers `
        -Settings  $settings `
        -Principal $principal `
        -Description "Automatically converts new ebooks in the inbox to TTS text and Kindle format" |
        Out-Null

    Write-EbookLog "Scheduled task '$taskName' registered (every $intervalMins min)" -Level SUCCESS
}

function Uninstall-EbookScheduledTask {
    <#
    .SYNOPSIS  Remove the Windows Scheduled Task created by Install-EbookScheduledTask.
    #>
    $cfg      = Get-EbookConfig
    $taskName = $cfg.scheduler.task_name

    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-EbookLog "Scheduled task '$taskName' removed" -Level SUCCESS
    } else {
        Write-EbookLog "Scheduled task '$taskName' not found" -Level WARN
    }
}

function Get-EbookTaskStatus {
    <#
    .SYNOPSIS  Show the current state of the scheduled task and last run info.
    #>
    $cfg      = Get-EbookConfig
    $taskName = $cfg.scheduler.task_name
    $task     = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

    if (-not $task) {
        Write-Host "Task '$taskName' is not installed." -ForegroundColor Yellow
        return
    }

    $info = Get-ScheduledTaskInfo -TaskName $taskName
    [PSCustomObject]@{
        TaskName    = $taskName
        State       = $task.State
        LastRunTime = $info.LastRunTime
        LastResult  = $info.LastTaskResult
        NextRunTime = $info.NextRunTime
    } | Format-List
}

#endregion

#region -- Setup wizard ------------------------------------------------------

function Initialize-EbookAutomation {
    <#
    .SYNOPSIS  First-time setup: verify dependencies, create folders, optionally install task.
    #>
    [CmdletBinding()]
    param(
        [switch]$InstallTask
    )

    Write-Host "`n=== Ebook Automation Setup ===" -ForegroundColor Cyan
    $cfg = Get-EbookConfig
    $ok  = $true

    # Check Python
    Write-Host "`n[1/4] Checking Python..." -ForegroundColor White
    try {
        $pyVer = & $cfg.paths.python --version 2>&1
        Write-Host "  + $pyVer" -ForegroundColor Green
    } catch {
        Write-Host "  x Python not found. Install from python.org and ensure it is in PATH." -ForegroundColor Red
        $ok = $false
    }

    # Check pypdf
    try {
        & $cfg.paths.python -c "import pypdf" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  + pypdf installed" -ForegroundColor Green
        } else {
            Write-Host "  x pypdf not found. Run: pip install pypdf" -ForegroundColor Red
            $ok = $false
        }
    } catch {}

    # Check pytesseract
    try {
        $pytesseractCheck = & $cfg.paths.python -c "import pytesseract; print('ok')" 2>&1
        if ($pytesseractCheck -eq 'ok') {
            Write-Host "  + pytesseract installed" -ForegroundColor Green
        } else {
            Write-Host "  [Optional] pytesseract not installed (python -m pip install pytesseract)" -ForegroundColor Yellow
        }
    } catch {}

    # Check Calibre
    Write-Host "`n[2/4] Checking Calibre..." -ForegroundColor White
    $calibrePath = Resolve-ProjectPath $cfg.paths.calibre
    if (Test-Path $calibrePath) {
        Write-Host "  + Calibre found at $calibrePath" -ForegroundColor Green

        # Check calibredb and calibre-debug (for Send-ToKindle)
        $calibreDir = Split-Path $calibrePath -Parent
        $calibreDbPath  = Join-Path $calibreDir 'calibredb.exe'
        $calibreDbgPath = Join-Path $calibreDir 'calibre-debug.exe'
        if (Test-Path $calibreDbPath) {
            Write-Host "  + calibredb.exe: $calibreDbPath" -ForegroundColor Green
        } else {
            Write-Host "  [Optional] calibredb.exe not found (needed for Send-ToKindle)" -ForegroundColor Yellow
        }
        if (Test-Path $calibreDbgPath) {
            Write-Host "  + calibre-debug.exe: $calibreDbgPath" -ForegroundColor Green
        } else {
            Write-Host "  [Optional] calibre-debug.exe not found (needed for Send-ToKindle)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ! Calibre not found at $calibrePath" -ForegroundColor Yellow
        Write-Host "    Install from calibre-ebook.com or update config/settings.json" -ForegroundColor Yellow
        Write-Host "    Kindle conversion will be skipped until Calibre is configured." -ForegroundColor Yellow
    }

    # Check Tesseract OCR
    Write-Host "`n[3/4] Checking Tesseract OCR..." -ForegroundColor White
    $tesseractPath = $cfg.paths.tesseract
    if ($tesseractPath) {
        $resolvedTesseract = if (Test-Path $tesseractPath) { $tesseractPath }
                             else { Resolve-ProjectPath $tesseractPath }

        if (Test-Path $resolvedTesseract) {
            $tesseractVersion = & $resolvedTesseract --version 2>&1 | Select-Object -First 1
            Write-Host "  + Tesseract OCR: $resolvedTesseract ($tesseractVersion)" -ForegroundColor Green
        } else {
            Write-Host "  [Optional] Tesseract OCR not found at $tesseractPath" -ForegroundColor Yellow
            Write-Host "    Install from github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
            Write-Host "    Scanned PDF conversion will be skipped without Tesseract." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [Optional] Tesseract OCR: not configured in settings.json" -ForegroundColor DarkGray
    }

    # Create folders
    Write-Host "`n[4/4] Creating folders..." -ForegroundColor White
    $dirs = @(
        $cfg.paths.inbox,
        $cfg.paths.processing,
        $cfg.paths.archive,
        $cfg.paths.logs,
        $cfg.paths.audiobooks,
        $cfg.paths.kindle,
        $cfg.paths.balabolka_txt,
        $cfg.paths.episodes,
        $cfg.paths.dictionaries
    )
    foreach ($d in $dirs) {
        $full = Resolve-ProjectPath $d
        if (-not (Test-Path $full)) {
            New-Item $full -ItemType Directory | Out-Null
            Write-Host "  Created: $full" -ForegroundColor Green
        } else {
            Write-Host "  Exists:  $full" -ForegroundColor DarkGray
        }
    }

    # Install scheduled task
    if ($InstallTask) {
        Write-Host "`nInstalling scheduled task..." -ForegroundColor White
        Install-EbookScheduledTask
    }

    Write-Host "`n=== Setup complete ===" -ForegroundColor $(if ($ok) { 'Green' } else { 'Yellow' })
    if (-not $ok) {
        Write-Host "Fix the issues above, then run Initialize-EbookAutomation again." -ForegroundColor Yellow
    } else {
        Write-Host @"

Next steps:
  1. Drop a PDF or EPUB into:   $(Resolve-ProjectPath $cfg.paths.inbox)
  2. Run manually:              Invoke-EbookPipeline
  3. Install scheduled task:    Install-EbookScheduledTask
  4. Check status:              Get-EbookTaskStatus

"@ -ForegroundColor Cyan
    }
}

#endregion

#region -- YouTube packaging -------------------------------------------------

function Convert-BriefToYouTube {
    <#
    .SYNOPSIS
        Combine Balabolka MP3 segments with a cover image to produce
        YouTube-ready MP4 files using FFmpeg.

    .DESCRIPTION
        Balabolka splits a daily brief into one MP3 per ALL-CAPS segment heading.
        This function takes those MP3s and a static cover image and produces one
        MP4 per segment -- ready to upload to YouTube individually, or combined
        into a single full-episode video.

        FFmpeg must be installed and available on the PATH, or the path to
        ffmpeg.exe must be set in config\settings.json under paths.ffmpeg.

    .PARAMETER InputFolder
        Folder containing the MP3 files from Balabolka. Defaults to
        output\audiobooks if not specified.

    .PARAMETER CoverImage
        Path to the cover image (JPG or PNG) to use as the video background.
        Recommended size: 1920x1080 (16:9). If omitted, looks for cover.jpg or
        cover.png in the InputFolder.

    .PARAMETER OutputFolder
        Where to save the MP4 files. Defaults to output\episodes.

    .PARAMETER EpisodeName
        Prefix added to each output filename. E.g. "FOH_Brief_Mar15" produces
        "FOH_Brief_Mar15_01_SEGMENT_TITLE.mp4". Defaults to today's date.

    .PARAMETER Combine
        If specified, also produce a single combined MP4 of all segments in order
        after the individual files are created.

    .PARAMETER DryRun
        Show what would be created without actually running FFmpeg.

    .EXAMPLE
        Convert-BriefToYouTube -CoverImage "F:\Projects\EbookAutomation\cover.jpg"

    .EXAMPLE
        Convert-BriefToYouTube `
            -InputFolder "F:\Projects\EbookAutomation\output\audiobooks" `
            -CoverImage  "F:\Projects\EbookAutomation\cover.jpg" `
            -EpisodeName "FOH_Brief_Mar15_IranArc" `
            -Combine
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string]$InputFolder  = '',
        [string]$CoverImage   = '',
        [string]$OutputFolder = '',
        [string]$EpisodeName  = '',
        [switch]$Combine,
        [switch]$DryRun
    )

    $cfg = Get-EbookConfig

    # Resolve paths
    if (-not $InputFolder)  { $InputFolder  = Resolve-ProjectPath $cfg.paths.audiobooks }
    if (-not $OutputFolder) { $OutputFolder = Resolve-ProjectPath $cfg.paths.episodes }
    if (-not $EpisodeName)  { $EpisodeName  = "FOH_Brief_{0}" -f (Get-Date -Format 'yyyy-MM-dd') }

    # Locate FFmpeg
    $ffmpeg = $cfg.paths.ffmpeg
    if (-not $ffmpeg) { $ffmpeg = 'ffmpeg' }
    try {
        $null = & $ffmpeg -version 2>&1
    } catch {
        Write-EbookLog "FFmpeg not found at '$ffmpeg'. Install FFmpeg and ensure it is on your PATH, or set paths.ffmpeg in settings.json." -Level ERROR
        Write-Host @"

  Install FFmpeg:
    winget install ffmpeg
  -- or --
    Download from https://ffmpeg.org/download.html and add to PATH.

"@ -ForegroundColor Yellow
        return
    }

    # Locate cover image
    if (-not $CoverImage) {
        foreach ($name in @('cover.jpg','cover.png','cover.jpeg')) {
            $candidate = Join-Path $InputFolder $name
            if (Test-Path $candidate) { $CoverImage = $candidate; break }
        }
    }
    if (-not $CoverImage -or -not (Test-Path $CoverImage)) {
        Write-EbookLog "Cover image not found. Provide -CoverImage path or place cover.jpg in the input folder." -Level ERROR
        return
    }
    Write-EbookLog "Cover image : $CoverImage" -Level INFO

    # Find MP3 files
    $mp3s = Get-ChildItem -Path $InputFolder -Filter '*.mp3' | Sort-Object Name
    if (-not $mp3s) {
        Write-EbookLog "No MP3 files found in: $InputFolder" -Level WARN
        return
    }
    Write-EbookLog "Found $($mp3s.Count) MP3 file(s) in $InputFolder" -Level INFO

    # Create output folder
    if (-not (Test-Path $OutputFolder)) {
        New-Item $OutputFolder -ItemType Directory | Out-Null
        Write-EbookLog "Created output folder: $OutputFolder" -Level INFO
    }

    # Convert each MP3 to MP4
    $outputFiles = @()
    $index = 1

    foreach ($mp3 in $mp3s) {
        # Build output filename: EpisodeName_01_original-name.mp4
        $baseName   = [System.IO.Path]::GetFileNameWithoutExtension($mp3.Name)
        $outName    = "{0}_{1:D2}_{2}.mp4" -f $EpisodeName, $index, $baseName
        $outPath    = Join-Path $OutputFolder $outName

        Write-Host ("  [{0}/{1}] {2}" -f $index, $mp3s.Count, $mp3.Name) -ForegroundColor Cyan

        if ($DryRun) {
            Write-Host "    [DryRun] Would create: $outName" -ForegroundColor DarkGray
        } else {
            # FFmpeg: loop the cover image, mux with audio, stop when audio ends
            $ffArgs = @(
                '-y',
                '-loop', '1',
                '-i', "`"$CoverImage`"",
                '-i', "`"$($mp3.FullName)`"",
                '-c:v', 'libx264',
                '-tune', 'stillimage',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-pix_fmt', 'yuv420p',
                '-shortest',
                "`"$outPath`""
            )

            $proc = Start-Process -FilePath $ffmpeg `
                                  -ArgumentList ($ffArgs -join ' ') `
                                  -Wait -PassThru -NoNewWindow `
                                  -RedirectStandardError "$env:TEMP\ffmpeg_err.txt"

            if ($proc.ExitCode -eq 0) {
                $sizeMB = [math]::Round((Get-Item $outPath).Length / 1MB, 1)
                Write-EbookLog "Created: $outName ($sizeMB MB)" -Level SUCCESS
                $outputFiles += $outPath
            } else {
                $errText = Get-Content "$env:TEMP\ffmpeg_err.txt" -Tail 5 -ErrorAction SilentlyContinue
                Write-EbookLog "FFmpeg failed on $($mp3.Name): $errText" -Level ERROR
            }
        }
        $index++
    }

    # Combine into single episode video (optional)
    if ($Combine -and $outputFiles.Count -gt 1) {
        Write-Host "`n  Combining $($outputFiles.Count) segments into single episode..." -ForegroundColor White

        $combinedName = "{0}_FULL_EPISODE.mp4" -f $EpisodeName
        $combinedPath = Join-Path $OutputFolder $combinedName

        # Build FFmpeg concat list
        $concatFile = Join-Path $env:TEMP "ffmpeg_concat.txt"
        $outputFiles | ForEach-Object { "file '$_'" } | Set-Content $concatFile -Encoding UTF8

        if ($DryRun) {
            Write-Host "    [DryRun] Would create combined: $combinedName" -ForegroundColor DarkGray
        } else {
            $concatArgs = "-y -f concat -safe 0 -i `"$concatFile`" -c copy `"$combinedPath`""
            $proc = Start-Process -FilePath $ffmpeg `
                                  -ArgumentList $concatArgs `
                                  -Wait -PassThru -NoNewWindow `
                                  -RedirectStandardError "$env:TEMP\ffmpeg_err.txt"

            if ($proc.ExitCode -eq 0) {
                $sizeMB = [math]::Round((Get-Item $combinedPath).Length / 1MB, 1)
                Write-EbookLog "Combined episode: $combinedName ($sizeMB MB)" -Level SUCCESS
            } else {
                $errText = Get-Content "$env:TEMP\ffmpeg_err.txt" -Tail 5 -ErrorAction SilentlyContinue
                Write-EbookLog "Combine step failed: $errText" -Level ERROR
            }
        }
    }

    # Summary
    Write-Host ""
    if ($DryRun) {
        Write-EbookLog "DryRun complete. $($mp3s.Count) file(s) would be created in: $OutputFolder" -Level INFO
    } else {
        Write-EbookLog "YouTube packaging complete. Output: $OutputFolder" -Level SUCCESS
        Write-Host @"

  Next steps:
    1. Open YouTube Studio:  https://studio.youtube.com
    2. Click 'Create' -> 'Upload videos'
    3. Upload individual segments or the FULL_EPISODE file
    4. Set visibility to 'Unlisted' to share via link only,
       or 'Public' to appear in search.

"@ -ForegroundColor Cyan
    }
}

#endregion

function Invoke-Balabolka {
    <#
    .SYNOPSIS  Convert a TXT file to MP3 audio using balcon.exe and ffmpeg.
    .DESCRIPTION
        Stage 1 -- balcon.exe synthesises speech to a temporary WAV file using -w,
        which suppresses speaker playback. Progress is monitored via WAV file growth.

        Stage 2 -- ffmpeg encodes the WAV to 128k MP3, then the temp WAV is deleted.

    .PARAMETER InputFile       Path to the Balabolka-ready .txt file.
    .PARAMETER OutputFile      Path for the output .mp3 file.
    .PARAMETER Voice           TTS voice name. Default: 'Microsoft Steffan Online'.
    .PARAMETER Speed           Speech speed (-10 to +10). Default: 0.
    .PARAMETER Volume          Speech volume (0-100). Default: 100.
    .PARAMETER DictionaryFile  Path to a .dic pronunciation file.
                               Defaults to dictionaries\master_pronunciation.dic if present.
    .PARAMETER Bitrate         MP3 bitrate for ffmpeg. Default: 128k.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$InputFile,
        [Parameter(Mandatory)][string]$OutputFile,
        [string]$Voice          = 'Microsoft Steffan Online',
        [int]   $Speed          = 0,
        [int]   $Volume         = 100,
        [string]$DictionaryFile = '',
        [string]$Bitrate        = '128k'
    )

    $cfg    = Get-EbookConfig
    $balcon = Resolve-ProjectPath $cfg.paths.balcon
    $ffmpeg = $cfg.paths.ffmpeg   # may be just 'ffmpeg' (on PATH) or a full path

    if (-not (Test-Path $balcon)) {
        Write-EbookLog "Invoke-Balabolka: balcon.exe not found at: $balcon" -Level ERROR
        return $false
    }

    if (-not (Test-Path $InputFile)) {
        Write-EbookLog "Invoke-Balabolka: input file not found: $InputFile" -Level ERROR
        return $false
    }

    # Resolve dictionary
    $dictPath = ''
    if ($DictionaryFile) {
        $dictPath = $DictionaryFile
    } else {
        $defaultDic = Resolve-ProjectPath 'dictionaries\master_pronunciation.dic'
        if (Test-Path $defaultDic) { $dictPath = $defaultDic }
    }

    # Ensure output directory exists
    $outDir = Split-Path $OutputFile -Parent
    if ($outDir -and -not (Test-Path $outDir)) {
        New-Item $outDir -ItemType Directory -Force | Out-Null
    }

    # Temp WAV path (same folder as output, cleaned up in finally)
    $tempWav = [System.IO.Path]::ChangeExtension($OutputFile, '.tmp.wav')

    Write-EbookLog "Balabolka: voice=$Voice  speed=$Speed  volume=$Volume"
    if ($dictPath) { Write-EbookLog "Balabolka: dictionary=$dictPath" }
    Write-EbookLog "Balabolka: $InputFile -> $OutputFile"

    try {
        # Stage 1: TTS -> WAV (no speaker output -- -w suppresses playback)
        $balconArgs = @('-f', "`"$InputFile`"", '-w', "`"$tempWav`"",
                        '-n', "`"$Voice`"", '-s', $Speed, '-v', $Volume)
        if ($dictPath) { $balconArgs += '-d', "`"$dictPath`"" }

        $errFile   = Join-Path $env:TEMP 'balcon_err.txt'
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

        $proc = Start-Process -FilePath $balcon `
                              -ArgumentList ($balconArgs -join ' ') `
                              -PassThru -NoNewWindow `
                              -RedirectStandardError $errFile

        while (-not $proc.HasExited) {
            Start-Sleep -Seconds 3
            $sizeMB = if (Test-Path $tempWav) {
                [math]::Round((Get-Item $tempWav).Length / 1MB, 1)
            } else { 0 }
            Write-EbookLog "Balabolka: synthesising... ($sizeMB MB)"
        }

        if ($proc.ExitCode -ne 0) {
            $errText = if (Test-Path $errFile) { Get-Content $errFile -Raw } else { '(no stderr)' }
            Write-EbookLog "Balabolka: balcon failed (exit $($proc.ExitCode)) -- $errText" -Level ERROR
            return $false
        }

        $wavMB = [math]::Round((Get-Item $tempWav).Length / 1MB, 1)
        Write-EbookLog "Balabolka: synthesis done -- WAV $wavMB MB in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 1))s"

        # Stage 2: WAV -> MP3 via ffmpeg
        Write-EbookLog "Balabolka: encoding MP3..."
        $ffmpegArgs = "-y -i `"$tempWav`" -b:a $Bitrate -loglevel error `"$OutputFile`""
        $ffErrFile  = Join-Path $env:TEMP 'ffmpeg_err.txt'

        $ffProc = Start-Process -FilePath $ffmpeg `
                                -ArgumentList $ffmpegArgs `
                                -Wait -PassThru -NoNewWindow `
                                -RedirectStandardError $ffErrFile

        if ($ffProc.ExitCode -ne 0) {
            $errText = if (Test-Path $ffErrFile) { Get-Content $ffErrFile -Raw } else { '(no stderr)' }
            Write-EbookLog "Balabolka: ffmpeg failed (exit $($ffProc.ExitCode)) -- $errText" -Level ERROR
            return $false
        }

        $elapsed = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
        $mp3MB   = if (Test-Path $OutputFile) { [math]::Round((Get-Item $OutputFile).Length / 1MB, 2) } else { '?' }
        Write-EbookLog "Balabolka: done -- $OutputFile ($mp3MB MB, ${elapsed}s total)"
        return $true

    } catch {
        Write-EbookLog "Balabolka: exception -- $_" -Level ERROR
        return $false
    } finally {
        if (Test-Path $tempWav) { Remove-Item $tempWav -Force -ErrorAction SilentlyContinue }
    }
}

#region -- Claude API integration --------------------------------------------

function Send-ToClaudeAPI {
    <#
    .SYNOPSIS  Send a single-turn message to the Anthropic Messages API.
    .DESCRIPTION
        General-purpose wrapper around POST /v1/messages. Reads the API key from
        $env:ANTHROPIC_API_KEY -- never logs or exposes the key value.
    .PARAMETER SystemPrompt
        The system message to prefix the conversation with.
    .PARAMETER UserMessage
        The user turn content.
    .PARAMETER Model
        Claude model ID. Defaults to claude-sonnet-4-6.
    .PARAMETER MaxTokens
        Maximum tokens in the response. Defaults to 4096.
    .OUTPUTS
        The response text string, or $null on failure.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$SystemPrompt,
        [Parameter(Mandatory)] [string]$UserMessage,
        [string]$Model     = 'claude-sonnet-4-6',
        [int]   $MaxTokens = 4096
    )

    if (-not $env:ANTHROPIC_API_KEY) {
        Write-EbookLog 'Claude API: ANTHROPIC_API_KEY is not set -- cannot call API' -Level ERROR
        return $null
    }

    $body = @{
        model      = $Model
        max_tokens = $MaxTokens
        system     = $SystemPrompt
        messages   = @(
            @{ role = 'user'; content = $UserMessage }
        )
    } | ConvertTo-Json -Depth 6

    $headers = @{
        'x-api-key'         = $env:ANTHROPIC_API_KEY
        'anthropic-version' = '2023-06-01'
        'Content-Type'      = 'application/json'
    }

    try {
        Write-EbookLog "Claude API: calling model=$Model maxTokens=$MaxTokens"
        $response = Invoke-RestMethod `
            -Uri     'https://api.anthropic.com/v1/messages' `
            -Method  POST `
            -Headers $headers `
            -Body    $body `
            -ErrorAction Stop

        $inputTok  = $response.usage.input_tokens
        $outputTok = $response.usage.output_tokens
        Write-EbookLog "Claude API: done -- input=$inputTok tokens, output=$outputTok tokens"

        # Extract the first text content block
        $textBlock = $response.content | Where-Object { $_.type -eq 'text' } | Select-Object -First 1
        if (-not $textBlock) {
            Write-EbookLog 'Claude API: response contained no text block' -Level WARN
            return $null
        }
        return $textBlock.text

    } catch {
        Write-EbookLog "Claude API: request failed -- $_" -Level ERROR
        return $null
    }
}

function Get-ChapterStructure {
    <#
    .SYNOPSIS  Use Claude to identify chapter/part titles with font-based pre-analysis.
    .DESCRIPTION
        Runs font-based heading detection on the source file, then sends three-zone
        text samples + font candidates to Claude for chapter confirmation.
    .PARAMETER TextContent
        The full extracted text of a book.
    .PARAMETER InputFile
        Path to the source PDF/EPUB. Required for font-based detection.
    .OUTPUTS
        An array of objects with 'level' and 'title' properties, or $null on failure.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$TextContent,
        [string]$InputFile
    )

    # -- Step 1: Run font-based heading detection (if source file provided)
    $fontCandidatesSection = ""
    if ($InputFile -and (Test-Path $InputFile)) {
        $cfg    = Get-EbookConfig
        $python = $cfg.paths.python
        $detectScript = Join-Path $script:ModuleRoot 'tools\detect_headings_font.py'

        if (Test-Path $detectScript) {
            Write-EbookLog "Chapter detection: running font-based heading analysis..."
            try {
                $fontJsonRaw = & $python $detectScript --input "$InputFile" --format json 2>$null
                $fontJson = if ($fontJsonRaw -is [array]) { $fontJsonRaw -join "`n" } else { $fontJsonRaw }
                if ($fontJson) {
                    $fontResult = $fontJson | ConvertFrom-Json
                    $candidates = $fontResult.heading_candidates
                    if ($candidates -and $candidates.Count -gt 0) {
                        Write-EbookLog "Chapter detection: font analysis found $($candidates.Count) heading candidates"
                        $lines = @()
                        $lines += "=== FONT-DETECTED HEADING CANDIDATES ==="
                        $lines += "The following headings were detected from font analysis of the full document."
                        $lines += "Confirm which are real chapter/section headings, flag false positives, and note any chapters in the text samples not in this list."
                        $lines += ""
                        foreach ($c in $candidates) {
                            $sizeStr = if ($c.font_size) { "$($c.font_size)pt" } else { "" }
                            $boldStr = if ($c.is_bold) { " bold" } else { "" }
                            $detail  = if ($sizeStr) { " ($sizeStr$boldStr)" } else { "" }
                            $lines += "  $($c.level)  p.$($c.page)  [$($c.confidence)] `"$($c.text)`"$detail"
                        }
                        $fontCandidatesSection = $lines -join "`n"
                    } else {
                        Write-EbookLog "Chapter detection: font analysis found 0 candidates -- Claude will search text only"
                    }
                }
            } catch {
                Write-EbookLog "Chapter detection: font analysis failed ($_) -- continuing without font candidates" -Level WARN
            }
        }
    }

    # -- Step 2: Build three-zone text samples
    $words = $TextContent -split '\s+'
    $totalWords = $words.Count

    if ($totalWords -lt 9000) {
        $sample = $TextContent
        Write-EbookLog "Chapter detection: short book ($totalWords words) -- sending full text to Claude"
    } else {
        $sampleParts = [System.Collections.Generic.List[string]]::new()

        # Zone 1: Front matter (first 3000 words)
        $zone1 = ($words[0..2999]) -join ' '
        $sampleParts.Add("=== FRONT MATTER (first 3000 words) ===`n$zone1")

        # Zone 2: 8 body samples at 10%-80%
        for ($i = 0; $i -lt 8; $i++) {
            $pct = 0.10 + $i * 0.10
            $startWord = [Math]::Floor($totalWords * $pct)
            $endWord = [Math]::Min($startWord + 499, $totalWords - 1)
            $pageEstimate = [Math]::Floor($pct * 100)
            $chunk = ($words[$startWord..$endWord]) -join ' '
            $sampleParts.Add("=== BODY SAMPLE $($i + 1) (~${pageEstimate}% through book) ===`n$chunk")
        }

        # Zone 3: Back matter (last 2000 words)
        $backStart = [Math]::Max(0, $totalWords - 2000)
        $zone3 = ($words[$backStart..($totalWords - 1)]) -join ' '
        $sampleParts.Add("=== BACK MATTER (last 2000 words) ===`n$zone3")

        $sample = $sampleParts -join "`n`n"
        Write-EbookLog "Chapter detection: three-zone sampling ($totalWords words total) -- sending ~9000 words to Claude"
    }

    # -- Step 3: Build Claude prompt
    $systemPrompt = @"
You are analyzing an ebook to build its table of contents. Identify the CHAPTER STRUCTURE.

PRIORITY ORDER:
1. MAIN CHAPTERS - numbered or titled divisions of core content
2. MAJOR SECTIONS - Parts containing chapters
3. FRONT MATTER - Preface, Foreword, Introduction, Acknowledgments
4. BACK MATTER - Notes, Bibliography, Index, Appendix (mark is_back_matter: true)

DO NOT treat as chapter headings:
- Running headers/footers repeated on every page
- Section sub-headings within a chapter
- Decorative text, epigraphs, pull quotes
- List items or numbered points within body text

Respond with a raw JSON array (no markdown fences). Each entry:
{"title": "exact heading text", "level": 1, "is_back_matter": false, "page_estimate": 45, "confidence": 0.95, "notes": "optional"}

Rules:
- level 1 = Part, Book, or Volume headings (top-level divisions containing chapters)
- level 2 = Chapters, Prologue, Epilogue, Introduction, Foreword, Preface, Afterword, Conclusion, Appendix
- level 3 = Sub-sections within a chapter (only include if clearly structured)
- Most books have 0-5 level-1 entries and 5-30 level-2 entries
- A book with 10 chapters should have >= 10 level-2 entries
- If the book has no Parts/Volumes, use level 2 for all chapter headings (no level 1)
- Preserve exact capitalization and numbering from the source
- If font candidates are provided below, use them as the primary guide and ADD any chapters you find in the text that the font analysis missed
- If no font candidates are provided, identify headings from the text samples only
- Mark back matter sections (Notes, Bibliography, Index, Appendix) with is_back_matter: true
"@

    $userContent = ""
    if ($fontCandidatesSection) {
        $userContent += "$fontCandidatesSection`n`n"
    }
    $userContent += "TEXT SAMPLES:`n`n$sample"

    Write-EbookLog "Chapter detection: sending to Claude API..."
    $raw = Send-ToClaudeAPI -SystemPrompt $systemPrompt -UserMessage $userContent

    if ($null -eq $raw) {
        Write-EbookLog 'Chapter detection: API call failed -- returning null' -Level ERROR
        return $null
    }

    # -- Step 4: Parse JSON response (handle prose before/after fenced JSON)
    if ($raw -match '(?s)```(?:json)?\s*(\[.*?\])\s*```') {
        $json = $Matches[1]
    } else {
        $json = $raw -replace '(?s)^```(?:json)?\s*', '' -replace '\s*```\s*$', ''
    }
    $json = $json.Trim()

    try {
        $chapters = $json | ConvertFrom-Json
        Write-EbookLog "Chapter detection: found $($chapters.Count) heading(s)" -Level SUCCESS
        return $chapters
    } catch {
        Write-EbookLog "Chapter detection: failed to parse JSON response -- $_" -Level ERROR
        Write-EbookLog "Chapter detection: raw response was: $($json.Substring(0, [Math]::Min(200, $json.Length)))" -Level ERROR
        return $null
    }
}

#endregion

#region -- Test harness --------------------------------------------------------

function Test-EbookPipeline {
    <#
    .SYNOPSIS
        Run the pdfminer HTML extraction regression test suite.
    .PARAMETER TestName
        Name of a specific test to run (default: all).
    .PARAMETER Quick
        Skip KFX conversion, only validate HTML output.
    .PARAMETER List
        List available test case names and exit.
    #>
    [CmdletBinding()]
    param(
        [string]$TestName,
        [switch]$Quick,
        [switch]$List
    )

    $pythonPath = (Get-EbookConfig).paths.python
    if (-not $pythonPath) { $pythonPath = "python" }
    $testScript = Join-Path $script:ModuleRoot "tools" "test_pipeline.py"

    if (-not (Test-Path $testScript)) {
        Write-EbookLog "Test harness not found: $testScript" -Level ERROR
        return $false
    }

    $pyArgs = "`"$testScript`""
    if ($TestName) { $pyArgs += " `"$TestName`"" }
    if ($Quick)    { $pyArgs += " --quick" }
    if ($List)     { $pyArgs += " --list" }

    Write-EbookLog "Running pipeline tests..."
    $proc = Start-Process -FilePath $pythonPath -ArgumentList $pyArgs `
                          -NoNewWindow -Wait -PassThru
    return ($proc.ExitCode -eq 0)
}

function Test-ConversionQuality {
    <#
    .SYNOPSIS
        Run visual QA on a converted ebook using Claude Vision API.
    .DESCRIPTION
        Converts the output file (KFX, AZW3, EPUB) to a paginated PDF via Calibre,
        renders sampled pages to PNG, and sends them to the Claude Vision API for
        structured evaluation against a visual quality rubric.

        Returns a report object and writes a _visual_qa_report.json file alongside
        the input file.

        Requires: Calibre, poppler (in tools\poppler), ANTHROPIC_API_KEY env var.
    .PARAMETER InputFile
        Path to the KFX, AZW3, or EPUB file to evaluate.
    .PARAMETER OutputDir
        Directory for the report JSON. Defaults to same directory as InputFile.
    .PARAMETER DPI
        PNG rendering resolution. Default: 100 (quick mode). Use -FullVQA for 150.
    .PARAMETER MaxPages
        Maximum pages to sample. Default: 8 (quick mode). Use -FullVQA for 20.
    .PARAMETER RubricPath
        Path to the rubric prompt template. Default: tools\visual_qa_rubric.md.
    .PARAMETER Model
        Claude model to use for evaluation. Default: claude-sonnet-4-6.
    .PARAMETER FullVQA
        Use full evaluation mode (20 pages at 150 DPI). Default is quick mode (8 pages at 100 DPI).
    .PARAMETER PassThreshold
        Minimum score to consider a pass. Default: 70.
    .EXAMPLE
        Test-ConversionQuality -InputFile "output\kindle\Author - Title.kfx"
    .EXAMPLE
        Get-ChildItem output\kindle\*.kfx | ForEach-Object {
            Test-ConversionQuality -InputFile $_.FullName
        }
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, ValueFromPipelineByPropertyName)]
        [Alias('FullName')]
        [string]$InputFile,

        [string]$OutputDir,
        [int]$DPI = 100,
        [int]$MaxPages = 8,
        [string]$RubricPath,
        [string]$Model = 'claude-sonnet-4-6',
        [int]$PassThreshold = 70,
        [switch]$FullVQA
    )

    $config = Get-EbookConfig
    $pythonPath = $config.paths.python
    if (-not $pythonPath) { $pythonPath = "python" }

    $qaScript = Join-Path (Join-Path $script:ModuleRoot "tools") "visual_qa.py"
    if (-not (Test-Path $qaScript)) {
        Write-EbookLog "Visual QA script not found: $qaScript" -Level ERROR
        return $null
    }

    if (-not (Test-Path $InputFile)) {
        Write-EbookLog "Input file not found: $InputFile" -Level ERROR
        return $null
    }

    # Build arguments
    $pyArgs = @("`"$qaScript`"", "--input", "`"$InputFile`"")

    if ($OutputDir) {
        $pyArgs += @("--output-dir", "`"$OutputDir`"")
    }
    if ($DPI -ne 100) {
        $pyArgs += @("--dpi", $DPI)
    }
    if ($MaxPages -ne 8) {
        $pyArgs += @("--max-pages", $MaxPages)
    }
    if ($FullVQA) {
        $pyArgs += "--full"
    }
    if ($Model -ne 'claude-sonnet-4-6') {
        $pyArgs += @("--model", $Model)
    }
    if ($PassThreshold -ne 70) {
        $pyArgs += @("--pass-threshold", $PassThreshold)
    }
    if ($RubricPath) {
        $pyArgs += @("--rubric", "`"$RubricPath`"")
    }

    $pyArgs += "--verbose"

    Write-EbookLog "Running visual QA on: $(Split-Path $InputFile -Leaf)"

    try {
        # Unique temp paths to prevent collision with concurrent VQA runs
        $vqaGuid   = [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
        $vqaStdout = Join-Path $env:TEMP "vqa_stdout_$vqaGuid.txt"
        $vqaStderr = Join-Path $env:TEMP "vqa_stderr_$vqaGuid.txt"

        $argString = $pyArgs -join ' '
        $proc = Start-Process -FilePath $pythonPath -ArgumentList $argString `
                              -NoNewWindow -Wait -PassThru `
                              -RedirectStandardOutput $vqaStdout `
                              -RedirectStandardError $vqaStderr

        $stdout = ""
        $stderr = ""
        if (Test-Path $vqaStdout) {
            $stdout = Get-Content $vqaStdout -Raw -ErrorAction SilentlyContinue
            Remove-Item $vqaStdout -ErrorAction SilentlyContinue
        }
        if (Test-Path $vqaStderr) {
            $stderr = Get-Content $vqaStderr -Raw -ErrorAction SilentlyContinue
            Remove-Item $vqaStderr -ErrorAction SilentlyContinue
        }

        # Log stderr (verbose progress)
        if ($stderr) {
            foreach ($line in ($stderr -split "`n")) {
                $trimmed = $line.Trim()
                if ($trimmed) {
                    Write-EbookLog "  [VQA] $trimmed"
                }
            }
        }

        if ($proc.ExitCode -eq 2) {
            Write-EbookLog "Visual QA failed (see errors above)" -Level ERROR
            return $null
        }

        # Parse summary from stdout
        $summary = $null
        if ($stdout) {
            try {
                $summary = $stdout | ConvertFrom-Json
            } catch {
                Write-EbookLog "Could not parse VQA summary JSON" -Level WARN
            }
        }

        if ($summary) {
            $scoreMsg = "Visual QA: $($summary.overall_score)/100"
            if ($summary.overall_pass) {
                $scoreMsg += " (PASS)"
                Write-EbookLog $scoreMsg
            } else {
                $scoreMsg += " (FAIL)"
                Write-EbookLog $scoreMsg -Level WARN
            }
            if ($summary.summary) {
                Write-EbookLog "  Summary: $($summary.summary)"
            }
            Write-EbookLog "  Cost: `$$($summary.estimated_cost_usd)"
        }

        return $summary

    } catch {
        Write-EbookLog "Visual QA error: $_" -Level ERROR
        return $null
    }
}

#endregion

#region -- Converge Loop -----------------------------------------------------

function Invoke-ConvergeLoop {
    <#
    .SYNOPSIS
        Convert an ebook with autonomous quality improvement.
    .DESCRIPTION
        Runs the converge loop: convert -> evaluate via VQA -> check exit conditions ->
        optionally shift extraction strategy -> repeat. Delivers the highest-scoring
        version of the book plus a diagnostic report.

        Exit conditions:
        - Score >= target: PASS — book meets quality standards
        - Score improved < stall_threshold from previous: CEILING — quality plateau reached
        - Max iterations reached: BUDGET — fix budget exhausted
        - No alternate strategy available: CEILING — all paths tried

        Each iteration is recorded in the pattern database. The final report includes
        score progression, costs, timing, and recommendations.
    .PARAMETER InputFile
        Path to the source ebook (PDF, EPUB, MOBI, AZW).
    .PARAMETER MaxIterations
        Maximum conversion+evaluation cycles. Default: 4.
    .PARAMETER TargetScore
        Minimum VQA score to accept as passing. Default: 85.
    .PARAMETER StallThreshold
        Minimum score improvement required between iterations. If the score improves
        by less than this, the loop stops (quality ceiling reached). Default: 3.
    .PARAMETER OutputDir
        Directory for the final KFX output. Defaults to kindle output path from settings.json.
    .PARAMETER CostLimit
        Maximum total API cost (USD) before stopping. Default: 2.00.
    .EXAMPLE
        Invoke-ConvergeLoop -InputFile "inbox\book.pdf"
    .EXAMPLE
        Invoke-ConvergeLoop -InputFile "inbox\book.pdf" -TargetScore 90 -MaxIterations 3
    .EXAMPLE
        Get-ChildItem inbox\*.pdf | ForEach-Object {
            Invoke-ConvergeLoop -InputFile $_.FullName
        }
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0, ValueFromPipelineByPropertyName)]
        [Alias('FullName')]
        [string]$InputFile,

        [int]$MaxIterations = 4,
        [int]$TargetScore = 85,
        [int]$StallThreshold = 3,
        [string]$OutputDir,
        [double]$CostLimit = 2.00
    )

    # ── Step 1: Setup ────────────────────────────────────────────────────────
    $cfg = Get-EbookConfig

    # Load converge_loop settings from config (with fallbacks)
    $clCfg = $cfg.converge_loop
    if ($clCfg) {
        if (-not $PSBoundParameters.ContainsKey('MaxIterations') -and $clCfg.max_iterations) {
            $MaxIterations = $clCfg.max_iterations
        }
        if (-not $PSBoundParameters.ContainsKey('TargetScore') -and $clCfg.target_score) {
            $TargetScore = $clCfg.target_score
        }
        if (-not $PSBoundParameters.ContainsKey('StallThreshold') -and $clCfg.stall_threshold) {
            $StallThreshold = $clCfg.stall_threshold
        }
        if (-not $PSBoundParameters.ContainsKey('CostLimit') -and $clCfg.cost_limit_per_book_usd) {
            $CostLimit = $clCfg.cost_limit_per_book_usd
        }
    }

    if (-not (Test-Path $InputFile)) {
        Write-EbookLog "ConvergeLoop: input file not found: $InputFile" -Level ERROR
        return $null
    }

    $fileName = Split-Path $InputFile -Leaf
    $ext      = [System.IO.Path]::GetExtension($InputFile).TrimStart('.').ToLower()

    Write-EbookLog "==================================================================" -Level INFO
    Write-EbookLog "CONVERGE LOOP: $fileName" -Level INFO
    Write-EbookLog "  Target: $TargetScore/100 | Max iterations: $MaxIterations | Stall: +$StallThreshold | Cost cap: `$$CostLimit" -Level INFO
    Write-EbookLog "==================================================================" -Level INFO

    $loopStart     = Get-Date
    $iterations    = @()   # Array of iteration result hashtables
    $totalCost     = 0.0
    $bestScore     = 0
    $bestIteration = 0
    $bestOutputPath = ""
    $exitReason    = "unknown"
    $lastVqaReportPath = ""   # VQA report from previous iteration for fix engine
    $cachedChapterHints = $null  # Chapter hints JSON cached from iteration 1 for reuse

    # ── Step 1b: Pre-flight source classification ───────────────────────────
    $python   = $cfg.paths.python
    $toolsDir = Join-Path $script:ModuleRoot "tools"

    $classification = $null
    if ($ext -eq 'pdf') {
        Write-EbookLog "ConvergeLoop: classifying source PDF..."
        try {
            $classifyScript = Join-Path $script:ModuleRoot "tools" "classify_source.py"
            $classifyResult = & $python $classifyScript --input "$InputFile" 2>$null
            if ($classifyResult) {
                $classifyJson = $classifyResult -join "`n"
                $classification = $classifyJson | ConvertFrom-Json
                Write-EbookLog "ConvergeLoop: source classified as $($classification.classification) (confidence: $($classification.confidence))"
                Write-EbookLog "  Text density: $($classification.signals.text_density_per_page) chars/page"
                Write-EbookLog "  File size/page: $($classification.signals.file_size_per_page_kb) KB"
                Write-EbookLog "  Recommended strategies: $($classification.recommended_strategies -join ' -> ')"

                if ($classification.flags.needs_ocr) {
                    Write-EbookLog "  WARNING: Source needs OCR - text layer is empty or unusable" -Level WARN
                }
                if ($classification.flags.likely_two_column) {
                    Write-EbookLog "  Detected: likely two-column layout"
                }
            }
        } catch {
            Write-EbookLog "ConvergeLoop: source classification failed (non-blocking) -- $_" -Level WARN
        }
    }

    # ── Step 1c: Smart strategy selection from historical data ────────────
    $dbRecommendation = $null
    $autoClaudeChapters = $false
    if ($ext -eq 'pdf') {
        try {
            $sourceTypeArg = if ($classification) { "'$($classification.classification)'" } else { "None" }
            $recScript = @"
import sys, json
sys.path.insert(0, r'$toolsDir')
from pattern_db import get_recommended_strategy
result = get_recommended_strategy(
    source_file_path=r'$InputFile',
    source_type=$sourceTypeArg,
    format='pdf'
)
print(json.dumps(result))
"@
            $recResult = & $python -c $recScript 2>$null
            if ($recResult) {
                $dbRecommendation = ($recResult -join "`n") | ConvertFrom-Json
                if ($dbRecommendation.source -ne 'default') {
                    Write-EbookLog "ConvergeLoop: database recommendation ($($dbRecommendation.source)):"
                    Write-EbookLog "  Strategy: $($dbRecommendation.strategy_order -join ' -> ')"
                    Write-EbookLog "  Reason: $($dbRecommendation.reason)"
                    Write-EbookLog "  Confidence: $($dbRecommendation.confidence)"
                    if ($dbRecommendation.flags.UseClaudeChapters) {
                        Write-EbookLog "  Auto-enabling: -UseClaudeChapters (no chapters in prior runs)"
                    }
                } else {
                    Write-EbookLog "ConvergeLoop: no historical data for this book - using classification"
                }
            }
        } catch {
            Write-EbookLog "ConvergeLoop: strategy recommendation failed (non-blocking) -- $_" -Level WARN
        }
    }

    # ── Step 2: Define strategy sequence (layered priority) ───────────────
    # Priority 1: Database recommendation (if confidence >= 0.5)
    # Priority 2: Classification recommendation (from classify_source.py)
    # Priority 3: Default hardcoded order

    $strategies     = @()
    $strategySource = 'default (no data)'

    # Helper to build strategy hashtable from a path name
    # (used by all three priority levels)
    function _BuildStrategyFromPath {
        param([string]$PathName)
        switch ($PathName) {
            'html_extraction' {
                return @{
                    Name        = "HTML extraction (pdfminer)"
                    Flags       = @{ UseHtmlExtraction = $true }
                    Description = "Font-metadata semantic HTML extraction"
                }
            }
            'legacy' {
                return @{
                    Name        = "Legacy extraction (pypdf)"
                    Flags       = @{ UseHtmlExtraction = $false; ForceColumns = $false }
                    Description = "Standard pypdf text extraction with Markdown headings"
                }
            }
            'column_aware' {
                return @{
                    Name        = "Column-aware extraction"
                    Flags       = @{ ForceColumns = $true }
                    Description = "PyMuPDF multi-column extraction for academic/commentary layouts"
                }
            }
            'ocr' {
                return @{
                    Name        = "OCR extraction (Tesseract)"
                    Flags       = @{ UseOCR = $true }
                    Description = "Tesseract OCR for scanned pages with no text layer"
                }
            }
            'epub_html' {
                return @{
                    Name        = "EPUB HTML extraction"
                    Flags       = @{}
                    Description = "Extract and merge EPUB chapter HTML preserving formatting"
                }
            }
            'direct' {
                return @{
                    Name        = "Direct conversion"
                    Flags       = @{ DirectConversion = $true }
                    Description = "Send raw file straight to Calibre without extraction"
                }
            }
        }
    }

    if ($dbRecommendation -and $dbRecommendation.confidence -ge 0.5 -and
        $dbRecommendation.strategy_order -and $dbRecommendation.strategy_order.Count -gt 0) {
        # Priority 1: Database recommendation
        foreach ($strat in $dbRecommendation.strategy_order) {
            $s = _BuildStrategyFromPath $strat
            if ($s) { $strategies += $s }
        }
        $strategySource = "database ($($dbRecommendation.source))"

        if ($dbRecommendation.flags.UseClaudeChapters) {
            $autoClaudeChapters = $true
        }

    } elseif ($classification -and $classification.recommended_strategies) {
        # Priority 2: Classification recommendation
        foreach ($strat in $classification.recommended_strategies) {
            $s = _BuildStrategyFromPath $strat
            if ($s) { $strategies += $s }
        }
        $strategySource = "classification ($($classification.classification))"

    } elseif ($ext -eq 'pdf') {
        # Priority 3: Default order for PDFs
        $strategies += @{
            Name        = "HTML extraction (pdfminer)"
            Flags       = @{ UseHtmlExtraction = $true }
            Description = "Font-metadata semantic HTML extraction"
        }
        $strategies += @{
            Name        = "Legacy extraction (pypdf)"
            Flags       = @{ UseHtmlExtraction = $false; ForceColumns = $false }
            Description = "Standard pypdf text extraction with Markdown headings"
        }
        $strategies += @{
            Name        = "Column-aware extraction"
            Flags       = @{ ForceColumns = $true }
            Description = "PyMuPDF multi-column extraction for academic/commentary layouts"
        }
    } elseif ($ext -eq 'epub') {
        # EPUB gets HTML extraction first, then direct fallback
        $strategies += @{
            Name        = "EPUB HTML extraction"
            Flags       = @{}
            Description = "Extract and merge EPUB chapter HTML preserving formatting"
        }
        $strategies += @{
            Name        = "Direct conversion"
            Flags       = @{ DirectConversion = $true }
            Description = "Send raw EPUB straight to Calibre without extraction"
        }
    } else {
        # MOBI/AZW — only one path (direct to Calibre)
        $strategies += @{
            Name        = "Direct conversion"
            Flags       = @{ DirectConversion = $true }
            Description = "Native format straight to Calibre"
        }
    }

    Write-EbookLog "ConvergeLoop: strategy source: $strategySource"
    Write-EbookLog "ConvergeLoop: sequence: $($strategies.Name -join ' -> ')"

    # For non-PDFs, max iterations is effectively 1 (no alternate strategies)
    $effectiveMax = [Math]::Min($MaxIterations, $strategies.Count)

    # ── Step 3: The Loop ─────────────────────────────────────────────────────
    for ($iter = 1; $iter -le $effectiveMax; $iter++) {
        $strategy  = $strategies[$iter - 1]
        $iterStart = Get-Date

        Write-EbookLog "------------------------------------------------------------------" -Level INFO
        Write-EbookLog "ITERATION $iter/$effectiveMax - $($strategy.Name)" -Level INFO
        Write-EbookLog "  Strategy: $($strategy.Description)" -Level INFO
        Write-EbookLog "------------------------------------------------------------------" -Level INFO

        # --- Convert ---
        $convertParams = @{
            InputFile = $InputFile
            NoCache   = $true   # Always fresh conversion in converge loop
        }
        if ($OutputDir) { $convertParams['OutputDir'] = $OutputDir }

        # Pass VQA report from previous iteration for targeted fix engine corrections
        if ($lastVqaReportPath -and (Test-Path $lastVqaReportPath)) {
            $convertParams['VqaReportPath'] = $lastVqaReportPath
        }

        # Auto-enable Claude chapter detection for PDFs (~$0.05, dramatically improves TOC)
        # Enabled by default when API key is available, reinforced by database recommendation
        if ($ext -eq 'pdf' -and ($env:ANTHROPIC_API_KEY -or $autoClaudeChapters)) {
            if ($cachedChapterHints -and (Test-Path $cachedChapterHints)) {
                # Reuse cached hints from iteration 1 — skip Claude API call
                $convertParams['ChapterHintsFile'] = $cachedChapterHints
                Write-EbookLog "  Using cached chapter hints from iteration 1"
            } elseif ($env:ANTHROPIC_API_KEY) {
                # First iteration — let Claude detect chapters
                $convertParams['UseClaudeChapters'] = $true
            }
        }

        # Apply strategy-specific flags
        foreach ($flag in $strategy.Flags.GetEnumerator()) {
            $convertParams[$flag.Key] = $flag.Value
        }

        $convertOk = Convert-ToKindle @convertParams

        # Capture chapter hints from iteration 1 for reuse in subsequent iterations
        if (-not $cachedChapterHints -or -not (Test-Path $cachedChapterHints)) {
            $hintsCandidate = Get-ChildItem $env:TEMP -Filter 'kindle_hints_*.json' -File -ErrorAction SilentlyContinue |
                              Where-Object { $_.LastWriteTime -gt $iterStart } |
                              Sort-Object LastWriteTime -Descending |
                              Select-Object -First 1
            if ($hintsCandidate) {
                $cachedChapterHints = Join-Path $env:TEMP "converge_chapters_$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).json"
                Copy-Item $hintsCandidate.FullName $cachedChapterHints -Force
                Write-EbookLog "  Cached chapter hints for reuse: $cachedChapterHints"
            }
        }
        if (-not $convertOk) {
            Write-EbookLog "  Iteration $iter`: conversion FAILED - skipping to next strategy" -Level WARN
            $iterations += @{
                Iteration = $iter
                Strategy  = $strategy.Name
                Score     = 0
                Pass      = $false
                Cost      = 0
                Duration  = [math]::Round(((Get-Date) - $iterStart).TotalSeconds, 1)
                Error     = "Conversion failed"
            }
            continue
        }

        # --- Find the output file ---
        $kindleDir = if ($OutputDir) { $OutputDir } else {
            Resolve-ProjectPath ($cfg.paths.kindle)
        }
        $outFile = $null
        # Find the most recently modified KFX in the output dir written after iteration started
        $recentKfx = Get-ChildItem -Path $kindleDir -Filter '*.kfx' -File -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTime -Descending |
                     Select-Object -First 1
        if ($recentKfx -and $recentKfx.LastWriteTime -gt $iterStart.AddSeconds(-5)) {
            $outFile = $recentKfx.FullName
        }

        if (-not $outFile -or -not (Test-Path $outFile)) {
            Write-EbookLog "  Iteration $iter`: output file not found after conversion" -Level WARN
            $iterations += @{
                Iteration = $iter
                Strategy  = $strategy.Name
                Score     = 0
                Pass      = $false
                Cost      = 0
                Duration  = [math]::Round(((Get-Date) - $iterStart).TotalSeconds, 1)
                Error     = "Output file not found"
            }
            continue
        }

        # --- Evaluate via VQA (always quick — full adds cost without diagnostic value) ---
        Write-EbookLog "  Running VQA evaluation (quick)..." -Level INFO
        $vqaParams = @{
            InputFile     = $outFile
            PassThreshold = $TargetScore
        }
        $vqaResult = Test-ConversionQuality @vqaParams

        # Save VQA report path for next iteration's fix engine
        $vqaReportFile = Join-Path (Split-Path $outFile) (
            [System.IO.Path]::GetFileNameWithoutExtension($outFile) + '_visual_qa_report.json'
        )
        if (Test-Path $vqaReportFile) {
            $lastVqaReportPath = $vqaReportFile
        }

        $iterScore = 0
        $iterCost  = 0
        $iterPass  = $false

        if ($vqaResult) {
            $iterScore = [int]$vqaResult.overall_score
            $iterPass  = [bool]$vqaResult.overall_pass
            $iterCost  = if ($vqaResult.estimated_cost_usd) { [double]$vqaResult.estimated_cost_usd } else { 0 }
        } else {
            Write-EbookLog "  Iteration $iter`: VQA returned no result" -Level WARN
        }

        # Content density sanity check — don't trust high scores on empty content
        if ($iterScore -ge 90 -and $classification) {
            if ($classification.classification -in @('scan_no_text', 'scan_with_text') -and
                $classification.signals.text_density_per_page -lt 200) {
                Write-EbookLog "ConvergeLoop: HIGH SCORE ($iterScore) on LOW-DENSITY source - likely empty content, not a real pass" -Level WARN
                $iterScore = 0
                $iterPass  = $false
            }
        }

        $totalCost   += $iterCost
        $iterDuration = [math]::Round(((Get-Date) - $iterStart).TotalSeconds, 1)

        # Track best result
        if ($iterScore -gt $bestScore) {
            $bestScore      = $iterScore
            $bestIteration  = $iter
            $bestOutputPath = $outFile
        }

        $iterations += @{
            Iteration      = $iter
            Strategy       = $strategy.Name
            Score          = $iterScore
            Pass           = $iterPass
            Cost           = $iterCost
            Duration       = $iterDuration
            OutputPath     = $outFile
            CategoryScores = if ($vqaResult -and $vqaResult.category_scores) {
                $vqaResult.category_scores
            } else { $null }
        }

        $resultLevel = if ($iterPass) { 'SUCCESS' } else { 'INFO' }
        Write-EbookLog "  Result: $iterScore/100 $(if ($iterPass) {'(PASS)'} else {'(FAIL)'}) | Cost: `$$([math]::Round($iterCost, 2)) | Time: ${iterDuration}s" -Level $resultLevel

        # --- Check exit conditions ---

        # EXIT: Score meets target
        if ($iterPass) {
            $exitReason = "PASS"
            Write-EbookLog "  EXIT: Score $iterScore >= target $TargetScore - PASS" -Level SUCCESS
            break
        }

        # EXIT: Score stalled (not enough improvement from previous iteration)
        if ($iter -gt 1) {
            $prevScore   = $iterations[$iter - 2].Score
            $improvement = $iterScore - $prevScore
            if ($improvement -lt $StallThreshold -and $improvement -ge 0) {
                $exitReason = "CEILING"
                Write-EbookLog "  EXIT: Score improved only +$improvement (threshold: +$StallThreshold) - quality ceiling reached" -Level WARN
                break
            }
        }

        # EXIT: Cost limit reached
        if ($totalCost -ge $CostLimit) {
            $exitReason = "COST"
            Write-EbookLog "  EXIT: Total cost `$$([math]::Round($totalCost, 2)) >= limit `$$CostLimit - budget exhausted" -Level WARN
            break
        }

        # EXIT: Last iteration
        if ($iter -eq $effectiveMax) {
            $exitReason = if ($effectiveMax -lt $MaxIterations) { "NO_ALTERNATE_STRATEGY" } else { "MAX_ITERATIONS" }
            Write-EbookLog "  EXIT: $(if ($exitReason -eq 'NO_ALTERNATE_STRATEGY') {'No more extraction strategies to try'} else {'Max iterations reached'})" -Level WARN
            break
        }

        Write-EbookLog "  Score $iterScore < target $TargetScore - trying next strategy..." -Level INFO
    }

    # Clean up cached chapter hints
    if ($cachedChapterHints -and (Test-Path $cachedChapterHints)) {
        Remove-Item $cachedChapterHints -Force -ErrorAction SilentlyContinue
    }

    # ── Step 4: Final Report ─────────────────────────────────────────────────
    $totalDuration = [math]::Round(((Get-Date) - $loopStart).TotalSeconds, 1)

    # Build score progression
    $scoreProgression = $iterations | ForEach-Object { $_.Score }

    # Generate recommendation text
    $recommendation = switch ($exitReason) {
        "PASS"                  { "Book meets quality target ($bestScore/$TargetScore). Ready for reading." }
        "CEILING"               { "Score $bestScore/100 represents the quality ceiling for this source. For higher quality, try a different edition or re-scanned source." }
        "COST"                  { "Cost limit reached at `$$([math]::Round($totalCost, 2)). Best score achieved: $bestScore/100." }
        "MAX_ITERATIONS"        { "All $MaxIterations iterations used. Best score: $bestScore/100. Consider manual review or a different source file." }
        "NO_ALTERNATE_STRATEGY" { "All available extraction strategies tried. Best score: $bestScore/100 from iteration $bestIteration." }
        default                 { "Loop completed. Best score: $bestScore/100." }
    }

    # Build the report object
    $report = @{
        book                   = $fileName
        exit_reason            = $exitReason
        best_score             = $bestScore
        best_iteration         = $bestIteration
        best_output_path       = $bestOutputPath
        target_score           = $TargetScore
        iterations_run         = $iterations.Count
        score_progression      = $scoreProgression
        total_cost_usd         = [math]::Round($totalCost, 4)
        total_duration_seconds = $totalDuration
        recommendation         = $recommendation
        iterations             = $iterations | ForEach-Object {
            @{
                iteration        = $_.Iteration
                strategy         = $_.Strategy
                score            = $_.Score
                pass             = $_.Pass
                cost_usd         = [math]::Round($_.Cost, 4)
                duration_seconds = $_.Duration
                output_path      = $_.OutputPath
                error            = $_.Error
            }
        }
        timestamp = (Get-Date -Format 'o')
    }

    # Write report JSON
    $reportDir  = if ($OutputDir) { $OutputDir } else { Resolve-ProjectPath ($cfg.paths.kindle) }
    $reportStem = [System.IO.Path]::GetFileNameWithoutExtension($bestOutputPath)
    if (-not $reportStem) { $reportStem = [System.IO.Path]::GetFileNameWithoutExtension($fileName) }
    $reportPath = Join-Path $reportDir "${reportStem}_converge_report.json"

    try {
        $report | ConvertTo-Json -Depth 5 | Set-Content $reportPath -Encoding UTF8
        Write-EbookLog "  Report: $reportPath" -Level INFO
    } catch {
        Write-EbookLog "  Failed to write converge report: $_" -Level WARN
    }

    # Print summary
    $summaryLevel = if ($exitReason -eq 'PASS') { 'SUCCESS' } else { 'WARN' }
    Write-EbookLog "==================================================================" -Level INFO
    Write-EbookLog "CONVERGE LOOP COMPLETE: $fileName" -Level $summaryLevel
    Write-EbookLog "  Exit: $exitReason | Best: $bestScore/100 (iteration $bestIteration)" -Level INFO
    Write-EbookLog "  Score progression: $($scoreProgression -join ' -> ')" -Level INFO
    Write-EbookLog "  Total: `$$([math]::Round($totalCost, 2)) | ${totalDuration}s | $($iterations.Count) iteration(s)" -Level INFO
    Write-EbookLog "  Output: $bestOutputPath" -Level INFO
    Write-EbookLog "  $recommendation" -Level INFO
    Write-EbookLog "==================================================================" -Level INFO

    # Return the report object for pipeline use
    return $report
}

#endregion

#region -- Module exports ----------------------------------------------------

Export-ModuleMember -Function @(
    'Invoke-EbookPipeline'
    'Convert-ToTTS'
    'Convert-ToKindle'
    'Send-ToKindle'
    'Convert-BriefToYouTube'
    'Install-EbookScheduledTask'
    'Uninstall-EbookScheduledTask'
    'Get-EbookTaskStatus'
    'Initialize-EbookAutomation'
    'Invoke-Balabolka'
    'Send-ToClaudeAPI'
    'Get-ChapterStructure'
    'Test-EbookPipeline'
    'Test-ConversionQuality'
    'Invoke-ConvergeLoop'
    'Write-EbookLog'
    'Get-EbookConfig'
)

#endregion
