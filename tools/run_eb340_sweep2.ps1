#Requires -Version 7.0
<#
EB-340 VQA stress sweep #2 - Lane A runner (phased).

Lane A is the zero-cloud local-VQA breadth sweep. This runner builds the
reproducibility manifest, runs preflight safety checks, and drives convert/VQA
per book with EXPLICIT flags so the EB-347 override is in force and large books
are NOT silently collapsed:

    --provider local --fallback-enabled false --dpi 150 --max-pages 50

Phases:
  -Phase Preflight : (default) git SHA + dirty-state warning, endpoint reachability,
                     n_ctx >= 32768 check, write run-meta.json. Runs nothing else.
  -Phase Select    : dry-run corpus selection. Enumerate -SourceDir PDFs, classify
                     each (classify_source.py), compute sha256/mb/pages, write
                     manifest.json. Use -SampleSize to limit for a dry run.
  -Phase Convert   : Convert-ToKindle per manifest book (-NoCache, NO converge, NO cloud).
  -Phase VQA       : local VQA on the produced KFX, projecting EB-340 F1 coverage fields.
  -Phase Both      : convert then VQA per book.
  -Phase Canary    : VQA-only smoke on a single existing KFX (-CanaryKfx). No conversion,
                     so no worktree data-dir hazard. Validates the runner + F1 schema.

Results accumulate into run-summary.json (merged by id, rewritten after every book
so partial results survive interruption). Fully local: zero cloud spend on Lane A.

NOTE: the breadth sweep (full manifest Convert/Both) and findings are intentionally
deferred until PR #170 is merged. Pre-merge, only Preflight / Select(dry-run) / Canary
are exercised.
#>
[CmdletBinding()]
param(
  [ValidateSet('Preflight', 'Select', 'Convert', 'VQA', 'Both', 'Canary')]
  [string]$Phase = 'Preflight',
  [int]$Dpi = 150,
  [int]$MaxPages = 50,
  [string]$SourceDir = 'F:\Books',
  [int]$SampleSize = 0,
  [string]$CanaryKfx = '',
  [switch]$AllowDirty
)
$ErrorActionPreference = 'Continue'

# --- Path resolution (runner lives in <repo>\tools\; outputs go to ignored logs\) ---
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RunRoot  = Join-Path $RepoRoot 'logs\eb340-sweep2-2026-06-01'
$KfxDir       = Join-Path $RunRoot 'kfx'
$VqaDir       = Join-Path $RunRoot 'vqa'
$Manifest     = Join-Path $RunRoot 'manifest.json'
$RunLog       = Join-Path $RunRoot 'run.log'
$SummaryJson  = Join-Path $RunRoot 'run-summary.json'
$MetaJson     = Join-Path $RunRoot 'run-meta.json'
$QaScript       = Join-Path $RepoRoot 'tools\visual_qa.py'
$ClassifyScript = Join-Path $RepoRoot 'tools\classify_source.py'
$SettingsJson   = Join-Path $RepoRoot 'config\settings.json'

# --- Local R9700 Qwen3-VL endpoint (zero-cost Lane A provider) ---
$BaseUrl  = 'http://192.168.1.33:8080/v1'
$BaseHost = 'http://192.168.1.33:8080'
$VisionModel  = 'Qwen3VL-30B-A3B-Instruct-Q4_K_M.gguf'
$RequiredNCtx = 32768
$env:LOCAL_LLM_BASE_URL     = $BaseUrl
$env:LOCAL_LLM_VISION_MODEL = $VisionModel

New-Item -ItemType Directory -Force -Path $RunRoot, $KfxDir, $VqaDir | Out-Null

function Write-SweepLog {
  param([string]$Message, [string]$Level = 'INFO')
  "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Level] $Message" |
    Tee-Object -FilePath $RunLog -Append | Out-Host
}

function Get-NCtx {
  try {
    $props = Invoke-RestMethod -Uri "$BaseHost/props" -TimeoutSec 8
    $n = $props.default_generation_settings.n_ctx
    if (-not $n) { $n = $props.n_ctx }
    return [int]$n
  } catch {
    return $null
  }
}

function Test-Endpoint {
  try {
    Invoke-RestMethod -Uri "$BaseUrl/models" -TimeoutSec 8 | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Invoke-Preflight {
  Write-SweepLog "=== PREFLIGHT ==="
  $ok = $true

  $gitSha   = (& git -C $RepoRoot rev-parse HEAD 2>$null)
  $dirty    = (& git -C $RepoRoot status --porcelain 2>$null)
  $isDirty  = [bool]$dirty
  Write-SweepLog "git SHA: $gitSha"
  if ($isDirty) {
    Write-SweepLog "Working tree is DIRTY ($(@($dirty).Count) entries). Reports will not be exactly reproducible from $gitSha." 'WARN'
    if (-not $AllowDirty -and $Phase -in 'Convert', 'Both') {
      Write-SweepLog "Refusing breadth Convert/Both on a dirty tree without -AllowDirty." 'ERROR'
      $ok = $false
    }
  }

  if (Test-Endpoint) {
    Write-SweepLog "Endpoint reachable: $BaseUrl ($VisionModel)"
  } else {
    Write-SweepLog "Endpoint UNREACHABLE: $BaseUrl - is the R9700 node up?" 'ERROR'
    $ok = $false
  }

  $nctx = Get-NCtx
  if ($null -eq $nctx) {
    Write-SweepLog "Could not read n_ctx from $BaseHost/props" 'ERROR'
    $ok = $false
  } elseif ($nctx -lt $RequiredNCtx) {
    Write-SweepLog "n_ctx=$nctx is below required $RequiredNCtx (8k overflows multi-image batches -> silent api_failure). Restart server with --ctx-size $RequiredNCtx." 'ERROR'
    $ok = $false
  } else {
    Write-SweepLog "n_ctx=$nctx (>= $RequiredNCtx OK)"
  }

  # --- Reproducibility snapshot ---
  $cfgBlocks = $null
  if (Test-Path $SettingsJson) {
    try {
      $cfg = Get-Content $SettingsJson -Raw | ConvertFrom-Json
      $cfgBlocks = [ordered]@{
        visual_qa             = $cfg.visual_qa
        classifier_escalation = $cfg.classifier_escalation
        ocr_escalation        = $cfg.ocr_escalation
        converge_loop         = $cfg.converge_loop
      }
    } catch {
      Write-SweepLog "Could not parse $SettingsJson : $($_.Exception.Message)" 'WARN'
    }
  }
  $pyVer = (& py -3.12 --version 2>&1 | Out-String).Trim()

  $meta = [ordered]@{
    timestamp     = (Get-Date -Format 'o')
    git_sha       = $gitSha
    git_dirty     = $isDirty
    repo_root     = $RepoRoot
    python        = $pyVer
    provider      = 'local'
    base_url      = $BaseUrl
    vision_model  = $VisionModel
    n_ctx         = $nctx
    flags = [ordered]@{
      provider          = 'local'
      fallback_enabled  = $false
      dpi               = $Dpi
      max_pages         = $MaxPages
    }
    vqa_command   = "py -3.12 tools\visual_qa.py --input <kfx> --provider local --fallback-enabled false --dpi $Dpi --max-pages $MaxPages --output-dir vqa"
    config        = $cfgBlocks
    preflight_ok  = $ok
  }
  $meta | ConvertTo-Json -Depth 10 | Set-Content $MetaJson -Encoding UTF8
  Write-SweepLog "Wrote reproducibility snapshot -> $MetaJson"

  if ($ok) { Write-SweepLog "PREFLIGHT OK" } else { Write-SweepLog "PREFLIGHT FAILED" 'ERROR' }
  return $ok
}

function Get-TypeAxis {
  param($Verdict)
  $cls = "$($Verdict.classification)"
  if ($cls -like 'scan*') { return 'scan' }
  if ($Verdict.flags.likely_two_column) { return 'two-column' }
  if ($Verdict.flags.needs_ocr) { return 'ocr' }
  return 'digital'
}

function Invoke-Select {
  Write-SweepLog "=== SELECT (dry-run corpus build) source=$SourceDir sample=$SampleSize ==="
  if (-not (Test-Path $SourceDir)) { Write-SweepLog "SourceDir missing: $SourceDir" 'ERROR'; return }

  $pdfs = Get-ChildItem -LiteralPath $SourceDir -Filter *.pdf -File |
    Where-Object { $_.Length -gt 0 } | Sort-Object Name
  if ($SampleSize -gt 0) { $pdfs = $pdfs | Select-Object -First $SampleSize }
  Write-SweepLog "Candidate PDFs (non-empty): $($pdfs.Count)"

  $rows = New-Object System.Collections.Generic.List[object]
  $idx = 0
  foreach ($f in $pdfs) {
    $idx++
    $id = 'p{0:d2}' -f $idx
    $raw = (& py -3.12 $ClassifyScript --input $f.FullName 2>$null | Out-String)
    $start = $raw.IndexOf('{')
    $verdict = if ($start -ge 0) {
      try { $raw.Substring($start) | ConvertFrom-Json } catch { $null }
    } else { $null }

    if ($null -eq $verdict) {
      Write-SweepLog "  $id classify FAILED: $($f.Name)" 'WARN'
      continue
    }
    $sha = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
    $row = [ordered]@{
      id              = $id
      type_axis       = (Get-TypeAxis $verdict)
      classification  = "$($verdict.classification)"
      confidence      = $verdict.confidence
      source_path     = $f.FullName
      sha256          = $sha
      mb              = [math]::Round($f.Length / 1MB, 2)
      pages           = $verdict.signals.total_pages
      needs_ocr       = $verdict.flags.needs_ocr
      needs_paid_tier = $verdict.flags.needs_paid_tier
    }
    $rows.Add([pscustomobject]$row)
    Write-SweepLog "  $id  $($row.type_axis)/$($row.classification)  $($row.mb)MB  $($row.pages)pg  $($f.Name)"
  }
  $rows | ConvertTo-Json -Depth 6 | Set-Content $Manifest -Encoding UTF8
  Write-SweepLog "Wrote manifest ($($rows.Count) books) -> $Manifest"
}

function Get-SummaryRowTemplate {
  param($Book)
  return [ordered]@{
    id = $Book.id; type_axis = $Book.type_axis; classification = $Book.classification
    mb = $Book.mb; source_path = $Book.source_path; sha256 = $Book.sha256; pages = $Book.pages
    kfx_path = $null; convert_ok = $false; convert_sec = $null
    vqa_exit = $null; vqa_sec = $null; vqa_report = $null
    overall_score = $null; evaluation_status = $null
    pages_sampled = $null; pages_requested = $null; pages_total = $null
    requested_dpi = $null; effective_dpi = $null
    coverage_status = $null; coverage_reason = $null
    error = $null
  }
}

function Read-VqaReport {
  param($Row, [string]$ReportPath)
  if (-not (Test-Path -LiteralPath $ReportPath)) { return }
  $Row.vqa_report = $ReportPath
  try {
    $j = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
    $Row.overall_score     = $j.overall_score
    $Row.evaluation_status = $j.evaluation_status
    $Row.pages_sampled     = $j.pages_sampled
    $Row.pages_requested   = $j.pages_requested
    $Row.pages_total       = $j.pages_total
    $Row.requested_dpi     = $j.requested_dpi
    $Row.effective_dpi     = $j.effective_dpi
    $Row.coverage_status   = $j.coverage_status
    $Row.coverage_reason   = $j.coverage_reason
  } catch {
    Write-SweepLog "  report parse failed: $ReportPath" 'WARN'
  }
}

function Invoke-Vqa {
  param($Row, [string]$KfxPath, [string]$Stem)
  Write-SweepLog "----- VQA $($Row.id) -----"
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $vqaArgs = @('-3.12', $QaScript, '--input', $KfxPath, '--provider', 'local',
    '--fallback-enabled', 'false', '--dpi', "$Dpi", '--max-pages', "$MaxPages", '--output-dir', $VqaDir)
  try {
    & py @vqaArgs *>&1 | ForEach-Object { "$(Get-Date -Format 'HH:mm:ss') [VQA][$($Row.id)] $_" | Add-Content -Path $RunLog }
    $Row.vqa_exit = $LASTEXITCODE
  } catch {
    Write-SweepLog "  VQA EXCEPTION: $($_.Exception.Message)" 'ERROR'; $Row.error = "vqa: $($_.Exception.Message)"
  }
  $sw.Stop(); $Row.vqa_sec = [math]::Round($sw.Elapsed.TotalSeconds, 1)
  Read-VqaReport -Row $Row -ReportPath (Join-Path $VqaDir ($Stem + '_visual_qa_report.json'))
  Write-SweepLog "  VQA done $($Row.vqa_sec)s exit=$($Row.vqa_exit) score=$($Row.overall_score) cov=$($Row.coverage_status)/$($Row.coverage_reason) pages=$($Row.pages_sampled)/$($Row.pages_total) reqdpi=$($Row.requested_dpi) effdpi=$($Row.effective_dpi)"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
Write-SweepLog "=== EB-340 sweep #2 runner  phase=$Phase  dpi=$Dpi  max-pages=$MaxPages ==="

if ($Phase -eq 'Preflight') {
  if (Invoke-Preflight) { exit 0 } else { exit 1 }
}

if ($Phase -eq 'Select') {
  if (-not (Invoke-Preflight)) { Write-SweepLog "Preflight failed; Select aborted." 'ERROR'; exit 1 }
  Invoke-Select
  exit 0
}

if ($Phase -eq 'Canary') {
  if (-not (Invoke-Preflight)) { Write-SweepLog "Preflight failed; Canary aborted." 'ERROR'; exit 1 }
  if (-not $CanaryKfx -or -not (Test-Path -LiteralPath $CanaryKfx)) {
    Write-SweepLog "Canary requires -CanaryKfx <existing .kfx path>." 'ERROR'; exit 1
  }
  $stem = [System.IO.Path]::GetFileNameWithoutExtension($CanaryKfx)
  $mb = [math]::Round((Get-Item -LiteralPath $CanaryKfx).Length / 1MB, 2)
  $crow = Get-SummaryRowTemplate ([pscustomobject]@{ id = 'canary'; type_axis = 'canary'; classification = 'n/a'; mb = $mb; source_path = $CanaryKfx; sha256 = $null; pages = $null })
  $crow.kfx_path = $CanaryKfx
  Invoke-Vqa -Row $crow -KfxPath $CanaryKfx -Stem $stem
  ([pscustomobject]$crow) | ConvertTo-Json -Depth 6 | Set-Content $SummaryJson -Encoding UTF8
  Write-SweepLog "Canary summary -> $SummaryJson"
  exit 0
}

# --- Convert / VQA / Both : breadth sweep (deferred until PR #170 merged) ---
if (-not (Invoke-Preflight)) { Write-SweepLog "Preflight failed; sweep aborted." 'ERROR'; exit 1 }
if (-not (Test-Path $Manifest)) { Write-SweepLog "No manifest.json - run -Phase Select first." 'ERROR'; exit 1 }

$books = Get-Content $Manifest -Raw | ConvertFrom-Json
$byId = [ordered]@{}
foreach ($b in $books) { $byId[$b.id] = Get-SummaryRowTemplate $b }
if (Test-Path $SummaryJson) {
  try {
    (Get-Content $SummaryJson -Raw | ConvertFrom-Json) | ForEach-Object {
      if ($byId.Contains($_.id)) { foreach ($p in $_.PSObject.Properties) { if ($null -ne $p.Value) { $byId[$_.id][$p.Name] = $p.Value } } }
    }
  } catch { Write-SweepLog "Prior summary unreadable, starting fresh: $($_.Exception.Message)" 'WARN' }
}
function Save-Summary { ($books | ForEach-Object { [pscustomobject]$byId[$_.id] }) | ConvertTo-Json -Depth 6 | Set-Content $SummaryJson -Encoding UTF8 }

if ($Phase -in 'Convert', 'Both') { Import-Module (Join-Path $RepoRoot 'module\EbookAutomation.psm1') -Force }

$i = 0
foreach ($b in $books) {
  $i++; $r = $byId[$b.id]
  $tag = "[$i/$($books.Count)] $($b.id)"
  $stem = [System.IO.Path]::GetFileNameWithoutExtension($b.source_path)
  $expectKfx = Join-Path $KfxDir ($stem + '.kfx')

  if ($Phase -in 'Convert', 'Both') {
    Write-SweepLog "----- CONVERT $tag ($($b.mb) MB, $($b.classification)) : $($b.type_axis) -----"
    if (-not (Test-Path -LiteralPath $b.source_path)) { Write-SweepLog "  MISSING SOURCE" 'ERROR'; $r.error = 'missing_source'; Save-Summary; continue }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
      Convert-ToKindle -InputFile $b.source_path -OutputDir $KfxDir -NoCache *>&1 |
        ForEach-Object { "$(Get-Date -Format 'HH:mm:ss') [CONV][$($b.id)] $_" | Add-Content -Path $RunLog }
    } catch { Write-SweepLog "  CONVERT EXCEPTION: $($_.Exception.Message)" 'ERROR'; $r.error = "convert: $($_.Exception.Message)" }
    $sw.Stop(); $r.convert_sec = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    if (Test-Path -LiteralPath $expectKfx) {
      $r.convert_ok = $true; $r.kfx_path = $expectKfx
      Write-SweepLog "  CONVERT OK $($r.convert_sec)s -> $([math]::Round((Get-Item -LiteralPath $expectKfx).Length/1MB,2)) MB"
    } else {
      Write-SweepLog "  CONVERT FAILED (no KFX) $($r.convert_sec)s" 'ERROR'
      if (-not $r.error) { $r.error = 'no_kfx_produced' }; Save-Summary; continue
    }
    Save-Summary
  } else {
    if (Test-Path -LiteralPath $expectKfx) { $r.convert_ok = $true; $r.kfx_path = $expectKfx }
  }

  if ($Phase -in 'VQA', 'Both') {
    if (-not $r.kfx_path -or -not (Test-Path -LiteralPath $r.kfx_path)) { Write-SweepLog "  VQA SKIP $tag (no KFX)" 'WARN'; continue }
    Invoke-Vqa -Row $r -KfxPath $r.kfx_path -Stem $stem
    Save-Summary
  }
}
Write-SweepLog "=== SWEEP PHASE '$Phase' COMPLETE ==="
Save-Summary
