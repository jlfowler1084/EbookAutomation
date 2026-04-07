# ════════════════════════════════════════════════════════════════════════
# Night Batch Setup — 2026-04-03 (simplified)
# ════════════════════════════════════════════════════════════════════════
# 1. Moves PDF ebooks from Downloads → F:\Books
# 2. Moves Double_Columned subfolder books up to F:\Books root
# 3. Runs batch_qa.py on F:\Books (flat scan, --limit 100)
# ════════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Continue"
$target = "F:\Books"

if (-not (Test-Path $target)) {
    New-Item -ItemType Directory -Path $target -Force | Out-Null
}

# ── Step 1: Move PDFs from Downloads ───────────────────────────
$downloads = "C:\Users\Joe\Downloads"
$moved = 0
$skipped = 0

Write-Host "`n=== Moving PDFs from Downloads ===" -ForegroundColor Green

Get-ChildItem -Path $downloads -Filter "*.pdf" -File | ForEach-Object {
    $dest = Join-Path $target $_.Name
    if (Test-Path $dest) {
        $skipped++
    } else {
        Move-Item $_.FullName $dest -ErrorAction SilentlyContinue
        if ($?) { $moved++ } else { $skipped++ }
    }
}

Write-Host "  Moved:   $moved PDFs"
if ($skipped -gt 0) { Write-Host "  Skipped: $skipped (already exist or failed)" -ForegroundColor Yellow }

# ── Step 2: Move Double_Columned books up to root ─────────────
$dcFolder = "F:\Books\Double_Columned"
$dcMoved = 0

if (Test-Path $dcFolder) {
    Write-Host "`n=== Moving Double_Columned books to F:\Books root ===" -ForegroundColor Green
    Get-ChildItem -Path $dcFolder -File | ForEach-Object {
        $dest = Join-Path $target $_.Name
        if (-not (Test-Path $dest)) {
            Move-Item $_.FullName $dest -ErrorAction SilentlyContinue
            if ($?) { $dcMoved++ }
        }
    }
    Write-Host "  Moved:   $dcMoved books"

    # Clean up empty folder
    if ((Get-ChildItem $dcFolder -Force | Measure-Object).Count -eq 0) {
        Remove-Item $dcFolder -Force
        Write-Host "  Removed empty Double_Columned folder"
    }
}

# ── Summary ─────────────────────────────────────────────────────
Write-Host "`n=== F:\Books Inventory ===" -ForegroundColor Green
$total = (Get-ChildItem $target -File | Measure-Object).Count
Get-ChildItem $target -File | Group-Object Extension | Sort-Object Count -Descending | ForEach-Object {
    Write-Host "  $($_.Count.ToString().PadLeft(4)) $($_.Name)"
}
Write-Host "  ---- -----"
Write-Host "  $($total.ToString().PadLeft(4)) total"

# ── Launch ──────────────────────────────────────────────────────
Write-Host "`n=== Launch Command ===" -ForegroundColor Green
Write-Host "cd F:\Projects\EbookAutomation" -ForegroundColor Cyan
Write-Host "python tools\batch_qa.py run `"$target`" --limit 100 --parallel 2" -ForegroundColor Cyan
Write-Host ""

$response = Read-Host "Launch batch now? (y/n)"
if ($response -eq 'y') {
    Set-Location "F:\Projects\EbookAutomation"
    Write-Host "`nStarting batch QA..." -ForegroundColor Green
    python tools\batch_qa.py run "$target" --limit 100 --parallel 2
} else {
    Write-Host "Staging complete. Run the command above when ready." -ForegroundColor Yellow
}
