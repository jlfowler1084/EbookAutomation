#Requires -Version 5.1
<#
.SYNOPSIS
    Scans a folder of PDFs, OCRs image-based ones with Tesseract, and converts all to Kindle KFX.

.DESCRIPTION
    Four-phase batch pipeline:
      Phase 1 — Classify PDFs as IMAGE-BASED / LIKELY-SCANNED / TEXT-BASED using pypdf word counts
      Phase 2 — OCR image-based/likely-scanned PDFs with Tesseract via pytesseract + pdf2image
      Phase 3 — Convert all PDFs (or OCR text outputs) to Kindle via the EbookAutomation module
      Phase 4 — Print summary report

    Dependency behaviour:
      - pypdf missing      → abort (required for Phase 1)
      - Tesseract missing  → warn, skip Phase 2 (OCR), still convert raw PDFs in Phase 3
      - pytesseract/pdf2image missing → same as above

.PARAMETER ScanRoot
    Root folder to scan recursively for PDF files. Default: F:\Books

.PARAMETER WhatIf
    Dry-run — Phase 1 classification only; no OCR or Kindle conversion.

.PARAMETER MaxFiles
    Process at most this many PDFs (0 = no limit). Useful for testing.

.PARAMETER SkipTextBased
    Skip Kindle conversion for TEXT-BASED PDFs; only convert OCR outputs.

.EXAMPLE
    .\Invoke-TesseractKindleBatch.ps1
    .\Invoke-TesseractKindleBatch.ps1 -WhatIf
    .\Invoke-TesseractKindleBatch.ps1 -ScanRoot 'D:\Library' -MaxFiles 10
    .\Invoke-TesseractKindleBatch.ps1 -SkipTextBased
#>
param(
    [string]$ScanRoot     = 'F:\Books',
    [switch]$WhatIf,
    [int]   $MaxFiles     = 0,
    [switch]$SkipTextBased
)

$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'
$totalSw = [System.Diagnostics.Stopwatch]::StartNew()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$ScriptRoot   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ModulePath   = Join-Path $ScriptRoot 'module\EbookAutomation.psd1'
$SettingsPath = Join-Path $ScriptRoot 'config\settings.json'
$OcrOutDir    = Join-Path $ScriptRoot 'processing\tesseract_batch'
$LogDir       = Join-Path $ScriptRoot 'logs'
$Timestamp    = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogFile      = Join-Path $LogDir "tesseract_scan_$Timestamp.log"

# ---------------------------------------------------------------------------
# Logging helper (used throughout — module not imported yet)
# ---------------------------------------------------------------------------
function Write-BatchLog {
    param([string]$Message, [string]$Level = 'INFO')
    $ts     = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line   = "[$ts] [$Level] $Message"
    $color  = switch ($Level) {
        'SUCCESS' { 'Green'  }
        'WARN'    { 'Yellow' }
        'ERROR'   { 'Red'    }
        default   { 'White'  }
    }
    Write-Host $line -ForegroundColor $color
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue } catch {}
}

# ---------------------------------------------------------------------------
# Ensure directories
# ---------------------------------------------------------------------------
foreach ($d in @($LogDir, $OcrOutDir)) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

$sep = '=' * 72
Write-BatchLog $sep
Write-BatchLog '  Invoke-TesseractKindleBatch'
Write-BatchLog $sep
Write-BatchLog "  ScanRoot     : $ScanRoot"
Write-BatchLog "  WhatIf       : $($WhatIf.IsPresent)"
Write-BatchLog "  MaxFiles     : $(if ($MaxFiles -le 0) { 'unlimited' } else { $MaxFiles })"
Write-BatchLog "  SkipTextBased: $($SkipTextBased.IsPresent)"
Write-BatchLog "  Log          : $LogFile"
Write-BatchLog $sep

# ---------------------------------------------------------------------------
# DEPENDENCY CHECK
# ---------------------------------------------------------------------------
Write-BatchLog '--- Dependency Check ---'

# Python
$pyOk = $false
try {
    $allOut = @(& python --version 2>&1)
    $pyVer = ($allOut | Where-Object { "$_" -match 'Python' } | Select-Object -First 1)
    if ($pyVer -and "$pyVer" -match 'Python') {
        Write-BatchLog "  Python       : $pyVer  [OK]"
        $pyOk = $true
    }
} catch {}
if (-not $pyOk) {
    Write-BatchLog '  ABORT: Python not found in PATH. Install Python 3.8+.' 'ERROR'
    exit 1
}

# pypdf — required for Phase 1
$pypdfOk = $false
try {
    $allOut = @(& python -c "import pypdf; print(pypdf.__version__)" 2>&1)
    $out = ($allOut | Where-Object { "$_" -notmatch '^(Traceback|ImportError|ModuleNotFoundError)' } | Select-Object -First 1)
    if ($out -and "$out" -match '[\d\.]') {
        Write-BatchLog "  pypdf        : $out  [OK]"
        $pypdfOk = $true
    }
} catch {}
if (-not $pypdfOk) {
    Write-BatchLog '  ABORT: pypdf not installed. Run: python -m pip install pypdf' 'ERROR'
    exit 1
}

# Tesseract / Poppler
$tesseractExe = $null
$popplerBinDir = $null
$tessPaths = @(
    'C:\Program Files\Tesseract-OCR\tesseract.exe',
    'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
)
if (Test-Path $SettingsPath -ErrorAction SilentlyContinue) {
    try {
        $cfg = Get-Content $SettingsPath -Raw | ConvertFrom-Json -ErrorAction Stop
        if ($cfg.paths.tesseract) {
            $t = $cfg.paths.tesseract
            if (-not [IO.Path]::IsPathRooted($t)) { $t = Join-Path $ScriptRoot $t }
            $tessPaths = @($t) + $tessPaths
        }
    } catch {}
}
foreach ($tp in $tessPaths) {
    if (Test-Path $tp -ErrorAction SilentlyContinue) { $tesseractExe = $tp; break }
}

$ocrDepsOk = $false
if (-not $tesseractExe) {
    Write-BatchLog '  WARN: Tesseract.exe not found — Phase 2 OCR will be skipped.' 'WARN'
} else {
    Write-BatchLog "  Tesseract    : $tesseractExe  [OK]"
    # Poppler — pdf2image needs pdftoppm.exe; resolve from settings or default tools\poppler
    $popplerSearch = Join-Path $ScriptRoot 'tools\poppler'
    if (Test-Path $SettingsPath -ErrorAction SilentlyContinue) {
        try {
            $cfgP = Get-Content $SettingsPath -Raw | ConvertFrom-Json -ErrorAction Stop
            if ($cfgP.paths.poppler) {
                $pp = $cfgP.paths.poppler
                if (-not [IO.Path]::IsPathRooted($pp)) { $pp = Join-Path $ScriptRoot $pp }
                $popplerSearch = $pp
            }
        } catch {}
    }
    $pdftoppm = Get-ChildItem -Path $popplerSearch -Filter 'pdftoppm.exe' -Recurse `
                              -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pdftoppm) {
        $popplerBinDir = $pdftoppm.DirectoryName
        Write-BatchLog "  Poppler      : $popplerBinDir  [OK]"
    } else {
        Write-BatchLog "  WARN: pdftoppm.exe not found under '$popplerSearch' — pdf2image may fail if Poppler is not on PATH." 'WARN'
    }
    $pytessOk  = $false
    $pdf2imgOk = $false
    try {
        $allOut = @(& python -c "import pytesseract" 2>&1)
        $hasError = @($allOut | Where-Object { "$_" -match '(Traceback|ImportError|ModuleNotFoundError|Error)' })
        if (-not $hasError) { $pytessOk = $true; Write-BatchLog '  pytesseract  : OK' }
    } catch {}
    try {
        $allOut = @(& python -c "import pdf2image" 2>&1)
        $hasError = @($allOut | Where-Object { "$_" -match '(Traceback|ImportError|ModuleNotFoundError|Error)' })
        if (-not $hasError) { $pdf2imgOk = $true; Write-BatchLog '  pdf2image    : OK' }
    } catch {}
    if (-not $pytessOk) {
        Write-BatchLog '  WARN: pytesseract not installed — OCR skipped. Run: python -m pip install pytesseract' 'WARN'
    } elseif (-not $pdf2imgOk) {
        Write-BatchLog '  WARN: pdf2image not installed — OCR skipped. Run: python -m pip install pdf2image' 'WARN'
    } else {
        $ocrDepsOk = $true
        Write-BatchLog '  OCR stack    : Tesseract + pytesseract + pdf2image  [OK]' 'SUCCESS'
    }
}

# Calibre
$calibreExe = 'C:\Program Files\Calibre2\ebook-convert.exe'
if (Test-Path $SettingsPath -ErrorAction SilentlyContinue) {
    try {
        $cfg = Get-Content $SettingsPath -Raw | ConvertFrom-Json -ErrorAction Stop
        if ($cfg.paths.calibre) {
            $c = $cfg.paths.calibre
            if (-not [IO.Path]::IsPathRooted($c)) { $c = Join-Path $ScriptRoot $c }
            $calibreExe = $c
        }
    } catch {}
}
if (Test-Path $calibreExe -ErrorAction SilentlyContinue) {
    Write-BatchLog "  Calibre      : $calibreExe  [OK]"
} else {
    Write-BatchLog "  WARN: Calibre not found at '$calibreExe' — Kindle conversion may fail." 'WARN'
}

# EbookAutomation module
if (-not (Test-Path $ModulePath -ErrorAction SilentlyContinue)) {
    Write-BatchLog "  ABORT: Module not found: $ModulePath" 'ERROR'
    exit 1
}
Write-BatchLog "  Module       : $ModulePath  [OK]"

# ---------------------------------------------------------------------------
# SCAN for PDFs
# ---------------------------------------------------------------------------
Write-BatchLog "--- Scanning '$ScanRoot' ---"
if (-not (Test-Path $ScanRoot -ErrorAction SilentlyContinue)) {
    Write-BatchLog "ABORT: ScanRoot does not exist: $ScanRoot" 'ERROR'
    exit 1
}

$allPdfs = @(
    Get-ChildItem -Path $ScanRoot -Filter '*.pdf' -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object FullName
)
$totalFound = $allPdfs.Count

if ($totalFound -eq 0) {
    Write-BatchLog "No PDF files found in '$ScanRoot'." 'WARN'
    exit 0
}
Write-BatchLog "Found $totalFound PDF(s)."

if ($MaxFiles -gt 0 -and $allPdfs.Count -gt $MaxFiles) {
    $allPdfs = @($allPdfs | Select-Object -First $MaxFiles)
    Write-BatchLog "Processing first $MaxFiles file(s) per -MaxFiles."
}

# ---------------------------------------------------------------------------
# PHASE 1: Classify PDFs
# ---------------------------------------------------------------------------
Write-BatchLog '--- Phase 1: Classify PDFs ---'

$classifyPy = Join-Path $env:TEMP 'ebook_tess_classify.py'
Set-Content -Path $classifyPy -Encoding UTF8 -Value @'
import sys, json
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def classify(path):
    try:
        import pypdf
    except ImportError:
        return {'status': 'ERROR', 'reason': 'pypdf not installed', 'words': 0}
    try:
        reader = pypdf.PdfReader(path)
    except Exception as e:
        return {'status': 'ERROR', 'reason': str(e)[:200], 'words': 0}
    total = 0
    checked = min(5, len(reader.pages))
    for i in range(checked):
        try:
            t = reader.pages[i].extract_text() or ''
            total += len(t.split())
        except Exception:
            pass
    if total < 50:
        status = 'IMAGE-BASED'
    elif total < 200:
        status = 'LIKELY-SCANNED'
    else:
        status = 'TEXT-BASED'
    return {'status': status, 'words': total, 'pages_checked': checked}

if __name__ == '__main__':
    print(json.dumps(classify(sys.argv[1])))
'@

$classifications = @{}
$counts = @{ 'IMAGE-BASED' = 0; 'LIKELY-SCANNED' = 0; 'TEXT-BASED' = 0; 'ERROR' = 0 }

for ($idx = 0; $idx -lt $allPdfs.Count; $idx++) {
    $pdf = $allPdfs[$idx]
    $n   = $idx + 1
    Write-BatchLog "[$n/$($allPdfs.Count)] Classify: $($pdf.Name)"
    try {
        $raw      = @(& python -u $classifyPy $pdf.FullName 2>&1)
        $jsonLine = @($raw | Where-Object { "$_" -match '^\{' }) | Select-Object -Last 1
        if ($jsonLine) {
            $result = "$jsonLine" | ConvertFrom-Json
        } else {
            $result = [PSCustomObject]@{ status = 'ERROR'; reason = "No JSON output"; words = 0 }
        }
    } catch {
        $result = [PSCustomObject]@{ status = 'ERROR'; reason = $_.Exception.Message; words = 0 }
    }
    $classifications[$pdf.FullName] = $result
    $st = "$($result.status)"
    if ($counts.ContainsKey($st)) { $counts[$st]++ } else { $counts['ERROR']++ }
    $wStr = if ($null -ne $result.words) { "($($result.words) words)" } else { '' }
    Write-BatchLog "  -> $st $wStr"
}

Write-BatchLog ("Classification totals: IMAGE-BASED={0}  LIKELY-SCANNED={1}  TEXT-BASED={2}  ERROR={3}" -f `
    $counts['IMAGE-BASED'], $counts['LIKELY-SCANNED'], $counts['TEXT-BASED'], $counts['ERROR'])

if ($WhatIf) {
    Write-BatchLog '=== -WhatIf specified: stopping after Phase 1 ==='
    Write-BatchLog ''
    Write-BatchLog 'Full classification results:'
    foreach ($pdf in $allPdfs) {
        $r = $classifications[$pdf.FullName]
        Write-BatchLog ("  [{0,-15}]  {1}" -f $r.status, $pdf.FullName)
    }
    exit 0
}

# ---------------------------------------------------------------------------
# PHASE 2: OCR image-based / likely-scanned PDFs
# ---------------------------------------------------------------------------
Write-BatchLog '--- Phase 2: OCR Image-Based PDFs ---'

$ocrPy = Join-Path $env:TEMP 'ebook_tess_ocr.py'
Set-Content -Path $ocrPy -Encoding UTF8 -Value @'
import sys
from pathlib import Path
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def main():
    pdf_path     = Path(sys.argv[1])
    out_file     = Path(sys.argv[2])
    tess_cmd     = sys.argv[3] if len(sys.argv) > 3 else None
    poppler_dir  = sys.argv[4] if len(sys.argv) > 4 else None
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from pypdf import PdfReader
    except ImportError as e:
        print(f'ERROR: missing dependency: {e}', flush=True)
        sys.exit(1)
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd
    try:
        total = len(PdfReader(str(pdf_path)).pages)
    except Exception as e:
        print(f'ERROR: could not read PDF: {e}', flush=True)
        sys.exit(2)
    progress_file = Path(str(out_file) + '.progress')
    out_file.parent.mkdir(parents=True, exist_ok=True)
    texts = []
    for page in range(1, total + 1):
        try:
            kwargs = {'dpi': 300, 'first_page': page, 'last_page': page}
            if poppler_dir:
                kwargs['poppler_path'] = poppler_dir
            imgs = convert_from_path(str(pdf_path), **kwargs)
            text = pytesseract.image_to_string(imgs[0], config='--oem 3 --psm 6') if imgs else ''
        except Exception as e:
            print(f'WARN: page {page} error: {e}', flush=True)
            text = ''
        texts.append(text)
        frac = f'{page}/{total}'
        print(f'OCR_PROGRESS:{frac}', flush=True)
        try:
            progress_file.write_text(frac, encoding='utf-8')
        except Exception:
            pass
    out_file.write_text('\n\n'.join(texts), encoding='utf-8')
    try:
        progress_file.unlink(missing_ok=True)
    except Exception:
        pass
    print(f'OCR_DONE:{out_file}', flush=True)

if __name__ == '__main__':
    main()
'@

$ocrTargets = @(
    $allPdfs | Where-Object {
        $c = $classifications[$_.FullName]
        $c -and ($c.status -eq 'IMAGE-BASED' -or $c.status -eq 'LIKELY-SCANNED')
    }
)
$ocrResults = @{}  # PDF FullName -> OCR txt path, or $null on failure/skip

if ($ocrTargets.Count -eq 0) {
    Write-BatchLog 'No image-based PDFs to OCR.'
} elseif (-not $ocrDepsOk) {
    Write-BatchLog "WARN: OCR dependencies missing — skipping Phase 2 for $($ocrTargets.Count) file(s)." 'WARN'
    foreach ($pdf in $ocrTargets) { $ocrResults[$pdf.FullName] = $null }
} else {
    for ($oi = 0; $oi -lt $ocrTargets.Count; $oi++) {
        $pdf    = $ocrTargets[$oi]
        $ocrN   = $oi + 1
        # Use a zero-padded index to avoid collisions between books with the same title
        $outTxt = Join-Path $OcrOutDir ("{0:D4}_{1}_ocr.txt" -f $oi, $pdf.BaseName)
        $ocrResults[$pdf.FullName] = $null

        Write-BatchLog "OCR [$ocrN/$($ocrTargets.Count)] $($pdf.Name)"

        # Resume support — skip if this OCR output already exists
        if (Test-Path $outTxt -ErrorAction SilentlyContinue) {
            $szKB = [math]::Round((Get-Item $outTxt).Length / 1KB, 1)
            Write-BatchLog "  Already exists ($szKB KB) — skipping OCR (delete to re-run)."
            $ocrResults[$pdf.FullName] = $outTxt
            continue
        }

        try {
            $outLog      = Join-Path $env:TEMP 'ebook_tess_ocr_out.txt'
            $errLog      = Join-Path $env:TEMP 'ebook_tess_ocr_err.txt'
            $progressFile = "$outTxt.progress"
            if (Test-Path $outLog)       { Remove-Item $outLog       -Force -ErrorAction SilentlyContinue }
            if (Test-Path $errLog)       { Remove-Item $errLog       -Force -ErrorAction SilentlyContinue }
            if (Test-Path $progressFile) { Remove-Item $progressFile -Force -ErrorAction SilentlyContinue }

            $argStr = "-u `"$ocrPy`" `"$($pdf.FullName)`" `"$outTxt`""
            if ($tesseractExe) { $argStr += " `"$tesseractExe`"" }
            else               { $argStr += " `"`"" }
            if ($popplerBinDir) { $argStr += " `"$popplerBinDir`"" }

            $proc  = Start-Process -FilePath 'python' -ArgumentList $argStr `
                                   -PassThru -NoNewWindow `
                                   -RedirectStandardOutput $outLog `
                                   -RedirectStandardError  $errLog
            $ocrSw    = [System.Diagnostics.Stopwatch]::StartNew()
            $lastProg = ''

            while (-not $proc.HasExited) {
                Start-Sleep -Seconds 5
                $elSec = [math]::Round($ocrSw.Elapsed.TotalSeconds, 0)
                $frac  = $null
                if (Test-Path $progressFile -ErrorAction SilentlyContinue) {
                    try { $frac = (Get-Content $progressFile -Raw -ErrorAction SilentlyContinue).Trim() } catch {}
                }
                if ($frac -and $frac -ne $lastProg) {
                    $lastProg = $frac
                    Write-BatchLog "  Page $frac  (${elSec}s)"
                } else {
                    Write-BatchLog "  Running... (${elSec}s)"
                }
            }
            $proc.WaitForExit()
            Remove-Item $progressFile -Force -ErrorAction SilentlyContinue

            $doneLine = ''
            if (Test-Path $outLog -ErrorAction SilentlyContinue) {
                $doneLine = @(
                    Get-Content $outLog -ErrorAction SilentlyContinue |
                    Where-Object { "$_" -match '^OCR_DONE:' }
                ) | Select-Object -Last 1
            }

            if ($doneLine) {
                $resultPath = "$doneLine" -replace '^OCR_DONE:', ''
                if (Test-Path $resultPath -ErrorAction SilentlyContinue) {
                    $szKB = [math]::Round((Get-Item $resultPath).Length / 1KB, 1)
                    Write-BatchLog "  Done -> $([IO.Path]::GetFileName($resultPath))  ($szKB KB)" 'SUCCESS'
                    $ocrResults[$pdf.FullName] = $resultPath
                } else {
                    Write-BatchLog "  WARN: OCR_DONE reported but file not found: $resultPath" 'WARN'
                }
            } else {
                $errTxt = ''
                if (Test-Path $errLog -ErrorAction SilentlyContinue) {
                    $errTxt = (Get-Content $errLog -Raw -ErrorAction SilentlyContinue) -replace '\r?\n', ' '
                }
                Write-BatchLog "  WARN: OCR produced no output. Exit=$($proc.ExitCode). $errTxt" 'WARN'
            }
        } catch {
            Write-BatchLog "  ERROR: $($_.Exception.Message)" 'ERROR'
        }
    }
}

# ---------------------------------------------------------------------------
# PHASE 3: Kindle Conversion
# ---------------------------------------------------------------------------
Write-BatchLog '--- Phase 3: Kindle Conversion ---'

try {
    Import-Module $ModulePath -Force -ErrorAction Stop
    Write-BatchLog 'EbookAutomation module imported.' 'SUCCESS'
} catch {
    Write-BatchLog "ABORT: Failed to import module: $($_.Exception.Message)" 'ERROR'
    exit 1
}

# Resolve Kindle output dir from config (for before/after snapshot)
$kindleDir = Join-Path $ScriptRoot 'output\kindle'
try {
    $kCfg = Get-EbookConfig -ErrorAction SilentlyContinue
    if ($kCfg -and $kCfg.paths.kindle) {
        $kp = $kCfg.paths.kindle
        $kindleDir = if ([IO.Path]::IsPathRooted($kp)) { $kp } else { Join-Path $ScriptRoot $kp }
    }
} catch {}

$kindleBefore = @()
if (Test-Path $kindleDir -ErrorAction SilentlyContinue) {
    $kindleBefore = @(
        Get-ChildItem -Path $kindleDir -Recurse -File -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    )
}

# Conversion results
$convResults = New-Object 'System.Collections.Generic.List[PSCustomObject]'

function Invoke-KindleConvert {
    param([string]$InputFile, [string]$OriginalPdf, [string]$Class)
    $item = [PSCustomObject]@{
        OriginalPdf    = $OriginalPdf
        InputFile      = $InputFile
        Classification = $Class
        Success        = $false
        SkippedReason  = $null
    }
    if (-not (Test-Path $InputFile -ErrorAction SilentlyContinue)) {
        Write-BatchLog "  WARN: Input file not found: $InputFile" 'WARN'
        $item.SkippedReason = 'InputNotFound'
        $script:convResults.Add($item)
        return
    }
    try {
        $ok = Convert-ToKindle -InputFile $InputFile
        $item.Success = ($ok -eq $true)
    } catch {
        Write-BatchLog "  ERROR: Convert-ToKindle threw: $($_.Exception.Message)" 'ERROR'
        $item.Success = $false
    }
    $script:convResults.Add($item)
}

for ($ci = 0; $ci -lt $allPdfs.Count; $ci++) {
    $pdf   = $allPdfs[$ci]
    $class = if ($classifications.ContainsKey($pdf.FullName)) { $classifications[$pdf.FullName].status } else { 'UNKNOWN' }
    Write-BatchLog ("Convert [{0}/{1}] [{2}] {3}" -f ($ci + 1), $allPdfs.Count, $class, $pdf.Name)

    if ($class -eq 'IMAGE-BASED' -or $class -eq 'LIKELY-SCANNED') {
        $ocrTxt = if ($ocrResults.ContainsKey($pdf.FullName)) { $ocrResults[$pdf.FullName] } else { $null }
        if ($ocrTxt -and (Test-Path $ocrTxt -ErrorAction SilentlyContinue)) {
            Write-BatchLog "  Using OCR text: $([IO.Path]::GetFileName($ocrTxt))"
            Invoke-KindleConvert -InputFile $ocrTxt -OriginalPdf $pdf.FullName -Class $class
        } else {
            if ($ocrDepsOk) {
                Write-BatchLog '  WARN: OCR text missing — falling back to raw PDF (may yield poor text).' 'WARN'
            } else {
                Write-BatchLog '  Converting raw PDF (OCR skipped — missing deps).'
            }
            Invoke-KindleConvert -InputFile $pdf.FullName -OriginalPdf $pdf.FullName -Class $class
        }
    } elseif ($class -eq 'TEXT-BASED') {
        if ($SkipTextBased) {
            Write-BatchLog '  Skipping (TEXT-BASED + -SkipTextBased).'
            $convResults.Add([PSCustomObject]@{
                OriginalPdf    = $pdf.FullName
                InputFile      = $pdf.FullName
                Classification = $class
                Success        = $false
                SkippedReason  = 'SkipTextBased'
            })
        } else {
            Invoke-KindleConvert -InputFile $pdf.FullName -OriginalPdf $pdf.FullName -Class $class
        }
    } else {
        Write-BatchLog "  Skipping (classification: $class)" 'WARN'
        $convResults.Add([PSCustomObject]@{
            OriginalPdf    = $pdf.FullName
            InputFile      = $pdf.FullName
            Classification = $class
            Success        = $false
            SkippedReason  = "ClassError:$class"
        })
    }
}

# ---------------------------------------------------------------------------
# PHASE 4: Summary
# ---------------------------------------------------------------------------
Write-BatchLog '--- Phase 4: Summary ---'

$succeeded = @($convResults | Where-Object { $_.Success })
$failed    = @($convResults | Where-Object { -not $_.Success -and -not $_.SkippedReason })
$skipped   = @($convResults | Where-Object { $_.SkippedReason })

# New Kindle files created this run
$kindleAfter = @()
if (Test-Path $kindleDir -ErrorAction SilentlyContinue) {
    $kindleAfter = @(
        Get-ChildItem -Path $kindleDir -Recurse -File -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    )
}
$newFiles = @($kindleAfter | Where-Object { $kindleBefore -notcontains $_ })

$ocrCompleted = @($ocrResults.GetEnumerator() | Where-Object { $null -ne $_.Value }).Count
$ocrFailed    = $ocrTargets.Count - $ocrCompleted
$totalElapsed = [math]::Round($totalSw.Elapsed.TotalSeconds, 1)

Write-BatchLog $sep
Write-BatchLog '  TESSERACT KINDLE BATCH — COMPLETE'
Write-BatchLog $sep
Write-BatchLog "  Scan root       : $ScanRoot"
Write-BatchLog "  PDFs found      : $totalFound   |   Processed: $($allPdfs.Count)"
Write-BatchLog "  Total elapsed   : ${totalElapsed}s"
Write-BatchLog ''
Write-BatchLog '  Classification  :'
Write-BatchLog "    IMAGE-BASED   : $($counts['IMAGE-BASED'])"
Write-BatchLog "    LIKELY-SCANNED: $($counts['LIKELY-SCANNED'])"
Write-BatchLog "    TEXT-BASED    : $($counts['TEXT-BASED'])"
Write-BatchLog "    ERROR         : $($counts['ERROR'])"
Write-BatchLog ''
Write-BatchLog '  OCR             :'
Write-BatchLog "    Targets       : $($ocrTargets.Count)"
Write-BatchLog "    Completed     : $ocrCompleted"
Write-BatchLog "    Failed        : $ocrFailed"
Write-BatchLog ''
Write-BatchLog '  Kindle output   :'
Write-BatchLog "    Succeeded     : $($succeeded.Count)"
Write-BatchLog "    Failed        : $($failed.Count)"
Write-BatchLog "    Skipped       : $($skipped.Count)"
Write-BatchLog ''
Write-BatchLog '  New Kindle files:'
if ($newFiles.Count -gt 0) {
    foreach ($f in $newFiles) {
        try {
            $szMB = [math]::Round((Get-Item $f -ErrorAction Stop).Length / 1MB, 2)
            Write-BatchLog ("    {0}  ({1} MB)" -f [IO.Path]::GetFileName($f), $szMB) 'SUCCESS'
        } catch {
            Write-BatchLog "    $([IO.Path]::GetFileName($f))" 'SUCCESS'
        }
    }
} else {
    Write-BatchLog '    (none)'
}
if ($failed.Count -gt 0) {
    Write-BatchLog ''
    Write-BatchLog '  Failed conversions:'
    foreach ($r in $failed) {
        Write-BatchLog "    $($r.OriginalPdf)" 'WARN'
    }
}
Write-BatchLog $sep
Write-BatchLog "  Log: $LogFile"
Write-BatchLog $sep

# Cleanup temp Python scripts
Remove-Item $classifyPy, $ocrPy -Force -ErrorAction SilentlyContinue
