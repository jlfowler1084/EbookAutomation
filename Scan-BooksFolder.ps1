<#
.SYNOPSIS
    Scan F:\Books (and subfolders) for ebook files, report counts by format,
    and list a few samples from each. Then optionally run the converter
    against selected files.

.EXAMPLE
    cd F:\Projects\EbookAutomation
    .\Scan-BooksFolder.ps1
    .\Scan-BooksFolder.ps1 -TestSamples       # auto-pick one per format and test
    .\Scan-BooksFolder.ps1 -BooksRoot "D:\Library"  # scan a different folder
#>
param(
    [string]$BooksRoot = "F:\Books",
    [switch]$TestSamples,
    [int]$SamplesPerFormat = 3,
    [string]$ProjectRoot = "F:\Projects\EbookAutomation"
)

$ErrorActionPreference = 'Continue'

# -- Supported formats (match SUPPORTED_FORMATS in extract_tts_text.py) --
$supportedExts = @('pdf','epub','mobi','azw','azw3','djvu')
$allEbookExts  = $supportedExts + @('txt','docx','cbz','cbr','fb2','lit','pdb','rtf')

Write-Host ""
Write-Host "  Ebook Library Scanner" -ForegroundColor White
Write-Host "  Scanning: $BooksRoot" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-Path $BooksRoot)) {
    Write-Host "  [ERROR] Folder not found: $BooksRoot" -ForegroundColor Red
    exit 1
}

# -- Scan all files recursively --
$allFiles = Get-ChildItem -Path $BooksRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -and $_.Extension.Length -gt 1 }

$byExt = @{}
foreach ($f in $allFiles) {
    $ext = $f.Extension.TrimStart('.').ToLower()
    if ($ext -in $allEbookExts) {
        if (-not $byExt[$ext]) { $byExt[$ext] = @() }
        $byExt[$ext] += $f
    }
}

# -- Display summary --
Write-Host ("=" * 65) -ForegroundColor Cyan
Write-Host "  FORMAT INVENTORY" -ForegroundColor Cyan
Write-Host ("=" * 65) -ForegroundColor Cyan
Write-Host ""

$totalSupported = 0
$totalOther = 0

foreach ($ext in $byExt.Keys | Sort-Object) {
    $count = $byExt[$ext].Count
    $isSupported = $ext -in $supportedExts
    $tag = if ($isSupported) { "[SUPPORTED]" } else { "[other]    " }
    $color = if ($isSupported) { 'Green' } else { 'DarkGray' }

    if ($isSupported) { $totalSupported += $count } else { $totalOther += $count }

    $sizeTotal = ($byExt[$ext] | Measure-Object -Property Length -Sum).Sum
    $sizeMB = [math]::Round($sizeTotal / 1MB, 1)

    Write-Host "  $tag  .$($ext.PadRight(6))  $($count.ToString().PadLeft(5)) files  ($sizeMB MB)" -ForegroundColor $color
}

Write-Host ""
Write-Host "  Supported formats: $totalSupported files" -ForegroundColor Green
Write-Host "  Other formats:     $totalOther files" -ForegroundColor DarkGray
Write-Host ""

# -- Show samples for each supported format --
Write-Host ("=" * 65) -ForegroundColor Cyan
Write-Host "  SAMPLE FILES (supported formats)" -ForegroundColor Cyan
Write-Host ("=" * 65) -ForegroundColor Cyan
Write-Host ""

$samplePicks = @{}  # first file per format for testing

foreach ($ext in $supportedExts) {
    if (-not $byExt[$ext] -or $byExt[$ext].Count -eq 0) {
        Write-Host "  .$ext -- no files found" -ForegroundColor Yellow
        Write-Host ""
        continue
    }

    $files = $byExt[$ext]

    # Pick a diverse set: sort by size and grab small, medium, large
    $sorted = $files | Sort-Object Length
    $samples = @()
    if ($sorted.Count -ge 3) {
        $samples += $sorted[0]                                           # smallest
        $samples += $sorted[[math]::Floor($sorted.Count / 2)]           # median
        $samples += $sorted[-1]                                          # largest
    } else {
        $samples = $sorted
    }

    # Also add a few random picks for variety (up to SamplesPerFormat total)
    if ($files.Count -gt 3) {
        $remaining = $files | Where-Object { $_.FullName -notin ($samples | ForEach-Object { $_.FullName }) }
        $random = $remaining | Get-Random -Count ([math]::Min($SamplesPerFormat, $remaining.Count)) -ErrorAction SilentlyContinue
        if ($random) { $samples += $random }
    }
    $samples = $samples | Select-Object -Unique -First ([math]::Max($SamplesPerFormat + 3, 6))

    # Store first file for auto-test
    $samplePicks[$ext] = $sorted[[math]::Floor($sorted.Count / 2)]  # median-sized file

    Write-Host "  .$ext ($($files.Count) files)" -ForegroundColor Green
    foreach ($s in $samples) {
        $sizeMB = [math]::Round($s.Length / 1MB, 1)
        $relPath = $s.FullName.Replace($BooksRoot, '').TrimStart('\')
        Write-Host "    $($sizeMB.ToString().PadLeft(6)) MB  $relPath" -ForegroundColor White
    }
    Write-Host ""
}

# -- If -TestSamples, run the converter against one file per format --
if ($TestSamples) {
    Write-Host ("=" * 65) -ForegroundColor Cyan
    Write-Host "  CONVERSION TESTS (one median-sized file per format)" -ForegroundColor Cyan
    Write-Host ("=" * 65) -ForegroundColor Cyan
    Write-Host ""

    $toolPath = Join-Path $ProjectRoot 'tools\extract_tts_text.py'
    $python   = 'python'
    $tempDir  = Join-Path $env:TEMP "ebook_bookscan_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    New-Item $tempDir -ItemType Directory -Force | Out-Null

    $results = @()

    foreach ($ext in $supportedExts) {
        if (-not $samplePicks[$ext]) {
            Write-Host "  [$ext] SKIP -- no files available" -ForegroundColor Yellow
            continue
        }

        $testFile = $samplePicks[$ext]
        $sizeMB = [math]::Round($testFile.Length / 1MB, 1)
        Write-Host "  [$ext] Testing: $($testFile.Name) ($sizeMB MB)" -ForegroundColor White

        # -- Balabolka mode --
        $outDir = Join-Path $tempDir "${ext}_balabolka"
        New-Item $outDir -ItemType Directory -Force | Out-Null

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $r = & $python $toolPath --input $testFile.FullName --output-dir $outDir 2>&1
        $sw.Stop()
        $exitCode = $LASTEXITCODE
        $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1)

        $outFile = Get-ChildItem $outDir -Filter "*.txt" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1

        if ($exitCode -eq 0 -and $outFile) {
            $content = Get-Content $outFile.FullName -Raw -ErrorAction SilentlyContinue
            $wordCount = if ($content) { $content.Split().Count } else { 0 }
            $outSizeMB = [math]::Round($outFile.Length / 1MB, 2)

            # Quick quality checks
            $hasAllCaps = $content -match '(?m)^[A-Z][A-Z\s:,]{5,}$'  # ALL-CAPS headings
            $htmlLeak   = $content -match '</?(?:html|body|div|span|p|h[1-6])\b'
            $emptyRatio = if ($content.Length -gt 0) {
                [math]::Round(($content -split '\n' | Where-Object { $_.Trim() -eq '' }).Count / ($content -split '\n').Count * 100, 1)
            } else { 100 }

            $status = "[PASS]"
            $color  = "Green"
            $notes  = @()
            $notes += "${wordCount} words"
            $notes += "${outSizeMB} MB"
            $notes += "${elapsed}s"
            if ($hasAllCaps) { $notes += "headings OK" }
            if ($htmlLeak)   { $notes += "HTML LEAKED"; $status = "[WARN]"; $color = "Yellow" }
            if ($emptyRatio -gt 40) { $notes += "high empty-line ratio (${emptyRatio}%)"; $status = "[WARN]"; $color = "Yellow" }
            if ($wordCount -lt 100 -and $sizeMB -gt 0.5) { $notes += "LOW word count"; $status = "[WARN]"; $color = "Yellow" }

            Write-Host "        Balabolka: $status $($notes -join ', ')" -ForegroundColor $color
        } elseif ($exitCode -eq 0) {
            Write-Host "        Balabolka: [WARN] Completed but no output file" -ForegroundColor Yellow
        } else {
            $errSnippet = ($r | Select-Object -Last 3) -join ' '
            if ($errSnippet.Length -gt 120) { $errSnippet = $errSnippet.Substring(0, 120) + '...' }
            Write-Host "        Balabolka: [FAIL] Exit $exitCode -- $errSnippet" -ForegroundColor Red
        }

        # -- Kindle mode --
        $outDir2 = Join-Path $tempDir "${ext}_kindle"
        New-Item $outDir2 -ItemType Directory -Force | Out-Null

        $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
        $r2 = & $python $toolPath --input $testFile.FullName --mode kindle --output-dir $outDir2 2>&1
        $sw2.Stop()
        $exitCode2 = $LASTEXITCODE
        $elapsed2 = [math]::Round($sw2.Elapsed.TotalSeconds, 1)

        $outFile2 = Get-ChildItem $outDir2 -Filter "*.txt" -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending | Select-Object -First 1

        if ($exitCode2 -eq 0 -and $outFile2) {
            $content2 = Get-Content $outFile2.FullName -Raw -ErrorAction SilentlyContinue
            $wordCount2 = if ($content2) { $content2.Split().Count } else { 0 }
            $hasMarkdown = $content2 -match '(?m)^##?\s'

            $notes2 = @()
            $notes2 += "${wordCount2} words"
            $notes2 += "${elapsed2}s"
            if ($hasMarkdown) { $notes2 += "Markdown headings OK" }

            Write-Host "        Kindle:    [PASS] $($notes2 -join ', ')" -ForegroundColor Green
        } elseif ($exitCode2 -eq 0) {
            Write-Host "        Kindle:    [WARN] Completed but no output file" -ForegroundColor Yellow
        } else {
            Write-Host "        Kindle:    [FAIL] Exit $exitCode2" -ForegroundColor Red
        }

        Write-Host ""

        $results += [PSCustomObject]@{
            Format    = ".$ext"
            File      = $testFile.Name
            InputMB   = $sizeMB
            BalWords  = if ($outFile) { $wordCount } else { 'FAIL' }
            BalTime   = $elapsed
            KinWords  = if ($outFile2) { $wordCount2 } else { 'FAIL' }
            KinTime   = $elapsed2
        }
    }

    # -- Summary table --
    Write-Host ("=" * 65) -ForegroundColor Cyan
    Write-Host "  SUMMARY" -ForegroundColor Cyan
    Write-Host ("=" * 65) -ForegroundColor Cyan
    Write-Host ""
    $results | Format-Table -AutoSize | Out-String | Write-Host

    Write-Host "  Output files in: $tempDir" -ForegroundColor DarkGray
    Write-Host "  Review the .txt files to verify content quality." -ForegroundColor DarkGray
    Write-Host ""
}
