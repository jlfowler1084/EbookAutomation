#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0' }
<#
.SYNOPSIS
    Pester 5 tests for the file-tracking functions and the cache-poisoning
    fix introduced in SCRUM-317.

.DESCRIPTION
    Covers:
    1. Add-ProcessedFile / Test-AlreadyProcessed basic round-trip
    2. Test-FullChainSucceeded — all-success, partial-success, all-disabled
    3. Cache-poisoning regression: Kindle:FAILED + TTS:OK must NOT mark processed
#>

BeforeAll {
    # Load the module from the canonical location relative to this test file.
    $repoRoot   = Split-Path -Parent $PSScriptRoot
    $moduleFile = Join-Path $repoRoot 'module' 'EbookAutomation.psm1'
    if (-not (Test-Path $moduleFile)) {
        throw "Cannot locate module at: $moduleFile"
    }
    # Remove any existing copy of the module (e.g. auto-loaded from profile)
    # before importing from the worktree, so InModuleScope resolves unambiguously.
    Get-Module EbookAutomation | Remove-Module -Force -ErrorAction SilentlyContinue
    Import-Module $moduleFile -Force

    # ---------------------------------------------------------------------------
    # Helper: create a temp directory mirroring the expected logs\ layout.
    # Add-ProcessedFile writes to "$ModuleRoot\logs\processed.txt", so we create
    # the logs\ sub-folder inside the temp root.
    # Returns the temp root path (ModuleRoot equivalent).
    # Defined inside BeforeAll so it is in scope for all It blocks.
    # ---------------------------------------------------------------------------
    function script:New-TempProcessedTxt {
        $root    = New-Item -ItemType Directory -Path (Join-Path ([System.IO.Path]::GetTempPath()) "PesterScrum317_$(New-Guid)")
        $logsDir = New-Item -ItemType Directory -Path (Join-Path $root.FullName 'logs')
        Set-Content (Join-Path $logsDir.FullName 'processed.txt') '' -Encoding UTF8
        return $root.FullName
    }
}

# ---------------------------------------------------------------------------
# Section 1 — Add-ProcessedFile / Test-AlreadyProcessed round-trip
# ---------------------------------------------------------------------------
Describe 'Add-ProcessedFile and Test-AlreadyProcessed' {

    It 'records an entry and detects it on re-check' {
        # Create temp root with logs\ sub-dir (mirrors what Get-ProcessedManifest expects)
        $tmpRoot = New-TempProcessedTxt
        $tmpPdf  = Join-Path ([System.IO.Path]::GetTempPath()) "dummy_$(New-Guid).pdf"
        [System.IO.File]::WriteAllBytes($tmpPdf, [byte[]](1,2,3,4))

        try {
            InModuleScope EbookAutomation -Parameters @{ TmpRoot = $tmpRoot; TmpPdf = $tmpPdf } {
                param($TmpRoot, $TmpPdf)
                $origRoot = $script:ModuleRoot
                $script:ModuleRoot = $TmpRoot
                try {
                    Test-AlreadyProcessed $TmpPdf | Should -BeFalse
                    Add-ProcessedFile $TmpPdf
                    Test-AlreadyProcessed $TmpPdf | Should -BeTrue
                } finally {
                    $script:ModuleRoot = $origRoot
                }
            }
        } finally {
            Remove-Item $tmpPdf -Force -ErrorAction SilentlyContinue
            Remove-Item $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'returns $false for an unknown file even when manifest is non-empty' {
        $tmpRoot = New-TempProcessedTxt
        $known   = Join-Path ([System.IO.Path]::GetTempPath()) "known_$(New-Guid).pdf"
        $unknown = Join-Path ([System.IO.Path]::GetTempPath()) "unknown_$(New-Guid).pdf"
        [System.IO.File]::WriteAllBytes($known,   [byte[]](1,2,3))
        [System.IO.File]::WriteAllBytes($unknown, [byte[]](9,8,7))

        try {
            InModuleScope EbookAutomation -Parameters @{ TmpRoot = $tmpRoot; Known = $known; Unknown = $unknown } {
                param($TmpRoot, $Known, $Unknown)
                $origRoot = $script:ModuleRoot
                $script:ModuleRoot = $TmpRoot
                try {
                    Add-ProcessedFile $Known
                    Test-AlreadyProcessed $Unknown | Should -BeFalse
                } finally {
                    $script:ModuleRoot = $origRoot
                }
            }
        } finally {
            Remove-Item $known   -Force -ErrorAction SilentlyContinue
            Remove-Item $unknown -Force -ErrorAction SilentlyContinue
            Remove-Item $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# ---------------------------------------------------------------------------
# Section 2 — Test-FullChainSucceeded logic (SCRUM-317 core fix)
# ---------------------------------------------------------------------------
Describe 'Test-FullChainSucceeded' {

    Context 'Both TTS and Kindle enabled — both succeed' {
        It 'returns $true' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $true  -KindleOk $true  -KindleMsg 'OK (CLEAN, 100/100, 12.3s)' `
                    -TtsEnabled    $true  -TtsOk    $true  -TtsMsg    'OK (5.1s)' `
                    -Mp3Enabled    $false -Mp3Ok    $false
                $result | Should -BeTrue
            }
        }
    }

    Context 'Kindle enabled and FAILED — TTS succeeded (SCRUM-317 regression case)' {
        It 'returns $false — book must NOT be marked processed' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $true  -KindleOk $false -KindleMsg 'FAILED' `
                    -TtsEnabled    $true  -TtsOk    $true  -TtsMsg    'OK (5.1s)' `
                    -Mp3Enabled    $false -Mp3Ok    $false
                $result | Should -BeFalse
            }
        }
    }

    Context 'Kindle enabled and EXCEPTION — TTS succeeded' {
        It 'returns $false' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $true  -KindleOk $false -KindleMsg 'EXCEPTION' `
                    -TtsEnabled    $true  -TtsOk    $true  -TtsMsg    'OK (5.1s)' `
                    -Mp3Enabled    $false -Mp3Ok    $false
                $result | Should -BeFalse
            }
        }
    }

    Context 'TTS enabled and FAILED — Kindle succeeded' {
        It 'returns $false' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $true  -KindleOk $true  -KindleMsg 'OK (CLEAN, 95/100, 8.0s)' `
                    -TtsEnabled    $true  -TtsOk    $false -TtsMsg    'FAILED (exit code)' `
                    -Mp3Enabled    $false -Mp3Ok    $false
                $result | Should -BeFalse
            }
        }
    }

    Context 'Kindle disabled — TTS-only pipeline, TTS succeeds' {
        It 'returns $true (Kindle not required)' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $false -KindleOk $false -KindleMsg 'disabled' `
                    -TtsEnabled    $true  -TtsOk    $true  -TtsMsg    'OK (5.1s)' `
                    -Mp3Enabled    $false -Mp3Ok    $false
                $result | Should -BeTrue
            }
        }
    }

    Context 'Kindle skipped due to unsupported format — TTS succeeds' {
        It 'returns $true (skipped format is not a failure)' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $true  -KindleOk $false -KindleMsg 'skipped (.epub)' `
                    -TtsEnabled    $true  -TtsOk    $true  -TtsMsg    'OK (5.1s)' `
                    -Mp3Enabled    $false -Mp3Ok    $false
                $result | Should -BeTrue
            }
        }
    }

    Context 'MP3 enabled and TTS succeeded, but MP3 generation failed' {
        It 'returns $false' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $false -KindleOk $false -KindleMsg 'disabled' `
                    -TtsEnabled    $true  -TtsOk    $true  -TtsMsg    'OK (5.1s)' `
                    -Mp3Enabled    $true  -Mp3Ok    $false
                $result | Should -BeFalse
            }
        }
    }

    Context 'All steps disabled' {
        It 'returns $false (nothing actually succeeded)' {
            InModuleScope EbookAutomation {
                $result = Test-FullChainSucceeded `
                    -KindleEnabled $false -KindleOk $false -KindleMsg 'disabled' `
                    -TtsEnabled    $false -TtsOk    $false -TtsMsg    'disabled' `
                    -Mp3Enabled    $false -Mp3Ok    $false
                $result | Should -BeFalse
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Section 3 — End-to-end cache-poisoning regression guard
# ---------------------------------------------------------------------------
Describe 'Cache-poisoning regression: Kindle:FAILED + TTS:OK' {

    It 'book is NOT added to processed.txt when Kindle step failed' {
        $tmpRoot = New-TempProcessedTxt
        $tmpPdf  = Join-Path ([System.IO.Path]::GetTempPath()) "book_$(New-Guid).pdf"
        [System.IO.File]::WriteAllBytes($tmpPdf, [byte[]](1,2,3,4,5))

        try {
            InModuleScope EbookAutomation -Parameters @{ TmpRoot = $tmpRoot; TmpPdf = $tmpPdf } {
                param($TmpRoot, $TmpPdf)
                $origRoot = $script:ModuleRoot
                $script:ModuleRoot = $TmpRoot
                try {
                    # Simulate the SCRUM-317 scenario:
                    # Kindle was enabled and FAILED; TTS succeeded.
                    # Test-FullChainSucceeded must return $false.
                    $shouldMark = Test-FullChainSucceeded `
                        -KindleEnabled $true  -KindleOk $false -KindleMsg 'FAILED' `
                        -TtsEnabled    $true  -TtsOk    $true  -TtsMsg    'OK (3.2s)' `
                        -Mp3Enabled    $false -Mp3Ok    $false

                    # Guard mirrors the new production code: only mark when all required steps pass
                    if ($shouldMark) {
                        Add-ProcessedFile $TmpPdf
                    }

                    # The book must NOT be in processed.txt
                    Test-AlreadyProcessed $TmpPdf | Should -BeFalse -Because `
                        'a book with Kindle:FAILED must not be cached as processed'

                    # Sanity: if we force-mark it, it is detected
                    Add-ProcessedFile $TmpPdf
                    Test-AlreadyProcessed $TmpPdf | Should -BeTrue
                } finally {
                    $script:ModuleRoot = $origRoot
                }
            }
        } finally {
            Remove-Item $tmpPdf -Force -ErrorAction SilentlyContinue
            Remove-Item $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
