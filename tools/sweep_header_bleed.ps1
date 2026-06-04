#Requires -Version 7.0
<#
.SYNOPSIS
Corpus sweep: re-extract the trusted baseline PDF books and scan each
_kindle.html artifact for welded ALL-CAPS running headers (EB-370).

.DESCRIPTION
Invokes run_extraction() on each of the 9 PDF baseline books + Pilgrim People
(EPUB Sherlock deferred per EB-370 scope). Scans every produced _kindle.html
with check_header_bleed.py. Writes per-book and sweep-summary reports under
data/batch_reports/header_bleed/.

Run from the main working tree (F:\Projects\EbookAutomation\) or pass
-OutputDir to redirect intermediate HTML output (never junction data dirs).

Exit codes (mirrors check_header_bleed.py):
    0 -- all scanned books clean
    1 -- nothing produced to scan
    2 -- >=1 book flagged
    3 -- infrastructure / extraction error

.EXAMPLE
pwsh -File tools\sweep_header_bleed.ps1

.EXAMPLE
pwsh -File tools\sweep_header_bleed.ps1 -OutputDir F:\tmp\sweep_out
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = 'F:\Projects\EbookAutomation',
    [string]$OutputDir   = ''   # default: <ProjectRoot>\output\kindle
)

$ErrorActionPreference = 'Stop'
$ToolsDir   = Join-Path $ProjectRoot 'tools'
$TestsDir   = Join-Path $ProjectRoot 'tests'
$ArchiveDir = Join-Path $ProjectRoot 'archive'
$ReportDir  = Join-Path $ProjectRoot 'data\batch_reports\header_bleed'

if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot 'output\kindle'
}

New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$ts = Get-Date -Format 'yyyyMMdd-HHmmss'

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    Write-Host "$(Get-Date -Format 'HH:mm:ss') [$Level] [SWEEP] $Message"
}

Write-Log "=== Header-bleed corpus sweep started ==="
Write-Log "ProjectRoot: $ProjectRoot"
Write-Log "ArchiveDir:  $ArchiveDir"
Write-Log "OutputDir:   $OutputDir"
Write-Log "ReportDir:   $ReportDir"

# ------------------------------------------------------------------
# Phase 1: Re-extract corpus books via run_extraction()
# ------------------------------------------------------------------
Write-Log "Phase 1: re-extracting corpus books"

# PDF corpus: 9 BOOK_PATTERNS entries (exclude Sherlock EPUB) + Pilgrim People.
# Sherlock (EPUB) is deferred — run_extraction() is PDF-oriented; the forward
# batch gate will catch EPUBs on their next batch run.
$corpusBooks = @(
    @{ Name = 'Oil Kings';               Pattern = '*Oil*Kings*';         Exclude = '' },
    @{ Name = 'Mexico';                  Pattern = '*Mexico*Illicit*';    Exclude = '' },
    @{ Name = 'Return of the Gods';      Pattern = '*Return*Gods*';       Exclude = '' },
    @{ Name = 'Python in Easy Steps';    Pattern = '*Python*easy*steps*'; Exclude = '' },
    @{ Name = 'Atomic Habits';           Pattern = '*Atomic*Habits*';     Exclude = '' },
    @{ Name = 'Decline of the West';     Pattern = '*Decline*West*';      Exclude = '' },
    @{ Name = 'Dionysius';               Pattern = '*Dionysius*';         Exclude = '' },
    @{ Name = 'Genesis (Barton)';        Pattern = '*Genesis*';           Exclude = 'Kass' },
    @{ Name = 'Fate of Empires (Glubb)'; Pattern = '*Fate*Empires*';     Exclude = '' },
    @{ Name = 'Pilgrim People';          Pattern = '*Pilgrim*People*';    Exclude = '' }
)

Write-Log "Corpus size: $($corpusBooks.Count) PDF books (Sherlock EPUB deferred)"

# Set OUTPUT_DIR so run_extraction() writes to the right place
$env:OUTPUT_DIR = $OutputDir

$htmlPaths  = @()
$skipCount  = 0
$failCount  = 0

foreach ($book in $corpusBooks) {
    Write-Log "  Extracting: $($book.Name)"

    # Find the PDF via Python (re-uses find_pdf from test_pipeline.py)
    $findPy = @"
import sys, os
sys.path.insert(0, r'$ToolsDir')
import test_pipeline as tp
pdf = tp.find_pdf(r'$($book.Pattern)', exclude=r'$($book.Exclude)' or None)
print(pdf or '')
"@
    $pdfPath = (py -3.12 -c $findPy 2>$null).Trim()

    if (-not $pdfPath -or -not (Test-Path -LiteralPath $pdfPath)) {
        Write-Log "    SKIP: PDF not found for pattern '$($book.Pattern)'" 'WARN'
        $skipCount++
        continue
    }
    Write-Log "    PDF: $(Split-Path $pdfPath -Leaf)"

    # Run extraction via run_extraction() primitive
    $safeName = ($book.Name -replace '[^\w\- ]', '_')
    $extractPy = @"
import sys, os, json
sys.path.insert(0, r'$ToolsDir')
sys.path.insert(0, r'$TestsDir')
import test_pipeline as tp
html_path, stdout, stderr = tp.run_extraction(r'$pdfPath', use_pdfminer=True, test_name='$safeName')
if html_path and os.path.exists(html_path):
    print(json.dumps({'ok': True, 'html_path': html_path}))
else:
    print(json.dumps({'ok': False, 'reason': 'no HTML produced'}))
"@
    $extractOut = (py -3.12 -c $extractPy 2>&1 | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)

    if (-not $extractOut) {
        Write-Log "    FAIL: extraction produced no JSON for $($book.Name)" 'ERROR'
        $failCount++
        continue
    }

    $extractResult = $extractOut | ConvertFrom-Json
    if ($extractResult.ok) {
        Write-Log "    HTML: $(Split-Path $extractResult.html_path -Leaf)"
        $htmlPaths += $extractResult.html_path
    } else {
        Write-Log "    FAIL: $($extractResult.reason)" 'ERROR'
        $failCount++
    }
}

Write-Log "Phase 1 complete: $($htmlPaths.Count) HTML(s) produced, $skipCount skipped, $failCount failed"

if ($htmlPaths.Count -eq 0) {
    Write-Log "No HTML artifacts available; sweep cannot proceed" 'ERROR'
    exit 1
}

# ------------------------------------------------------------------
# Phase 2: Scan HTML artifacts with check_header_bleed.py
# ------------------------------------------------------------------
Write-Log "Phase 2: scanning $($htmlPaths.Count) HTML artifact(s) for welds"

$flagged  = 0
$clean    = 0
$hbErrors = 0

foreach ($htmlPath in $htmlPaths) {
    $bookName  = Split-Path $htmlPath -Leaf
    $bookReport = Join-Path $ReportDir "sweep-${ts}-${bookName}.json"

    $hbArgs = @(
        '-3.12',
        (Join-Path $ToolsDir 'check_header_bleed.py'),
        '--input', $htmlPath,
        '--out',   $bookReport,
        '--quiet'
    )
    & py @hbArgs 2>&1 | ForEach-Object { "$(Get-Date -Format 'HH:mm:ss') [HB] $_" | Out-Host }
    $hbExit = $LASTEXITCODE

    switch ($hbExit) {
        0 { $clean++;    Write-Log "    clean:   $bookName" }
        1 {              Write-Log "    nothing scannable: $bookName" 'WARN' }
        2 { $flagged++;  Write-Log "    FLAGGED: $bookName" 'WARN' }
        3 { $hbErrors++; Write-Log "    ERROR:   $bookName" 'ERROR' }
    }
}

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
Write-Log "=== Corpus sweep complete ==="
Write-Log "  Total corpus entries:  $($corpusBooks.Count)"
Write-Log "  Extracted (HTML):      $($htmlPaths.Count)"
Write-Log "  Skipped (no PDF):      $skipCount"
Write-Log "  Extraction failures:   $failCount"
Write-Log "  Clean:                 $clean"
Write-Log "  Flagged:               $flagged"
Write-Log "  Scan errors:           $hbErrors"
Write-Log "Reports: $ReportDir"

$batchStatus = 0
if ($hbErrors -gt 0 -or $failCount -gt 0) { $batchStatus = 3 }
elseif ($flagged -gt 0)                    { $batchStatus = 2 }
elseif ($clean -eq 0)                      { $batchStatus = 1 }

Write-Log "Sweep exit status: $batchStatus"
exit $batchStatus
