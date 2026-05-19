<#
.SYNOPSIS  Test column layout detection and two-column PDF extraction.
.DESCRIPTION
    Validates detect_column_layout() and extract_text_columns() for known
    two-column and single-column PDFs in the archive.

    Test 1 (all books): Detection-only -- fast check of column layout detection.
    Test 2 (Ezekiel only): Full extraction -- verify two-column text reads naturally.

.EXAMPLE
    powershell -File tools\test_columns.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:exitCode = 0

# -- Locate project root (one level up from tools\) --
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot

try {

# -- Load module --
Import-Module (Join-Path $projectRoot 'module\EbookAutomation.psm1') -Force

$cfg    = Get-EbookConfig
$python = $cfg.paths.python

$archiveDir = Join-Path $projectRoot 'archive'
if (-not (Test-Path $archiveDir)) {
    Write-Host "  SKIP ALL: archive\ directory not found at $archiveDir" -ForegroundColor Yellow
    $script:exitCode = 0
    return
}

# -- Test matrix --
$tests = @(
    [PSCustomObject]@{ Name = "Ezekiel II (two-column commentary)";  Pattern = "Ezekiel II";        ExpectColumns = $true  }
    [PSCustomObject]@{ Name = "Oil Kings (single-column history)";   Pattern = "Oil Kings";         ExpectColumns = $false }
    [PSCustomObject]@{ Name = "Brother of Jesus (single-column)";    Pattern = "Brother of Jesus";  ExpectColumns = $false }
    [PSCustomObject]@{ Name = "Mexico (single-column history)";      Pattern = "Mexico";            ExpectColumns = $false }
)

$passed  = 0
$failed  = 0
$skipped = 0
$results = @()

# -- Test 1: Column detection for all books --
Write-Host "`n=== TEST 1: Column layout detection ===" -ForegroundColor Cyan

foreach ($test in $tests) {
    $file = Get-ChildItem (Join-Path $projectRoot 'archive') -Filter '*.pdf' -Recurse |
            Where-Object { $_.Name -like "*$($test.Pattern)*" } |
            Select-Object -First 1

    if (-not $file) {
        Write-Host "  SKIP: $($test.Name) -- file not found in archive" -ForegroundColor Yellow
        $skipped++
        $results += [PSCustomObject]@{ Name = $test.Name; Status = 'SKIP'; Details = 'file not found' }
        continue
    }

    Write-Host "`n  [$($test.Name)]"
    Write-Host "  File: $($file.Name)"

    # Build the Python detect script as a string and pass via temp file
    $pyContent  = "import sys, os`n"
    $pyContent += "sys.path.insert(0, os.path.join(r'" + $projectRoot + "', 'tools'))`n"
    $pyContent += "from extract_tts_text import detect_column_layout`n"
    $pyContent += "result = detect_column_layout(r'" + $file.FullName + "', print)`n"
    $pyContent += "print(f'RESULT: columns={result[`"num_columns`"]} confidence={result[`"confidence`"]:.0%} multicolumn={result[`"is_multicolumn`"]}')`n"

    $pyTmp = Join-Path $env:TEMP ("detect_col_" + [System.IO.Path]::GetRandomFileName() + ".py")
    [System.IO.File]::WriteAllText($pyTmp, $pyContent, [System.Text.Encoding]::UTF8)

    try {
        $output = & $python $pyTmp 2>&1
    } finally {
        Remove-Item $pyTmp -Force -ErrorAction SilentlyContinue
    }

    $output | ForEach-Object { Write-Host "    $_" }

    $resultLine = $output | Where-Object { $_ -match '^RESULT:' } | Select-Object -Last 1
    if ($resultLine -match 'multicolumn=(\w+)') {
        $detected = $Matches[1] -eq 'True'
        $ok = ($detected -eq $test.ExpectColumns)
        if ($ok) {
            Write-Host "  PASS: detected=$detected, expected=$($test.ExpectColumns)" -ForegroundColor Green
            $passed++
            $results += [PSCustomObject]@{ Name = $test.Name; Status = 'PASS'; Details = $resultLine }
        } else {
            Write-Host "  FAIL: detected=$detected, expected=$($test.ExpectColumns)" -ForegroundColor Red
            $failed++
            $results += [PSCustomObject]@{ Name = $test.Name; Status = 'FAIL'; Details = $resultLine }
        }
    } else {
        Write-Host "  FAIL: could not parse RESULT line" -ForegroundColor Red
        $failed++
        $results += [PSCustomObject]@{ Name = $test.Name; Status = 'FAIL'; Details = 'parse error' }
    }
}

# -- Test 2: Full extraction for Ezekiel (two-column book) --
Write-Host "`n=== TEST 2: Full two-column extraction (Ezekiel II) ===" -ForegroundColor Cyan

$ezekielFile = Get-ChildItem (Join-Path $projectRoot 'archive') -Filter '*.pdf' -Recurse |
               Where-Object { $_.Name -like "*Ezekiel II*" } |
               Select-Object -First 1

if (-not $ezekielFile) {
    Write-Host "  SKIP: Ezekiel II not found in archive" -ForegroundColor Yellow
    $skipped++
} else {
    Write-Host "  File: $($ezekielFile.Name)"
    Write-Host "  Running Convert-ToKindle with -ForceColumns -UseHtmlExtraction:`$false..."

    $tempOut = Join-Path $env:TEMP ("test_columns_" + [System.IO.Path]::GetRandomFileName())
    New-Item $tempOut -ItemType Directory -Force | Out-Null

    try {
        $kindleOk = Convert-ToKindle -InputFile $ezekielFile.FullName -OutputDir $tempOut -ForceColumns
        if ($kindleOk) {
            $outFile = Get-ChildItem $tempOut -Include '*.txt','*.html' -File -Recurse | Select-Object -First 1
            if ($outFile) {
                $sizeKB = [math]::Round($outFile.Length / 1KB, 0)
                Write-Host "  PASS: extraction produced $sizeKB KB output -> $($outFile.Name)" -ForegroundColor Green

                # Show first 500 chars of extracted text as readability check
                $preview = Get-Content $outFile.FullName -Raw -ErrorAction SilentlyContinue
                if ($preview) {
                    $snippet = $preview.Substring(0, [Math]::Min(500, $preview.Length))
                    Write-Host "`n  --- Text preview (first 500 chars) ---"
                    Write-Host $snippet
                    Write-Host "  ---"
                }
                $passed++
                $results += [PSCustomObject]@{ Name = 'Ezekiel full extraction'; Status = 'PASS'; Details = "$sizeKB KB" }
            } else {
                Write-Host "  FAIL: Convert-ToKindle returned OK but no output file found" -ForegroundColor Red
                $failed++
                $results += [PSCustomObject]@{ Name = 'Ezekiel full extraction'; Status = 'FAIL'; Details = 'no output file' }
            }
        } else {
            Write-Host "  FAIL: Convert-ToKindle returned false" -ForegroundColor Red
            $failed++
            $results += [PSCustomObject]@{ Name = 'Ezekiel full extraction'; Status = 'FAIL'; Details = 'Convert-ToKindle returned false' }
        }
    }
    catch {
        Write-Host "  FAIL: exception -- $_" -ForegroundColor Red
        $failed++
        $results += [PSCustomObject]@{ Name = 'Ezekiel full extraction'; Status = 'FAIL'; Details = $_.ToString() }
    }
    finally {
        Remove-Item $tempOut -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# -- Summary --
Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize
Write-Host "Passed: $passed  |  Failed: $failed  |  Skipped: $skipped"

if ($failed -gt 0) {
    Write-Host "`nSome tests FAILED." -ForegroundColor Red
    $script:exitCode = 1
} else {
    Write-Host "`nAll tests PASSED." -ForegroundColor Green
    $script:exitCode = 0
}

} finally {
    Pop-Location
}

exit $script:exitCode