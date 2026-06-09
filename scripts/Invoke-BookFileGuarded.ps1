#Requires -Version 7.0
<#
.SYNOPSIS
    Guarded cron entry point for the steady-state propose-only inbox sweep (EB-380 U3/U4).

.DESCRIPTION
    Validates -LibraryRoot against the canonical config/settings.json value,
    sets PYTHONHASHSEED=0, shells out to the Python inbox driver, verifies the
    queue artifact, and posts a Discord digest.

    MOVES NOTHING.  Phase-1 propose-only.
    Auto-move is T3 (ADR-0043) and requires a new ADR before it is added here.

.PARAMETER LibraryRoot
    Library root to sweep.  Must match the canonical value in config/settings.json.
    When omitted the canonical config value is used without validation.

.PARAMETER RunDir
    Directory for the queue and lock file.
    Defaults to data\batch_reports\book_inbox_sweep under the project root.

.PARAMETER SettingsPath
    Path to settings.json.  Defaults to config\settings.json under the project root.
    Exposed as a test seam; production always uses the default.

.PARAMETER Python
    Python executable.  Defaults to 'python'.

.PARAMETER SettleSeconds
    Minimum file age in seconds before a file is eligible.  Default: 30.

.PARAMETER DiscordSender
    Path to Send-DiscordWebhook.ps1.  Defaults to the ClaudeInfra canonical location.
    Exposed as a test seam.

.PARAMETER NoRun
    Suppress the entry-point call.  Used by tests that dot-source this file to
    load function definitions without triggering Main.

.EXAMPLE
    .\scripts\Invoke-BookFileGuarded.ps1
    Run the inbox sweep using config defaults.

.EXAMPLE
    .\scripts\Invoke-BookFileGuarded.ps1 -WhatIf
    Dry-run: classify without writing the queue.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$LibraryRoot  = '',
    [string]$RunDir       = '',
    [string]$SettingsPath = '',
    [string]$Python       = 'python',
    [int]$SettleSeconds   = 30,
    [string]$DiscordSender = 'F:\Projects\ClaudeInfra\tools\Send-DiscordWebhook.ps1',
    [switch]$NoRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# CRITICAL: Snapshot run decision and ALL args BEFORE any dot-source.
# A dot-source that declares param([switch]$NoRun) in THIS scope would reassign
# our own $NoRun, silently turning the entry point into a no-op (INFRA-439
# dot-source scope-leak).  The entry guard reads $runMain, never $NoRun.
$runMain          = -not $NoRun
$argLibRoot       = $LibraryRoot
$argRunDir        = $RunDir
$argSettings      = $SettingsPath
$argPython        = $Python
$argSettle        = $SettleSeconds
$argDiscordSender = $DiscordSender

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

# AUTO-MOVE IS T3 — do NOT add confirm invocation without a new ADR

# ── Config helpers ────────────────────────────────────────────────────────────

function Get-CanonicalLibraryRoot {
    param([string]$SettingsFile)
    $sf = if ($SettingsFile) { $SettingsFile } else { Join-Path $ProjectRoot 'config\settings.json' }
    $data = Get-Content -LiteralPath $sf -Raw -Encoding UTF8 | ConvertFrom-Json
    return [System.IO.Path]::GetFullPath([string]$data.library.library_root)
}

# ── Aging-backlog helper ──────────────────────────────────────────────────────

function Get-AgingBacklogSummary {
    param([string]$QueuePath, [int]$ThresholdDays = 7)

    if (-not (Test-Path -LiteralPath $QueuePath)) { return '' }

    $actionable = 'proposed', 'ambiguous', 'no_match', 'duplicate', 'review_oracle_missing'
    $now = [DateTimeOffset]::UtcNow
    $agingCount = 0
    $maxAgeDays = 0.0

    foreach ($line in (Get-Content -LiteralPath $QueuePath -Encoding UTF8)) {
        $line = $line.Trim()
        if (-not $line) { continue }
        try {
            $row = $line | ConvertFrom-Json
            if ($row.tier -notin $actionable) { continue }
            $swept = [DateTimeOffset]::Parse(
                $row.swept_at, $null,
                [System.Globalization.DateTimeStyles]::RoundtripKind)
            $ageDays = ($now - $swept).TotalDays
            if ($ageDays -ge $ThresholdDays) {
                $agingCount++
                if ($ageDays -gt $maxAgeDays) { $maxAgeDays = $ageDays }
            }
        }
        catch { }
    }

    if ($agingCount -eq 0) { return '' }
    $oldest = [Math]::Round($maxAgeDays)
    return "aging backlog: $agingCount row(s), oldest $oldest day(s)"
}

# ── Discord digest (U4 — best-effort) ────────────────────────────────────────

function Send-BookInboxDigest {
    param([string]$DigestText, [string]$SenderPath)

    if (-not $DigestText) { return }

    if (-not (Test-Path -LiteralPath $SenderPath)) {
        Write-Host "Discord sender not found; digest (stdout only):"
        Write-Host $DigestText
        return
    }

    try {
        # -Verbose:$false prevents the REST call details from leaking into transcript.
        # The sender's output is suppressed (*> $null) so the webhook URL/token never
        # surfaces in the wrapper's stdout/stderr.  Never pass the URL as ShouldProcess.
        & $SenderPath `
            -ProjectName EbookAutomation `
            -EventType   Info `
            -Summary     $DigestText `
            -Verbose:$false *> $null
    }
    catch {
        Write-Warning "Discord digest failed (non-fatal): $_"
    }
}

# ── Main ──────────────────────────────────────────────────────────────────────

function Main {
    # Resolve canonical library root from config
    $canonicalRoot = Get-CanonicalLibraryRoot -SettingsFile $argSettings

    # Validate -LibraryRoot when provided
    if ($argLibRoot) {
        $given = [System.IO.Path]::GetFullPath($argLibRoot)
        if (-not [string]::Equals($given, $canonicalRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Error ("LibraryRoot mismatch: given '$given' != canonical '$canonicalRoot'" +
                         " (from config/settings.json).  Pass the canonical path.")
            exit 2
        }
    }

    $resolvedRunDir = if ($argRunDir) {
        [System.IO.Path]::GetFullPath($argRunDir)
    } else {
        Join-Path $ProjectRoot 'data\batch_reports\book_inbox_sweep'
    }

    New-Item -ItemType Directory -Force -Path $resolvedRunDir | Out-Null
    $queuePath = Join-Path $resolvedRunDir 'inbox-proposals.jsonl'

    # Set PYTHONPATH so `python -m book_filer.inbox` resolves the package
    $oldPythonPath = $env:PYTHONPATH
    # Set PYTHONHASHSEED=0 for deterministic queue output (EB-380 R6)
    $oldSeed = $env:PYTHONHASHSEED
    $env:PYTHONPATH   = Join-Path $ProjectRoot 'tools'
    $env:PYTHONHASHSEED = '0'

    $exitCode    = 0
    $sweepOutput = @()

    try {
        $pythonArgs = @(
            '-m', 'book_filer.inbox',
            '--library-root', $canonicalRoot,
            '--run-dir',      $resolvedRunDir,
            '--settle-seconds', $argSettle
        )
        if ($argSettings) {
            $pythonArgs += '--settings-path', $argSettings
        }

        if ($PSCmdlet.ShouldProcess($canonicalRoot, 'sweep inbox')) {
            $sweepOutput = & $argPython @pythonArgs 2>&1
            $exitCode    = $LASTEXITCODE
        }
    }
    finally {
        $env:PYTHONHASHSEED = $oldSeed
        $env:PYTHONPATH     = $oldPythonPath
    }

    # ── Artifact verification — not exit code alone ───────────────────────────
    $artifactPresent = Test-Path -LiteralPath $queuePath
    $sweepFailed     = ($exitCode -ne 0) -or (-not $artifactPresent)

    if ($sweepFailed) {
        Write-Warning ("INBOX-SWEEP ALERT: exit=$exitCode artifact_present=$artifactPresent")
        if ($sweepOutput) { Write-Warning ($sweepOutput -join "`n") }
    }

    # ── Build digest ──────────────────────────────────────────────────────────
    $timestamp   = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mmZ')
    $summaryLine = ($sweepOutput | Select-Object -Last 1) -as [string]
    if (-not $summaryLine) { $summaryLine = '(no output)' }

    $isQuietRun  = $summaryLine -match 'swept 0 files'
    $agingSummary = if ($artifactPresent -and -not $sweepFailed) {
        Get-AgingBacklogSummary -QueuePath $queuePath
    } else { '' }

    $digestLines = @("EB-380 inbox sweep -- $timestamp", "  $summaryLine")
    if ($agingSummary)  { $digestLines += "  $agingSummary" }
    if ($isQuietRun)    { $digestLines += "  heartbeat: 0 new files, healthy" }
    if ($sweepFailed)   { $digestLines += "  ALERT: sweep failed (exit=$exitCode, artifact=$artifactPresent)" }
    $digestText = $digestLines -join "`n"

    Write-Host $digestText

    # ── U4: Discord digest (best-effort) ─────────────────────────────────────
    Send-BookInboxDigest -DigestText $digestText -SenderPath $argDiscordSender

    # ── Exit with correct signal ──────────────────────────────────────────────
    if ($exitCode -eq 3) {
        # Lock held — distinct non-success so operators know this is a skip, not a success
        exit 3
    }
    if ($sweepFailed) {
        exit 1
    }
    exit 0
}

if ($runMain) {
    Main
}
