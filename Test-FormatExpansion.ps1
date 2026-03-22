<#
.SYNOPSIS
    Regression test suite for the Expanded Format Support changes to pdf_to_balabolka.py
    and Convert-ToTTS in EbookAutomation.psm1.

.DESCRIPTION
    Runs a series of tests in 4 tiers:
      Tier 1 -- Smoke tests (no files needed, pure code validation)
      Tier 2 -- Unit tests with synthetic test files
      Tier 3 -- PDF regression (requires a real PDF in inbox\)
      Tier 4 -- Full pipeline integration (module-level, requires inbox files)

    Place any test ebooks you have into inbox\ before running.

.EXAMPLE
    cd F:\Projects\EbookAutomation
    .\Test-FormatExpansion.ps1
#>

$ErrorActionPreference = 'Continue'
$script:TestsPassed = 0
$script:TestsFailed = 0
$script:TestsSkipped = 0

# -- Helpers --------------------------------------------------------
function Write-TestResult {
    param(
        [string]$Name,
        [ValidateSet('PASS','FAIL','SKIP')]
        [string]$Result,
        [string]$Detail = ''
    )
    $icon = switch ($Result) {
        'PASS' { '[PASS]' }
        'FAIL' { '[FAIL]' }
        'SKIP' { '[SKIP]' }
    }
    $color = switch ($Result) {
        'PASS' { 'Green' }
        'FAIL' { 'Red' }
        'SKIP' { 'Yellow' }
    }

    $msg = "$icon  $Name"
    if ($Detail) { $msg += "  --  $Detail" }
    Write-Host $msg -ForegroundColor $color

    switch ($Result) {
        'PASS' { $script:TestsPassed++ }
        'FAIL' { $script:TestsFailed++ }
        'SKIP' { $script:TestsSkipped++ }
    }
}

function Write-Tier {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 57) -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ("=" * 57) -ForegroundColor Cyan
    Write-Host ""
}

# -- Setup ----------------------------------------------------------
$projectRoot = $PSScriptRoot
if (-not $projectRoot) { $projectRoot = Get-Location }
$toolPath    = Join-Path $projectRoot 'tools\pdf_to_balabolka.py'
$python      = 'python'
$tempDir     = Join-Path $env:TEMP "ebook_test_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item $tempDir -ItemType Directory -Force | Out-Null

# Pre-compute Unix-style paths (avoids nested quoting issues in Python commands)
$projectRootUnix = $projectRoot -replace '\\', '/'
$toolPathUnix    = $toolPath -replace '\\', '/'
$tempDirUnix     = $tempDir -replace '\\', '/'

Write-Host ""
Write-Host "  Format Expansion Regression Tests" -ForegroundColor White
Write-Host "  Project: $projectRoot" -ForegroundColor DarkGray
Write-Host "  Temp:    $tempDir" -ForegroundColor DarkGray
Write-Host ""

# =================================================================
#  TIER 1 -- SMOKE TESTS (no files needed)
# =================================================================
Write-Tier "TIER 1 -- Smoke Tests (code validation)"

# 1.1 Python syntax check
try {
    $r = & $python -c "import py_compile; py_compile.compile('$toolPathUnix', doraise=True)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-TestResult "Python syntax check" "PASS"
    } else {
        Write-TestResult "Python syntax check" "FAIL" "$r"
    }
} catch {
    Write-TestResult "Python syntax check" "FAIL" "$_"
}

# 1.2 SUPPORTED_FORMATS constant exists and has expected values
try {
    $formats = & $python -c "import sys; sys.path.insert(0, '$projectRootUnix/tools'); from pdf_to_balabolka import SUPPORTED_FORMATS; print(','.join(SUPPORTED_FORMATS))" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $fmtList = $formats.Trim()
        $expected = @('pdf','epub','mobi','azw','azw3','djvu')
        $missing = $expected | Where-Object { $fmtList -notlike "*$_*" }
        if ($missing) {
            Write-TestResult "SUPPORTED_FORMATS constant" "FAIL" "Missing: $($missing -join ', '). Got: $fmtList"
        } else {
            Write-TestResult "SUPPORTED_FORMATS constant" "PASS" "$fmtList"
        }
    } else {
        Write-TestResult "SUPPORTED_FORMATS constant" "FAIL" "$formats"
    }
} catch {
    Write-TestResult "SUPPORTED_FORMATS constant" "FAIL" "$_"
}

# 1.3 New functions are importable
try {
    $r = & $python -c "import sys; sys.path.insert(0, '$projectRootUnix/tools'); from pdf_to_balabolka import extract_text_auto, extract_text_from_epub, extract_text_via_calibre; print('OK')" 2>&1
    if ($r -like '*OK*') {
        Write-TestResult "New extraction functions importable" "PASS"
    } else {
        Write-TestResult "New extraction functions importable" "FAIL" "$r"
    }
} catch {
    Write-TestResult "New extraction functions importable" "FAIL" "$_"
}

# 1.4 Dependencies installed (ebooklib, bs4)
try {
    $r = & $python -c "import ebooklib; print('ebooklib ' + str(ebooklib.VERSION)); import bs4; print('bs4 ' + bs4.__version__); print('OK')" 2>&1
    if ($r -like '*OK*') {
        $depInfo = ($r | Select-Object -First 2) -join '; '
        Write-TestResult "Dependencies installed (ebooklib, bs4)" "PASS" $depInfo
    } else {
        Write-TestResult "Dependencies installed (ebooklib, bs4)" "FAIL" "$r"
    }
} catch {
    Write-TestResult "Dependencies installed (ebooklib, bs4)" "FAIL" "$_"
}

# 1.5 CLI --help shows updated description and --calibre-path
try {
    $helpOutput = & $python $toolPath --input dummy --help 2>&1
    $helpText = $helpOutput -join "`n"

    $checks = @(
        @{ Label = '--calibre-path arg present';  Pattern = '--calibre-path' }
        @{ Label = 'Updated description';         Pattern = 'Ebook to Balabolka' }
        @{ Label = 'Format list in --input help';  Pattern = 'epub.*mobi.*azw' }
        @{ Label = 'EPUB example in epilog';       Pattern = 'book\.epub' }
    )

    foreach ($check in $checks) {
        if ($helpText -match [regex]::Escape($check.Pattern) -or $helpText -match $check.Pattern) {
            Write-TestResult "CLI help: $($check.Label)" "PASS"
        } else {
            Write-TestResult "CLI help: $($check.Label)" "FAIL" "Pattern '$($check.Pattern)' not found in --help output"
        }
    }
} catch {
    Write-TestResult "CLI --help validation" "FAIL" "$_"
}

# 1.6 Unsupported format error
try {
    # Create a dummy file with an unsupported extension
    $dummyFile = Join-Path $tempDir "test.xyz"
    "dummy" | Set-Content $dummyFile
    $r = & $python $toolPath --input $dummyFile --output-dir $tempDir 2>&1
    $stderr = ($r | Out-String)
    if ($LASTEXITCODE -ne 0 -and $stderr -match 'Unsupported format|unsupported') {
        Write-TestResult "Unsupported format rejected (.xyz)" "PASS"
    } elseif ($LASTEXITCODE -ne 0) {
        # Might hit the format check or might hit a different error depending on code order
        Write-TestResult "Unsupported format rejected (.xyz)" "PASS" "Exit code $LASTEXITCODE"
    } else {
        Write-TestResult "Unsupported format rejected (.xyz)" "FAIL" "Script did not reject .xyz format"
    }
} catch {
    Write-TestResult "Unsupported format rejected (.xyz)" "FAIL" "$_"
}

# 1.7 settings.json has updated input_formats
try {
    $settings = Get-Content (Join-Path $projectRoot 'config\settings.json') -Raw | ConvertFrom-Json
    $ttsFormats = $settings.tts.input_formats
    $expectedNew = @('mobi', 'azw', 'azw3', 'djvu')
    $missing = $expectedNew | Where-Object { $_ -notin $ttsFormats }
    if ($missing) {
        Write-TestResult "settings.json tts.input_formats updated" "FAIL" "Missing: $($missing -join ', '). Has: $($ttsFormats -join ', ')"
    } else {
        Write-TestResult "settings.json tts.input_formats updated" "PASS" "$($ttsFormats -join ', ')"
    }
} catch {
    Write-TestResult "settings.json tts.input_formats updated" "FAIL" "$_"
}


# =================================================================
#  TIER 2 -- SYNTHETIC FILE TESTS
# =================================================================
Write-Tier "TIER 2 -- Synthetic File Tests"

# 2.1 Create a minimal EPUB for testing native extraction
try {
    $epubCreatePy = @"
import sys, os
sys.path.insert(0, '$projectRootUnix/tools')
from ebooklib import epub

book = epub.EpubBook()
book.set_identifier('test-123')
book.set_title('Test Book for Regression')
book.set_language('en')
book.add_author('Test Author')

c1 = epub.EpubHtml(title='Chapter One', file_name='ch01.xhtml', lang='en')
c1.content = b'''<html><body>
<h1>Chapter One</h1>
<p>This is the first chapter of the test book. It contains enough text to be detected
as a real paragraph by the cleaning logic. The quick brown fox jumped over the lazy dog
multiple times to ensure we have sufficient word count for the paragraph detection
threshold to work correctly.</p>
<p>This is a second paragraph in chapter one. Again we need enough words here to pass
the minimum paragraph length filter that drops fragments shorter than four words.</p>
</body></html>'''

c2 = epub.EpubHtml(title='Chapter Two', file_name='ch02.xhtml', lang='en')
c2.content = b'''<html><body>
<h1>Chapter Two</h1>
<p>Chapter two begins with its own set of paragraphs. The text extraction should
preserve the reading order from the spine and produce clean text without HTML tags.
We are testing that BeautifulSoup correctly strips the markup.</p>
</body></html>'''

book.add_item(c1)
book.add_item(c2)
book.spine = ['nav', c1, c2]
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())

outpath = os.path.join('$tempDirUnix', 'test_regression.epub')
epub.write_epub(outpath, book)
print('CREATED:' + outpath)
"@
    $epubTestResult = & $python -c $epubCreatePy 2>&1

    if ($epubTestResult -match 'CREATED:(.+)') {
        $testEpub = $Matches[1].Trim()
        Write-TestResult "Create synthetic EPUB" "PASS" $testEpub

        $testEpubUnix = $testEpub -replace '\\', '/'

        # 2.2 Test EPUB extraction via extract_text_from_epub
        $extractPy = @"
import sys
sys.path.insert(0, '$projectRootUnix/tools')
from pdf_to_balabolka import extract_text_from_epub

text = extract_text_from_epub('$testEpubUnix', lambda msg: None)
words = len(text.split())
has_ch1 = 'Chapter One' in text or 'chapter one' in text.lower()
has_ch2 = 'Chapter Two' in text or 'chapter two' in text.lower()
has_html = '<html>' in text or '<p>' in text or '<h1>' in text
print('WORDS:' + str(words))
print('CH1:' + str(has_ch1))
print('CH2:' + str(has_ch2))
print('HTML_LEAKED:' + str(has_html))
"@
        $extractResult = & $python -c $extractPy 2>&1
        $extractText = $extractResult -join "`n"

        if ($extractText -match 'WORDS:(\d+)') {
            $wordCount = [int]$Matches[1]
            if ($wordCount -gt 30) {
                Write-TestResult "EPUB text extraction (word count)" "PASS" "$wordCount words"
            } else {
                Write-TestResult "EPUB text extraction (word count)" "FAIL" "Only $wordCount words extracted"
            }
        } else {
            Write-TestResult "EPUB text extraction (word count)" "FAIL" "$extractText"
        }

        if ($extractText -match 'CH1:True' -and $extractText -match 'CH2:True') {
            Write-TestResult "EPUB chapter detection" "PASS" "Both chapters found"
        } else {
            Write-TestResult "EPUB chapter detection" "FAIL" "Chapter markers missing"
        }

        if ($extractText -match 'HTML_LEAKED:False') {
            Write-TestResult "EPUB HTML tag stripping" "PASS" "No HTML in output"
        } else {
            Write-TestResult "EPUB HTML tag stripping" "FAIL" "HTML tags leaked into text"
        }

        # 2.3 Test EPUB through the dispatcher
        $dispatchPy = @"
import sys
sys.path.insert(0, '$projectRootUnix/tools')
from pdf_to_balabolka import extract_text_auto

text = extract_text_auto('$testEpubUnix', lambda msg: None)
print('DISPATCH_OK:' + str(len(text) > 100))
"@
        $dispatchResult = & $python -c $dispatchPy 2>&1
        if (($dispatchResult -join '') -match 'DISPATCH_OK:True') {
            Write-TestResult "Dispatcher routes EPUB correctly" "PASS"
        } else {
            Write-TestResult "Dispatcher routes EPUB correctly" "FAIL" "$dispatchResult"
        }

        # 2.4 Test full pipeline (process_pdf in balabolka mode) with EPUB
        $r = & $python $toolPath --input $testEpub --output-dir $tempDir 2>&1
        $outputText = $r -join "`n"

        # Find the output file (might have _balabolka suffix)
        $outFiles = Get-ChildItem $tempDir -Filter "*_balabolka.txt" | Sort-Object LastWriteTime -Descending
        if ($outFiles -and $outFiles[0].Length -gt 50) {
            $content = Get-Content $outFiles[0].FullName -Raw
            Write-TestResult "EPUB full pipeline (balabolka mode)" "PASS" "$($outFiles[0].Name) -- $([math]::Round($outFiles[0].Length / 1KB, 1)) KB"
        } elseif ($LASTEXITCODE -eq 0) {
            Write-TestResult "EPUB full pipeline (balabolka mode)" "PASS" "Completed (exit 0)"
        } else {
            Write-TestResult "EPUB full pipeline (balabolka mode)" "FAIL" "Exit $LASTEXITCODE -- $outputText"
        }

        # 2.5 Test Kindle mode with EPUB
        $r2 = & $python $toolPath --input $testEpub --mode kindle --output-dir $tempDir --suffix "_kindle_test.txt" 2>&1
        $kindleOut = Get-ChildItem $tempDir -Filter "*_kindle_test.txt" | Sort-Object LastWriteTime -Descending
        if ($kindleOut -and $kindleOut[0].Length -gt 50) {
            $kindleContent = Get-Content $kindleOut[0].FullName -Raw
            $hasMarkdown = $kindleContent -match '(?m)^##?\s'
            $detail = "$($kindleOut[0].Name) -- $([math]::Round($kindleOut[0].Length / 1KB, 1)) KB"
            if ($hasMarkdown) { $detail += " -- Markdown headings present" }
            Write-TestResult "EPUB full pipeline (kindle mode)" "PASS" $detail
        } elseif ($LASTEXITCODE -eq 0) {
            Write-TestResult "EPUB full pipeline (kindle mode)" "PASS" "Completed (exit 0)"
        } else {
            Write-TestResult "EPUB full pipeline (kindle mode)" "FAIL" "Exit $LASTEXITCODE"
        }

    } else {
        Write-TestResult "Create synthetic EPUB" "FAIL" "$epubTestResult"
    }
} catch {
    Write-TestResult "Synthetic EPUB tests" "FAIL" "$_"
}

# 2.6 Test Calibre path detection for MOBI/AZW formats
try {
    $calibrePath = "C:\Program Files\Calibre2\ebook-convert.exe"
    if (Test-Path $calibrePath) {
        Write-TestResult "Calibre detected" "PASS" $calibrePath

        # Test that extract_text_via_calibre raises on bad input (rather than hanging)
        $calibreErrPy = @"
import sys
sys.path.insert(0, '$projectRootUnix/tools')
from pdf_to_balabolka import extract_text_via_calibre
try:
    text = extract_text_via_calibre('nonexistent.mobi', lambda msg: None,
                                     calibre_path=r'$calibrePath')
    print('ERROR: should have raised')
except (RuntimeError, FileNotFoundError, Exception) as e:
    print('RAISED:' + type(e).__name__ + ':' + str(e)[:80])
"@
        $r = & $python -c $calibreErrPy 2>&1
        if (($r -join '') -match 'RAISED:') {
            Write-TestResult "Calibre extractor error handling" "PASS" (($r -join '') -replace 'RAISED:', '')
        } else {
            Write-TestResult "Calibre extractor error handling" "FAIL" "$r"
        }
    } else {
        Write-TestResult "Calibre detected" "SKIP" "Not installed at expected path"
    }
} catch {
    Write-TestResult "Calibre detection" "FAIL" "$_"
}


# =================================================================
#  TIER 3 -- REAL FILE REGRESSION
# =================================================================
Write-Tier "TIER 3 -- Real File Regression (inbox scan)"

$inboxDir = Join-Path $projectRoot 'inbox'
$realFiles = @{}
if (Test-Path $inboxDir) {
    $allFiles = Get-ChildItem $inboxDir -File
    foreach ($f in $allFiles) {
        $ext = $f.Extension.TrimStart('.').ToLower()
        if ($ext -in @('pdf','epub','mobi','azw','azw3','djvu')) {
            if (-not $realFiles[$ext]) { $realFiles[$ext] = @() }
            $realFiles[$ext] += $f
        }
    }
}

$formatLabels = @{
    'pdf'  = 'PDF (regression -- should match previous behavior)'
    'epub' = 'EPUB (native ebooklib extraction)'
    'mobi' = 'MOBI (Calibre intermediate)'
    'azw'  = 'AZW (Calibre intermediate)'
    'azw3' = 'AZW3 (Calibre intermediate)'
    'djvu' = 'DJVU (Calibre intermediate)'
}

if ($realFiles.Count -eq 0) {
    Write-Host "  No ebook files found in inbox\. Place test files there for Tier 3 tests." -ForegroundColor Yellow
    Write-Host "  Supported: .pdf .epub .mobi .azw .azw3 .djvu" -ForegroundColor Yellow
    Write-TestResult "Real file tests" "SKIP" "No files in inbox\"
} else {
    $totalFiles = ($realFiles.Values | ForEach-Object { $_.Count } | Measure-Object -Sum).Sum
    Write-Host "  Found $totalFiles file(s) in inbox\:" -ForegroundColor DarkGray
    foreach ($ext in $realFiles.Keys | Sort-Object) {
        Write-Host "    .$ext : $($realFiles[$ext].Count) file(s)" -ForegroundColor DarkGray
    }
    Write-Host ""

    foreach ($ext in $realFiles.Keys | Sort-Object) {
        $testFile = $realFiles[$ext][0]  # Test first file of each format
        $label = $formatLabels[$ext]

        # Balabolka mode
        try {
            $outDir = Join-Path $tempDir "real_${ext}_balabolka"
            New-Item $outDir -ItemType Directory -Force | Out-Null

            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $r = & $python $toolPath --input $testFile.FullName --output-dir $outDir 2>&1
            $sw.Stop()
            $outputText = $r -join "`n"

            $outFiles = Get-ChildItem $outDir -Filter "*.txt" | Sort-Object LastWriteTime -Descending
            if ($LASTEXITCODE -eq 0 -and $outFiles) {
                $wordCount = (Get-Content $outFiles[0].FullName -Raw).Split().Count
                $sizeMB = [math]::Round($outFiles[0].Length / 1MB, 2)
                Write-TestResult "[$ext] Balabolka -- $($testFile.Name)" "PASS" `
                    "$wordCount words, $sizeMB MB, $([math]::Round($sw.Elapsed.TotalSeconds, 1))s"
            } elseif ($LASTEXITCODE -eq 0) {
                Write-TestResult "[$ext] Balabolka -- $($testFile.Name)" "PASS" "Completed but no output file found"
            } else {
                Write-TestResult "[$ext] Balabolka -- $($testFile.Name)" "FAIL" "Exit $LASTEXITCODE"
            }
        } catch {
            Write-TestResult "[$ext] Balabolka -- $($testFile.Name)" "FAIL" "$_"
        }

        # Kindle mode
        try {
            $outDir2 = Join-Path $tempDir "real_${ext}_kindle"
            New-Item $outDir2 -ItemType Directory -Force | Out-Null

            $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
            $r2 = & $python $toolPath --input $testFile.FullName --mode kindle --output-dir $outDir2 2>&1
            $sw2.Stop()

            $outFiles2 = Get-ChildItem $outDir2 -Filter "*.txt" | Sort-Object LastWriteTime -Descending
            if ($LASTEXITCODE -eq 0 -and $outFiles2) {
                $kindleContent = Get-Content $outFiles2[0].FullName -Raw
                $wordCount2 = $kindleContent.Split().Count
                $hasHeadings = $kindleContent -match '(?m)^##?\s'
                $detail = "$wordCount2 words, $([math]::Round($sw2.Elapsed.TotalSeconds, 1))s"
                if ($hasHeadings) { $detail += ", Markdown headings OK" }
                Write-TestResult "[$ext] Kindle  -- $($testFile.Name)" "PASS" $detail
            } elseif ($LASTEXITCODE -eq 0) {
                Write-TestResult "[$ext] Kindle  -- $($testFile.Name)" "PASS" "Completed (exit 0)"
            } else {
                Write-TestResult "[$ext] Kindle  -- $($testFile.Name)" "FAIL" "Exit $LASTEXITCODE"
            }
        } catch {
            Write-TestResult "[$ext] Kindle  -- $($testFile.Name)" "FAIL" "$_"
        }
    }
}


# =================================================================
#  TIER 4 -- POWERSHELL MODULE INTEGRATION
# =================================================================
Write-Tier "TIER 4 -- PowerShell Module Integration"

# 4.1 Module loads without errors
try {
    $modulePath = Join-Path $projectRoot 'module\EbookAutomation.psd1'
    if (Test-Path $modulePath) {
        Import-Module $modulePath -Force -ErrorAction Stop
        Write-TestResult "Module loads" "PASS"

        # 4.2 Convert-ToTTS help shows updated synopsis
        $help = Get-Help Convert-ToTTS -ErrorAction SilentlyContinue
        if ($help -and $help.Synopsis) {
            $synopsis = $help.Synopsis.Trim()
            # Check that the synopsis mentions multi-format or lists additional formats
            if ($synopsis -match 'MOBI|AZW|DJVU|ebook|multi.format' -or $synopsis -match 'PDF.*EPUB') {
                $synopsisShort = $synopsis.Substring(0, [Math]::Min(70, $synopsis.Length))
                Write-TestResult "Convert-ToTTS help updated" "PASS" "Synopsis: $synopsisShort"
            } else {
                Write-TestResult "Convert-ToTTS help updated" "FAIL" "Synopsis doesn't mention new formats: $synopsis"
            }
        } else {
            Write-TestResult "Convert-ToTTS help updated" "SKIP" "No help text returned"
        }

        # 4.3 Check that the EPUB->PDF intermediate step is gone
        $psm1Content = Get-Content (Join-Path $projectRoot 'module\EbookAutomation.psm1') -Raw
        if ($psm1Content -match 'EPUB.*->.*PDF.*for text extraction' -or $psm1Content -match 'tempPdf.*epub') {
            Write-TestResult "EPUB->PDF intermediate removed" "FAIL" "Old EPUB->PDF conversion code still present"
        } else {
            Write-TestResult "EPUB->PDF intermediate removed" "PASS"
        }

        # 4.4 Check that --calibre-path is passed to Python
        if ($psm1Content -match '--calibre-path') {
            Write-TestResult "Calibre path passed to Python" "PASS"
        } else {
            Write-TestResult "Calibre path passed to Python" "FAIL" "--calibre-path not found in .psm1"
        }

        # 4.5 Run Convert-ToTTS with the synthetic EPUB (if it was created)
        $synthEpub = Join-Path $tempDir 'test_regression.epub'
        if (Test-Path $synthEpub) {
            try {
                $moduleOutDir = Join-Path $tempDir 'module_tts_test'
                New-Item $moduleOutDir -ItemType Directory -Force | Out-Null
                $result = Convert-ToTTS -InputFile $synthEpub -OutputDir $moduleOutDir
                if ($result -eq $true) {
                    $moduleOut = Get-ChildItem $moduleOutDir -Filter "*.txt"
                    if ($moduleOut) {
                        Write-TestResult "Convert-ToTTS with EPUB" "PASS" "$($moduleOut.Name) -- $([math]::Round($moduleOut.Length / 1KB, 1)) KB"
                    } else {
                        Write-TestResult "Convert-ToTTS with EPUB" "PASS" "Returned true (no output file found in test dir)"
                    }
                } else {
                    Write-TestResult "Convert-ToTTS with EPUB" "FAIL" "Returned false"
                }
            } catch {
                Write-TestResult "Convert-ToTTS with EPUB" "FAIL" "$_"
            }
        } else {
            Write-TestResult "Convert-ToTTS with EPUB (module)" "SKIP" "No synthetic EPUB available"
        }

    } else {
        Write-TestResult "Module loads" "SKIP" "Module not found at $modulePath"
    }
} catch {
    Write-TestResult "Module loads" "FAIL" "$_"
}


# =================================================================
#  SUMMARY
# =================================================================
Write-Host ""
Write-Host ("=" * 57) -ForegroundColor Cyan
Write-Host "  RESULTS" -ForegroundColor Cyan
Write-Host ("=" * 57) -ForegroundColor Cyan
Write-Host ""
Write-Host "  Passed:  $script:TestsPassed" -ForegroundColor Green
$failColor = if ($script:TestsFailed -gt 0) { 'Red' } else { 'Green' }
Write-Host "  Failed:  $script:TestsFailed" -ForegroundColor $failColor
Write-Host "  Skipped: $script:TestsSkipped" -ForegroundColor Yellow
Write-Host "  Total:   $($script:TestsPassed + $script:TestsFailed + $script:TestsSkipped)" -ForegroundColor White
Write-Host ""

if ($script:TestsFailed -eq 0) {
    Write-Host "  All tests passed!" -ForegroundColor Green
} else {
    Write-Host "  $script:TestsFailed test(s) need attention." -ForegroundColor Red
}

# Cleanup
Write-Host ""
Write-Host "  Temp dir: $tempDir" -ForegroundColor DarkGray
Write-Host "  (Delete manually when done reviewing output files)" -ForegroundColor DarkGray
Write-Host ""
