#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
<#
.SYNOPSIS
    EB-356 wrapper integration tests for Invoke-EbookBookDownload (review round 2).

.DESCRIPTION
    Exercises the PowerShell -> Python boundary end to end in --dry-run mode.
    These catch defects the metadata-only ParamSet tests could not:

      * manual-quoting bug -- splatted native args were wrapped in literal quotes
        ("`"$file`""), so book_downloader.py looked for a path *with quotes* and
        reported "No books found" / "File not found".
      * parameter-set binding bug -- -Format / -OutputDir were pinned to a single
        set, so `-Ids x -Format pdf` and `-File x -Format pdf` failed to bind.

    SAFETY: every case pins -OutputDir to a TestDrive directory, so no test reads
    or writes the real F:\Books library, and -DryRun guarantees no LibGen / Anna
    network calls (no book is ever downloaded).

    Run with:
        Invoke-Pester -Path tests/Invoke-EbookBookDownload.Wrapper.Tests.ps1
#>

BeforeAll {
    $modulePath = Join-Path $PSScriptRoot '..\module\EbookAutomation.psm1'
    Import-Module $modulePath -Force
}

Describe 'Invoke-EbookBookDownload wrapper (EB-356 quoting + param-set fixes)' {

    BeforeEach {
        $script:outDir = Join-Path $TestDrive "bf_out_$(Get-Random)"
        New-Item -ItemType Directory -Force -Path $script:outDir | Out-Null

        $script:jsonFile = Join-Path $TestDrive "results_$(Get-Random).json"
        @(
            [pscustomobject]@{
                title = 'Test Book'; author = 'Test Author'; format = 'epub'
                download_url = 'http://example.invalid/x.epub'; md5 = ''
                file_size = ''; source = 'libgen'
            }
        ) | ConvertTo-Json -Depth 5 | Out-File -FilePath $script:jsonFile -Encoding utf8
    }

    It '-File resolves the JSON path (quoting fix) and dry-runs its book' {
        $out = Invoke-EbookBookDownload -File $script:jsonFile -DryRun `
                   -Format pdf -OutputDir $script:outDir *>&1 | Out-String
        $out | Should -Not -Match 'No books found'
        $out | Should -Match 'Test Book'
    }

    It 'pipeline input dry-runs without a "No books found" failure (temp-JSON quoting fix)' {
        $book = [pscustomobject]@{
            title = 'Pipe Book'; author = 'A'; format = 'epub'
            download_url = 'http://example.invalid/y.epub'
        }
        $out = $book | Invoke-EbookBookDownload -DryRun -OutputDir $script:outDir *>&1 | Out-String
        $out | Should -Not -Match 'No books found'
        $out | Should -Match 'Pipe Book'
    }

    It '-Ids with -Format binds (param-set fix) without a ParameterBindingException' {
        # Empty DB => "No pending/failed books with IDs" is the expected functional
        # outcome and makes no network call. The point under test is that the
        # parameter set RESOLVES -- pre-fix this threw a binding error because
        # -Format lived only in the FromResult set.
        {
            Invoke-EbookBookDownload -Ids '1' -Format pdf -OutputDir $script:outDir *>&1 | Out-Null
        } | Should -Not -Throw
    }

    It '-File with -Format binds (param-set fix) without a ParameterBindingException' {
        {
            Invoke-EbookBookDownload -File $script:jsonFile -Format pdf -DryRun `
                -OutputDir $script:outDir *>&1 | Out-Null
        } | Should -Not -Throw
    }
}
