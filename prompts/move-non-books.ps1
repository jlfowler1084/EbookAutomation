# ── Move Non-Book PDFs from F:\Books ──────────────────────────────────────
# Reads the batch_20260403_231239.json report and identifies non-book PDFs
# (tax forms, billing notices, duplicates, etc.) then moves them to
# F:\Books\Non_Books\ so they don't clutter future batch runs.

$ErrorActionPreference = "Stop"
$booksDir = "F:\Books"
$nonBooksDir = "F:\Books\Non_Books"
$batchJson = "F:\Projects\EbookAutomation\data\batch_reports\batch_20260403_231239.json"

# ── Load batch report ──────────────────────────────────────────────────────
if (-not (Test-Path $batchJson)) {
    Write-Host "ERROR: Batch report not found at $batchJson" -ForegroundColor Red
    exit 1
}

$report = Get-Content $batchJson -Raw | ConvertFrom-Json

# ── Identify non-book PDFs ─────────────────────────────────────────────────
# Criteria: PDF files that are clearly not books based on batch diagnostics
# 1. Zero chapters AND word count < 3000 (forms, notices, statements)
# 2. Known non-book filename patterns (tax, billing, COBRA, leave request, etc.)
# 3. Duplicate copies (multiple copies of same book name)

$nonBookPatterns = @(
    "tax", "billing", "invoice", "statement", "cobra",
    "leave.*request", "brokerage", "1099", "w-?2", "w-?4",
    "pay.*stub", "receipt", "insurance", "benefits"
)

$nonBooks = @()
$duplicates = @{}

foreach ($book in $report.books) {
    $fn = $book.filename
    $ext = [System.IO.Path]::GetExtension($fn).ToLower()

    # Only process PDFs (EPUBs have separate issues tracked in EB-82)
    if ($ext -ne ".pdf") { continue }

    $isNonBook = $false
    $reason = ""

    # Check 1: Zero chapters + very low word count = likely a form/notice
    $chapters = $book.structure.chapter_count
    $words = $book.structure.word_count
    if ($chapters -eq 0 -and $words -lt 3000) {
        $isNonBook = $true
        $reason = "0 chapters, $words words (likely form/notice)"
    }

    # Check 2: Filename matches non-book patterns
    foreach ($pattern in $nonBookPatterns) {
        if ($fn -imatch $pattern) {
            $isNonBook = $true
            $reason = "Filename matches non-book pattern: $pattern"
            break
        }
    }

    # Track duplicates (same stem appearing multiple times)
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($fn) -replace '\s*\(\d+\)\s*$', '' -replace '\s*-\s*Copy\s*$', ''
    if (-not $duplicates.ContainsKey($stem)) {
        $duplicates[$stem] = @()
    }
    $duplicates[$stem] += $fn

    if ($isNonBook) {
        $nonBooks += [PSCustomObject]@{
            Filename = $fn
            Reason   = $reason
            Words    = $words
            Chapters = $chapters
            Status   = $book.overall_status
        }
    }
}

# Check 3: Find duplicates (stem appears 3+ times)
foreach ($stem in $duplicates.Keys) {
    if ($duplicates[$stem].Count -ge 3) {
        # Keep the first one, mark the rest as duplicates
        $copies = $duplicates[$stem] | Select-Object -Skip 1
        foreach ($copy in $copies) {
            # Don't double-add if already in nonBooks
            if ($nonBooks.Filename -notcontains $copy) {
                $book = $report.books | Where-Object { $_.filename -eq $copy }
                $nonBooks += [PSCustomObject]@{
                    Filename = $copy
                    Reason   = "Duplicate of '$stem' ($($duplicates[$stem].Count) copies found)"
                    Words    = if ($book) { $book.structure.word_count } else { 0 }
                    Chapters = if ($book) { $book.structure.chapter_count } else { 0 }
                    Status   = if ($book) { $book.overall_status } else { "N/A" }
                }
            }
        }
    }
}

# ── Display findings ───────────────────────────────────────────────────────
if ($nonBooks.Count -eq 0) {
    Write-Host "`nNo non-book PDFs identified." -ForegroundColor Green
    exit 0
}

Write-Host "`n══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Non-Book PDFs Identified: $($nonBooks.Count)" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════════════════════" -ForegroundColor Cyan

foreach ($nb in $nonBooks | Sort-Object Filename) {
    $color = if ($nb.Status -eq "WARN") { "Yellow" } elseif ($nb.Status -eq "FAIL") { "Red" } else { "Gray" }
    Write-Host "  [$($nb.Status)]" -ForegroundColor $color -NoNewline
    Write-Host " $($nb.Filename)" -NoNewline
    Write-Host " — $($nb.Reason)" -ForegroundColor DarkGray
}

# ── Confirm and move ──────────────────────────────────────────────────────
Write-Host "`nDestination: $nonBooksDir" -ForegroundColor Cyan
$confirm = Read-Host "`nMove these $($nonBooks.Count) files to Non_Books? (y/n)"

if ($confirm -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# Create destination
if (-not (Test-Path $nonBooksDir)) {
    New-Item -ItemType Directory -Path $nonBooksDir -Force | Out-Null
    Write-Host "Created: $nonBooksDir" -ForegroundColor Green
}

$moved = 0
$notFound = 0
foreach ($nb in $nonBooks) {
    $src = Join-Path $booksDir $nb.Filename
    $dst = Join-Path $nonBooksDir $nb.Filename
    if (Test-Path $src) {
        Move-Item -Path $src -Destination $dst -Force
        $moved++
        Write-Host "  Moved: $($nb.Filename)" -ForegroundColor Green
    } else {
        $notFound++
        Write-Host "  Not found: $($nb.Filename)" -ForegroundColor Yellow
    }
}

Write-Host "`nDone: $moved moved, $notFound not found." -ForegroundColor Cyan
