#requires -RunAsAdministrator
<#
.SYNOPSIS
    Create SAPI 5 voice aliases that surface as the names the EbookAutomation
    pipeline expects (`Microsoft Steffan/Guy/Aria/Jenny Online`) but route to
    real bridged OneCore voices under the hood.

.DESCRIPTION
    The pipeline's settings.json + tools/test_voice_tags.py allowlist + the
    SecondBrain SB-8 contract all reference voice names that don't ship with
    Windows -- they were aspirational. SAPI XML's `<voice required="Name=X">`
    constraint throws SPERR_NOT_FOUND when the voice doesn't exist, so the
    autobook MP3 path was failing anywhere it ran.

    This script creates four registry alias tokens that mirror existing
    OneCore voice tokens but advertise the pipeline-expected friendly names.
    SAPI enumerates them as the requested names; the engine instantiates
    them with the underlying voice's actual data files.

    Mappings (alias -> underlying voice):
        Microsoft Steffan Online -> Microsoft George    (en-GB male)
        Microsoft Guy Online     -> Microsoft Mark      (en-US male)
        Microsoft Aria Online    -> Microsoft Susan     (en-GB female)
        Microsoft Jenny Online   -> Microsoft Catherine (en-AU female)

    Idempotent: re-running rebuilds the aliases from current source tokens.
    Reversible: invoke with -Remove to drop the four alias keys without
    touching the bridged voices.

.PARAMETER Remove
    Delete the four alias tokens. Underlying bridged voices are untouched.

.NOTES
    Run in an elevated PowerShell (pwsh) session.
    Prerequisite: bridge-onecore-voices.ps1 must have run first so the
    `MSTTS_V110_*` source tokens exist under the SAPI 5 tree.
#>
[CmdletBinding()]
param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Alias mappings ---------------------------------------------------------
# AliasKey is the registry-safe token ID; Alias is the friendly name balcon
# / SAPI XML will look up. Source is the bridged OneCore token to clone from.
$mappings = @(
    [PSCustomObject]@{ Alias = 'Microsoft Steffan Online'; Source = 'MSTTS_V110_enGB_GeorgeM';    AliasKey = 'EBA_ALIAS_STEFFAN_ONLINE' }
    [PSCustomObject]@{ Alias = 'Microsoft Guy Online';     Source = 'MSTTS_V110_enUS_MarkM';      AliasKey = 'EBA_ALIAS_GUY_ONLINE' }
    [PSCustomObject]@{ Alias = 'Microsoft Aria Online';    Source = 'MSTTS_V110_enGB_SusanM';     AliasKey = 'EBA_ALIAS_ARIA_ONLINE' }
    [PSCustomObject]@{ Alias = 'Microsoft Jenny Online';   Source = 'MSTTS_V110_enAU_CatherineM'; AliasKey = 'EBA_ALIAS_JENNY_ONLINE' }
)

$roots = @(
    'HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Speech\Voices\Tokens'
)

# --- Remove mode ------------------------------------------------------------
if ($Remove) {
    Write-Host "=== Removing pipeline voice aliases ===" -ForegroundColor Cyan
    $removed = 0
    foreach ($root in $roots) {
        foreach ($m in $mappings) {
            $aliasPath = Join-Path $root $m.AliasKey
            if (Test-Path $aliasPath) {
                Remove-Item $aliasPath -Recurse -Force
                Write-Host "  - $aliasPath"
                $removed++
            }
        }
    }
    Write-Host ""
    Write-Host "Removed $removed alias key(s). Underlying bridged voices untouched." -ForegroundColor Green
    return
}

# --- Create mode ------------------------------------------------------------
Write-Host "=== Creating SAPI 5 pipeline voice aliases ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: backup
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupPath = Join-Path $scriptDir "sapi5-tokens-pre-aliases-$timestamp.reg"
Write-Host "[1/3] Backing up current SAPI 5 tokens..." -ForegroundColor Yellow
& reg.exe export 'HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens' $backupPath /y | Out-Null
if ($LASTEXITCODE -ne 0) { throw "reg export failed ($LASTEXITCODE)" }
Write-Host "      $backupPath  ($([int]((Get-Item $backupPath).Length/1KB)) KB)" -ForegroundColor Green
Write-Host ""

# Step 2: create aliases in both registry views
Write-Host "[2/3] Creating aliases in 64-bit + WOW6432Node trees..." -ForegroundColor Yellow
foreach ($root in $roots) {
    $label = if ($root -match 'WOW6432Node') { '32-bit (WOW6432Node)' } else { '64-bit' }
    Write-Host "  Tree: $label" -ForegroundColor DarkCyan
    foreach ($m in $mappings) {
        $sourcePath = Join-Path $root $m.Source
        $aliasPath  = Join-Path $root $m.AliasKey

        if (-not (Test-Path $sourcePath)) {
            Write-Warning "    Source token $($m.Source) not found in $root -- skipping $($m.Alias)"
            Write-Warning "    (Did bridge-onecore-voices.ps1 run successfully?)"
            continue
        }

        # Idempotent: drop existing alias before recreating
        if (Test-Path $aliasPath) {
            Remove-Item $aliasPath -Recurse -Force
        }

        # Recursive copy preserves all values + the Attributes subkey
        Copy-Item -Path $sourcePath -Destination $aliasPath -Recurse -Force

        # Override the friendly name in the two places SAPI looks
        Set-ItemProperty -Path $aliasPath -Name '(default)' -Value $m.Alias
        $attrPath = Join-Path $aliasPath 'Attributes'
        if (Test-Path $attrPath) {
            Set-ItemProperty -Path $attrPath -Name 'Name' -Value $m.Alias
        }

        Write-Host ("    + {0,-30} -> {1}" -f $m.Alias, $m.Source) -ForegroundColor Green
    }
}
Write-Host ""

# Step 3: verify
Write-Host "[3/3] COM SAPI voice list (what balcon will see):" -ForegroundColor Yellow
$voices = (New-Object -ComObject SAPI.SpVoice).GetVoices()
$visible = @()
$voices | ForEach-Object {
    $name = $_.GetAttribute('Name')
    $visible += $name
    $marker = if ($name -match '^Microsoft (Steffan|Guy|Aria|Jenny) Online$') { '  *' } else { '   ' }
    Write-Host ("  {0} {1}" -f $marker, $name)
}
Write-Host ""

$aliasNames = $mappings | ForEach-Object { $_.Alias }
$missing = @($aliasNames | Where-Object { $_ -notin $visible })
if ($missing.Count -eq 0) {
    Write-Host "All 4 pipeline aliases visible to SAPI 5. balcon contract satisfied." -ForegroundColor Green
} else {
    Write-Warning "Missing aliases: $($missing -join ', ')"
}

Write-Host ""
Write-Host "Rollback options:" -ForegroundColor DarkGray
Write-Host "  Drop aliases only:  & '$($MyInvocation.MyCommand.Path)' -Remove" -ForegroundColor DarkGray
Write-Host "  Full registry undo: reg import `"$backupPath`"" -ForegroundColor DarkGray
