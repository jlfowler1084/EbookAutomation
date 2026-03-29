# tools/verify-manifest.ps1
# Verifies EbookAutomation feature manifest - runs from project root
param([switch]$Verbose)

$projectRoot = Split-Path $PSScriptRoot -Parent
$manifestPath = Join-Path $projectRoot 'feature-manifest.json'

if (-not (Test-Path $manifestPath)) {
    Write-Host "ERROR: feature-manifest.json not found at $manifestPath" -ForegroundColor Red
    exit 1
}

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$failures = @()

$ver = $manifest.version
$gen = $manifest.generated
Write-Host "Feature Manifest Verification (v$ver, generated $gen)"
Write-Host "=========================================================="

# 1. Check critical files exist and meet minimum line count
Write-Host ""
Write-Host "Checking critical files..."
foreach ($file in $manifest.critical_files) {
    $filePath = $file.path
    $fullPath = Join-Path $projectRoot $filePath
    if (-not (Test-Path $fullPath)) {
        $failures += "MISSING: $filePath"
        Write-Host "  FAIL: $filePath - FILE MISSING" -ForegroundColor Red
        continue
    }
    $lineCount = (Get-Content $fullPath).Count
    $minLines = $file.min_lines
    if ($lineCount -lt $minLines) {
        $failures += "TRUNCATED: $filePath - $lineCount lines, min $minLines"
        Write-Host "  FAIL: $filePath - $lineCount lines, min $minLines" -ForegroundColor Red
    } elseif ($Verbose) {
        Write-Host "  OK: $filePath - $lineCount lines" -ForegroundColor Green
    }
}

# 2. Check exported functions exist in PSM1
Write-Host ""
Write-Host "Checking exported functions..."
$psm1Path = Join-Path $projectRoot 'module\EbookAutomation.psm1'
$psm1 = Get-Content $psm1Path -Raw
foreach ($fn in $manifest.exported_functions) {
    $fnName = $fn.name
    if ($psm1 -notmatch "function $([regex]::Escape($fnName))\b") {
        $failures += "FUNCTION MISSING: $fnName not found in EbookAutomation.psm1"
        Write-Host "  FAIL: function $fnName - NOT FOUND" -ForegroundColor Red
    } elseif ($Verbose) {
        Write-Host "  OK: function $fnName" -ForegroundColor Green
    }
}

# 3. Check exported functions in PSD1 manifest
Write-Host ""
Write-Host "Checking PSD1 exports..."
$psd1Path = Join-Path $projectRoot 'module\EbookAutomation.psd1'
$psd1 = Get-Content $psd1Path -Raw
foreach ($fn in $manifest.exported_functions) {
    $fnName = $fn.name
    if ($psd1 -notmatch [regex]::Escape($fnName)) {
        $failures += "EXPORT MISSING: $fnName not in FunctionsToExport"
        Write-Host "  FAIL: $fnName - not in FunctionsToExport" -ForegroundColor Red
    } elseif ($Verbose) {
        Write-Host "  OK: $fnName in PSD1" -ForegroundColor Green
    }
}

# 4. Check key parameters exist in function definitions
Write-Host ""
Write-Host "Checking key parameters..."
foreach ($fn in $manifest.exported_functions) {
    $fnName = $fn.name
    if ($fn.key_parameters.Count -eq 0) { continue }
    $fnPattern = "function $([regex]::Escape($fnName))\b"
    $fnMatch = [regex]::Match($psm1, $fnPattern)
    if (-not $fnMatch.Success) { continue }
    $blockLen = [math]::Min(15000, $psm1.Length - $fnMatch.Index)
    $fnBlock = $psm1.Substring($fnMatch.Index, $blockLen)
    foreach ($param in $fn.key_parameters) {
        $paramPattern = '\$' + [regex]::Escape($param) + '\b'
        if ($fnBlock -notmatch $paramPattern) {
            $failures += "PARAM MISSING: $fnName -$param"
            Write-Host "  FAIL: $fnName -$param - NOT FOUND" -ForegroundColor Red
        } elseif ($Verbose) {
            Write-Host "  OK: $fnName -$param" -ForegroundColor Green
        }
    }
}

# 5. Check Python CLI scripts exist
Write-Host ""
Write-Host "Checking Python CLI scripts..."
foreach ($cli in $manifest.python_cli_modes) {
    $scriptName = $cli.script
    $cliMode = $cli.mode
    $scriptPath = Join-Path $projectRoot $scriptName
    if (-not (Test-Path $scriptPath)) {
        $failures += "SCRIPT MISSING: $scriptName"
        Write-Host "  FAIL: $scriptName - FILE MISSING" -ForegroundColor Red
    } elseif ($Verbose) {
        Write-Host "  OK: $scriptName [$cliMode]" -ForegroundColor Green
    }
}

# 6. Check config schema keys
Write-Host ""
Write-Host "Checking config schema..."
$cfgPath = Join-Path $projectRoot $manifest.config_schema_keys.file
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
foreach ($key in $manifest.config_schema_keys.required_top_level) {
    if (-not ($cfg.PSObject.Properties.Name -contains $key)) {
        $failures += "CONFIG KEY MISSING: $key not in settings.json"
        Write-Host "  FAIL: config key '$key' - MISSING" -ForegroundColor Red
    } elseif ($Verbose) {
        Write-Host "  OK: config key '$key'" -ForegroundColor Green
    }
}

# 7. Check test infrastructure
Write-Host ""
Write-Host "Checking test infrastructure..."
$testScript = Join-Path $projectRoot $manifest.test_infrastructure.test_script
if (-not (Test-Path $testScript)) {
    $failures += "TEST SCRIPT MISSING: $($manifest.test_infrastructure.test_script)"
    Write-Host "  FAIL: test script missing" -ForegroundColor Red
} elseif ($Verbose) {
    Write-Host "  OK: test script exists" -ForegroundColor Green
}
$hookScript = Join-Path $projectRoot $manifest.test_infrastructure.hook_script
if (-not (Test-Path $hookScript)) {
    $failures += "HOOK SCRIPT MISSING: $($manifest.test_infrastructure.hook_script)"
    Write-Host "  FAIL: hook script missing" -ForegroundColor Red
} elseif ($Verbose) {
    Write-Host "  OK: hook script exists" -ForegroundColor Green
}
$corpusDir = Join-Path $projectRoot $manifest.test_infrastructure.corpus_dir
if (-not (Test-Path $corpusDir)) {
    $failures += "CORPUS DIR MISSING: $($manifest.test_infrastructure.corpus_dir)"
    Write-Host "  FAIL: corpus directory missing" -ForegroundColor Red
} elseif ($Verbose) {
    Write-Host "  OK: corpus directory exists" -ForegroundColor Green
}

# 8. Report
Write-Host ""
Write-Host "=========================================================="
if ($failures.Count -gt 0) {
    $failCount = $failures.Count
    Write-Host "=== MANIFEST VERIFICATION FAILED ===" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  FAIL: $f" -ForegroundColor Red }
    Write-Host "$failCount failure(s) detected" -ForegroundColor Red
    exit 1
} else {
    $fileCount = $manifest.critical_files.Count
    $fnCount = $manifest.exported_functions.Count
    $cliCount = $manifest.python_cli_modes.Count
    $keyCount = $manifest.config_schema_keys.required_top_level.Count
    Write-Host "=== MANIFEST VERIFIED ===" -ForegroundColor Green
    Write-Host "  $fileCount critical files present and above minimum size"
    Write-Host "  $fnCount exported functions found in PSM1 and PSD1"
    Write-Host "  $cliCount Python CLI modes cataloged"
    Write-Host "  $keyCount config schema keys intact"
    exit 0
}
