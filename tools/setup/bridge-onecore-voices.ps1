#requires -RunAsAdministrator
<#
.SYNOPSIS
    Bridge Windows OneCore TTS voice tokens into the SAPI 5 registry tree
    so legacy SAPI 5 applications (e.g. balcon.exe) can enumerate them.

.DESCRIPTION
    Modern Windows ships TTS voices under HKLM\SOFTWARE\Microsoft\Speech_OneCore,
    but balcon and other SAPI 5 consumers only enumerate
    HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens. This script mirrors the
    OneCore token subkeys into the SAPI 5 tree (and the WOW6432Node mirror
    for 32-bit consumers like balcon). The actual voice data files
    (.APM/.BR2/.NNM in C:\Windows\Speech_OneCore\Engines\TTS\) are shared,
    so no file copying is needed -- only the registry tokens that point at
    them.

    Idempotent: existing destination tokens are left untouched.
    A pre-change backup of the SAPI 5 Tokens key is written next to this
    script so you can roll back with `reg import` if anything misbehaves.

.NOTES
    Run in an elevated PowerShell (pwsh) session. Requires Administrator.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupPath = Join-Path $scriptDir "sapi5-tokens-backup-$timestamp.reg"

Write-Host "=== OneCore -> SAPI 5 voice token bridge ===" -ForegroundColor Cyan
Write-Host ""

# ---- Step 1: backup current SAPI 5 token tree ------------------------------
Write-Host "[1/4] Backing up current SAPI 5 tokens to:" -ForegroundColor Yellow
Write-Host "      $backupPath"
& reg.exe export 'HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens' $backupPath /y | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "reg export failed with exit code $LASTEXITCODE"
}
Write-Host "      OK ($([int]((Get-Item $backupPath).Length / 1KB)) KB)" -ForegroundColor Green
Write-Host ""

# ---- Step 2: bridge 64-bit OneCore -> 64-bit SAPI 5 -----------------------
Write-Host "[2/4] Mirroring 64-bit OneCore tokens into SAPI 5..." -ForegroundColor Yellow
$src64 = 'HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens'
$dst64 = 'HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens'

$copied64 = 0
$skipped64 = 0
Get-ChildItem $src64 | ForEach-Object {
    $name = $_.PSChildName
    $dest = Join-Path $dst64 $name
    if (Test-Path $dest) {
        $skipped64++
    } else {
        Copy-Item -Path $_.PSPath -Destination $dst64 -Recurse -Force
        Write-Host "      + $name"
        $copied64++
    }
}
Write-Host "      Copied: $copied64  Skipped (already present): $skipped64" -ForegroundColor Green
Write-Host ""

# ---- Step 3: bridge for 32-bit applications (WOW6432Node) -----------------
Write-Host "[3/4] Mirroring tokens into WOW6432Node SAPI 5 (for 32-bit balcon)..." -ForegroundColor Yellow
$dst32 = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Speech\Voices\Tokens'

# Source preference: WOW6432Node OneCore if it exists, else 64-bit OneCore
$src32 = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Speech_OneCore\Voices\Tokens'
if (-not (Test-Path $src32)) {
    Write-Host "      (WOW6432Node OneCore tree absent -- using 64-bit OneCore as source)" -ForegroundColor DarkYellow
    $src32 = $src64
}

if (-not (Test-Path $dst32)) {
    New-Item -Path $dst32 -Force | Out-Null
}

$copied32 = 0
$skipped32 = 0
Get-ChildItem $src32 | ForEach-Object {
    $name = $_.PSChildName
    $dest = Join-Path $dst32 $name
    if (Test-Path $dest) {
        $skipped32++
    } else {
        Copy-Item -Path $_.PSPath -Destination $dst32 -Recurse -Force
        Write-Host "      + $name"
        $copied32++
    }
}
Write-Host "      Copied: $copied32  Skipped (already present): $skipped32" -ForegroundColor Green
Write-Host ""

# ---- Step 4: verify by enumerating COM SAPI ------------------------------
Write-Host "[4/4] COM SAPI voice list (what balcon will see):" -ForegroundColor Yellow
$voices = (New-Object -ComObject SAPI.SpVoice).GetVoices()
$voices | ForEach-Object {
    "      {0}" -f $_.GetAttribute('Name')
}
Write-Host ""
Write-Host ("Total SAPI 5 voices visible: {0}" -f $voices.Count) -ForegroundColor Cyan
Write-Host ""
Write-Host "Bridge complete. Re-run this script anytime new OneCore voices are installed." -ForegroundColor Green
Write-Host "Rollback (if needed): reg import `"$backupPath`"" -ForegroundColor DarkGray
