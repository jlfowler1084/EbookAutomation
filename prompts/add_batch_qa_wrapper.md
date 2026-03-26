# Prompt: Add Invoke-BatchQA PowerShell Wrapper + Integrate batch_qa.py

## Context
We've built `tools/batch_qa.py` — a batch QA orchestrator that processes a folder of ebooks, collects structured diagnostics per book, detects failure patterns across the batch, and generates JSON + Markdown reports. It writes results to the pattern_db SQLite database.

## Tasks

### 1. Copy batch_qa.py into the tools/ folder
The file should already be at the project root or in a staging location. Move/copy it to `tools/batch_qa.py`.

### 2. Add `Invoke-BatchQA` function to EbookAutomation.psm1

Add this function BEFORE the `Test-EbookPipeline` function. Follow existing patterns for parameter style, logging, and Python delegation.

```powershell
function Invoke-BatchQA {
    <#
    .SYNOPSIS
        Run batch QA diagnostics on a folder of ebooks.
    .DESCRIPTION
        Processes every supported file in the target folder through the
        extraction pipeline, collects structured diagnostics, detects
        failure patterns across books, and produces summary reports.

        Results are stored in the pattern database and written as both
        JSON (machine-readable) and Markdown (human-readable) reports
        to data\batch_reports\.

        Default mode is Quick (HTML extraction only, no API costs).
        Use -IncludeVQA to add Visual QA scoring (~$0.04/book).
    .PARAMETER FolderPath
        Path to folder containing ebooks to process. Required.
    .PARAMETER Quick
        HTML extraction diagnostics only (default behavior).
        Mutually exclusive with -Full.
    .PARAMETER Full
        Include KFX conversion in addition to HTML extraction.
    .PARAMETER IncludeVQA
        Run Visual QA scoring on each book's KFX output.
        Requires -Full mode. Adds ~$0.04 API cost per book.
    .PARAMETER Limit
        Maximum number of books to process.
    .PARAMETER FormatFilter
        Filter to specific format (e.g., 'pdf', 'epub').
    .PARAMETER Parallel
        Number of concurrent workers (default: 1).
    .PARAMETER Resume
        Resume an interrupted batch run by providing the run ID.
    .PARAMETER NoDb
        Skip writing results to the pattern database.
    .EXAMPLE
        Invoke-BatchQA -FolderPath "F:\TestBooks"
    .EXAMPLE
        Invoke-BatchQA -FolderPath "F:\Library\PDFs" -Limit 10
    .EXAMPLE
        Invoke-BatchQA -FolderPath "F:\TestBooks" -Full -IncludeVQA
    .EXAMPLE
        Invoke-BatchQA -FolderPath "F:\TestBooks" -Parallel 3
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$FolderPath,

        [switch]$Full,
        [switch]$IncludeVQA,
        [int]$Limit,
        [string]$FormatFilter,
        [int]$Parallel = 1,
        [string]$Resume,
        [switch]$NoDb
    )

    $pythonPath = (Get-EbookConfig).paths.python
    if (-not $pythonPath) { $pythonPath = "python" }
    $batchScript = Join-Path $script:ModuleRoot "tools" "batch_qa.py"

    if (-not (Test-Path $batchScript)) {
        Write-EbookLog "Batch QA script not found: $batchScript" -Level ERROR
        return $null
    }

    if (-not (Test-Path $FolderPath)) {
        Write-EbookLog "Folder not found: $FolderPath" -Level ERROR
        return $null
    }

    # Build argument list
    $pyArgs = @("`"$batchScript`"", "run", "`"$FolderPath`"")

    if ($Full)        { $pyArgs += "--full" }
    if ($IncludeVQA)  { $pyArgs += "--vqa" }
    if ($Limit -gt 0) { $pyArgs += @("--limit", $Limit) }
    if ($FormatFilter) { $pyArgs += @("--format", $FormatFilter) }
    if ($Parallel -gt 1) { $pyArgs += @("--parallel", $Parallel) }
    if ($Resume)       { $pyArgs += @("--resume", $Resume) }
    if ($NoDb)         { $pyArgs += "--no-db" }

    Write-EbookLog "--------------------------------------------------------"
    Write-EbookLog "Batch QA started on: $FolderPath"
    if ($Full) { Write-EbookLog "  Mode: Full (HTML + KFX)" }
    else { Write-EbookLog "  Mode: Quick (HTML only)" }
    if ($IncludeVQA) { Write-EbookLog "  Visual QA: ENABLED" }
    if ($Limit -gt 0) { Write-EbookLog "  Limit: $Limit books" }
    if ($Parallel -gt 1) { Write-EbookLog "  Workers: $Parallel" }
    Write-EbookLog "--------------------------------------------------------"

    $pyArgsStr = $pyArgs -join " "
    $proc = Start-Process -FilePath $pythonPath -ArgumentList $pyArgsStr `
                          -NoNewWindow -Wait -PassThru

    if ($proc.ExitCode -eq 0) {
        Write-EbookLog "Batch QA completed successfully" -Level SUCCESS
    } else {
        Write-EbookLog "Batch QA finished with exit code $($proc.ExitCode)" -Level WARN
    }

    return ($proc.ExitCode -eq 0)
}
```

### 3. Export `Invoke-BatchQA` in the module manifest

In `EbookAutomation.psd1`, add `'Invoke-BatchQA'` to the `FunctionsToExport` array.

### 4. Create the `data/batch_reports/` directory

Ensure the directory exists: `data/batch_reports/` (alongside the existing `data/ebook_patterns.db`).

### 5. Git commit and push

```
git add tools/batch_qa.py module/EbookAutomation.psm1 module/EbookAutomation.psd1
git commit -m "feat: add Batch QA system (tools/batch_qa.py + Invoke-BatchQA)

- New batch_qa.py orchestrator processes folder of ebooks with diagnostics
- Per-book structural analysis: chapter detection, text quality, formatting
- Rule-based failure pattern detection across batch
- JSON + Markdown report generation in data/batch_reports/
- Database integration via existing pattern_db schema + new batch_runs table
- Compare subcommand for tracking progress between runs
- Resume support for interrupted batches
- Concurrent processing via --parallel flag
- PowerShell Invoke-BatchQA wrapper for consistent module interface"
git push
```
