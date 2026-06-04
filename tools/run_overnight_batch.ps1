#Requires -Version 7.0
<#
.SYNOPSIS
Overnight batch: copy selected PDFs into inbox, run Invoke-EbookPipeline,
then run partial VQA (8 pages) against every resulting KFX.

.DESCRIPTION
One-shot wrapper for unattended overnight runs. Reads a selection manifest
(JSON array of {Category, Name, MB} objects), copies the matching PDFs from
the source library into inbox/, invokes the pipeline, then runs VQA on
every new KFX in output/kindle/. All output goes to a single timestamped
log plus per-book VQA JSON reports.

.PARAMETER Manifest
Path to the JSON selection manifest.

.PARAMETER SourceDir
Directory containing the source PDFs (default: F:\books).

.PARAMETER MaxPages
Pages to sample per book for VQA (default: 8).

.EXAMPLE
pwsh -File tools\run_overnight_batch.ps1 `
  -Manifest logs\overnight-batch-selection-2026-04-23.json
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Manifest,
  [string]$SourceDir = 'F:\books',
  [int]$MaxPages = 8
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = 'F:\Projects\EbookAutomation'
$InboxDir    = Join-Path $ProjectRoot 'inbox'
$OutputDir   = Join-Path $ProjectRoot 'output\kindle'
$LogDir      = Join-Path $ProjectRoot 'logs'

$timestamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
$datestamp = Get-Date -Format 'yyyy-MM-dd'
$LogFile   = Join-Path $LogDir "overnight-batch-$timestamp.log"
$VqaDir    = Join-Path $LogDir "vqa-overnight-$datestamp"

New-Item -ItemType Directory -Force -Path $LogDir, $VqaDir | Out-Null

# Load .env into process environment. Required because Start-Process inherits
# from the parent shell, which does not auto-source project .env files.
$envFile = Join-Path $ProjectRoot '.env'
$envLoaded = @()
if (Test-Path $envFile) {
  foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
      $name  = $Matches[1]
      $value = $Matches[2] -replace '^"(.*)"$', '$1' -replace "^'(.*)'$", '$1'
      [Environment]::SetEnvironmentVariable($name, $value, 'Process')
      $envLoaded += $name
    }
  }
}

function Write-Log {
  param([string]$Message, [string]$Level = 'INFO')
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Level] $Message"
  $line | Tee-Object -FilePath $LogFile -Append | Out-Host
}

Write-Log "=== Overnight batch started ==="
Write-Log ".env loaded: $($envLoaded -join ', ')"
$keyStatus = @()
foreach ($k in 'ANTHROPIC_API_KEY','OPENROUTER_API_KEY') {
  $present = [bool][Environment]::GetEnvironmentVariable($k, 'Process')
  $keyStatus += "$k=$(if ($present) { 'SET' } else { 'MISSING' })"
}
Write-Log "API keys: $($keyStatus -join ' | ')"
Write-Log "Manifest:   $Manifest"
Write-Log "SourceDir:  $SourceDir"
Write-Log "Inbox:      $InboxDir"
Write-Log "Output:     $OutputDir"
Write-Log "VQA output: $VqaDir"
Write-Log "Max pages:  $MaxPages"

# ---------- Phase 0: sync pattern DB to VM ----------
Write-Log "Phase 0: syncing ebook_patterns.db to VM"
$syncScript = Join-Path $PSScriptRoot 'sync_pattern_db.ps1'
if (Test-Path $syncScript) {
  & pwsh -NonInteractive -File $syncScript 2>&1 | ForEach-Object {
    "$(Get-Date -Format 'HH:mm:ss') [SYNC] $_" | Tee-Object -FilePath $LogFile -Append | Out-Host
  }
  if ($LASTEXITCODE -eq 0) {
    Write-Log "Phase 0 complete: DB synced OK"
  } elseif ($LASTEXITCODE -eq 2) {
    Write-Log "Phase 0 WARNING: sync completed but row-count mismatch detected - proceeding with caution" 'WARN'
  } else {
    Write-Log "Phase 0 WARNING: sync failed (exit=$LASTEXITCODE) - batch will use VM's existing DB" 'WARN'
  }
} else {
  Write-Log "Phase 0 SKIP: sync_pattern_db.ps1 not found at $syncScript" 'WARN'
}

# ---------- Phase 1: seed inbox ----------
Write-Log "Phase 1: seeding inbox from manifest"
$selection = Get-Content $Manifest -Raw | ConvertFrom-Json
Write-Log "Manifest entries: $($selection.Count)"

$copied = 0
foreach ($entry in $selection) {
  $src = Join-Path $SourceDir $entry.Name
  $dst = Join-Path $InboxDir $entry.Name
  if (-not (Test-Path $src)) {
    Write-Log "MISSING SOURCE: $($entry.Name)" 'ERROR'
    continue
  }
  if (Test-Path $dst) {
    Write-Log "Already in inbox: $($entry.Name)" 'SKIP'
    continue
  }
  Copy-Item -LiteralPath $src -Destination $dst
  $copied++
  Write-Log "Copied [$($entry.Category)] $($entry.Name)"
}
Write-Log "Phase 1 complete: $copied file(s) copied"

# Snapshot existing KFX before pipeline so we only VQA new output
$preExisting = @{}
if (Test-Path $OutputDir) {
  Get-ChildItem $OutputDir -Filter *.kfx -File | ForEach-Object { $preExisting[$_.Name] = $true }
}
Write-Log "Pre-existing KFX in output: $($preExisting.Count)"

# Status accumulator — precedence 3 > 2 > 1 > 0 (mirrors compare_vqa_reports.py audit codes)
$batchStatus = 0
function Set-Status { param([int]$Code) if ($Code -gt $script:batchStatus) { $script:batchStatus = $Code } }
# HB gate counters (safe defaults if Phase 2.5 is skipped)
$hbInBatch = 0; $hbScanned = 0; $hbMissing = @(); $hbFlagged = @()

# ---------- Phase 2: run pipeline ----------
Write-Log "Phase 2: running Invoke-EbookPipeline"
$pipelineStart = Get-Date
try {
  Import-Module (Join-Path $ProjectRoot 'module\EbookAutomation.psm1') -Force
  Invoke-EbookPipeline -UseClaudeChapters *>&1 | ForEach-Object {
    "$(Get-Date -Format 'HH:mm:ss') $_" | Tee-Object -FilePath $LogFile -Append | Out-Host
  }
  $pipelineElapsed = (Get-Date) - $pipelineStart
  Write-Log "Phase 2 complete in $([int]$pipelineElapsed.TotalMinutes) min"
} catch {
  Write-Log "Pipeline FAILED: $($_.Exception.Message)" 'ERROR'
  Write-Log $_.ScriptStackTrace 'ERROR'
  Set-Status 3
}

# ---------- Phase 2.5: header-bleed gate ----------
Write-Log "Phase 2.5: scanning new KFX intermediates for header-bleed welds"
$intermediatesDir = Join-Path $OutputDir '.intermediates'
$hbReportDir      = Join-Path $ProjectRoot 'data\batch_reports\header_bleed'
New-Item -ItemType Directory -Force -Path $hbReportDir | Out-Null

# Resolve this run's new KFX (same snapshot-diff as Phase 3)
$hbNewKfx = @()
if (Test-Path $OutputDir) {
  $hbNewKfx = Get-ChildItem $OutputDir -Filter *.kfx -File |
              Where-Object { -not $preExisting.ContainsKey($_.Name) }
}

$hbInBatch    = $hbNewKfx.Count
$hbScanned    = 0
$hbMissing    = @()
$hbFlagged    = @()

if ($hbInBatch -eq 0) {
  Write-Log "[HB] No new KFX this run — Phase 2.5 skipped"
} else {
  Write-Log "[HB] Books in batch: $hbInBatch"
  foreach ($kfx in $hbNewKfx) {
    $htmlName = "$($kfx.BaseName)_kindle.html"
    $htmlPath = Join-Path $intermediatesDir $htmlName
    if (-not (Test-Path -LiteralPath $htmlPath)) {
      Write-Log "[HB] WARN: missing intermediate for $($kfx.Name) — coverage gap" 'WARN'
      $hbMissing += $kfx.Name
      continue
    }
    $hbScanned++
    $hbReport = Join-Path $hbReportDir "batch-${timestamp}-$($kfx.BaseName).json"
    $hbArgs   = @(
      '-3.12',
      (Join-Path $ProjectRoot 'tools\check_header_bleed.py'),
      '--input', $htmlPath,
      '--out',   $hbReport,
      '--quiet'
    )
    & py @hbArgs *>&1 | ForEach-Object {
      "$(Get-Date -Format 'HH:mm:ss') [HB] $_" |
        Tee-Object -FilePath $LogFile -Append | Out-Host
    }
    $hbExit = $LASTEXITCODE
    Set-Status $hbExit
    if ($hbExit -eq 2) {
      $hbFlagged += $kfx.Name
      Write-Log "[HB] FLAGGED: $($kfx.Name) — see $(Split-Path $hbReport -Leaf)" 'WARN'
    } elseif ($hbExit -eq 3) {
      Write-Log "[HB] ERROR scanning $($kfx.Name)" 'ERROR'
    }
  }
  Write-Log "[HB] Coverage: $hbInBatch in batch | $hbScanned scanned | $($hbMissing.Count) missing"
  if ($hbMissing.Count -gt 0) {
    Write-Log "[HB] Missing intermediates: $($hbMissing -join ', ')" 'WARN'
  }
  if ($hbFlagged.Count -gt 0) {
    Write-Log "[HB] Flagged books: $($hbFlagged -join ', ')" 'WARN'
  }
}
Write-Log "Phase 2.5 complete (batchStatus so far: $batchStatus)"

# ---------- Phase 3: partial VQA on new KFX ----------
Write-Log "Phase 3: running partial VQA (max-pages=$MaxPages)"
$newKfx = @()
if (Test-Path $OutputDir) {
  $newKfx = Get-ChildItem $OutputDir -Filter *.kfx -File |
            Where-Object { -not $preExisting.ContainsKey($_.Name) }
}
Write-Log "New KFX to evaluate: $($newKfx.Count)"

$vqaSuccess = 0
$vqaFail = 0
foreach ($kfx in $newKfx) {
  Write-Log "VQA: $($kfx.Name)"
  $vqaStart = Get-Date
  try {
    $vqaArgs = @(
      '-3.12',
      (Join-Path $ProjectRoot 'tools\visual_qa.py'),
      '--input', $kfx.FullName,
      '--max-pages', $MaxPages,
      '--dpi', '100',
      # EB-339: provider intentionally NOT pinned here — inherit the
      # config/settings.json visual_qa.provider default (now "local", the
      # free R9700 Qwen3-VL endpoint). settings.json is the single toggle
      # point; pass --provider cloud to fall back to paid OpenRouter.
      '--output-dir', $VqaDir
    )
    & py @vqaArgs *>&1 | ForEach-Object {
      "$(Get-Date -Format 'HH:mm:ss') [VQA] $_" |
        Tee-Object -FilePath $LogFile -Append | Out-Host
    }
    if ($LASTEXITCODE -eq 0) {
      $vqaSuccess++
      $elapsed = [int]((Get-Date) - $vqaStart).TotalSeconds
      Write-Log "  OK ($elapsed s)"
    } else {
      $vqaFail++
      Write-Log "  VQA exit=$LASTEXITCODE for $($kfx.Name)" 'ERROR'
      Set-Status 3
    }
  } catch {
    $vqaFail++
    Write-Log "  VQA EXCEPTION: $($_.Exception.Message)" 'ERROR'
    Set-Status 3
  }
}

# ---------- Summary ----------
Write-Log "=== Overnight batch complete ==="
Write-Log "Books copied to inbox:   $copied"
Write-Log "New KFX produced:        $($newKfx.Count)"
Write-Log "HB in batch:             $hbInBatch"
Write-Log "HB scanned:              $hbScanned"
Write-Log "HB flagged:              $($hbFlagged.Count)"
Write-Log "HB missing artifacts:    $($hbMissing.Count)"
Write-Log "VQA successes:           $vqaSuccess"
Write-Log "VQA failures:            $vqaFail"
Write-Log "Log:                     $LogFile"
Write-Log "VQA reports:             $VqaDir"
Write-Log "Batch exit status:       $batchStatus"
exit $batchStatus
