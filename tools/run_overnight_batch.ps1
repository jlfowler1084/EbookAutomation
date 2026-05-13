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
}

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
      '--provider', 'cloud',
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
    }
  } catch {
    $vqaFail++
    Write-Log "  VQA EXCEPTION: $($_.Exception.Message)" 'ERROR'
  }
}

# ---------- Summary ----------
Write-Log "=== Overnight batch complete ==="
Write-Log "Books copied to inbox:   $copied"
Write-Log "New KFX produced:        $($newKfx.Count)"
Write-Log "VQA successes:           $vqaSuccess"
Write-Log "VQA failures:            $vqaFail"
Write-Log "Log:                     $LogFile"
Write-Log "VQA reports:             $VqaDir"
