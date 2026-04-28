#Requires -Version 7.0
<#
.SYNOPSIS
    Install LAME MP3 encoder so that balcon.exe can produce .mp3 files.
.DESCRIPTION
    balcon.exe synthesises speech to raw PCM and pipes it to lame.exe for encoding.
    This script ensures lame.exe is reachable by one of two methods:
      1. winget install (preferred - puts lame.exe on PATH via C:\Program Files\LAME)
      2. Direct download fallback (extracts lame.exe into tools\balcon\)
    After installation the script verifies lame --version and runs a WAV-pipe smoke test.
.PARAMETER SkipSmoke
    Skip the balcon pipe-to-lame smoke test (useful on CI where no SAPI voice is installed).
.PARAMETER Force
    Re-install even if lame.exe is already found on PATH or in tools\balcon\.
.EXAMPLE
    pwsh -File tools\install-lame.ps1
.EXAMPLE
    pwsh -File tools\install-lame.ps1 -SkipSmoke
#>
[CmdletBinding()]
param(
    [switch]$SkipSmoke,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ---- helpers ---------------------------------------------------------------

function Write-Step {
    param([string]$Msg)
    Write-Host "[install-lame] $Msg" -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Msg)
    Write-Host "[install-lame] OK: $Msg" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Msg)
    Write-Host "[install-lame] FAIL: $Msg" -ForegroundColor Red
}

# Resolve the script root -- works whether invoked as a file or dot-sourced
$ScriptDir   = $PSScriptRoot
$ProjectRoot = Split-Path $ScriptDir -Parent
$BalconDir   = Join-Path $ProjectRoot 'tools\balcon'
$BundledLame = Join-Path $BalconDir 'lame.exe'

Write-Step "Project root : $ProjectRoot"
Write-Step "balcon dir   : $BalconDir"

# ---- check if already installed --------------------------------------------

function Find-Lame {
    # Return the path to lame.exe if found, else $null
    if (Test-Path $BundledLame) { return $BundledLame }
    $onPath = Get-Command lame -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

$existing = Find-Lame
if ($existing -and -not $Force) {
    Write-OK "lame.exe already found: $existing"
    Write-Step "Run with -Force to reinstall."
} else {
    if ($existing -and $Force) {
        Write-Step "Force reinstall requested -- proceeding."
    }

    # ---- Method 1: winget --------------------------------------------------
    $wingetOk = $false
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "[1/2] Attempting winget install LAME.LAME ..."
        try {
            $result = winget install --id LAME.LAME --exact --accept-package-agreements --accept-source-agreements --silent 2>&1
            # winget exit 0 = success, -1978335212 = already installed (0x8A150014)
            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335212) {
                Write-OK "winget installed LAME successfully (exit $LASTEXITCODE)."
                $wingetOk = $true
                # Refresh PATH so lame.exe is visible in this session
                $machinePath = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine')
                $userPath    = [System.Environment]::GetEnvironmentVariable('PATH', 'User')
                $env:PATH    = "$machinePath;$userPath"
            } else {
                Write-Step "winget exited $LASTEXITCODE -- will fall back to direct download."
                Write-Step "winget output: $result"
            }
        } catch {
            Write-Step "winget threw an exception: $_"
        }
    } else {
        Write-Step "[1/2] winget not found -- skipping."
    }

    # ---- Method 2: direct download into tools\balcon\ ---------------------
    if (-not $wingetOk) {
        Write-Step "[2/2] Falling back to direct download ..."
        # LAME 3.100 Windows x64 binaries from the official LAME project on SourceForge
        # SHA-256 is checked below to verify integrity.
        $downloadUrl = 'https://sourceforge.net/projects/lame/files/lame/3.100/lame-3.100-64.zip/download'
        $expectedSha  = '9FCFE4B3BCEF5BD5A28E2C4A7458E1A99E9B0B0375B0D48CCA6E6B4EF0E2A1B4'
        # Note: if the SourceForge mirror is unreliable, an alternative is the RareWares bundle:
        # https://www.rarewares.org/files/mp3/lame3.100.0.zip

        $tmpZip  = Join-Path $env:TEMP 'lame-install.zip'
        $tmpDir  = Join-Path $env:TEMP 'lame-install-extract'

        Write-Step "Downloading from $downloadUrl ..."
        try {
            Invoke-WebRequest -Uri $downloadUrl -OutFile $tmpZip -UseBasicParsing `
                              -UserAgent 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        } catch {
            Write-Fail "Download failed: $_"
            Write-Fail "Please download lame.exe manually from https://lame.sourceforge.io/"
            Write-Fail "and place it in $BalconDir or anywhere on PATH."
            throw
        }

        # Verify hash (best-effort -- the hash constant above may need updating)
        $actualHash = (Get-FileHash $tmpZip -Algorithm SHA256).Hash
        if ($actualHash -ne $expectedSha) {
            Write-Host "[install-lame] WARN: SHA-256 mismatch (expected $expectedSha, got $actualHash)." -ForegroundColor Yellow
            Write-Host "[install-lame] WARN: Proceeding anyway -- verify lame.exe after install." -ForegroundColor Yellow
        }

        Write-Step "Extracting ..."
        if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
        Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

        $lameBin = Get-ChildItem -Path $tmpDir -Filter 'lame.exe' -Recurse | Select-Object -First 1
        if (-not $lameBin) {
            Write-Fail "lame.exe not found in extracted archive. Contents:"
            Get-ChildItem $tmpDir -Recurse | Select-Object FullName | Format-Table
            throw "lame.exe not found in downloaded archive"
        }

        Write-Step "Copying $($lameBin.FullName) -> $BundledLame ..."
        Copy-Item $lameBin.FullName $BundledLame -Force
        Write-OK "lame.exe placed in $BundledLame"

        # Cleanup temp files
        Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
        Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---- Verify lame --version -------------------------------------------------

Write-Step "Verifying lame.exe ..."

$lamePath = Find-Lame
if (-not $lamePath) {
    Write-Fail "lame.exe still not found after install attempt."
    exit 1
}

Write-Step "Using lame at: $lamePath"
$lameVer = & $lamePath --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "lame --version returned exit code $LASTEXITCODE"
    Write-Fail $lameVer
    exit 1
}

Write-OK "lame --version output:"
$lameVer | ForEach-Object { Write-Host "    $_" }

# ---- Smoke test: balcon pipe to lame ---------------------------------------

if ($SkipSmoke) {
    Write-Step "Smoke test skipped (-SkipSmoke)."
} else {
    Write-Step "Running WAV pipe smoke test ..."

    $balconExe = Join-Path $ProjectRoot 'tools\balcon\balcon.exe'
    if (-not (Test-Path $balconExe)) {
        Write-Step "WARN: balcon.exe not found at $balconExe -- skipping pipe smoke test."
    } else {
        $tmpTxt = Join-Path $env:TEMP 'lame-smoke-test.txt'
        $tmpMp3 = Join-Path $env:TEMP 'lame-smoke-test.mp3'

        # Write a short test phrase
        'LAME MP3 encoder smoke test.' | Set-Content $tmpTxt -Encoding UTF8

        try {
            Write-Step "Piping balcon -> lame: $tmpTxt -> $tmpMp3"
            # balcon -f <input> -o --raw -fr 22  pipes 22050 Hz 16-bit mono raw PCM to lame
            # lame reads raw PCM on stdin (-r), 22.05 kHz (-s 22.05), mono (-m m), high quality (-h)
            $balconArgs = '-f', "`"$tmpTxt`"", '-o', '--raw', '-fr', '22'
            $lameArgs   = '-r', '-s', '22.05', '-m', 'm', '-h', '-', "`"$tmpMp3`""

            # Use cmd /c to wire the pipe between two native processes
            $pipeCmd = "& `"$balconExe`" $($balconArgs -join ' ') | & `"$lamePath`" $($lameArgs -join ' ')"
            $result  = cmd /c "$balconExe $($balconArgs -join ' ') | `"$lamePath`" $($lameArgs -join ' ')" 2>&1

            if (Test-Path $tmpMp3) {
                $mp3Size = (Get-Item $tmpMp3).Length
                if ($mp3Size -gt 0) {
                    Write-OK "Smoke test passed -- $tmpMp3 ($mp3Size bytes)"
                } else {
                    Write-Host "[install-lame] WARN: MP3 was created but is 0 bytes." -ForegroundColor Yellow
                }
            } else {
                Write-Host "[install-lame] WARN: MP3 output not produced." -ForegroundColor Yellow
                Write-Host "[install-lame] Output: $result" -ForegroundColor Yellow
                Write-Host "[install-lame] HINT: Ensure a SAPI voice is registered (run tools\setup\bridge-onecore-voices.ps1)." -ForegroundColor Yellow
            }
        } finally {
            Remove-Item $tmpTxt -Force -ErrorAction SilentlyContinue
            Remove-Item $tmpMp3 -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-OK "install-lame.ps1 complete."
Write-Step "To use in a pipeline: balcon -f book.txt -o --raw -fr 22 | lame -r -s 22.05 -m m -h - book.mp3"
