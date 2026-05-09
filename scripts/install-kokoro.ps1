#Requires -Version 7
<#
.SYNOPSIS
    Install Kokoro TTS dependencies and download model files.

.DESCRIPTION
    1. Installs kokoro-onnx, soundfile, and onnxruntime-gpu (or onnxruntime for CPU-only).
    2. Downloads kokoro-v0.19.onnx and voices.bin to tools\kokoro-models\.
    3. Runs a 3-second smoke test to confirm synthesis works.

.PARAMETER CpuOnly
    Install onnxruntime (CPU) instead of onnxruntime-gpu.
    Use this on machines without an NVIDIA GPU.

.EXAMPLE
    # Desktop (GPU):
    pwsh -File scripts\install-kokoro.ps1

    # Laptop (CPU only):
    pwsh -File scripts\install-kokoro.ps1 -CpuOnly
#>
[CmdletBinding()]
param(
    [switch]$CpuOnly
)

$ErrorActionPreference = 'Stop'

# ── Resolve Python ─────────────────────────────────────────────────────────────
$cfg     = Get-Content "$PSScriptRoot\..\config\settings.json" -Raw | ConvertFrom-Json
$python  = $cfg.paths.python
if (-not (Test-Path $python)) {
    # Fallback: look for py launcher or python on PATH
    $python = (Get-Command py   -ErrorAction SilentlyContinue)?.Source `
           ?? (Get-Command python3 -ErrorAction SilentlyContinue)?.Source `
           ?? (Get-Command python  -ErrorAction SilentlyContinue)?.Source
    if (-not $python) {
        Write-Error "Python not found. Set paths.python in config\settings.json."
        exit 1
    }
}
Write-Host "Python: $python" -ForegroundColor Cyan

# ── Install packages ───────────────────────────────────────────────────────────
Write-Host "`nInstalling kokoro-onnx and soundfile..." -ForegroundColor Cyan
& $python -m pip install --upgrade kokoro-onnx soundfile

if ($CpuOnly) {
    Write-Host "`nCPU-only mode: installing onnxruntime..." -ForegroundColor Yellow
    & $python -m pip install --upgrade onnxruntime
} else {
    Write-Host "`nGPU mode: replacing onnxruntime with onnxruntime-gpu..." -ForegroundColor Cyan
    # onnxruntime and onnxruntime-gpu conflict — remove base first
    & $python -m pip uninstall onnxruntime -y 2>$null
    & $python -m pip install --upgrade onnxruntime-gpu
}

# ── Download model files ──────────────────────────────────────────────────────
$modelDir = Join-Path $PSScriptRoot "..\tools\kokoro-models"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

$files = @(
    @{ Name = "kokoro-v1.0.onnx"; Url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx" },
    @{ Name = "voices-v1.0.bin";  Url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin" }
)

foreach ($file in $files) {
    $dest = Join-Path $modelDir $file.Name
    if (Test-Path $dest) {
        Write-Host "Already present: $($file.Name)" -ForegroundColor DarkGray
        continue
    }
    Write-Host "Downloading $($file.Name)..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $file.Url -OutFile $dest -UseBasicParsing
    $sizeMB = [math]::Round((Get-Item $dest).Length / 1MB, 1)
    Write-Host "  Saved: $dest  ($sizeMB MB)" -ForegroundColor Green
}

# ── Smoke test ────────────────────────────────────────────────────────────────
Write-Host "`nRunning smoke test (3-second synthesis)..." -ForegroundColor Cyan

$smokeScript = @'
import sys, tempfile, os
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from kokoro_onnx import Kokoro
import soundfile as sf

model_dir = Path(sys.argv[1])
kokoro = Kokoro(str(model_dir / "kokoro-v1.0.onnx"), str(model_dir / "voices-v1.0.bin"))
samples, sr = kokoro.create("Hello. Kokoro TTS is ready.", voice="af_heart", speed=1.0, lang="en-us")
tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, samples, sr)
size_kb = os.path.getsize(tmp) // 1024
os.unlink(tmp)
duration = len(samples) / sr
print(f"Smoke test OK: {duration:.1f}s audio, {size_kb} KB written")
'@

& $python -c $smokeScript $modelDir

if ($LASTEXITCODE -ne 0) {
    Write-Error "Smoke test FAILED. Check logs above."
    exit 1
}

Write-Host "`nKokoro TTS ready." -ForegroundColor Green
Write-Host "Enable it: set mp3.engine = `"kokoro`" in config\settings.json" -ForegroundColor Cyan
Write-Host "Test run:  py -3.12 tools\kokoro_synth.py --list-voices" -ForegroundColor Cyan
